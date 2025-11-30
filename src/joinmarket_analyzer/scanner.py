"""
CoinJoin Scanner and Analyzer.
Scans blocks for JoinMarket transactions and analyzes them.
"""

import argparse
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic

from loguru import logger
from sqlmodel import Session

from joinmarket_analyzer.db import (
    AnalysisSummary,
    CoinJoinTx,
    ScannedBlock,
    get_session,
    init_db,
)
from joinmarket_analyzer.finder import (
    DEFAULT_MIN_CJ_AMOUNT,
    DEFAULT_MIN_PARTICIPANTS,
    CoinJoinCandidate,
    JoinMarketDetector,
    MempoolClient,
    Transaction,
)
from joinmarket_analyzer.greedy import greedy_preprocessing
from joinmarket_analyzer.parser import parse_transaction
from joinmarket_analyzer.solver import analyze_greedy_results, solve_all_solutions

# Global flag for graceful shutdown
SHUTDOWN_REQUESTED = False


def handle_interrupt(signum, frame):
    """Handle Ctrl+C."""
    global SHUTDOWN_REQUESTED
    logger.warning("\n⚠ Interrupt received. Finishing current block...")
    SHUTDOWN_REQUESTED = True


def analyze_candidate(
    candidate: CoinJoinCandidate, tx_model: Transaction, session: Session
) -> None:
    """Run analysis on a CoinJoin candidate and save results."""
    logger.info(f"Analyzing {candidate.txid}...")

    # 1. Parse Transaction
    try:
        # Convert finder Transaction model to dict for parser
        # by_alias=True is important if fields have aliases, but here names match
        tx_dict = tx_model.model_dump(mode="json")
        tx_data = parse_transaction(tx_dict)
    except Exception as e:
        logger.error(f"Failed to parse transaction {candidate.txid}: {e}")
        return

    # 2. Run Greedy Preprocessing (to capture partial progress)
    greedy = None
    if tx_data.num_participants >= 3:
        try:
            greedy = greedy_preprocessing(tx_data, 0.005)
        except Exception as e:
            logger.warning(f"Greedy preprocessing failed: {e}")

    # 3. Run Solver
    solutions = []
    error_message = None
    try:
        solutions = solve_all_solutions(
            tx_data,
            max_fee_rel=0.005,
            max_solutions=10,  # Limit solutions to keep it fast
            time_limit_per_solve=10,  # Fast timeout
            save_incrementally=False,
        )
    except Exception as e:
        logger.error(f"Solver failed for {candidate.txid}: {e}")
        error_message = str(e)

    # 4. Aggregate Stats & Save
    summary = AnalysisSummary(
        txid=candidate.txid,
        success=bool(solutions),
        error_message=error_message,
        solution_count=len(solutions),
    )

    # Add Greedy Stats
    if greedy:
        summary.greedy_inputs_assigned = len(greedy.forced_assignments)

        # Check if taker found in greedy
        analysis = analyze_greedy_results(greedy, tx_data, 0.005)
        summary.greedy_taker_found = analysis["taker_found"]

        # If no full solution but greedy found taker, capture it as partial success
        if not solutions and analysis["taker_found"]:
            summary.is_partial = True

            # Calculate estimated taker fee from greedy result
            # We need to find which participant is the taker
            taker_idx = analysis["taker_original_idx"]

            # Reconstruct fee logic (simplified from solver.py)
            input_indices = [i for i, p in greedy.forced_assignments.items() if p == taker_idx]
            input_sum = sum(tx_data.inputs[i].amount for i in input_indices)

            change_rel_idx = greedy.forced_changes.get(taker_idx)
            change_val = 0
            if change_rel_idx is not None:
                change_val = tx_data.change_outputs[change_rel_idx].amount

            fee = input_sum - change_val - tx_data.equal_amount
            summary.estimated_taker_fee = fee
            summary.taker_index_confidence = 1.0  # Greedy is deterministic/confident

    if solutions:
        # Calculate stats from solutions
        maker_fees = [s.total_maker_fees for s in solutions]
        best_sol = solutions[0]
        taker_idx = best_sol.taker_index
        taker_fee = best_sol.participants[taker_idx].fee

        taker_counts: dict[int, int] = {}
        for s in solutions:
            taker_counts[s.taker_index] = taker_counts.get(s.taker_index, 0) + 1
        confidence = taker_counts.get(taker_idx, 0) / len(solutions)

        summary.min_maker_fees = min(maker_fees)
        summary.max_maker_fees = max(maker_fees)
        summary.avg_maker_fees = sum(maker_fees) / len(maker_fees)
        summary.estimated_taker_fee = taker_fee
        summary.taker_index_confidence = confidence

    # If no solution and no greedy taker found, use error message from solver if available
    if not solutions and not summary.is_partial and not error_message:
        summary.error_message = "No solutions found"

    session.merge(summary)
    session.commit()

    if solutions:
        logger.success(f"Analyzed {candidate.txid}: {len(solutions)} solutions")
    elif summary.is_partial:
        logger.success(f"Analyzed {candidate.txid}: Partial (Taker found by greedy)")
    else:
        logger.warning(f"Analyzed {candidate.txid}: No solutions")


def process_block(
    height: int, client: MempoolClient, engine, min_participants: int, min_amount: int
) -> None:
    """Scan and analyze a single block."""
    session = get_session(engine)

    try:
        # Check if already scanned
        existing = session.get(ScannedBlock, height)
        if existing:
            logger.debug(f"Block {height} already scanned. Skipping.")
            return

        # Fetch block info
        block_hash = client.get_block_hash(height)
        block_info = client.get_block_info(block_hash)

        logger.info(f"Scanning block {height} ({block_info.tx_count} txs)...")

        start_time = monotonic()
        found_count = 0

        # Scan transactions
        start_index = 0
        tx_index = 0

        while start_index < block_info.tx_count:
            if SHUTDOWN_REQUESTED:
                return

            txs = client.get_block_transactions(block_hash, start_index)
            if not txs:
                break

            for tx in txs:
                candidate = JoinMarketDetector.is_joinmarket(tx, min_participants, min_amount)
                if candidate:
                    found_count += 1
                    logger.info(f"Found CJ: {candidate.txid} ({candidate.equal_amount} sats)")

                    # Store Transaction
                    cj_tx = CoinJoinTx(
                        txid=candidate.txid,
                        height=candidate.height,
                        timestamp=candidate.timestamp,
                        num_participants=candidate.n_outputs // 2
                        if candidate.n_outputs % 2 == 0
                        else (candidate.n_outputs + 1) // 2,  # Approximation or use logic
                        equal_amount=candidate.equal_amount,
                        network_fee=candidate.network_fee,
                        vsize=candidate.vsize,
                        version=candidate.version,
                        locktime=candidate.locktime,
                    )
                    # Use merge to handle potential duplicates if re-running
                    session.merge(cj_tx)
                    session.commit()

                    # Analyze immediately
                    # Check if analysis exists
                    existing_analysis = session.get(AnalysisSummary, candidate.txid)
                    if not existing_analysis:
                        analyze_candidate(candidate, tx, session)

                tx_index += 1

            start_index += len(txs)

        # Mark block as scanned
        scanned = ScannedBlock(
            height=height, timestamp=block_info.timestamp, tx_count=block_info.tx_count
        )
        session.add(scanned)
        session.commit()

        elapsed = monotonic() - start_time
        logger.info(f"Processed block {height} in {elapsed:.2f}s. Found {found_count} CJs.")

    except Exception as e:
        logger.error(f"Error processing block {height}: {e}")
        session.rollback()
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Scan and analyze JoinMarket CoinJoins")
    parser.add_argument(
        "start", type=int, help="Start block height (or negative for last N blocks)"
    )
    parser.add_argument("end", type=int, nargs="?", help="End block height (default: tip)")
    parser.add_argument("--db", default="joinmarket_stats.db", help="Database file")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel jobs (blocks)")
    parser.add_argument("--min-participants", type=int, default=DEFAULT_MIN_PARTICIPANTS)
    parser.add_argument("--min-amount", type=int, default=DEFAULT_MIN_CJ_AMOUNT)
    parser.add_argument("--url", default="https://mempool.sgn.space", help="Mempool API URL")

    args = parser.parse_args()

    # Setup
    signal.signal(signal.SIGINT, handle_interrupt)
    engine = init_db(args.db)

    with MempoolClient(args.url) as client:
        # Determine range
        tip = client.get_block_height()
        end_block = args.end if args.end is not None else tip
        start_block = args.start

        if start_block < 0:
            start_block = end_block + start_block + 1

        logger.info(f"Scanning range: {start_block} - {end_block}")

        # Processing loop
        if args.jobs > 1:
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                futures = {}
                for h in range(start_block, end_block + 1):
                    if SHUTDOWN_REQUESTED:
                        break
                    futures[
                        executor.submit(
                            process_block, h, client, engine, args.min_participants, args.min_amount
                        )
                    ] = h

                for f in as_completed(futures):
                    if SHUTDOWN_REQUESTED:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        f.result()
                    except Exception as e:
                        logger.error(f"Job failed: {e}")
        else:
            for h in range(start_block, end_block + 1):
                if SHUTDOWN_REQUESTED:
                    break
                process_block(h, client, engine, args.min_participants, args.min_amount)

    logger.info("Done.")


if __name__ == "__main__":
    main()
