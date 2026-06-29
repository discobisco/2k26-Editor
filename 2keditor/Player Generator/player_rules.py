from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from player_evidence import PlayerEvidence
from stat_neighbor_framework import hot_zone_neutral_values, load_latest_stat_neighbor_model, select_positions_from_evidence


@dataclass(frozen=True)
class ProfileValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class RuleValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerProfileResult:
    values: dict[str, ProfileValue]


@dataclass(frozen=True)
class PlayerRuleResult:
    values: dict[str, RuleValue]


def derive_player_profile_values(evidence: PlayerEvidence) -> PlayerProfileResult:
    values: dict[str, ProfileValue] = {}
    first, last = _split_name(evidence.identity.get("player") or evidence.season_info.get("player") or evidence.player_id)
    _add_profile(values, "Vitals/FIRSTNAME", first, "profile_sql_identity", "player_info.player")
    _add_profile(values, "Vitals/LASTNAME", last, "profile_sql_identity", "player_info.player")

    height = _int_round(evidence.identity.get("ht_in_in"))
    weight = _int_round(evidence.identity.get("wt"))
    _add_profile(values, "Vitals/HEIGHT", height, "profile_sql_bio", "player_info.ht_in_in")
    _add_profile(values, "Vitals/WEIGHT", weight, "profile_sql_bio", "player_info.wt")

    positions = select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    _add_profile(values, "Vitals/POSITION", positions.primary, "profile_sql_position_percent", "play_by_play.position_percent")
    if positions.secondary:
        _add_profile(values, "Vitals/SECONDARYPOSITION", positions.secondary, "profile_sql_position_percent", "play_by_play.position_percent")

    birth = _birth_date_from_source(evidence.identity.get("birth_date"))
    if birth:
        _add_profile(values, "Vitals/BIRTHYEAR", birth.year, "profile_sql_birth_date", "player_info.birth_date")
        _add_profile(values, "Vitals/BIRTHMONTH", birth.month, "profile_sql_birth_date", "player_info.birth_date")
        _add_profile(values, "Vitals/BIRTHDAY", birth.day, "profile_sql_birth_date", "player_info.birth_date")
    elif (age := _int_round(evidence.season_info.get("age"))) is not None:
        _add_profile(values, "Vitals/BIRTHYEAR", int(evidence.season) - age, "profile_sql_age_estimate", "season_info.age")

    draft_year = _int_round(_source_value(evidence, "draft_picks.season", "draft.season"))
    draft_round = _int_round(_source_value(evidence, "draft_picks.round", "draft.round"))
    draft_pick = _int_round(_source_value(evidence, "draft_picks.overall_pick", "draft.overall_pick"))
    _add_profile(values, "Vitals/DRAFTYEAR", draft_year, "profile_sql_draft", "draft_picks.season")
    _add_profile(values, "Vitals/DRAFTEDYEAR", draft_year, "profile_sql_draft", "draft_picks.season")
    _add_profile(values, "Vitals/DRAFTROUND", draft_round, "profile_sql_draft", "draft_picks.round")
    _add_profile(values, "Vitals/DRAFTPICKNUMBER", draft_pick, "profile_sql_draft", "draft_picks.overall_pick")
    _add_profile(values, "Vitals/DRAFTPICK", draft_pick, "profile_sql_draft", "draft_picks.overall_pick")
    return PlayerProfileResult(values=values)


def derive_player_rule_values(evidence: PlayerEvidence) -> PlayerRuleResult:
    positions = select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    if not positions.primary:
        return PlayerRuleResult(values={})

    model = load_latest_stat_neighbor_model()
    suggestions = model.suggestions_for_evidence(evidence=evidence, position=positions.primary)
    values: dict[str, RuleValue] = {
        key: RuleValue(value=suggestion.value, source_rule=suggestion.source_rule, evidence_keys=suggestion.evidence_keys)
        for key, suggestion in suggestions.items()
    }
    for key, suggestion in hot_zone_neutral_values().items():
        values.setdefault(key, RuleValue(value=suggestion.value, source_rule=suggestion.source_rule, evidence_keys=suggestion.evidence_keys))
    return PlayerRuleResult(values=values)


def _add_profile(values: dict[str, ProfileValue], key: str, value: object, source_rule: str, *evidence_keys: str) -> None:
    if value is None or value == "":
        return
    if isinstance(value, (int, str)):
        stored: int | str = value
    else:
        rounded = _int_round(value)
        stored = rounded if rounded is not None else str(value)
    values[key] = ProfileValue(value=stored, source_rule=source_rule, evidence_keys=tuple(evidence_keys))


def _split_name(value: object) -> tuple[str, str]:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "", ""
    parts = text.split(" ")
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def _birth_date_from_source(value: object) -> datetime | None:
    number = _float(value)
    if number is None:
        return None
    # NBA_DATA_Master stores Excel serial dates in player_info.birth_date.
    return datetime(1899, 12, 30) + timedelta(days=int(number))


def _source_value(evidence: PlayerEvidence, *keys: str) -> object:
    for key in keys:
        if key in evidence.source_context:
            return evidence.source_context[key]
    return None


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_round(value: object) -> int | None:
    number = _float(value)
    if number is None:
        return None
    return int(round(number))


__all__ = [
    "PlayerProfileResult",
    "PlayerRuleResult",
    "ProfileValue",
    "RuleValue",
    "derive_player_profile_values",
    "derive_player_rule_values",
]
