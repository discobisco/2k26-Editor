from __future__ import annotations

"""Exact-identity special Player Generator rules.

Every entry is keyed by season, league, source player ID, and source team.
Names are intentionally excluded because they are display-only and do not identify
records. Formula modules consume this registry; they do not own player exceptions.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SpecialPlayerIdentity:
    season: int
    league: str
    player_id: str
    team: str

    @property
    def lookup_key(self) -> tuple[int, str, str, str]:
        return (self.season, self.league, self.player_id, self.team)


@dataclass(frozen=True)
class ResearchedDefenseQualityRule:
    identity: SpecialPlayerIdentity
    quality_score: float
    research_source: str
    expected_field_values: tuple[tuple[str, int], ...]

    @property
    def provenance_evidence_keys(self) -> tuple[str, ...]:
        return (
            f"researched_player_id={self.identity.player_id}",
            f"researched_team={self.identity.team}",
            f"researched_defense_quality={self.quality_score:.8f}",
            f"research_source={self.research_source}",
            "research_scope=exact_player_exact_team_exact_season_exact_league",
        )

    @property
    def expected_values_by_field(self) -> Mapping[str, int]:
        return MappingProxyType(dict(self.expected_field_values))


RESEARCHED_DEFENSE_QUALITY_RULES: tuple[ResearchedDefenseQualityRule, ...] = (
    ResearchedDefenseQualityRule(
        identity=SpecialPlayerIdentity(
            season=1947,
            league="NBL",
            player_id="MIKANGE01",
            team="CAG",
        ),
        quality_score=1.0,
        research_source="https://probasketballencyclopedia.com/seasons/1946-1947/",
        expected_field_values=(
            ("Attributes/INTERIORDEFENSE", 99),
            ("Attributes/PERIMETERDEFENSE", 36),
        ),
    ),
)

_RESEARCHED_DEFENSE_QUALITY_RULE_BY_IDENTITY = MappingProxyType(
    {rule.identity.lookup_key: rule for rule in RESEARCHED_DEFENSE_QUALITY_RULES}
)


def researched_defense_quality_rule_for(
    *,
    season: int,
    league: str,
    player_id: str,
    team: str,
) -> ResearchedDefenseQualityRule | None:
    key = (
        int(season),
        str(league or "").strip().upper(),
        str(player_id or "").strip().upper(),
        str(team or "").strip().upper(),
    )
    return _RESEARCHED_DEFENSE_QUALITY_RULE_BY_IDENTITY.get(key)


__all__ = [
    "RESEARCHED_DEFENSE_QUALITY_RULES",
    "ResearchedDefenseQualityRule",
    "SpecialPlayerIdentity",
    "researched_defense_quality_rule_for",
]
