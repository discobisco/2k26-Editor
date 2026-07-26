from __future__ import annotations

import sys
from pathlib import Path


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import derive_formula_rule_values  # type: ignore[import-not-found]


def _empty_evidence() -> PlayerEvidence:
    return PlayerEvidence(
        player_id="fixed-rule-test",
        season=2025,
        team="TST",
        identity={},
        season_info={},
        per_game={},
        totals={},
        per_36={},
        per_100={},
        advanced={},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )


def test_fixed_rule_is_not_rejected_by_provenance_only_evidence_key() -> None:
    values = derive_formula_rule_values(
        _empty_evidence(),
        league_player_rows=({},),
    )

    back = values["Attributes/BACKDURABILITY"]
    assert back.value == 90
    assert back.source_rule == "derive_attribute_backdurability"
    assert back.evidence_keys == ("durability.default_90_pending_injury_database",)
