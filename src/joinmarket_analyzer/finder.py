"""
JoinMarket CoinJoin Finder using Mempool API.
Adapted from jmfinder.py.
"""

from collections import Counter
from typing import Optional

import httpx
from loguru import logger
from pydantic import BaseModel, Field, field_validator

# Configuration defaults
DEFAULT_MIN_PARTICIPANTS = 3
DEFAULT_MIN_CJ_AMOUNT = 75000
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3


class TransactionInput(BaseModel):
    """Transaction input model."""

    txid: str
    vout: int
    prevout: Optional[dict] = None
    scriptsig: str = ""
    sequence: int
    is_coinbase: bool = False


class TransactionOutput(BaseModel):
    """Transaction output model."""

    scriptpubkey: str
    scriptpubkey_address: Optional[str] = None
    scriptpubkey_type: str
    value: int


class TransactionStatus(BaseModel):
    """Transaction status model."""

    confirmed: bool
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[int] = None


class Transaction(BaseModel):
    """Transaction model."""

    txid: str
    version: int
    locktime: int
    vin: list[TransactionInput]
    vout: list[TransactionOutput]
    size: int
    weight: int
    fee: int
    status: TransactionStatus

    @property
    def vsize(self) -> float:
        """Calculate virtual size."""
        return self.weight / 4

    @property
    def n_inputs(self) -> int:
        """Number of inputs."""
        return len(self.vin)

    @property
    def n_outputs(self) -> int:
        """Number of outputs."""
        return len(self.vout)

    @property
    def output_values(self) -> list[int]:
        """List of output values."""
        return [out.value for out in self.vout]


class BlockInfo(BaseModel):
    """Block information model."""

    id: str = Field(alias="id")
    height: int
    tx_count: int
    timestamp: int

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, v):
        """Allow 'id' field despite it being a Python builtin."""
        return v


class CoinJoinCandidate(BaseModel):
    """CoinJoin candidate model."""

    txid: str
    height: int
    tx_index: int
    n_inputs: int
    n_outputs: int
    equal_outputs: int
    equal_amount: int
    vsize: float
    version: int
    locktime: int
    timestamp: int  # Added for DB storage
    network_fee: int


class MempoolClient:
    """Client for Mempool API."""

    def __init__(self, base_url: str = "https://mempool.sgn.space"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=REQUEST_TIMEOUT)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def _get(self, endpoint: str, retries: int = MAX_RETRIES) -> httpx.Response:
        """Make GET request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP {e.response.status_code} for {url}")
                if attempt == retries - 1:
                    raise
            except httpx.RequestError as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt == retries - 1:
                    raise

        raise httpx.RequestError(f"Failed after {retries} retries")

    def get_block_height(self) -> int:
        """Get current block height."""
        response = self._get("/api/blocks/tip/height")
        return int(response.text)

    def get_block_hash(self, height: int) -> str:
        """Get block hash for given height."""
        response = self._get(f"/api/block-height/{height}")
        return response.text.strip()

    def get_block_info(self, block_hash: str) -> BlockInfo:
        """Get block information."""
        response = self._get(f"/api/v1/block/{block_hash}")
        return BlockInfo.model_validate(response.json())

    def get_block_transactions(self, block_hash: str, start_index: int = 0) -> list[Transaction]:
        """Get transactions from a block (paginated)."""
        response = self._get(f"/api/v1/block/{block_hash}/txs/{start_index}")
        txs = response.json()
        return [Transaction.model_validate(tx) for tx in txs]

    def get_transaction(self, txid: str) -> Transaction:
        """Get single transaction details."""
        response = self._get(f"/api/tx/{txid}")
        return Transaction.model_validate(response.json())


class JoinMarketDetector:
    """Detect JoinMarket CoinJoin patterns."""

    @staticmethod
    def is_joinmarket(
        tx: Transaction,
        min_participants: int = DEFAULT_MIN_PARTICIPANTS,
        min_amount: int = DEFAULT_MIN_CJ_AMOUNT,
    ) -> Optional[CoinJoinCandidate]:
        """
        Check if transaction matches JoinMarket pattern.
        """
        n_in = tx.n_inputs
        n_out = tx.n_outputs
        values = tx.output_values

        # Skip coinbase transactions
        if any(inp.is_coinbase for inp in tx.vin):
            return None

        # Calculate assumed CoinJoin outputs
        assumed_cj_outs = n_out // 2
        if n_out % 2:
            assumed_cj_outs += 1

        # Check minimum participants
        if assumed_cj_outs < min_participants:
            return None

        # Check input count
        if n_in < assumed_cj_outs:
            return None

        # Find most common output value
        counter = Counter(values)
        if not counter:
            return None

        most_common_value, equal_outs = counter.most_common(1)[0]

        # Check minimum amount
        if most_common_value < min_amount:
            return None

        # Check equal output count matches assumption
        if equal_outs != assumed_cj_outs:
            return None

        return CoinJoinCandidate(
            txid=tx.txid,
            height=tx.status.block_height or 0,
            tx_index=0,  # Will be set by caller
            n_inputs=n_in,
            n_outputs=n_out,
            equal_outputs=equal_outs,
            equal_amount=most_common_value,
            vsize=tx.vsize,
            version=tx.version,
            locktime=tx.locktime,
            timestamp=tx.status.block_time or 0,
            network_fee=tx.fee,
        )
