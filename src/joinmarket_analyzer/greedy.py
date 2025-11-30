"""Greedy preprocessing heuristic for CoinJoin analysis - SINGLE TAKER CONSTRAINT."""

from typing import Optional

from loguru import logger

from joinmarket_analyzer.models import GreedyAssignment, TransactionData


def greedy_preprocessing(tx_data: TransactionData, max_fee_rel: float) -> GreedyAssignment:
    """
    Greedy preprocessing with strict unequivocal matching and SINGLE TAKER constraint.

    CRITICAL: Only assigns matches that are bidirectionally unique:
    - Input must have exactly ONE compatible change
    - That change must be compatible with exactly ONE unassigned input
    - OR input must be the ONLY no-change compatible input (taker)

    SINGLE TAKER CONSTRAINT:
    - At most ONE participant can be identified as taker
    - Once taker is found, all remaining assignments must be makers

    FEE MODEL:
    - 1 taker per transaction (pays all fees)
    - N-1 makers per transaction (each receives their individual fee, may be 0)

    Maker with change:
        input + maker_fee = equal_amount + change
        maker_fee = equal_amount + change - input
        Constraint: 0 <= maker_fee <= max_reasonable_fee

    Taker (no change):
        input = equal_amount + network_fee + total_maker_fees
        total_maker_fees = input - equal_amount - network_fee
        Constraint: 0 <= total_maker_fees <= max_reasonable_fee * (N-1)

    Taker (with change):
        input = equal_amount + network_fee + total_maker_fees + change
        total_maker_fees = input - equal_amount - network_fee - change
        Constraint: 0 <= total_maker_fees <= max_reasonable_fee * (N-1)

    Args:
        tx_data: Parsed transaction data
        max_fee_rel: Maximum individual maker fee as fraction of equal_amount

    Returns:
        GreedyAssignment with forced assignments and unassigned sets
    """
    logger.info("=" * 70)
    logger.info("GREEDY PREPROCESSING (Unequivocal Matches Only)")
    logger.info("=" * 70)

    n_participants = tx_data.num_participants
    equal_amount = tx_data.equal_amount
    max_maker_fee = int(equal_amount * max_fee_rel)
    max_total_maker_fees = max_maker_fee * (n_participants - 1)

    # Detect no-change participant scenario
    has_no_change_participant = len(tx_data.change_outputs) == n_participants - 1
    if has_no_change_participant:
        logger.info(
            f"⚡ Detected: {len(tx_data.change_outputs)} changes for {n_participants} participants"
        )
        logger.info("   → One participant has no change output (taker)")

    forced_assignments: dict[int, int] = {}  # input_idx -> participant_idx
    forced_changes: dict[
        int, Optional[int]
    ] = {}  # participant_idx -> relative change_idx (None means NO change)
    used_change_rel_indices: set[int] = set()
    next_participant = 0
    taker_found = False  # <<<< CRITICAL: Track if taker has been identified

    logger.info("\nIterative Unequivocal Matching:")
    logger.info("─" * 70)

    iteration = 0
    assignments_made = True

    while assignments_made and next_participant < n_participants:
        assignments_made = False
        iteration += 1

        unassigned_inputs = [inp for inp in tx_data.inputs if inp.index not in forced_assignments]

        if not unassigned_inputs:
            break

        for inp in unassigned_inputs:
            if next_participant >= n_participants:
                break

            remaining = inp.amount - equal_amount

            # Find all compatible changes for this input
            compatible_as_maker = []  # (rel_idx, change, maker_fee)
            compatible_as_taker = []  # (rel_idx, change, total_maker_fees)

            for rel_idx, change in enumerate(tx_data.change_outputs):
                if rel_idx in used_change_rel_indices:
                    continue

                # Check maker compatibility: input + maker_fee = equal_amount + change
                maker_fee = change.amount - remaining
                if 0 <= maker_fee <= max_maker_fee:
                    compatible_as_maker.append((rel_idx, change, maker_fee))

                # Check taker compatibility:
                # input = equal_amount + network_fee + total_maker_fees + change
                # Only check if taker not yet found
                if not taker_found:
                    total_maker_fees = remaining - tx_data.network_fee - change.amount
                    if 0 <= total_maker_fees <= max_total_maker_fees:
                        compatible_as_taker.append((rel_idx, change, total_maker_fees))

            # Check no-change compatibility (taker scenario) - only if taker not yet found
            total_maker_fees_no_change = remaining - tx_data.network_fee
            no_change_compatible = (
                not taker_found and 0 <= total_maker_fees_no_change <= max_total_maker_fees
            )

            # CASE 1: Unique change match - prioritize maker over taker
            if len(compatible_as_maker) == 1 and not (
                len(compatible_as_taker) > 0 and not taker_found
            ):
                # Unique maker match
                rel_idx, change, fee = compatible_as_maker[0]

                # BIDIRECTIONAL CHECK:
                # Is this change compatible with any OTHER unassigned input as maker?
                other_compatible_inputs = []
                for other_inp in unassigned_inputs:
                    if other_inp.index == inp.index:
                        continue
                    other_remaining = other_inp.amount - equal_amount
                    other_maker_fee = change.amount - other_remaining
                    if 0 <= other_maker_fee <= max_maker_fee:
                        other_compatible_inputs.append(other_inp.index)

                if not other_compatible_inputs:
                    # UNEQUIVOCAL MAKER MATCH
                    forced_assignments[inp.index] = next_participant
                    forced_changes[next_participant] = rel_idx
                    used_change_rel_indices.add(rel_idx)

                    logger.info(
                        f"  [{iteration}] Input[{inp.index}] → Participant {next_participant + 1} "
                        f"(maker)"
                    )
                    logger.info(
                        f"       Change[{change.index}] = {change.amount:,} sats, "
                        f"receives {fee:,} sats fee"
                    )

                    next_participant += 1
                    assignments_made = True
                    continue

            # CASE 2: Unique taker match (with change) - ONLY if taker not yet found
            if (
                len(compatible_as_taker) == 1
                and len(compatible_as_maker) == 0
                and not no_change_compatible
                and not taker_found
            ):
                rel_idx, change, total_fees = compatible_as_taker[0]

                # BIDIRECTIONAL CHECK:
                # Is this change compatible with any OTHER unassigned input as taker?
                other_compatible_inputs = []
                for other_inp in unassigned_inputs:
                    if other_inp.index == inp.index:
                        continue
                    other_remaining = other_inp.amount - equal_amount
                    other_total_maker_fees = other_remaining - tx_data.network_fee - change.amount
                    if 0 <= other_total_maker_fees <= max_total_maker_fees:
                        other_compatible_inputs.append(other_inp.index)

                if not other_compatible_inputs:
                    # UNEQUIVOCAL TAKER MATCH (with change)
                    forced_assignments[inp.index] = next_participant
                    forced_changes[next_participant] = rel_idx
                    used_change_rel_indices.add(rel_idx)
                    taker_found = True  # <<<< Mark taker as found

                    logger.info(
                        f"  [{iteration}] Input[{inp.index}] → Participant {next_participant + 1} "
                        f"(taker with change) ⚡"
                    )
                    logger.info(
                        f"       Change[{change.index}] = {change.amount:,} sats, "
                        f"pays {tx_data.network_fee:,} sats network + {total_fees:,} sats makers"
                    )

                    next_participant += 1
                    assignments_made = True
                    continue

            # CASE 3: No compatible changes, but no-change is valid (taker)
            # ONLY if taker not yet found
            if (
                len(compatible_as_maker) == 0
                and len(compatible_as_taker) == 0
                and no_change_compatible
                and not taker_found
            ):
                forced_assignments[inp.index] = next_participant
                forced_changes[next_participant] = None
                taker_found = True  # <<<< Mark taker as found

                logger.info(
                    f"  [{iteration}] Input[{inp.index}] → Participant {next_participant + 1} "
                    f"(taker, no-change) ⚡"
                )
                logger.info(
                    f"       Pays {tx_data.network_fee:,} sats network fee "
                    f"+ {total_maker_fees_no_change:,} sats total maker fees"
                )

                next_participant += 1
                assignments_made = True
                continue

            # CASE 4: Multiple compatible changes exist - look for unique maker match
            if len(compatible_as_maker) >= 1:
                # Check if ANY change is uniquely compatible with THIS input only (as maker)
                unique_change_found = False

                for rel_idx, change, fee in compatible_as_maker:
                    # Is this change compatible with any OTHER unassigned input as maker?
                    other_compatible_inputs = []
                    for other_inp in unassigned_inputs:
                        if other_inp.index == inp.index:
                            continue
                        other_remaining = other_inp.amount - equal_amount
                        other_maker_fee = change.amount - other_remaining
                        if 0 <= other_maker_fee <= max_maker_fee:
                            other_compatible_inputs.append(other_inp.index)

                    if not other_compatible_inputs:
                        # This change is ONLY compatible with current input as maker
                        forced_assignments[inp.index] = next_participant
                        forced_changes[next_participant] = rel_idx
                        used_change_rel_indices.add(rel_idx)

                        logger.info(
                            f"  [{iteration}] Input[{inp.index}] → "
                            f"Participant {next_participant + 1} (maker)"
                        )
                        logger.info(
                            f"       Change[{change.index}] = {change.amount:,} sats (unique), "
                            f"receives {fee:,} sats fee"
                        )

                        next_participant += 1
                        assignments_made = True
                        unique_change_found = True
                        break

                if unique_change_found:
                    continue

            # CASE 5: Ambiguous - skip this input

    if iteration > 0:
        logger.success(
            f"Completed {iteration} iteration(s): "
            f"{len(forced_assignments)}/{len(tx_data.inputs)} inputs assigned"
        )
    else:
        logger.info("No unequivocal matches found")

    # Compute unassigned sets
    assigned_inputs = set(forced_assignments.keys())
    all_inputs = set(inp.index for inp in tx_data.inputs)
    unassigned_inputs_set = all_inputs - assigned_inputs

    assigned_changes: set[int] = set(used_change_rel_indices)
    all_changes = set(range(len(tx_data.change_outputs)))
    unassigned_changes = all_changes - assigned_changes

    assigned_participants = set(forced_assignments.values())
    all_participants = set(range(n_participants))
    unassigned_participants = all_participants - assigned_participants

    result = GreedyAssignment(
        forced_assignments=forced_assignments,
        forced_changes=forced_changes,
        unassigned_inputs=unassigned_inputs_set,
        unassigned_changes=unassigned_changes,
        unassigned_participants=unassigned_participants,
    )

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("PREPROCESSING SUMMARY")
    logger.info("=" * 70)
    logger.success(f"Assigned: {len(forced_assignments)}/{len(tx_data.inputs)} inputs")
    logger.info(f"Assigned participants: {len(assigned_participants)}/{n_participants}")
    logger.info(f"Assigned changes: {len(assigned_changes)}/{len(tx_data.change_outputs)}")
    if taker_found:
        logger.info("✓ Taker identified")
    else:
        logger.info("⚠ Taker not yet identified")

    # Display detailed mapping
    if forced_assignments:
        logger.info("\nAssignment Details:")
        logger.info("─" * 70)

        participant_mapping: dict[int, list[int]] = {}
        for input_idx, participant_idx in forced_assignments.items():
            if participant_idx not in participant_mapping:
                participant_mapping[participant_idx] = []
            participant_mapping[participant_idx].append(input_idx)

        for participant_idx in sorted(participant_mapping.keys()):
            input_indices = sorted(participant_mapping[participant_idx])

            # Calculate fees
            total_input = sum(tx_data.inputs[idx].amount for idx in input_indices)
            remaining = total_input - equal_amount

            change_info = ""
            fee_info = ""
            role = "maker"

            if participant_idx in forced_changes:
                rel_change_idx = forced_changes[participant_idx]
                if rel_change_idx is None:
                    # Taker with no change
                    change_info = " → NO change"
                    total_maker_fees = remaining - tx_data.network_fee
                    fee_info = (
                        f", pays {tx_data.network_fee:,} sats network + "
                        f"{total_maker_fees:,} sats makers"
                    )
                    role = "taker ⚡"
                else:
                    abs_change_idx = tx_data.change_outputs[rel_change_idx].index
                    change_amount = tx_data.change_outputs[rel_change_idx].amount
                    change_info = f" → Change[{abs_change_idx}]"

                    # Check if maker or taker with change
                    maker_fee = change_amount - remaining
                    if 0 <= maker_fee <= max_maker_fee:
                        # Likely a maker
                        fee_info = f", receives {maker_fee:,} sats fee"
                        role = "maker"
                    else:
                        # Likely a taker with change
                        total_maker_fees = remaining - tx_data.network_fee - change_amount
                        fee_info = (
                            f", pays {tx_data.network_fee:,} sats network + "
                            f"{total_maker_fees:,} sats makers"
                        )
                        role = "taker ⚡"

            input_list = ", ".join(f"Input[{idx}]" for idx in input_indices)
            logger.info(
                f"  Participant {participant_idx + 1} ({role}): {input_list}{change_info}{fee_info}"
            )

        if unassigned_inputs_set:
            unassigned_list = ", ".join(f"Input[{idx}]" for idx in sorted(unassigned_inputs_set))
            logger.info(f"  Unassigned: {unassigned_list}")

        logger.info("─" * 70)

    if len(forced_assignments) == len(tx_data.inputs):
        logger.success("✓ Complete deterministic solution found!")
    elif len(forced_assignments) > 0:
        logger.info(
            f"Partial solution: {len(unassigned_inputs_set)} inputs deferred to ILP "
            "(ambiguous matches)"
        )
    else:
        logger.info("No deterministic assignments - full ILP search required")

    return result
