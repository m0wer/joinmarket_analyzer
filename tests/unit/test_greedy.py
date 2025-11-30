"""Unit tests for greedy preprocessing heuristic - UNEQUIVOCAL MATCHING."""

from joinmarket_analyzer.greedy import greedy_preprocessing
from joinmarket_analyzer.models import UTXO, TransactionData


class TestUnequivocalMatching:
    """Test strict unequivocal matching logic."""

    def test_single_input_unique_change_match(self):
        """Test unequivocal match: one input, one compatible change - TAKER with change."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=105_000_000, index=0),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=1),
            ],
            change_outputs=[
                UTXO(address="change1", amount=4_000_000, index=2),
            ],
            network_fee=1_000_000,
            num_participants=1,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # This should be identified as a TAKER with change (single participant, pays network fee)
        # Calculation: 105M = 100M (equal) + 1M (network) + 0M (makers, since n=1) + 4M (change)
        assert result.forced_assignments == {0: 0}
        assert result.forced_changes == {0: 0}
        assert len(result.unassigned_inputs) == 0

    def test_no_change_maker(self):
        """Test unequivocal no-change match."""
        equal_amt = 100_000_000
        fee = 3_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=equal_amt + fee, index=0),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=1),
            ],
            change_outputs=[],
            network_fee=fee,
            num_participants=1,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        assert result.forced_assignments == {0: 0}
        assert result.forced_changes == {0: None}
        assert len(result.unassigned_inputs) == 0

    def test_two_participants_maker_and_taker(self):
        """Test two participants: one maker receiving fee, one taker with change."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="maker", amount=104_000_000, index=0),  # Maker
                UTXO(address="taker", amount=110_000_000, index=1),  # Taker
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change_maker", amount=5_000_000, index=4),
                UTXO(address="change_taker", amount=8_000_000, index=5),
            ],
            network_fee=1_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Maker: 104M + 1M fee = 100M + 5M
        # Taker: 110M = 100M + 1M network + 1M maker_fee + 8M change
        assert len(result.forced_assignments) == 2

    def test_ambiguous_two_similar_inputs(self):
        """
        Test ambiguous case: two similar inputs, one change - SHOULD NOT ASSIGN.

        Both inputs are compatible with the same change, so no unequivocal match exists.
        """
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=105_000_000, index=0),  # 5M remaining
                UTXO(address="addr2", amount=104_500_000, index=1),  # 4.5M remaining
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change1", amount=4_000_000, index=4),  # Both inputs compatible
            ],
            network_fee=5_500_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Should NOT assign - ambiguous which input matches the change
        assert len(result.forced_assignments) == 0
        assert len(result.unassigned_inputs) == 2

    def test_ambiguous_two_similar_changes(self):
        """
        Test ambiguous case: two maker inputs, two similar changes - SHOULD NOT ASSIGN.

        Maker inputs are compatible with both changes, so no unequivocal match exists.
        """
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=210_000_000, index=0),  # 210M remaining
                UTXO(address="addr2", amount=105_000_000, index=1),  # 5M remaining
                UTXO(address="addr3", amount=105_000_000, index=2),  # 5M remaining
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=0),
                UTXO(address="equal2", amount=equal_amt, index=1),
                UTXO(address="equal3", amount=equal_amt, index=2),
            ],
            change_outputs=[
                UTXO(address="change1", amount=5_500_000, index=3),
                UTXO(address="change2", amount=5_500_000, index=4),
                UTXO(address="change3", amount=108_000_000, index=5),
            ],
            network_fee=1_000_000,
            num_participants=3,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Should only assign the taker input addr1 → change3
        # addr1: 210M = 100M + 1M network + X makers + 108M change
        # X = 210M - 100M - 1M - 108M = 1M (valid for 2 makers)
        assert len(result.forced_assignments) == 1

    def test_iterative_matching_cascade(self):
        """
        Test iterative matching: first match enables second match.

        Initially ambiguous, but after first assignment, second becomes unequivocal.
        """
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=120_000_000, index=0),  # 20M remaining
                UTXO(address="addr2", amount=103_000_000, index=1),  # 3M remaining
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change1", amount=17_000_000, index=0),  # Only fits input 0
                UTXO(
                    address="change2", amount=4_000_000, index=1
                ),  # Only fits input 1 after input 0 assigned
            ],
            network_fee=2_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # First iteration: input 0 → change 17M is unique
        # Second iteration: input 1 → change 4M is now unique
        assert len(result.forced_assignments) == 2
        assert result.forced_assignments[0] == 0
        assert result.forced_assignments[1] == 1
        assert result.forced_changes[0] == 0
        assert result.forced_changes[1] == 1

    def test_multiple_inputs_same_participant_rejected(self):
        """
        Test that multi-input assignments are NOT made by greedy (left to ILP).

        Greedy only handles single-input assignments to avoid incorrect grouping.
        """
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=50_000_000, index=0),
                UTXO(address="addr2", amount=60_000_000, index=1),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
            ],
            change_outputs=[
                UTXO(address="change1", amount=8_000_000, index=3),
            ],
            network_fee=2_000_000,
            num_participants=1,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Neither input alone can cover equal_amt + reasonable change
        # Should NOT assign - requires multi-input logic (ILP handles this)
        assert len(result.forced_assignments) == 0


class TestMakerTakerDetection:
    """Test maker/taker identification via fee signs."""

    def test_maker_negative_fee(self):
        """Test maker with negative fee (receives fee from taker)."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=110_000_000, index=0),
                UTXO(address="addr2", amount=200_000_000, index=1),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change1", amount=11_000_000, index=0),
                UTXO(address="change2", amount=98_000_000, index=1),
            ],
            network_fee=1_000_000,
            num_participants=1,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        assert result.forced_assignments == {0: 0}


class TestEdgeCases:
    """Edge case tests."""

    def test_fee_exceeds_threshold(self):
        """Test that excessive fees are rejected."""
        equal_amt = 100_000_000
        max_fee_rel = 0.05

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=120_000_000, index=0),
                UTXO(address="addr2", amount=100_000_000, index=1),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=1),
                UTXO(address="equal2", amount=equal_amt, index=2),
            ],
            change_outputs=[
                UTXO(
                    address="change1", amount=10_000_000, index=0
                ),  # 10M fee = 10% so assume it's the taker's change
            ],
            network_fee=10_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=max_fee_rel)

        # Fee exceeds 5% threshold → can't be the taker paying this fee,
        # assume it's change for the taker
        # And no fee for the maker
        assert len(result.forced_assignments) == 1

    def test_fee_does_not_exceed_threshold(self):
        """Test that acceptable fees are processed."""
        equal_amt = 100_000_000
        max_fee_rel = 0.15

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=120_000_000, index=0),
                UTXO(address="addr2", amount=100_000_000, index=1),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=1),
                UTXO(address="equal2", amount=equal_amt, index=2),
            ],
            change_outputs=[
                UTXO(
                    address="change1", amount=10_000_000, index=0
                ),  # 10M fee = 10% can be for the maker
            ],
            network_fee=10_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=max_fee_rel)

        # This time the maker gets the change and all is clear
        assert len(result.forced_assignments) == 2

    def test_all_changes_assigned_one_no_change(self):
        """Test N participants, N-1 changes (one participant has no change)."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=103_000_000, index=0),
                UTXO(address="addr2", amount=105_000_000, index=1),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change1", amount=4_000_000, index=4),
            ],
            network_fee=4_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # addr2 is the taker with no change

        assert len(result.forced_assignments) >= 1

    def test_empty_inputs(self):
        """Test with no inputs (degenerate case)."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[],
            equal_outputs=[],
            change_outputs=[],
            network_fee=0,
            num_participants=0,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        assert len(result.forced_assignments) == 0

    def test_single_participant_complete_assignment(self):
        """Test single-participant transaction gets completely assigned."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=110_000_000, index=0),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=1),
            ],
            change_outputs=[
                UTXO(address="change1", amount=9_000_000, index=2),
            ],
            network_fee=1_000_000,
            num_participants=1,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        assert len(result.forced_assignments) == 1
        assert len(result.unassigned_inputs) == 0
        assert result.forced_changes[0] == 0

    def test_large_transaction_partial_assignment(self):
        """Test large transaction with mix of unequivocal and ambiguous matches."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                # Unequivocal: 210M remaining → 206.5M change (3.5M gone in fees)
                UTXO(address="addr1", amount=210_000_000, index=0),
                # Ambiguous: 5M remaining
                UTXO(address="addr2", amount=105_000_000, index=1),
                # Ambiguous: 5M remaining
                UTXO(address="addr3", amount=105_000_000, index=2),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=3),
                UTXO(address="equal2", amount=equal_amt, index=4),
                UTXO(address="equal3", amount=equal_amt, index=5),
            ],
            change_outputs=[
                UTXO(address="change1", amount=106_500_000, index=0),  # Only input 0
                UTXO(address="change2", amount=5_000_000, index=1),  # Input 1 or 2
                UTXO(address="change3", amount=5_500_000, index=2),  # Input 1 or 2
            ],
            network_fee=3_000_000,
            num_participants=3,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Should assign input 0 → change 106.5M (unequivocal)
        # Should NOT assign inputs 1 and 2 (ambiguous)
        assert 0 in result.forced_assignments
        assert result.forced_changes[result.forced_assignments[0]] == 0

        # Inputs 1 and 2 should remain unassigned
        assert len(result.unassigned_inputs) == 2


class TestSymmetricScenarios:
    """Test scenarios with symmetric inputs/outputs."""

    def test_perfectly_symmetric_inputs(self):
        """Test two identical inputs - SHOULD NOT ASSIGN."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=105_000_000, index=0),
                UTXO(address="addr2", amount=105_000_000, index=1),  # Identical
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=2),
                UTXO(address="equal2", amount=equal_amt, index=3),
            ],
            change_outputs=[
                UTXO(address="change1", amount=4_000_000, index=4),
                UTXO(address="change2", amount=4_000_000, index=5),  # Identical
            ],
            network_fee=2_000_000,
            num_participants=2,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Perfectly symmetric - no unequivocal matches possible
        assert len(result.unassigned_changes) == 2

    def test_near_symmetric_with_one_unique(self):
        """Test mostly symmetric with one clearly different input."""
        equal_amt = 100_000_000

        tx_data = TransactionData(
            txid="test_tx",
            inputs=[
                UTXO(address="addr1", amount=150_000_000, index=0),  # Unique
                UTXO(address="addr2", amount=105_000_000, index=1),
                UTXO(address="addr3", amount=105_000_000, index=2),
            ],
            equal_outputs=[
                UTXO(address="equal1", amount=equal_amt, index=3),
                UTXO(address="equal2", amount=equal_amt, index=4),
                UTXO(address="equal3", amount=equal_amt, index=5),
            ],
            change_outputs=[
                UTXO(address="change1", amount=45_000_000, index=6),  # Only fits input 0
                UTXO(address="change2", amount=6_000_000, index=7),
                UTXO(address="change3", amount=6_000_000, index=8),
            ],
            network_fee=3_000_000,
            num_participants=3,
            equal_amount=equal_amt,
        )

        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Should assign input 0 → change 49M (unequivocal)
        # Inputs 1 and 2 remain ambiguous with changes 4M
        assert 0 in result.forced_assignments
        assert result.forced_changes[result.forced_assignments[0]] == 0
        assert len(result.unassigned_inputs) == 2
