"""Pytest configuration and shared fixtures."""

import pytest

from joinmarket_analyzer.models import UTXO, TransactionData


@pytest.fixture
def simple_coinjoin_tx():
    """Simple 2-participant CoinJoin with change outputs."""
    return TransactionData(
        txid="simple_test",
        inputs=[
            UTXO(address="bc1qinput1", amount=100_000_000, index=0),
            UTXO(address="bc1qinput2", amount=100_000_000, index=1),
        ],
        equal_outputs=[
            UTXO(address="bc1qequal1", amount=50_000_000, index=0),
            UTXO(address="bc1qequal2", amount=50_000_000, index=1),
        ],
        change_outputs=[
            UTXO(address="bc1qchange1", amount=45_000_000, index=2),
            UTXO(address="bc1qchange2", amount=45_000_000, index=3),
        ],
        network_fee=10_000_000,
        num_participants=2,
        equal_amount=50_000_000,
    )


@pytest.fixture
def no_change_tx():
    """CoinJoin with no change outputs."""
    return TransactionData(
        txid="no_change_test",
        inputs=[
            UTXO(address="bc1qinput1", amount=55_000_000, index=0),
            UTXO(address="bc1qinput2", amount=55_000_000, index=1),
        ],
        equal_outputs=[
            UTXO(address="bc1qequal1", amount=50_000_000, index=0),
            UTXO(address="bc1qequal2", amount=50_000_000, index=1),
        ],
        change_outputs=[],
        network_fee=10_000_000,
        num_participants=2,
        equal_amount=50_000_000,
    )


@pytest.fixture
def large_coinjoin_tx():
    """Larger CoinJoin with 5 participants."""
    equal_amt = 100_000_000

    return TransactionData(
        txid="large_test",
        inputs=[
            UTXO(address=f"bc1qinput{i}", amount=110_000_000 + i * 1_000_000, index=i)
            for i in range(8)
        ],
        equal_outputs=[UTXO(address=f"bc1qequal{i}", amount=equal_amt, index=i) for i in range(5)],
        change_outputs=[
            UTXO(address=f"bc1qchange{i}", amount=5_000_000 + i * 100_000, index=i + 5)
            for i in range(5)
        ],
        network_fee=30_000_000,
        num_participants=5,
        equal_amount=equal_amt,
    )


@pytest.fixture
def mock_mempool_response():
    """Mock response from mempool API."""
    return {
        "txid": "0" * 64,
        "vin": [
            {"prevout": {"scriptpubkey_address": "addr1", "value": 100_000_000}},
            {"prevout": {"scriptpubkey_address": "addr2", "value": 100_000_000}},
        ],
        "vout": [
            {"scriptpubkey_address": "out1", "value": 50_000_000},
            {"scriptpubkey_address": "out2", "value": 50_000_000},
            {"scriptpubkey_address": "change1", "value": 45_000_000},
            {"scriptpubkey_address": "change2", "value": 45_000_000},
        ],
        "fee": 10_000_000,
    }
