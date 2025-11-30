"""HTTP client for fetching transaction data and high-level analysis API."""

from __future__ import annotations

import requests
from loguru import logger

from joinmarket_analyzer.models import Solution
from joinmarket_analyzer.parser import parse_transaction
from joinmarket_analyzer.solver import solve_all_solutions

DEFAULT_MEMPOOL_URL = "https://mempool.sgn.space/api"


def fetch_transaction(txid: str, mempool_url: str = DEFAULT_MEMPOOL_URL) -> dict:
    """
    Fetch transaction data from mempool API.

    Args:
        txid: Transaction ID (hex string)
        mempool_url: Base URL for mempool API

    Returns:
        Raw transaction data as dict

    Raises:
        requests.RequestException: If fetch fails
    """
    url = f"{mempool_url}/tx/{txid}"
    logger.info(f"Fetching transaction: {txid}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    return response.json()


def analyze_transaction(
    txid: str,
    max_fee_rel: float = 0.05,
    max_solutions: int = 1000,
    mempool_url: str = DEFAULT_MEMPOOL_URL,
) -> list[Solution]:
    """
    Analyze a JoinMarket CoinJoin transaction end-to-end.

    Args:
        txid: Transaction ID (hex string)
        max_fee_rel: Maximum maker fee as fraction of equal_amount (default: 0.05)
        max_solutions: Maximum number of solutions to find (default: 1000)
        mempool_url: Base URL for mempool API

    Returns:
        List of valid solutions found

    Raises:
        requests.RequestException: If fetch fails
        ValueError: If transaction parsing fails
    """
    raw_tx = fetch_transaction(txid, mempool_url)
    tx_data = parse_transaction(raw_tx)

    solutions = solve_all_solutions(
        tx_data,
        max_fee_rel=max_fee_rel,
        max_solutions=max_solutions,
        save_incrementally=False,
    )

    return solutions
