"""Pydantic models for transaction data and solutions."""

from typing import Optional

from pydantic import BaseModel, Field


class UTXO(BaseModel):
    """Bitcoin UTXO (Unspent Transaction Output)."""

    address: str
    amount: int  # satoshis
    index: int


class Participant(BaseModel):
    """CoinJoin participant with inputs, outputs, and fees."""

    role: str  # "taker" or "maker"
    inputs: list[UTXO]
    equal_output: int  # satoshis
    change_output: Optional[UTXO] = None
    fee: int  # satoshis (positive for taker, negative for makers)

    @property
    def input_sum(self) -> int:
        """Total input value in satoshis."""
        return sum(inp.amount for inp in self.inputs)


class Solution(BaseModel):
    """A valid CoinJoin decomposition."""

    participants: list[Participant]
    taker_index: int
    total_maker_fees: int
    network_fee: int
    discrepancy: int = 0  # Validation: should be 0


class TransactionData(BaseModel):
    """Parsed CoinJoin transaction data."""

    txid: str
    inputs: list[UTXO]
    equal_outputs: list[UTXO]
    change_outputs: list[UTXO]
    network_fee: int
    num_participants: int
    equal_amount: int


class GreedyAssignment(BaseModel):
    """Preprocessing assignments from greedy heuristic."""

    forced_assignments: dict[int, int] = Field(default_factory=dict)
    # None value means explicitly NO change output for that participant
    forced_changes: dict[int, Optional[int]] = Field(default_factory=dict)
    unassigned_inputs: set[int] = Field(default_factory=set)
    unassigned_changes: set[int] = Field(default_factory=set)
    unassigned_participants: set[int] = Field(default_factory=set)


class AnalysisResult(BaseModel):
    """Complete analysis result with metadata."""

    transaction: TransactionData
    solutions: list[Solution]
    num_solutions: int
    is_unique: bool

    @property
    def taker_probabilities(self) -> dict[int, float]:
        """Calculate probability distribution over potential takers."""
        if not self.solutions:
            return {}

        taker_counts: dict[int, int] = {}
        for sol in self.solutions:
            taker_counts[sol.taker_index] = taker_counts.get(sol.taker_index, 0) + 1

        total = len(self.solutions)
        return {idx: count / total for idx, count in taker_counts.items()}
