"""ILP solver logic for JoinMarket analysis."""

from pathlib import Path
from typing import Any, Optional

import pulp
from loguru import logger

from joinmarket_analyzer.greedy import greedy_preprocessing
from joinmarket_analyzer.models import (
    GreedyAssignment,
    Participant,
    Solution,
    TransactionData,
)
from joinmarket_analyzer.output import save_solutions

DUST_THRESHOLD = 546
GREEDY_THRESHOLD = 3


def get_solution_signature(solution: Solution) -> tuple:
    """
    Create canonical signature that is invariant to participant relabeling.

    Returns tuple of (sorted_participant_profiles, taker_profile) where each
    participant profile is (sorted_input_indices, change_idx_or_none).

    The taker_profile specifically identifies which profile belongs to the taker.
    """
    profiles = []
    taker_profile = None

    for p_idx, participant in enumerate(solution.participants):
        input_indices = tuple(sorted(inp.index for inp in participant.inputs))
        change_idx = participant.change_output.index if participant.change_output else None
        profile = (input_indices, change_idx)

        profiles.append(profile)
        if p_idx == solution.taker_index:
            taker_profile = profile

    sorted_profiles = tuple(sorted(profiles))
    return (sorted_profiles, taker_profile)


def add_solution_exclusion_cut(
    prob,
    x,
    c,
    t,
    solution: Solution,
    unassigned_inputs,
    unassigned_changes,
    greedy: GreedyAssignment,
):
    """
    Exclude this exact solution pattern in REDUCED problem space.

    We only need to exclude the ILP-assigned portion since greedy assignments are fixed.
    Focus on participants that were assigned by ILP (not in greedy.forced_assignments).
    """
    n_unassigned_inputs = len(unassigned_inputs)
    n_unassigned_changes = len(unassigned_changes)
    n_unassigned_participants = len(greedy.unassigned_participants)

    # Map original indices to reduced indices
    original_to_reduced_input = {
        inp.index: reduced_idx for reduced_idx, inp in enumerate(unassigned_inputs)
    }
    original_to_reduced_change = {
        ch.index: reduced_idx for reduced_idx, ch in enumerate(unassigned_changes)
    }
    unassigned_participant_list = sorted(greedy.unassigned_participants)
    original_to_reduced_participant = {
        orig_p: reduced_idx for reduced_idx, orig_p in enumerate(unassigned_participant_list)
    }

    # Only create exclusion constraints for ILP-assigned participants
    ilp_participant_matches = []

    for orig_p_idx, participant in enumerate(solution.participants):
        # Skip greedy-assigned participants (they're fixed)
        if orig_p_idx not in greedy.unassigned_participants:
            continue

        original_to_reduced_participant[orig_p_idx]

        # Get inputs assigned to this participant (filter to unassigned only)
        participant_input_indices = set(inp.index for inp in participant.inputs)
        participant_reduced_inputs = {
            original_to_reduced_input[i]
            for i in participant_input_indices
            if i in original_to_reduced_input
        }

        if not participant_reduced_inputs:
            # This participant got no ILP inputs (only greedy), skip
            continue

        match_terms = []

        for reduced_p in range(n_unassigned_participants):
            has_exact_inputs = pulp.LpVariable(
                f"match_inputs_{len(prob.constraints)}_{orig_p_idx}_{reduced_p}",
                cat=pulp.LpBinary,
            )

            # Must have all the specific inputs
            prob += (
                has_exact_inputs
                <= pulp.lpSum(x[(i, reduced_p)] for i in participant_reduced_inputs)
                - len(participant_reduced_inputs)
                + 1
            )

            # Must NOT have any other inputs
            prob += (
                has_exact_inputs
                <= len(participant_reduced_inputs)
                - pulp.lpSum(
                    x[(i, reduced_p)]
                    for i in range(n_unassigned_inputs)
                    if i not in participant_reduced_inputs
                )
                + 1
            )

            # Check change match
            if participant.change_output:
                change_orig_idx = participant.change_output.index
                if change_orig_idx in original_to_reduced_change:
                    reduced_change_idx = original_to_reduced_change[change_orig_idx]
                    prob += has_exact_inputs <= c[(reduced_p, reduced_change_idx)]
                else:
                    # Change was assigned by greedy, not in reduced problem
                    # This shouldn't match anyone in ILP
                    prob += has_exact_inputs <= 0
            else:
                # No change
                prob += has_exact_inputs <= 1 - pulp.lpSum(
                    c[(reduced_p, j)] for j in range(n_unassigned_changes)
                )

            # Taker constraint (only if t exists)
            if t is not None:
                is_taker = orig_p_idx == solution.taker_index
                if is_taker:
                    prob += has_exact_inputs <= t[reduced_p]
                else:
                    prob += has_exact_inputs <= 1 - t[reduced_p]
            # If t is None, all are makers, no constraint needed

            match_terms.append(has_exact_inputs)

        if match_terms:  # Only add if there are terms
            participant_match = pulp.LpVariable(
                f"participant_match_{len(prob.constraints)}_{orig_p_idx}",
                cat=pulp.LpBinary,
            )
            prob += participant_match <= pulp.lpSum(match_terms)
            prob += participant_match * len(match_terms) >= pulp.lpSum(match_terms)
            ilp_participant_matches.append(participant_match)

    # At least one ILP-assigned participant must differ
    if ilp_participant_matches:
        prob += pulp.lpSum(ilp_participant_matches) <= len(ilp_participant_matches) - 1


def analyze_greedy_results(
    greedy: GreedyAssignment, tx_data: TransactionData, max_fee_rel: float
) -> dict:
    """
    Analyze greedy results to determine ILP problem parameters.

    Returns:
        dict with:
            - taker_found: bool - was taker identified?
            - taker_original_idx: Optional[int] - original participant index of taker
            - remaining_maker_fees: int - total maker fees left to distribute
            - unassigned_input_indices: list[int] - original input indices
            - unassigned_change_indices: list[int] - relative change indices
            - n_unassigned_participants: int
    """
    equal_amount = tx_data.equal_amount
    max_maker_fee = int(equal_amount * max_fee_rel)

    # Check if taker was found
    taker_found = False
    taker_original_idx = None
    total_assigned_maker_fees = 0

    for participant_idx, change_rel_idx in greedy.forced_changes.items():
        if change_rel_idx is None:
            # No change = taker
            taker_found = True
            taker_original_idx = participant_idx
            logger.info(f"  → Taker identified in greedy: Participant {participant_idx + 1}")
        else:
            # Maker with change - calculate their fee
            input_indices = [
                i for i, p in greedy.forced_assignments.items() if p == participant_idx
            ]
            input_sum = sum(tx_data.inputs[i].amount for i in input_indices)
            change_amount = tx_data.change_outputs[change_rel_idx].amount
            maker_fee = input_sum - equal_amount - change_amount
            total_assigned_maker_fees += abs(maker_fee)

    # Calculate remaining maker fees
    n_total_makers = tx_data.num_participants - 1  # Always 1 taker
    n_assigned_makers = len([p for p, c in greedy.forced_changes.items() if c is not None])
    n_unassigned_makers = n_total_makers - n_assigned_makers

    if taker_found:
        # Taker already assigned, calculate remaining fees
        # Get taker's total input
        taker_input_indices = [
            i for i, p in greedy.forced_assignments.items() if p == taker_original_idx
        ]
        taker_input_sum = sum(tx_data.inputs[i].amount for i in taker_input_indices)

        # Taker: input = equal_amount + network_fee + total_maker_fees
        total_maker_fees = taker_input_sum - equal_amount - tx_data.network_fee
        remaining_maker_fees = total_maker_fees - total_assigned_maker_fees

        logger.info(f"  → Total maker fees (from taker): {total_maker_fees:,} sats")
        logger.info(f"  → Already assigned to makers: {total_assigned_maker_fees:,} sats")
        logger.info(
            f"  → Remaining for {n_unassigned_makers} makers: {remaining_maker_fees:,} sats"
        )
    else:
        # Taker not found yet, use standard max
        remaining_maker_fees = max_maker_fee * n_unassigned_makers
        logger.info("  → Taker not yet identified")
        logger.info(
            f"  → Max remaining maker fees: {remaining_maker_fees:,} sats "
            f"(for {n_unassigned_makers} makers)"
        )

    return {
        "taker_found": taker_found,
        "taker_original_idx": taker_original_idx,
        "remaining_maker_fees": remaining_maker_fees,
        "n_unassigned_makers": n_unassigned_makers,
        "unassigned_input_indices": sorted(greedy.unassigned_inputs),
        "unassigned_change_indices": sorted(greedy.unassigned_changes),
        "n_unassigned_participants": len(greedy.unassigned_participants),
    }


def create_reduced_problem(
    tx_data: TransactionData,
    max_fee_rel: float,
    greedy: GreedyAssignment,
    analysis: dict,
):
    """
    Create ILP problem ONLY for unassigned inputs/changes/participants.

    This is a smaller, cleaner problem that only solves for what remains.
    """
    # Use ONLY unassigned elements
    unassigned_inputs = [tx_data.inputs[i] for i in analysis["unassigned_input_indices"]]
    unassigned_changes = [tx_data.change_outputs[i] for i in analysis["unassigned_change_indices"]]
    n_unassigned = analysis["n_unassigned_participants"]

    n_inputs = len(unassigned_inputs)
    n_changes = len(unassigned_changes)
    equal_amount = tx_data.equal_amount
    network_fee = tx_data.network_fee

    logger.info("\n  Creating REDUCED ILP problem:")
    logger.info(f"    Unassigned inputs: {n_inputs}")
    logger.info(f"    Unassigned changes: {n_changes}")
    logger.info(f"    Unassigned participant slots: {n_unassigned}")

    # Calculate constraints
    max_input_sum = sum(inp.amount for inp in unassigned_inputs)
    M = max_input_sum + equal_amount
    max_reasonable_fee = int(equal_amount * max_fee_rel)

    prob = pulp.LpProblem("CoinJoin_Reduced", pulp.LpMinimize)

    # Variables use REDUCED indices (0 to n_unassigned-1)
    x = pulp.LpVariable.dicts(
        "x",
        ((i, p) for i in range(n_inputs) for p in range(n_unassigned)),
        cat=pulp.LpBinary,
    )

    c = pulp.LpVariable.dicts(
        "c",
        ((p, j) for p in range(n_unassigned) for j in range(n_changes)),
        cat=pulp.LpBinary,
    )

    prob += 0  # Feasibility only

    # Taker variable (if not already found)
    if not analysis["taker_found"]:
        t = pulp.LpVariable.dicts("t", range(n_unassigned), cat=pulp.LpBinary)
        prob += pulp.lpSum(t[p] for p in range(n_unassigned)) == 1
    else:
        # All remaining participants are makers
        t = None
        logger.info("    All remaining participants are MAKERS (taker already assigned)")

    # Input uniqueness
    for i in range(n_inputs):
        prob += pulp.lpSum(x[(i, p)] for p in range(n_unassigned)) == 1

    # Change uniqueness
    for j in range(n_changes):
        prob += pulp.lpSum(c[(p, j)] for p in range(n_unassigned)) == 1

    # Participant validity
    for p in range(n_unassigned):
        prob += pulp.lpSum(x[(i, p)] for i in range(n_inputs)) >= 1
        prob += pulp.lpSum(c[(p, j)] for j in range(n_changes)) <= 1

    # Balance constraints
    for p in range(n_unassigned):
        p_inputs = pulp.lpSum(x[(i, p)] * unassigned_inputs[i].amount for i in range(n_inputs))
        p_changes = pulp.lpSum(c[(p, j)] * unassigned_changes[j].amount for j in range(n_changes))
        balance = p_inputs - p_changes - equal_amount

        if t is not None:
            # Taker not found yet - standard constraints
            # Maker bounds
            prob += balance <= M * t[p]
            prob += balance >= -max_reasonable_fee - M * t[p]

            # Taker bounds
            prob += balance >= network_fee - M * (1 - t[p])
            max_total_fees = analysis["remaining_maker_fees"]
            prob += balance <= network_fee + max_total_fees + M * (1 - t[p])
        else:
            # All are makers - simpler constraints
            prob += balance <= 0
            prob += balance >= -max_reasonable_fee

    # Net cost for extraction
    net_cost = pulp.LpVariable.dicts(
        "net_cost",
        range(n_unassigned),
        lowBound=-max_reasonable_fee,
        upBound=network_fee + max_reasonable_fee * n_unassigned,
        cat=pulp.LpInteger,
    )

    for p in range(n_unassigned):
        p_inputs = pulp.lpSum(x[(i, p)] * unassigned_inputs[i].amount for i in range(n_inputs))
        p_changes = pulp.lpSum(c[(p, j)] * unassigned_changes[j].amount for j in range(n_changes))
        prob += net_cost[p] == p_inputs - p_changes - equal_amount

    return prob, x, c, t, net_cost, unassigned_inputs, unassigned_changes


def extract_reduced_solution(
    prob,
    x,
    c,
    t,
    net_cost,
    unassigned_inputs,
    unassigned_changes,
    analysis: dict,
    tx_data: TransactionData,
    greedy: GreedyAssignment,
) -> Optional[Solution]:
    """
    Extract solution from reduced ILP and merge with greedy assignments.
    """
    n_unassigned = analysis["n_unassigned_participants"]
    equal_amount = tx_data.equal_amount
    network_fee = tx_data.network_fee
    n_total_participants = tx_data.num_participants

    # Find taker in reduced solution (if not already found)
    if t is not None:
        reduced_taker_idx = next((p for p in range(n_unassigned) if pulp.value(t[p]) == 1), None)
        if reduced_taker_idx is None:
            return None
    else:
        reduced_taker_idx = None  # Taker was found in greedy

        # Build complete solution by merging greedy + ILP
    participants_data: list[dict[str, Any]] = [None] * n_total_participants  # type: ignore
    # type: ignore

    # 1. Add greedy-assigned participants
    for input_idx, participant_idx in greedy.forced_assignments.items():
        if participants_data[participant_idx] is None:
            participants_data[participant_idx] = {
                "inputs": [],
                "change_output": None,
                "role": None,
            }
        participants_data[participant_idx]["inputs"].append(tx_data.inputs[input_idx])

    for participant_idx, change_rel_idx in greedy.forced_changes.items():
        if change_rel_idx is None:
            participants_data[participant_idx]["change_output"] = None
            participants_data[participant_idx]["role"] = "taker"
        else:
            participants_data[participant_idx]["change_output"] = tx_data.change_outputs[
                change_rel_idx
            ]
            participants_data[participant_idx]["role"] = "maker"

    # 2. Add ILP-assigned participants
    unassigned_participant_indices = sorted(greedy.unassigned_participants)

    for reduced_p in range(n_unassigned):
        original_p = unassigned_participant_indices[reduced_p]

        # Get inputs (using original indices)
        part_inputs = []
        for i, unassigned_inp in enumerate(unassigned_inputs):
            if pulp.value(x[(i, reduced_p)]) == 1:
                part_inputs.append(unassigned_inp)

        # Get change (using original indices)
        change_output = None
        for j, unassigned_change in enumerate(unassigned_changes):
            if pulp.value(c[(reduced_p, j)]) == 1:
                change_output = unassigned_change
                break

        # Determine role
        if reduced_taker_idx is not None and reduced_p == reduced_taker_idx:
            role = "taker"
        elif analysis["taker_found"]:
            role = "maker"
        else:
            role = "maker"

        participants_data[original_p] = {
            "inputs": part_inputs,
            "change_output": change_output,
            "role": role,
        }

    # 3. Calculate fees and build Participant objects
    participants = []
    maker_fees_total = 0
    taker_idx = None

    for p_idx, data in enumerate(participants_data):
        if data is None:
            return None  # Should not happen

        input_sum = sum(inp.amount for inp in data["inputs"])
        change_val = data["change_output"].amount if data["change_output"] else 0
        fee = input_sum - change_val - equal_amount

        role = data["role"]
        if role == "taker":
            taker_idx = p_idx
        else:
            maker_fees_total += abs(fee)

        participants.append(
            Participant(
                role=role,
                inputs=data["inputs"],
                equal_output=equal_amount,
                change_output=data["change_output"],
                fee=fee,
            )
        )

    if taker_idx is None:
        return None

    taker_fee = participants[taker_idx].fee
    expected_taker_fee = maker_fees_total + network_fee
    discrepancy = abs(taker_fee - expected_taker_fee)

    return Solution(
        participants=participants,
        taker_index=taker_idx,
        total_maker_fees=maker_fees_total,
        network_fee=network_fee,
        discrepancy=discrepancy,
    )


def solution_from_greedy(greedy: GreedyAssignment, tx_data: TransactionData) -> Solution:
    """Construct a Solution object directly from a complete GreedyAssignment."""
    n_participants = tx_data.num_participants
    equal_amount = tx_data.equal_amount
    network_fee = tx_data.network_fee

    participants_data: list[dict[str, Any]] = []

    # First pass: collect data and calculate fees to identify taker
    for p_idx in range(n_participants):
        # Gather inputs
        p_inputs = [
            tx_data.inputs[i]
            for i, assigned_p in greedy.forced_assignments.items()
            if assigned_p == p_idx
        ]

        # Gather change
        change_rel_idx = greedy.forced_changes.get(p_idx)
        change_output = None
        if change_rel_idx is not None:
            change_output = tx_data.change_outputs[change_rel_idx]

        # Calculate net cost (fee)
        input_sum = sum(inp.amount for inp in p_inputs)
        change_val = change_output.amount if change_output else 0
        fee = input_sum - change_val - equal_amount

        participants_data.append({"inputs": p_inputs, "change_output": change_output, "fee": fee})

    # Identify taker: max fee (should be positive and cover network fee)
    fees = [d["fee"] for d in participants_data]
    taker_idx = fees.index(max(fees))

    participants = []
    maker_fees_total = 0

    for p_idx, data in enumerate(participants_data):
        role = "taker" if p_idx == taker_idx else "maker"
        fee = data["fee"]

        if role == "maker":
            maker_fees_total += abs(fee)

        participants.append(
            Participant(
                role=role,
                inputs=data["inputs"],
                equal_output=equal_amount,
                change_output=data["change_output"],
                fee=fee,
            )
        )

    taker_fee = participants[taker_idx].fee
    expected_taker_fee = maker_fees_total + network_fee
    discrepancy = abs(taker_fee - expected_taker_fee)

    return Solution(
        participants=participants,
        taker_index=taker_idx,
        total_maker_fees=maker_fees_total,
        network_fee=network_fee,
        discrepancy=discrepancy,
    )


def log_solution_details(solution: Solution, solution_idx: int):
    """Log details of a found solution."""
    logger.success(f"✓ Solution #{solution_idx} found")
    logger.info("─" * 70)
    taker_fee = solution.participants[solution.taker_index].fee
    logger.info(f"Taker: Participant {solution.taker_index + 1} (pays {taker_fee:,} sats)")

    for idx, participant in enumerate(solution.participants):
        role_marker = "🎯" if idx == solution.taker_index else "💰"
        input_indices = [inp.index for inp in participant.inputs]
        outputs_summary = [f"Equal={participant.equal_output:,} sats"]
        if participant.change_output:
            outputs_summary.append(
                f"Change[{participant.change_output.index}]="
                f"{participant.change_output.amount:,} sats"
            )
        else:
            outputs_summary.append("No change output")

        if participant.role == "taker":
            fee_label = "pays"
            fee_amount = participant.fee
        else:
            fee_label = "receives"
            fee_amount = abs(participant.fee)

        logger.info(f"  {role_marker} Participant {idx + 1} ({participant.role})")
        logger.info(f"    Inputs: {input_indices}")
        logger.info(f"    Outputs: {', '.join(outputs_summary)}")
        logger.info(f"    Fee {fee_label}: {fee_amount:,} sats")

    logger.info(f"Total maker fees collected: {solution.total_maker_fees:,} sats")
    logger.info(f"Network fee: {solution.network_fee:,} sats")

    if solution.discrepancy > 0:
        logger.warning(f"⚠ Discrepancy: {solution.discrepancy} sats")

    logger.info("─" * 70)


def solve_all_solutions(
    tx_data: TransactionData,
    max_fee_rel: float = 0.05,
    max_solutions: int = 1000,
    time_limit_per_solve: int = 60,
    output_path: Optional[Path] = None,
    save_incrementally: bool = True,
) -> list[Solution]:
    """Enumerate all DISTINCT valid CoinJoin decompositions."""

    logger.info("=" * 70)
    logger.info("ENUMERATING ALL DISTINCT SOLUTIONS")
    logger.info("=" * 70)
    logger.info(f"Max solutions: {max_solutions}")
    logger.info(f"Time limit per solve: {time_limit_per_solve}s")
    if save_incrementally and output_path:
        logger.info(f"Saving incrementally to: {output_path}")

    solutions: list[Solution] = []
    seen_signatures: set[tuple] = set()

    greedy: Optional[GreedyAssignment] = None
    if tx_data.num_participants >= GREEDY_THRESHOLD:
        greedy = greedy_preprocessing(tx_data, max_fee_rel)

    # CHECK FOR COMPLETE DETERMINISTIC SOLUTION
    if greedy and not greedy.unassigned_inputs:
        logger.success("Complete deterministic solution found via Greedy Preprocessing!")
        logger.info("Skipping ILP solver...")

        solution = solution_from_greedy(greedy, tx_data)
        solutions.append(solution)

        log_solution_details(solution, 1)

        if output_path:
            save_solutions(solutions, tx_data, output_path)

        return solutions

    # Analyze greedy results
    if greedy:
        analysis = analyze_greedy_results(greedy, tx_data, max_fee_rel)
        prob, x, c, t, net_cost, unassigned_inputs, unassigned_changes = create_reduced_problem(
            tx_data, max_fee_rel, greedy, analysis
        )
    else:
        # No greedy - this shouldn't happen with GREEDY_THRESHOLD=3, but handle it
        logger.warning("No greedy preprocessing performed - using full problem")
        # Fall back to original logic (not implemented here for brevity)
        return solutions

    # Log ILP problem statistics
    n_vars = len(prob.variables())
    n_constraints = len(prob.constraints)

    logger.info("\n" + "=" * 70)
    logger.info("REDUCED ILP PROBLEM STATISTICS")
    logger.info("=" * 70)
    logger.info(f"Variables: {n_vars:,} (reduced from full problem)")
    logger.info(f"Constraints: {n_constraints:,}")
    logger.info("=" * 70)

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_per_solve)

    iteration = 0
    duplicate_permutation_count = 0

    logger.info("\n" + "=" * 70)
    logger.info("SOLUTION ENUMERATION")
    logger.info("=" * 70)

    while len(solutions) < max_solutions:
        iteration += 1
        logger.info(f"\n[Iteration {iteration}] Solving reduced ILP problem...")

        status = prob.solve(solver)

        if status != pulp.LpStatusOptimal:
            if iteration == 1:
                logger.error(f"No solution found: {pulp.LpStatus[status]}")
            else:
                logger.success(
                    f"\n{'=' * 70}\n"
                    f"ENUMERATION COMPLETE: {len(solutions)} distinct solution(s) found\n"
                    f"{'=' * 70}"
                )
            break

        solution_opt = extract_reduced_solution(
            prob,
            x,
            c,
            t,
            net_cost,
            unassigned_inputs,
            unassigned_changes,
            analysis,
            tx_data,
            greedy,
        )

        if solution_opt is None:
            logger.error("Failed to extract solution from optimal status")
            break

        solution = solution_opt

        # Check if truly distinct using canonical signature
        sig = get_solution_signature(solution)
        if sig in seen_signatures:
            duplicate_permutation_count += 1
            if duplicate_permutation_count >= 10:
                logger.warning(
                    "Limit of 10 duplicate solution permutations reached. "
                    "Stopping to prevent infinite loop."
                )
                break

            logger.warning(f"⚠ Duplicate solution at iteration {iteration} (permutation detected)")
            add_solution_exclusion_cut(
                prob, x, c, t, solution, unassigned_inputs, unassigned_changes, greedy
            )
            continue

        seen_signatures.add(sig)
        solutions.append(solution)

        log_solution_details(solution, len(solutions))

        if save_incrementally and output_path:
            try:
                save_solutions(solutions, tx_data, output_path)
            except Exception as exc:
                logger.warning(f"Failed to save incrementally: {exc}")

        add_solution_exclusion_cut(
            prob, x, c, t, solution, unassigned_inputs, unassigned_changes, greedy
        )

    if len(solutions) >= max_solutions:
        logger.warning(f"Reached max solutions limit ({max_solutions})")

    return solutions
