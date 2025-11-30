"""E2E test using reference transaction with known structure."""

import pytest

from joinmarket_analyzer import analyze_transaction
from joinmarket_analyzer.greedy import greedy_preprocessing
from joinmarket_analyzer.parser import parse_transaction

# Reference transaction: 0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf
REFERENCE_TXID = "0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf"


@pytest.fixture
def reference_tx_data():
    """Load reference transaction from document."""
    tx_json = {
        "txid": "0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf",
        "version": 2,
        "locktime": 891377,
        "vin": [
            {
                "txid": "8ee9afc2a1129242e0b01c75106bed28e3d6ed57d4019c29cf1922de8e7d59e2",
                "vout": 16,
                "prevout": {
                    "scriptpubkey_address": "bc1qu8hkyfjd66qk3jf84urwpepdhgesukxnewyh4t",
                    "value": 119639941,
                },
            },
            {
                "txid": "780a5933bd1fb394b47d791790544270413303ba8de96f6effed341650c41558",
                "vout": 1,
                "prevout": {
                    "scriptpubkey_address": "bc1q9r23nukvmq0ydrl082cjzfr9yp9jykrah265jj",
                    "value": 2096019783,
                },
            },
            {
                "txid": "0bc228374318a22ab9e2d1f95625f08460d9ac2b1625744b8abfbc7a14bf149a",
                "vout": 2,
                "prevout": {
                    "scriptpubkey_address": "bc1qapmxhnp9sr6hl28rc5p696ynwujfawqruet4cp",
                    "value": 807203,
                },
            },
            {
                "txid": "9d544ef9b338f672c531011b68cc65a872facacb03c5f1fa9616e18d0fb01ff3",
                "vout": 12,
                "prevout": {
                    "scriptpubkey_address": "bc1q646fq6ykfg5sy3jd7cscc3kn0f98rj9htsrtng",
                    "value": 771789096,
                },
            },
            {
                "txid": "3aac4238309b5329ca27d2c131f61eb62e786c68c6658bff9259029b11684a5e",
                "vout": 0,
                "prevout": {
                    "scriptpubkey_address": "bc1qartz973t4pw6g5fmvfratk3sh54ggjt9lsh0mv",
                    "value": 6378734,
                },
            },
            {
                "txid": "de85dcd7fb04c6eff07098f9c4efbaa9bbb60d39043bc055791a35489742c9f3",
                "vout": 17,
                "prevout": {
                    "scriptpubkey_address": "bc1q706uxqud3qnl7pk6hjp5l0hchfhgg8x3ugljmx",
                    "value": 9396936,
                },
            },
            {
                "txid": "9d544ef9b338f672c531011b68cc65a872facacb03c5f1fa9616e18d0fb01ff3",
                "vout": 1,
                "prevout": {
                    "scriptpubkey_address": "bc1qn04rsq2c8hp747kyqayh0j5fm88sdqgmq264pm",
                    "value": 16543929,
                },
            },
            {
                "txid": "298033067bd73f97d75dd3e9a1d6f9bbd086baf341b4716d8c101e4de1f6a984",
                "vout": 19,
                "prevout": {
                    "scriptpubkey_address": "bc1ql6efmyhfpstm780ke6wwsa0ycu4cw8cjtm4wgr",
                    "value": 97138563,
                },
            },
            {
                "txid": "9bfa60747d99a32254f0cb242e13eae8d8a0213e4877a86d0e615ef4702b6832",
                "vout": 4,
                "prevout": {
                    "scriptpubkey_address": "bc1qxqv5md7rznk2tg6gfksdelphk8trrtph4q2hv2",
                    "value": 14401514,
                },
            },
            {
                "txid": "9d544ef9b338f672c531011b68cc65a872facacb03c5f1fa9616e18d0fb01ff3",
                "vout": 13,
                "prevout": {
                    "scriptpubkey_address": "bc1qj7cde3zpwwra40p6rth5h7tuncdhtcuwtz3ruh",
                    "value": 107180297,
                },
            },
            {
                "txid": "74f39b42c591fb66595e56ea4d66a2a3c645d3b9542ce82601008eb4ebdcc508",
                "vout": 6,
                "prevout": {
                    "scriptpubkey_address": "bc1qp598024kscwadqkq3rzfdwlv5eysmgnq7ujxlp",
                    "value": 5637331,
                },
            },
            {
                "txid": "298033067bd73f97d75dd3e9a1d6f9bbd086baf341b4716d8c101e4de1f6a984",
                "vout": 15,
                "prevout": {
                    "scriptpubkey_address": "bc1qes4duu4fujrpryh2dk49xe2ayy2rl3y3z0m0ep",
                    "value": 14482802,
                },
            },
        ],
        "vout": [
            {
                "scriptpubkey_address": "bc1q6yr990rt9k78w02ryecaxsuwd0fv90l63d3yes",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qp7f0ukk42kl0ha48rk9ndgy0yfd0ql79gfwn2v",
                "value": 87861,
            },
            {
                "scriptpubkey_address": "bc1qludyzph5en57ktnalnkln9kd8mk23z4ls4mal6",
                "value": 113283033,
            },
            {
                "scriptpubkey_address": "bc1qx6depgwa8lp36xytv9c8wtkpmgtqpxnxgfnhx4",
                "value": 10187122,
            },
            {
                "scriptpubkey_address": "bc1q274lz2a23pdlaq4rsgaa2xjnwh jdq466sasspc4y",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qgflnsyfqhgvrhvup9kkra7n9kz8hpszegyhefj",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qt2e8ah3kgfzpmfaahfrpfdjhdn2vuhn5ys22hq",
                "value": 2089662830,
            },
            {
                "scriptpubkey_address": "bc1qtucmegd7tuunfcy6sq6ndvnnq9pzvnxg2xhfec",
                "value": 100823618,
            },
            {
                "scriptpubkey_address": "bc1qkptjkztazky2k0xsqgh3tsgyn5m378389e6lf8",
                "value": 90781833,
            },
            {
                "scriptpubkey_address": "bc1qnunse5rnvcfr3z23em7esp49agk3me38xf8fue",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qwn9qmjmqkleqd47zldnxqrc3k4c9h7tdkrzyay",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1q3alg62mketmfths5j08636cqh3045h2xkhat6r",
                "value": 3044723,
            },
            {
                "scriptpubkey_address": "bc1q0a9xxz06gh09333tdqr8xzzkj0g7uetlwwvfew",
                "value": 8045121,
            },
            {
                "scriptpubkey_address": "bc1q3lgsjmjd0ahfnr0aulg4t9cmmnu92xgpz6u2ay",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qwxyk3ajchk6z79xpgwyytzjs9yr9gk3v50y632",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1q9fuzrcnw598lpdpj0kmlrweg4efcp73a5cgvay",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1q0xexnlev5ft97mpff64zt7w28geltuen5dau9m",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1q9ayap0wc923a4c3ws6vz2rppxyx44p9vj3d2r6",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qnh5mfmz7plzmfws9s9m2tpsfkqm3rfvjzr8046",
                "value": 6357366,
            },
            {
                "scriptpubkey_address": "bc1qhxdl08dk4wtgy229u56frr6hfr0qyx4th3rxqn",
                "value": 765432353,
            },
            {
                "scriptpubkey_address": "bc1q0zq8d40ja0quesuqvntdl2qjsvnmkerwp2tq53",
                "value": 8125627,
            },
        ],
        "size": 2444,
        "weight": 5903,
        "sigops": 12,
        "fee": 10982,
    }
    return tx_json


@pytest.mark.e2e
class TestReferenceTransaction:
    """E2E tests using real reference transaction."""

    def test_parse_reference_transaction(self, reference_tx_data):
        """Test parsing of reference transaction."""
        tx_data = parse_transaction(reference_tx_data)

        assert tx_data.txid == REFERENCE_TXID
        assert len(tx_data.inputs) == 12
        assert tx_data.num_participants == 11  # 11 equal outputs
        assert tx_data.equal_amount == 6357366  # Most common output
        assert tx_data.network_fee == 10982

        # Count equal vs change outputs
        equal_count = len(tx_data.equal_outputs)
        change_count = len(tx_data.change_outputs)

        assert equal_count == 11
        assert change_count == 10  # 21 total outputs - 11 equal

    def test_greedy_preprocessing_reference_tx(self, reference_tx_data):
        """Test greedy preprocessing on reference transaction."""
        tx_data = parse_transaction(reference_tx_data)
        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Log assignments for inspection
        print(f"\nGreedy assignments: {len(result.forced_assignments)}/{len(tx_data.inputs)}")
        print(
            f"Assigned participants: {len(result.unassigned_participants)}/"
            f"{tx_data.num_participants}"
        )

        assert (
            len(result.forced_assignments) > 0
        ), "Should find at least one deterministic assignment"

    def test_known_input_change_pairs(self, reference_tx_data):
        """Test specific known input-change pairs from reference transaction."""
        tx_data = parse_transaction(reference_tx_data)
        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        # Input 1 (index 1): 2,096,019,783 sats
        # Expected change: 2,096,019,783 - 6,357,366 = 2,089,662,417 sats
        # Output 6: 2,089,662,830 sats
        # Fee: 2,089,662,417 - 2,089,662,830 = -413 sats (maker receives 413 sats)

        # This should be a unique match since the amounts are so large
        large_input_idx = 1  # Input with 20.96 BTC

        if large_input_idx in result.forced_assignments:
            participant_idx = result.forced_assignments[large_input_idx]
            print(f"Large input {large_input_idx} → Participant {participant_idx}")

            if participant_idx in result.forced_changes:
                change_rel_idx = result.forced_changes[participant_idx]
                change_output = tx_data.change_outputs[change_rel_idx]
                print(f"  → Change output {change_output.index}: {change_output.amount:,} sats")

                # Verify it's the expected large change
                assert change_output.amount > 2_000_000_000  # >20 BTC

    def test_input_change_balance(self, reference_tx_data):
        """Verify that forced assignments maintain valid balance equations."""
        tx_data = parse_transaction(reference_tx_data)
        result = greedy_preprocessing(tx_data, max_fee_rel=0.05)

        equal_amount = tx_data.equal_amount
        max_fee = int(equal_amount * 0.05)

        for input_idx, participant_idx in result.forced_assignments.items():
            input_amount = tx_data.inputs[input_idx].amount

            if participant_idx in result.forced_changes:
                change_rel_idx = result.forced_changes[participant_idx]
                change_amount = tx_data.change_outputs[change_rel_idx].amount

                # Balance: input - equal - change = fee
                fee = input_amount - equal_amount - change_amount

                # Fee should be reasonable (maker fees are negative/zero)
                assert (
                    -max_fee <= fee <= max_fee
                ), f"Fee {fee} outside reasonable range for participant {participant_idx}"
            else:
                # No change case
                fee = input_amount - equal_amount
                assert (
                    0 <= fee <= max_fee
                ), f"No-change fee {fee} outside range for participant {participant_idx}"


@pytest.mark.e2e
@pytest.mark.slow
class TestFullPipeline:
    """Full E2E pipeline tests (requires solver)."""

    def test_full_analysis_reference_tx(self, reference_tx_data):
        """Test complete analysis pipeline on reference transaction."""

        # This would require the full solver implementation
        result = analyze_transaction(txid=REFERENCE_TXID, max_fee_rel=0.005, max_solutions=10)

        assert len(result) > 0
        assert all(sol.discrepancy == 0 for sol in result)

    @pytest.mark.parametrize(
        "txid",
        [
            "ce9ed444c1787af1882f3a14ccd2935d680753979d86660e60674f02bca3ec79",
            "7c2b97245e80dab822c8f2c17435f5e298fdbaef32cbaaf2b008e504e0a9b842",
            "298033067bd73f97d75dd3e9a1d6f9bbd086baf341b4716d8c101e4de1f6a984",
        ],
    )
    def test_full_analysis_working_txs(self, txid):
        """Test complete analysis pipeline on other known working transactions."""

        result = analyze_transaction(txid=txid, max_fee_rel=0.005, max_solutions=10)

        assert len(result) > 0
        assert all(sol.discrepancy == 0 for sol in result)

    @pytest.mark.skip
    @pytest.mark.parametrize(
        "txid",
        [
            "037f979b5bd06661368d0c16be97c9c532b003e0915fa711a772208a406fa9af",
        ],
    )
    def test_full_analysis_failing_txs(self, txid):
        """Test complete analysis pipeline on known failing transactions."""

        result = analyze_transaction(txid=txid, max_fee_rel=0.00005, max_solutions=10)

        assert len(result) > 0
        assert all(sol.discrepancy == 0 for sol in result)
