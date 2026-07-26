from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PlayerEraContext:
    season: int
    league: str
    era_key: str
    three_point_line: str
    has_three_point_line: bool
    has_shortened_nba_three_point_line: bool
    expects_shooting_distance_data: bool
    expects_split_rebounds: bool
    expects_steals_and_blocks: bool
    expects_player_turnovers: bool
    expects_public_tracking: bool
    dunk_attempt_multiplier: float
    hard_foul_regime: str

    @property
    def evidence_keys(self) -> tuple[str, ...]:
        return (
            f"era_context={self.era_key}",
            f"league={self.league or 'UNKNOWN'}",
            f"three_point_line={self.three_point_line}",
            f"dunk_attempt_multiplier={self.dunk_attempt_multiplier:.2f}",
            f"hard_foul_regime={self.hard_foul_regime}",
        )


def player_era_context(evidence: Any) -> PlayerEraContext:
    season = int(getattr(evidence, "season", 0) or 0)
    season_info = getattr(evidence, "season_info", {})
    source_context = getattr(evidence, "source_context", {})
    league = _normalized_league(
        _dict_value(season_info, "lg")
        or _dict_value(source_context, "player_season_info.lg")
        or _dict_value(source_context, "lg")
    )

    aba_three = league == "ABA" and 1968 <= season <= 1976
    nba_three = league == "NBA" and season >= 1980
    shortened_nba_line = league == "NBA" and 1995 <= season <= 1997
    if aba_three:
        three_point_line = "aba_standard"
    elif shortened_nba_line:
        three_point_line = "nba_shortened_1995_1997"
    elif nba_three:
        three_point_line = "nba_standard"
    else:
        three_point_line = "none"

    return PlayerEraContext(
        season=season,
        league=league,
        era_key=_era_key(season, league),
        three_point_line=three_point_line,
        has_three_point_line=aba_three or nba_three,
        has_shortened_nba_three_point_line=shortened_nba_line,
        expects_shooting_distance_data=season >= 1997,
        expects_split_rebounds=(league == "NBA" and season >= 1974) or (league == "ABA" and season >= 1969),
        expects_steals_and_blocks=(league == "NBA" and season >= 1974) or (league == "ABA" and season >= 1973),
        expects_player_turnovers=(league == "NBA" and season >= 1978) or league == "ABA",
        expects_public_tracking=league == "NBA" and season >= 2014,
        dunk_attempt_multiplier=_dunk_attempt_multiplier(season),
        hard_foul_regime=_hard_foul_regime(season),
    )


def _dunk_attempt_multiplier(season: int) -> float:
    if season < 1950:
        return 0.15
    if season < 1960:
        return 0.30
    if season < 1970:
        return 0.65
    return 1.0


def _hard_foul_regime(season: int) -> str:
    if season < 1960:
        return "universal_maximum_pre_1960"
    if season < 1970:
        return "unspecified_1960s_use_player_evidence"
    if season < 1990:
        return "maximum_for_most_with_low_contact_exceptions"
    return "use_player_evidence"


def filter_same_league_rows(evidence: Any, rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    row_tuple = tuple(rows or ())
    league = player_era_context(evidence).league
    if not league:
        return row_tuple
    return tuple(row for row in row_tuple if _row_league(row) == league)


def _row_league(row: dict[str, Any]) -> str:
    for key in ("player_season_info.lg", "season_info.lg", "lg"):
        if key in row:
            return _normalized_league(row.get(key))
    return ""


def _dict_value(source: Any, key: str) -> Any:
    return source.get(key) if isinstance(source, dict) else None


def _normalized_league(value: Any) -> str:
    return str(value or "").strip().upper()


def _era_key(season: int, league: str) -> str:
    if season <= 1954:
        return "pre_shot_clock"
    if season <= 1964:
        return "shot_clock_twelve_foot_lane"
    if season <= 1967:
        return "sixteen_foot_lane_pre_aba"
    if league == "ABA" and season <= 1976:
        return "aba_three_point_era"
    if season <= 1976:
        return "nba_pre_merger_no_three"
    if season <= 1979:
        return "post_merger_pre_nba_three"
    if season <= 1988:
        return "early_nba_three"
    if season <= 1994:
        return "established_low_volume_three"
    if season <= 1997:
        return "shortened_nba_three"
    if season <= 2001:
        return "restored_line_late_nineties"
    if season <= 2004:
        return "defensive_rule_transition"
    if season <= 2012:
        return "perimeter_freedom_early_spacing"
    if season <= 2018:
        return "pace_and_space_expansion"
    return "high_volume_three_position_flexible"


__all__ = ["PlayerEraContext", "filter_same_league_rows", "player_era_context"]
