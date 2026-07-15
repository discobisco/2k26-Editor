from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping


_PER_START_SEASON = 1952
_FIRST_THREE_POINT_SEASON = 1969
_GENERATOR_DIR = Path(__file__).resolve().parent
_PSEUDO_PER_TABLE = "generated_pseudo_per_1947_1951"
_ATTRIBUTE_MIN = 25
_ATTRIBUTE_MAX = 99
_EXCLUDED_ATTRIBUTE_NAMES = {
    "BACKDURABILITY",
    "HEADDURABILITY",
    "LEFTANKLEDURABILITY",
    "LEFTELBOWDURABILITY",
    "LEFTFOOTDURABILITY",
    "LEFTHANDDURABILITY",
    "LEFTHIPDURABILITY",
    "LEFTKNEEDURABILITY",
    "LEFTSHOULDERDURABILITY",
    "MISCDURABILITY",
    "NECKDURABILITY",
    "RIGHTANKLEDURABILITY",
    "RIGHTELBOWDURABILITY",
    "RIGHTFOOTDURABILITY",
    "RIGHTHANDDURABILITY",
    "RIGHTHIPDURABILITY",
    "RIGHTKNEEDURABILITY",
    "RIGHTSHOULDERDURABILITY",
    "POTENTIAL",
    "FREETHROW",
    "CACHCEDOVR",
    "MAXOVR",
    "MINOVR",
}


@dataclass(frozen=True)
class AttributeRankEntry:
    proposal: Any
    metric_value: float
    metric_source: str
    current_total: int
    target_total: int
    adjustable_candidates: tuple[Any, ...]


@dataclass(frozen=True)
class AttributeRankAdjustment:
    player_id: str
    team: str
    metric_source: str
    metric_value: float
    before_total: int
    after_total: int
    target_total: int
    changed_fields: int


@dataclass(frozen=True)
class AttributeRankAdjustmentResult:
    proposals: tuple[Any, ...]
    adjustments: tuple[AttributeRankAdjustment, ...]


class _EvidenceAdapter:
    def __init__(self, row: Any) -> None:
        self.row = row

    def get(self, namespace: str, key: str) -> Any:
        row = self.row
        if hasattr(row, namespace):
            source = getattr(row, namespace)
            if isinstance(source, Mapping):
                return source.get(key)
        if isinstance(row, Mapping):
            prefixed = f"{namespace}.{key}"
            if prefixed in row:
                return row.get(prefixed)
            if key in row:
                return row.get(key)
        return None


def align_attribute_totals_to_metric_ranks(proposals: Iterable[Any], evidence_by_key: Mapping[tuple[str, str], Any] | None = None) -> AttributeRankAdjustmentResult:
    """Adjust generated Attribute totals so their spacing follows PER/pseudo-PER.

    PER is used when the season has real Basketball-Reference PER coverage
    (1952+ and non-null `advanced.per`).  Earlier seasons use the imported
    generated pseudo-PER source table.
    """

    proposal_tuple = tuple(proposals)
    evidence_lookup = _normalized_evidence_lookup(evidence_by_key or {})
    entries: list[AttributeRankEntry] = []
    passthrough: list[Any] = []

    for proposal in proposal_tuple:
        metric = _proposal_metric(proposal, evidence_lookup)
        adjustable = _adjustable_attribute_candidates(proposal)
        total = _attribute_total(adjustable)
        if metric is None or not adjustable or total is None:
            passthrough.append(proposal)
            continue
        entries.append(
            AttributeRankEntry(
                proposal=proposal,
                metric_value=metric[0],
                metric_source=metric[1],
                current_total=total,
                target_total=total,
                adjustable_candidates=adjustable,
            )
        )

    if len(entries) < 2:
        return AttributeRankAdjustmentResult(proposals=proposal_tuple, adjustments=())

    metric_order = sorted(entries, key=_metric_sort_key)
    target_by_identity = _metric_ratio_target_totals(metric_order)

    adjusted_by_identity: dict[tuple[str, str], Any] = {}
    adjustments: list[AttributeRankAdjustment] = []
    for entry in entries:
        target_total = target_by_identity[_proposal_identity(entry.proposal)]
        adjusted_proposal, adjustment = _proposal_with_adjusted_total(entry, target_total)
        adjusted_by_identity[_proposal_identity(entry.proposal)] = adjusted_proposal
        if adjustment is not None:
            adjustments.append(adjustment)

    return AttributeRankAdjustmentResult(
        proposals=tuple(adjusted_by_identity.get(_proposal_identity(proposal), proposal) for proposal in proposal_tuple),
        adjustments=tuple(adjustments),
    )


def _proposal_metric(proposal: Any, evidence_lookup: Mapping[tuple[str, str], Any]) -> tuple[float, str] | None:
    evidence = evidence_lookup.get(_proposal_identity(proposal))
    if evidence is None:
        return None
    adapter = _EvidenceAdapter(evidence)
    season = _int_value(getattr(proposal, "season", None)) or _int_value(adapter.get("season_info", "season"))
    per = _float_value(adapter.get("advanced", "per"))
    if season is not None and season >= _PER_START_SEASON and per is not None:
        return per, "advanced.per"
    pseudo = _generated_pseudo_per_from_source_table(proposal, adapter)
    if pseudo is None:
        return None
    return pseudo, f"{_PSEUDO_PER_TABLE}.generated_pseudo_per"


def _generated_pseudo_per_from_source_table(proposal: Any, adapter: _EvidenceAdapter) -> float | None:
    season = _proposal_season(proposal) or _int_value(adapter.get("season_info", "season"))
    player_id = _norm(getattr(proposal, "player_id", ""))
    team = _norm(getattr(proposal, "team", ""))
    if season is None or not player_id or not team:
        return None
    database = _GENERATOR_DIR / "NBA Player Data" / "NBA_DATA_Master.sqlite"
    if not database.is_file():
        return None
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            f"SELECT generated_pseudo_per FROM {_PSEUDO_PER_TABLE} WHERE season=? AND upper(player_id)=? AND upper(team)=?",
            (season, player_id, team),
        ).fetchone()
        if row is None:
            return None
        return _float_value(row[0])


def _metric_ratio_target_totals(metric_order: list[AttributeRankEntry]) -> dict[tuple[str, str], int]:
    positive_entries = [entry for entry in metric_order if entry.metric_value > 0 and entry.adjustable_candidates]
    if not positive_entries:
        return {_proposal_identity(entry.proposal): entry.current_total for entry in metric_order}
    anchor_metric = _metric_average_anchor(positive_entries)
    anchor_average = max(entry.current_total / len(entry.adjustable_candidates) for entry in positive_entries)
    if anchor_metric <= 0 or anchor_average <= 0:
        return {_proposal_identity(entry.proposal): entry.current_total for entry in metric_order}
    targets: dict[tuple[str, str], int] = {}
    for entry in metric_order:
        if entry.metric_value <= 0:
            targets[_proposal_identity(entry.proposal)] = entry.current_total
            continue
        target_average = anchor_average * (entry.metric_value / anchor_metric)
        raw_target = int(round(target_average * len(entry.adjustable_candidates)))
        targets[_proposal_identity(entry.proposal)] = _clamp_total_for_entry(entry, raw_target)
    return targets


def _metric_average_anchor(metric_order: list[AttributeRankEntry]) -> float:
    if len(metric_order) >= 2 and metric_order[1].metric_value > 0:
        return metric_order[1].metric_value
    return metric_order[0].metric_value


def _clamp_total_for_entry(entry: AttributeRankEntry, target_total: int) -> int:
    count = len(entry.adjustable_candidates)
    return max(_ATTRIBUTE_MIN * count, min(_ATTRIBUTE_MAX * count, target_total))


def _proposal_with_adjusted_total(entry: AttributeRankEntry, target_total: int) -> tuple[Any, AttributeRankAdjustment | None]:
    values = [int(candidate.display_value) for candidate in entry.adjustable_candidates]
    adjusted_values = _redistribute_total(values, target_total)
    if adjusted_values == values:
        return entry.proposal, None

    adjusted_by_key = {
        candidate.field_key: replace(
            candidate,
            display_value=value,
            source_rule="attribute_rank_alignment",
            evidence_keys=tuple(candidate.evidence_keys)
            + (
                f"attribute_rank_metric={entry.metric_source}",
                f"attribute_rank_metric_value={entry.metric_value:.6f}",
                f"attribute_rank_before_total={entry.current_total}",
                f"attribute_rank_target_total={target_total}",
            ),
        )
        for candidate, value in zip(entry.adjustable_candidates, adjusted_values)
        if int(candidate.display_value) != value
    }
    field_candidates = tuple(adjusted_by_key.get(candidate.field_key, candidate) for candidate in entry.proposal.field_candidates)
    adjusted_proposal = replace(entry.proposal, field_candidates=field_candidates)
    after_total = _attribute_total(_adjustable_attribute_candidates(adjusted_proposal)) or entry.current_total
    return adjusted_proposal, AttributeRankAdjustment(
        player_id=str(getattr(entry.proposal, "player_id", "") or ""),
        team=str(getattr(entry.proposal, "team", "") or ""),
        metric_source=entry.metric_source,
        metric_value=entry.metric_value,
        before_total=entry.current_total,
        after_total=after_total,
        target_total=target_total,
        changed_fields=len(adjusted_by_key),
    )


def _redistribute_total(values: list[int], target_total: int) -> list[int]:
    adjusted = [max(_ATTRIBUTE_MIN, min(_ATTRIBUTE_MAX, int(value))) for value in values]
    delta = int(target_total) - sum(adjusted)
    if delta > 0:
        while delta > 0:
            changed = False
            for index in sorted(range(len(adjusted)), key=lambda i: (adjusted[i], i)):
                if adjusted[index] >= _ATTRIBUTE_MAX:
                    continue
                adjusted[index] += 1
                delta -= 1
                changed = True
                if delta == 0:
                    break
            if not changed:
                break
    elif delta < 0:
        while delta < 0:
            changed = False
            for index in sorted(range(len(adjusted)), key=lambda i: (-adjusted[i], i)):
                if adjusted[index] <= _ATTRIBUTE_MIN:
                    continue
                adjusted[index] -= 1
                delta += 1
                changed = True
                if delta == 0:
                    break
            if not changed:
                break
    return adjusted


def _adjustable_attribute_candidates(proposal: Any) -> tuple[Any, ...]:
    candidates: list[Any] = []
    season = _proposal_season(proposal)
    for candidate in getattr(proposal, "field_candidates", ()):
        if str(getattr(candidate, "section", "") or "") != "Attributes":
            continue
        field_key = str(getattr(candidate, "field_key", "") or "")
        if not field_key.startswith("Attributes/"):
            continue
        normalized = str(getattr(candidate, "normalized_name", "") or field_key.rsplit("/", 1)[-1]).upper()
        if normalized in _EXCLUDED_ATTRIBUTE_NAMES or "DURABILITY" in normalized:
            continue
        if normalized == "3POINT" and season is not None and season < _FIRST_THREE_POINT_SEASON:
            continue
        value = _int_value(getattr(candidate, "display_value", None))
        if value is None:
            continue
        candidates.append(candidate)
    return tuple(candidates)


def _attribute_total(candidates: Iterable[Any]) -> int | None:
    total = 0
    count = 0
    for candidate in candidates:
        value = _int_value(getattr(candidate, "display_value", None))
        if value is None:
            continue
        total += value
        count += 1
    if count == 0:
        return None
    return total


def _normalized_evidence_lookup(evidence_by_key: Mapping[tuple[str, str], Any]) -> dict[tuple[str, str], Any]:
    return {(_norm(left), _norm(right)): value for (left, right), value in evidence_by_key.items()}


def _proposal_identity(proposal: Any) -> tuple[str, str]:
    return (_norm(getattr(proposal, "player_id", "")), _norm(getattr(proposal, "team", "")))


def _proposal_season(proposal: Any) -> int | None:
    return _int_value(getattr(proposal, "season", None))


def _metric_sort_key(entry: AttributeRankEntry) -> tuple[float, int, str, str]:
    player_id, team = _proposal_identity(entry.proposal)
    return (-entry.metric_value, -entry.current_total, player_id, team)


def _float_value(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    number = _float_value(value)
    if number is None:
        return None
    return int(round(number))


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


__all__ = [
    "AttributeRankAdjustment",
    "AttributeRankAdjustmentResult",
    "align_attribute_totals_to_metric_ranks",
]
