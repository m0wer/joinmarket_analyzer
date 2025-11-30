"""Output utilities for JoinMarket analyzer."""

import json
from pathlib import Path

from loguru import logger

from joinmarket_analyzer.models import Solution, TransactionData


def solutions_to_json(solutions: list[Solution], tx_data: TransactionData) -> dict:
    """Convert solutions to JSON-serializable format."""

    return {
        "transaction": {
            "txid": tx_data.txid,
            "num_participants": tx_data.num_participants,
            "equal_amount": tx_data.equal_amount,
            "network_fee": tx_data.network_fee,
            "num_inputs": len(tx_data.inputs),
            "num_outputs": len(tx_data.equal_outputs) + len(tx_data.change_outputs),
        },
        "num_solutions": len(solutions),
        "solutions": [
            {
                "solution_id": idx + 1,
                "taker_index": sol.taker_index,
                "total_maker_fees": sol.total_maker_fees,
                "network_fee": sol.network_fee,
                "discrepancy": sol.discrepancy,
                "participants": [
                    {
                        "participant_id": p_idx + 1,
                        "role": participant.role,
                        "num_inputs": len(participant.inputs),
                        "input_indices": [inp.index for inp in participant.inputs],
                        "input_sum": participant.input_sum,
                        "equal_output": participant.equal_output,
                        "change_output_index": (
                            participant.change_output.index if participant.change_output else None
                        ),
                        "change_amount": (
                            participant.change_output.amount if participant.change_output else 0
                        ),
                        "fee": participant.fee,
                    }
                    for p_idx, participant in enumerate(sol.participants)
                ],
            }
            for idx, sol in enumerate(solutions)
        ],
    }


def print_solution_summary(solutions: list[Solution], tx_data: TransactionData) -> None:
    """Print concise solution summary to stdout."""

    logger.info("=" * 70)
    logger.info("SOLUTION SUMMARY")
    logger.info("=" * 70)

    if len(solutions) == 0:
        logger.warning("No valid solutions found")
        return

    logger.info(f"Total distinct solutions: {len(solutions)}")

    if len(solutions) == 1:
        logger.success("✓ Unique solution found - transaction is unambiguous")
        solution = solutions[0]

        logger.info(f"\nTaker: Participant {solution.taker_index + 1}")
        logger.info(
            f"  Inputs: {[inp.index for inp in solution.participants[solution.taker_index].inputs]}"
        )
        logger.info(f"  Fee paid: {solution.participants[solution.taker_index].fee:,} sats")

        logger.info("\nMakers:")
        for idx, participant in enumerate(solution.participants):
            if participant.role == "maker":
                logger.info(f"  Participant {idx + 1}")
                logger.info(f"    Inputs: {[inp.index for inp in participant.inputs]}")
                logger.info(f"    Fee received: {abs(participant.fee):,} sats")
    else:
        logger.warning(f"⚠ Multiple distinct solutions exist ({len(solutions)})")
        logger.info("Transaction is ambiguous - deanonymization inconclusive")

        taker_counts: dict[int, int] = {}
        for solution in solutions:
            taker_counts[solution.taker_index] = taker_counts.get(solution.taker_index, 0) + 1

        logger.info("\nTaker probability distribution:")
        for idx in sorted(taker_counts.keys()):
            probability = taker_counts[idx] / len(solutions) * 100
            logger.info(
                f"  Participant {idx + 1}: {probability:.1f}% ({taker_counts[idx]} solutions)"
            )


def save_solutions(solutions: list[Solution], tx_data: TransactionData, output_path: Path) -> None:
    """Save solutions to JSON file."""

    data = solutions_to_json(solutions, tx_data)

    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"\n✓ Saved {len(solutions)} distinct solution(s) to {output_path}")
