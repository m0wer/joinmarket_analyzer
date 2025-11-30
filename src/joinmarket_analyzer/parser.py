"""Transaction parsing logic."""

from collections import Counter

from loguru import logger

from .models import UTXO, TransactionData


def parse_transaction(tx_data: dict) -> TransactionData:
    """
    Parse raw transaction data into structured format.

    Identifies equal outputs (CoinJoin anonymity set) and change outputs.
    """
    inputs = [
        UTXO(
            address=vin["prevout"].get("scriptpubkey_address", f"unknown_{idx}"),
            amount=vin["prevout"]["value"],
            index=idx,
        )
        for idx, vin in enumerate(tx_data["vin"])
    ]

    outputs = [
        UTXO(
            address=vout.get("scriptpubkey_address", f"unknown_{idx}"),
            amount=vout["value"],
            index=idx,
        )
        for idx, vout in enumerate(tx_data["vout"])
    ]

    # Identify equal outputs (most common amount = CoinJoin outputs)
    amount_counts = Counter(out.amount for out in outputs)
    equal_amount, num_participants = amount_counts.most_common(1)[0]

    equal_outputs = [out for out in outputs if out.amount == equal_amount]
    change_outputs = [out for out in outputs if out.amount != equal_amount]

    total_in = sum(inp.amount for inp in inputs)
    total_out = sum(out.amount for out in outputs)
    network_fee = total_in - total_out

    logger.info(f"Identified {num_participants} equal outputs of {equal_amount} sats")
    logger.info(f"Inputs: {len(inputs)}, Change outputs: {len(change_outputs)}")
    logger.info(f"Network fee: {network_fee} sats")

    return TransactionData(
        txid=tx_data["txid"],
        inputs=inputs,
        equal_outputs=equal_outputs,
        change_outputs=change_outputs,
        network_fee=network_fee,
        num_participants=num_participants,
        equal_amount=equal_amount,
    )
