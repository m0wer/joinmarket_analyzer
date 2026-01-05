from unittest.mock import MagicMock

from sqlmodel import Session

from joinmarket_analyzer.finder import CoinJoinCandidate, MempoolClient, Transaction
from joinmarket_analyzer.scanner import analyze_candidate


def test_analyze_candidate_retry():
    # Mock session
    session = MagicMock(spec=Session)

    # Mock candidate
    candidate = CoinJoinCandidate(
        txid="test_tx",
        height=100,
        tx_index=0,
        n_inputs=2,
        n_outputs=2,
        equal_outputs=2,
        equal_amount=1000,
        vsize=100,
        version=1,
        locktime=0,
        timestamp=1234567890,
        network_fee=100,
    )

    # Mock BAD transaction (missing prevout)
    bad_tx_data = {
        "txid": "test_tx",
        "version": 1,
        "locktime": 0,
        "vin": [
            {"txid": "prev", "vout": 0, "prevout": None, "scriptsig": "", "sequence": 0}
        ],  # Missing prevout
        "vout": [{"scriptpubkey": "abc", "value": 1000, "scriptpubkey_type": "p2pkh"}],
        "size": 100,
        "weight": 400,
        "fee": 100,
        "status": {"confirmed": True},
    }
    bad_tx = Transaction.model_validate(bad_tx_data)

    # Mock GOOD transaction (refetched)
    good_tx_data = bad_tx_data.copy()
    good_tx_data["vin"] = [
        {
            "txid": "prev",
            "vout": 0,
            "prevout": {"value": 1100, "scriptpubkey_address": "addr"},
            "scriptsig": "",
            "sequence": 0,
        }
    ]
    good_tx = Transaction.model_validate(good_tx_data)

    # Mock client
    client = MagicMock(spec=MempoolClient)
    client.get_transaction.return_value = good_tx

    # Run analysis
    analyze_candidate(candidate, bad_tx, session, client)

    # Verify refetch happened
    client.get_transaction.assert_called_once_with("test_tx")

    # Verify session.merge was called (meaning analysis proceeded to save something)
    session.merge.assert_called()


if __name__ == "__main__":
    test_analyze_candidate_retry()
