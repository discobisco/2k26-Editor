from __future__ import annotations

import sys
from pathlib import Path


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_special_rules import (  # type: ignore[import-not-found]
    RESEARCHED_DEFENSE_QUALITY_RULES,
    researched_defense_quality_rule_for,
)


def test_mikan_defense_override_is_registered_by_exact_source_identity() -> None:
    rule = researched_defense_quality_rule_for(
        season=1947,
        league="nbl",
        player_id="mikange01",
        team="cag",
    )

    assert rule is RESEARCHED_DEFENSE_QUALITY_RULES[0]
    assert rule.quality_score == 1.0
    assert rule.expected_values_by_field == {
        "Attributes/INTERIORDEFENSE": 99,
        "Attributes/PERIMETERDEFENSE": 36,
    }
    assert "researched_player_id=MIKANGE01" in rule.provenance_evidence_keys
    assert "research_scope=exact_player_exact_team_exact_season_exact_league" in rule.provenance_evidence_keys


def test_special_player_rule_does_not_match_a_different_source_record() -> None:
    exact = {"season": 1947, "league": "NBL", "player_id": "MIKANGE01", "team": "CAG"}
    for key, different in (
        ("season", 1948),
        ("league", "BAA"),
        ("player_id", "OTHER01"),
        ("team", "MNL"),
    ):
        candidate = dict(exact)
        candidate[key] = different
        assert researched_defense_quality_rule_for(**candidate) is None
