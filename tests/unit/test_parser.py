"""Unit tests for transaction parser."""

from joinmarket_analyzer.parser import parse_transaction


class TestTransactionParser:
    """Test transaction parsing logic."""

    def test_parse_basic_coinjoin(self):
        """Test parsing a basic 2-participant CoinJoin."""
        raw_tx = {
            "txid": "test123",
            "vin": [
                {"prevout": {"scriptpubkey_address": "addr1", "value": 100_000_000}},
                {"prevout": {"scriptpubkey_address": "addr2", "value": 100_000_000}},
            ],
            "vout": [
                {"scriptpubkey_address": "equal1", "value": 50_000_000},
                {"scriptpubkey_address": "equal2", "value": 50_000_000},
                {"scriptpubkey_address": "change1", "value": 45_000_000},
                {"scriptpubkey_address": "change2", "value": 45_000_000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        assert tx_data.txid == "test123"
        assert len(tx_data.inputs) == 2
        assert len(tx_data.equal_outputs) == 2
        assert len(tx_data.change_outputs) == 2
        assert tx_data.equal_amount == 50_000_000
        assert tx_data.num_participants == 2
        assert tx_data.network_fee == 10_000_000

    def test_parse_no_change(self):
        """Test parsing CoinJoin with no change outputs."""
        raw_tx = {
            "txid": "test456",
            "vin": [
                {"prevout": {"scriptpubkey_address": "addr1", "value": 55_000_000}},
                {"prevout": {"scriptpubkey_address": "addr2", "value": 55_000_000}},
            ],
            "vout": [
                {"scriptpubkey_address": "equal1", "value": 50_000_000},
                {"scriptpubkey_address": "equal2", "value": 50_000_000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        assert len(tx_data.change_outputs) == 0
        assert tx_data.network_fee == 10_000_000

    def test_parse_mixed_output_values(self):
        """Test parsing with multiple output values (identifies most common)."""
        raw_tx = {
            "txid": "test789",
            "vin": [
                {"prevout": {"scriptpubkey_address": "addr1", "value": 100_000_000}},
            ],
            "vout": [
                {"scriptpubkey_address": "out1", "value": 30_000_000},
                {"scriptpubkey_address": "out2", "value": 30_000_000},
                {"scriptpubkey_address": "out3", "value": 30_000_000},
                {"scriptpubkey_address": "change", "value": 5_000_000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        # Most common output value is 30M (appears 3 times)
        assert tx_data.equal_amount == 30_000_000
        assert tx_data.num_participants == 3
        assert len(tx_data.equal_outputs) == 3
        assert len(tx_data.change_outputs) == 1

    def test_parse_missing_addresses(self):
        """Test handling of outputs without addresses."""
        raw_tx = {
            "txid": "test_no_addr",
            "vin": [
                {"prevout": {"value": 100_000_000}},  # No address
            ],
            "vout": [
                {"value": 50_000_000},  # No address
                {"scriptpubkey_address": "addr1", "value": 45_000_000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        # Should assign placeholder addresses
        assert tx_data.inputs[0].address.startswith("unknown_")
        assert tx_data.equal_outputs[0].address == "unknown_0"

    def test_input_output_indices(self):
        """Test that input/output indices are correctly assigned."""
        raw_tx = {
            "txid": "test_indices",
            "vin": [
                {"prevout": {"scriptpubkey_address": f"in{i}", "value": 10_000_000}}
                for i in range(5)
            ],
            "vout": [{"scriptpubkey_address": f"out{i}", "value": 8_000_000} for i in range(5)],
        }

        tx_data = parse_transaction(raw_tx)

        # Check indices
        for idx, inp in enumerate(tx_data.inputs):
            assert inp.index == idx

        for idx, out in enumerate(tx_data.equal_outputs):
            assert out.index == idx


class TestEdgeCases:
    """Edge case tests for parser."""

    def test_single_output(self):
        """Test transaction with single output value (degenerate CoinJoin)."""
        raw_tx = {
            "txid": "single",
            "vin": [
                {"prevout": {"scriptpubkey_address": "addr1", "value": 100_000_000}},
            ],
            "vout": [
                {"scriptpubkey_address": "out1", "value": 95_000_000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        assert tx_data.num_participants == 1
        assert len(tx_data.equal_outputs) == 1
        assert len(tx_data.change_outputs) == 0

    def test_large_values(self):
        """Test handling of large satoshi values."""
        raw_tx = {
            "txid": "large",
            "vin": [
                {
                    "prevout": {
                        "scriptpubkey_address": "addr1",
                        "value": 21_000_000_000_000,
                    }
                },
            ],
            "vout": [
                {"scriptpubkey_address": "out1", "value": 21_000_000_000_000 - 1000},
            ],
        }

        tx_data = parse_transaction(raw_tx)

        assert tx_data.network_fee == 1000
        assert tx_data.inputs[0].amount == 21_000_000_000_000
