from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

FIRST_PRE_PER_SEASON = 1947
FIRST_RECORDED_PER_SEASON = 1952
ALIGNMENT_LEAGUE_BY_SEASON = {
    1947: "BAA",
    1948: "BAA",
    1949: "BAA",
    1950: "NBA",
    1951: "NBA",
}
MINIMUM_GAMES_EXCLUSIVE = 10.0
UNRESOLVED_COMPLETION_RULE = "required_active_field_set_value"

# Rank alignment is not allowed to rewrite formula-owned Attributes. Every
# shooting, passing, rebounding, defense, athleticism, durability, stamina,
# intangibles, Potential, and OVR-storage field retains its original owner.
# These two unresolved soft Attributes are the complete positive allowlist.
# If either receives a real formula later, the source-rule gate below protects
# it automatically without requiring another exclusion here.
ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS = frozenset(
    {
        "Attributes/HANDS",
        "Attributes/HUSTLE",
    }
)


class AlignmentContractError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def uses_pre_per_alignment(season: int) -> bool:
    return int(season) in ALIGNMENT_LEAGUE_BY_SEASON


def _evidence_key(player_id: object, team: object) -> tuple[str, str]:
    return (str(player_id or "").strip().upper(), str(team or "").strip().upper())


def _eligible_record(proposal: Any, evidence_by_key: Mapping[tuple[str, str], Any]) -> dict[str, Any] | None:
    evidence = evidence_by_key.get(_evidence_key(proposal.player_id, proposal.team))
    if evidence is None:
        raise AlignmentContractError(
            f"missing exact evidence for player_id={proposal.player_id} team={proposal.team}"
        )
    league = str(evidence.season_info.get("lg") or "").strip().upper()
    games = _number(evidence.per_game.get("g"))
    ows = _number(evidence.advanced.get("ows"))
    dws = _number(evidence.advanced.get("dws"))
    ws = _number(evidence.advanced.get("ws"))
    fg_percent = _number(evidence.per_game.get("fg_percent"))
    expected_league = ALIGNMENT_LEAGUE_BY_SEASON.get(int(proposal.season))
    if league != expected_league or games is None or games <= MINIMUM_GAMES_EXCLUSIVE:
        return None
    if None in (ows, dws, ws, fg_percent):
        return None
    return {
        "proposal": proposal,
        "player_id": str(proposal.player_id),
        "team": str(proposal.team),
        "games": games,
        "ows": ows,
        "dws": dws,
        "ws": ws,
        "fg_percent": fg_percent,
    }


def _numeric_attributes(proposal: Any) -> tuple[Any, ...]:
    candidates = tuple(
        candidate
        for candidate in proposal.field_candidates
        if candidate.section == "Attributes"
        and isinstance(candidate.display_value, int)
        and not isinstance(candidate.display_value, bool)
    )
    if not candidates:
        raise AlignmentContractError(f"proposal has no numeric Attributes: {proposal.player_id}/{proposal.team}")
    return candidates


def _adjustable_attributes(proposal: Any) -> tuple[Any, ...]:
    attributes = _numeric_attributes(proposal)
    return tuple(
        candidate
        for candidate in attributes
        if candidate.field_key in ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS
        and candidate.source_rule == UNRESOLVED_COMPLETION_RULE
    )


def _strict_rank_targets(records: Sequence[dict[str, Any]], metric: str, total: str) -> dict[tuple[str, str], int]:
    ordered = sorted(records, key=lambda row: (-row[metric], row["player_id"], row["team"]))
    existing_totals = sorted((int(row[total]) for row in records), reverse=True)
    groups: list[tuple[float, list[dict[str, Any]], float]] = []
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][metric] == ordered[cursor][metric]:
            end += 1
        groups.append(
            (
                float(ordered[cursor][metric]),
                ordered[cursor:end],
                sum(existing_totals[cursor:end]) / (end - cursor),
            )
        )
        cursor = end

    low = min(existing_totals)
    high = max(existing_totals)
    group_count = len(groups)
    if high - low + 1 < group_count:
        raise AlignmentContractError(
            f"{metric} has {group_count} distinct ranks but {total} has only {high - low + 1} integer totals"
        )

    targets: list[int] = []
    for index, (_metric_value, _members, base) in enumerate(groups):
        minimum = low + (group_count - 1 - index)
        maximum = high - index
        targets.append(max(minimum, min(maximum, round(base))))
    for index in range(1, group_count):
        targets[index] = min(targets[index], targets[index - 1] - 1)
    for index in range(group_count - 2, -1, -1):
        targets[index] = max(targets[index], targets[index + 1] + 1)

    if targets[0] > high or targets[-1] < low or any(
        targets[index] <= targets[index + 1] for index in range(group_count - 1)
    ):
        raise AlignmentContractError(f"could not construct strict descending targets for {metric}")

    return {
        (member["player_id"], member["team"]): target
        for (_metric_value, members, _base), target in zip(groups, targets)
        for member in members
    }


def _replace_group(
    candidates: Sequence[Any],
    target_total: int,
    *,
    metric: str,
    metric_value: float,
    group_name: str,
) -> dict[str, Any]:
    values = {candidate.field_key: int(candidate.display_value) for candidate in candidates}
    minimum = 25 * len(candidates)
    maximum = 99 * len(candidates)
    if not minimum <= target_total <= maximum:
        raise AlignmentContractError(
            f"target outside legal range: group={group_name} target={target_total} legal={minimum}..{maximum}"
        )
    before_total = sum(values.values())
    delta = target_total - before_total
    while delta > 0:
        available = [candidate for candidate in candidates if values[candidate.field_key] < 99]
        if not available:
            raise AlignmentContractError(f"cannot raise {group_name} to {target_total}")
        candidate = min(available, key=lambda item: (values[item.field_key], item.ordinal, item.field_key))
        values[candidate.field_key] += 1
        delta -= 1
    while delta < 0:
        available = [candidate for candidate in candidates if values[candidate.field_key] > 25]
        if not available:
            raise AlignmentContractError(f"cannot lower {group_name} to {target_total}")
        candidate = max(available, key=lambda item: (values[item.field_key], -item.ordinal, item.field_key))
        values[candidate.field_key] -= 1
        delta += 1

    return {
        candidate.field_key: (
            candidate
            if values[candidate.field_key] == int(candidate.display_value)
            else replace(
                candidate,
                display_value=values[candidate.field_key],
                source_rule="pre_per_1947_1951_rank_alignment",
                evidence_keys=tuple(candidate.evidence_keys)
                + (
                    f"alignment_metric={metric}",
                    f"alignment_metric_value={metric_value:.8f}",
                    f"alignment_group={group_name}",
                    f"alignment_before_total={before_total}",
                    f"alignment_target_total={target_total}",
                    f"alignment_original_source_rule={candidate.source_rule}",
                ),
            )
        )
        for candidate in candidates
    }


def align_pre_per_proposals(
    proposals: Iterable[Any],
    evidence_by_key: Mapping[tuple[str, str], Any],
) -> tuple[Any, ...]:
    proposal_tuple = tuple(proposals)
    if not proposal_tuple or any(not uses_pre_per_alignment(proposal.season) for proposal in proposal_tuple):
        return proposal_tuple

    records: list[dict[str, Any]] = []
    for proposal in proposal_tuple:
        record = _eligible_record(proposal, evidence_by_key)
        if record is None:
            continue
        attributes = _numeric_attributes(proposal)
        adjustable = _adjustable_attributes(proposal)
        record.update(
            {
                "attributes": attributes,
                "adjustable": adjustable,
                "attribute_total": sum(candidate.display_value for candidate in attributes),
            }
        )
        records.append(record)
    if not records:
        return proposal_tuple

    total_targets = _strict_rank_targets(records, "ws", "attribute_total")

    replacements: dict[tuple[str, str], Any] = {}
    for record in records:
        key = (record["player_id"], record["team"])
        total_target = total_targets[key]
        candidates = record["adjustable"]
        if not candidates:
            continue
        current_adjustable_total = sum(int(candidate.display_value) for candidate in candidates)
        requested_adjustable_total = current_adjustable_total + total_target - int(record["attribute_total"])
        bounded_adjustable_total = max(
            25 * len(candidates),
            min(99 * len(candidates), requested_adjustable_total),
        )
        candidate_replacements = _replace_group(
            candidates,
            bounded_adjustable_total,
            metric="advanced.ws",
            metric_value=record["ws"],
            group_name="underdetermined_soft_attributes",
        )
        adjusted_candidates = tuple(
            candidate_replacements.get(candidate.field_key, candidate)
            for candidate in record["proposal"].field_candidates
        )
        replacements[key] = replace(record["proposal"], field_candidates=adjusted_candidates)

    return tuple(replacements.get((proposal.player_id, proposal.team), proposal) for proposal in proposal_tuple)


__all__ = [
    "ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS",
    "ALIGNMENT_LEAGUE_BY_SEASON",
    "AlignmentContractError",
    "FIRST_PRE_PER_SEASON",
    "FIRST_RECORDED_PER_SEASON",
    "align_pre_per_proposals",
    "uses_pre_per_alignment",
]
