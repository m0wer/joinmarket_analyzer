"""CLI entry point for JoinMarket CoinJoin analyzer."""

from __future__ import annotations

import resource
import signal
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from joinmarket_analyzer.api import fetch_transaction
from joinmarket_analyzer.output import print_solution_summary, save_solutions
from joinmarket_analyzer.parser import parse_transaction
from joinmarket_analyzer.solver import solve_all_solutions

MEMORY_LIMIT_GB = 10

_solutions_state: dict[str, Any] = {
    "solutions": [],
    "tx_data": None,
    "output_path": None,
}


def set_memory_limit() -> None:
    """Set memory limit to guard against excessive usage."""

    try:
        limit_bytes = MEMORY_LIMIT_GB * 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        logger.info(f"Memory limit set to {MEMORY_LIMIT_GB}GB")
    except (ValueError, OSError) as exc:  # noqa: BLE001
        logger.warning(f"Could not set memory limit: {exc}")
        logger.info("Consider running with: docker run -m 10g ...")


def handle_interrupt(signum, frame):  # type: ignore[override]
    """Handle Ctrl+C by saving solutions before exiting."""

    logger.warning("\n\n⚠ Interrupt received (Ctrl+C)")

    solutions = _solutions_state["solutions"]
    tx_data = _solutions_state["tx_data"]
    output_path = _solutions_state["output_path"]

    if solutions and tx_data and output_path:
        logger.info(f"Saving {len(solutions)} solution(s) found so far...")
        try:
            save_solutions(solutions, tx_data, output_path)
            print_solution_summary(solutions, tx_data)
            logger.success("✓ Solutions saved successfully")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to save solutions: {exc}")
    else:
        logger.info("No solutions to save")

    sys.exit(130)


def configure_logger() -> None:
    """Configure loguru logger for CLI output."""

    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        ),
        level="DEBUG",
    )


def run_analyzer(txid: str, max_fee_rel: float, max_solutions: int) -> int:
    """Run CoinJoin analyzer for a given transaction."""

    try:
        raw_tx = fetch_transaction(txid)
        tx_data = parse_transaction(raw_tx)

        output_path = Path(f"solutions_{tx_data.txid[:16]}.json")
        _solutions_state["output_path"] = output_path

        solutions = solve_all_solutions(
            tx_data,
            max_fee_rel=max_fee_rel,
            max_solutions=max_solutions,
            output_path=output_path,
            save_incrementally=True,
        )

        _solutions_state["solutions"] = solutions
        _solutions_state["tx_data"] = tx_data

        if solutions:
            save_solutions(solutions, tx_data, output_path)
            print_solution_summary(solutions, tx_data)
            return 0

        logger.error("No valid solutions found")
        return 1

    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Analysis failed: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    import argparse

    configure_logger()

    parser = argparse.ArgumentParser(
        prog="joinmarket-analyze",
        description="Analyze JoinMarket CoinJoin transactions using ILP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  joinmarket-analyze 0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf
   joinmarket-analyze <txid> --max-fee-rel 0.001 --max-solutions 100
        """,
    )
    parser.add_argument("txid", help="Transaction ID (hex string)")
    parser.add_argument(
        "--max-fee-rel",
        type=float,
        default=0.005,
        metavar="REL",
        help="Maximum maker fee as fraction of equal_amount (default: 0.005)",
    )
    parser.add_argument(
        "--max-solutions",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of solutions to find (default: 10)",
    )

    args = parser.parse_args(argv)

    set_memory_limit()
    signal.signal(signal.SIGINT, handle_interrupt)

    exit_code = run_analyzer(args.txid, args.max_fee_rel, args.max_solutions)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
