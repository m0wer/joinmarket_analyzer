"""Database models and connection logic."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine


class ScannedBlock(SQLModel, table=True):  # type: ignore[call-arg]
    """Record of scanned blocks to resume progress."""

    height: int = Field(primary_key=True)
    timestamp: int
    tx_count: int
    scanned_at: datetime = Field(default_factory=datetime.utcnow)


class CoinJoinTx(SQLModel, table=True):  # type: ignore[call-arg]
    """Found JoinMarket CoinJoin transaction."""

    txid: str = Field(primary_key=True)
    height: int = Field(index=True)
    timestamp: int
    num_participants: int
    equal_amount: int
    network_fee: int
    vsize: float
    version: int
    locktime: int


class AnalysisSummary(SQLModel, table=True):  # type: ignore[call-arg]
    """Summary of analysis results for a transaction."""

    txid: str = Field(primary_key=True, foreign_key="coinjointx.txid")
    success: bool
    error_message: Optional[str] = None

    # Solution stats
    solution_count: int = 0
    min_maker_fees: Optional[int] = None  # Total maker fees (min across solutions)
    max_maker_fees: Optional[int] = None  # Total maker fees (max across solutions)
    avg_maker_fees: Optional[float] = None  # Total maker fees (avg across solutions)

    # New stat: Max fee paid to any single maker (estimator for fee limit)
    max_single_maker_fee: Optional[int] = None

    # Taker stats (from best/most likely solution)
    estimated_taker_fee: Optional[int] = None
    taker_index_confidence: Optional[float] = None

    # Partial results (from greedy preprocessing)
    is_partial: bool = False
    greedy_inputs_assigned: Optional[int] = None
    greedy_taker_found: Optional[bool] = None

    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


def init_db(db_path: str = "joinmarket_stats.db"):
    """Initialize the database."""
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    SQLModel.metadata.create_all(engine)
    return engine


def get_session(engine) -> Session:
    """Get a new database session."""
    return Session(engine)
