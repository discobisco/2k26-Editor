from __future__ import annotations

import inspect
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from player_evidence import PlayerEvidence
from player_rules import ATTRIBUTE_FIELDS, PROFILE_FIELDS, TENDENCY_FIELDS, derive_player_profile_values, derive_player_rule_values


OFFSETS_PLAYERS_PATH = Path(__file__).resolve().parents[1] / "nba2k_editor" / "core" / "Offsets" / "offsets_players.json"


def _authored_rule_fields(domain: str) -> set[str]:
    payload = json.loads(OFFSETS_PLAYERS_PATH.read_text(encoding="utf-8"))
    return {f"{domain}/{row['normalized_name']}" for rows in payload["Players"][domain].values() for row in rows}


def _evidence(**overrides: object) -> PlayerEvidence:
    base = PlayerEvidence(
        player_id="player01",
        season=2025,
        team="NYK",
        identity={
            "player": "Rule Test",
            "player_id": "player01",
            "pos": "G",
            "ht_in_in": 75,
            "wt": 195,
            "colleges": "Memphis",
            "from": 2021,
        },
        season_info={"player_id": "player01", "team": "NYK", "pos": "G", "experience": 4},
        per_game={
            "pts_per_game": 20.0,
            "trb_per_game": 5.0,
            "ast_per_game": 6.0,
            "stl_per_game": 1.4,
            "blk_per_game": 0.5,
            "x3p_percent": 0.390,
            "x3pa_per_game": 7.0,
            "ft_percent": 0.850,
            "fg_percent": 0.470,
        },
        per_100={"pts_per_100_poss": 31.0, "ast_per_100_poss": 9.0, "trb_per_100_poss": 7.0},
        advanced={"ts_percent": 0.600, "usg_percent": 27.0, "per": 20.0},
        shooting={"percent_fga_from_x0_3_range": 0.20, "percent_dunks_of_fga": 0.04, "num_of_dunks": 18},
        play_by_play={"pg_percent": 70, "sg_percent": 30},
        team_roster=(
            {"player_id": "player01", "team": "NYK", "season": 2025, "player": "Rule Test"},
            {"player_id": "player02", "team": "NYK", "season": 2025, "player": "Teammate"},
        ),
        team_stats_per_game={"abbreviation": "NYK", "pts_per_game": 117.0, "x3pa_per_game": 37.0},
        team_stats_per_100={"abbreviation": "NYK", "pts_per_100_poss": 119.0},
        team_summary={"abbreviation": "NYK", "o_rtg": 119.0, "d_rtg": 112.0, "pace": 99.0},
        opponent_stats_per_game={"abbreviation": "NYK", "opp_pts_per_game": 112.0},
        opponent_stats_per_100={"abbreviation": "NYK", "opp_pts_per_100_poss": 112.0},
        missing_sources=(),
    )
    return replace(base, **overrides)


class PlayerRulesTests(unittest.TestCase):
    def test_rule_field_sets_match_all_authored_attributes_and_tendencies(self) -> None:
        self.assertEqual(ATTRIBUTE_FIELDS, _authored_rule_fields("Attributes"))
        self.assertEqual(TENDENCY_FIELDS, _authored_rule_fields("Tendencies"))
        self.assertEqual(len(ATTRIBUTE_FIELDS), 62)
        self.assertEqual(len(TENDENCY_FIELDS), 120)

    def test_modern_evidence_generates_every_authored_attribute_and_tendency(self) -> None:
        result = derive_player_rule_values(_evidence())

        self.assertEqual(set(result.values), ATTRIBUTE_FIELDS | TENDENCY_FIELDS)
        self.assertEqual(result.skipped, {})

    def test_profile_values_include_height_weight_name_position_and_from_context(self) -> None:
        result = derive_player_profile_values(_evidence())

        self.assertEqual(set(result.values), PROFILE_FIELDS)
        self.assertEqual(result.values["Vitals/FIRSTNAME"].value, "Rule")
        self.assertEqual(result.values["Vitals/LASTNAME"].value, "Test")
        self.assertEqual(result.values["Vitals/HEIGHT"].value, 75)
        self.assertEqual(result.values["Vitals/HEIGHTCM"].value, 191)
        self.assertEqual(result.values["Vitals/WEIGHT"].value, 195)
        self.assertEqual(result.values["Vitals/WEIGHTKG"].value, 88)
        self.assertEqual(result.values["Vitals/POSITION"].value, "G")
        self.assertEqual(result.values["Vitals/COLLEGEFROM"].value, "Memphis")
        self.assertEqual(result.values["Vitals/YEARSPRO"].value, 4)
        self.assertEqual(result.skipped, {})

    def test_profile_position_falls_back_to_player_info_when_season_position_is_blank(self) -> None:
        result = derive_player_profile_values(_evidence(season_info={"player_id": "player01", "team": "NYK", "pos": None, "experience": 4}))

        self.assertEqual(result.values["Vitals/POSITION"].value, "G")

    def test_profile_college_from_does_not_fall_back_to_debut_year(self) -> None:
        result = derive_player_profile_values(_evidence(identity={"player": "Rule Test", "player_id": "player01", "pos": "G", "ht_in_in": 75, "wt": 195, "colleges": None, "from": 2021}))

        self.assertNotIn("Vitals/COLLEGEFROM", result.values)
        self.assertEqual(result.skipped["Vitals/COLLEGEFROM"], "missing required profile evidence")
        self.assertEqual(result.values["Vitals/YEARSPRO"].value, 4)

    def test_identical_evidence_returns_identical_values(self) -> None:
        evidence = _evidence()
        league_rows = [
            {"pts_per_game": 8.0, "x3p_percent": 0.300, "x3pa_per_game": 1.0, "ft_percent": 0.650, "trb_per_game": 3.0, "ast_per_game": 1.0},
            {"pts_per_game": 28.0, "x3p_percent": 0.420, "x3pa_per_game": 9.0, "ft_percent": 0.910, "trb_per_game": 8.0, "ast_per_game": 9.0},
        ]

        first = derive_player_rule_values(evidence, league_player_rows=league_rows)
        second = derive_player_rule_values(evidence, league_player_rows=league_rows)

        self.assertEqual(first, second)
        self.assertEqual(first.values["Attributes/3POINT"].source_rule, "attribute_3point_v1")
        self.assertEqual(first.values["Attributes/3POINT"].field, "3POINT")
        self.assertEqual(first.values["Attributes/3POINT"].domain, "Attributes")
        self.assertEqual(first.skipped, {})

    def test_generated_values_stay_in_editor_display_ranges(self) -> None:
        result = derive_player_rule_values(_evidence(), league_player_rows=[])

        self.assertGreaterEqual(set(result.values), ATTRIBUTE_FIELDS | TENDENCY_FIELDS)
        for field in ATTRIBUTE_FIELDS:
            self.assertGreaterEqual(result.values[field].value, 25)
            self.assertLessEqual(result.values[field].value, 99)
        for field in TENDENCY_FIELDS:
            self.assertGreaterEqual(result.values[field].value, 0)
            self.assertLessEqual(result.values[field].value, 100)

    def test_changed_player_evidence_changes_derived_values(self) -> None:
        base = derive_player_rule_values(_evidence())
        changed = derive_player_rule_values(
            _evidence(
                per_game={**_evidence().per_game, "x3p_percent": 0.250, "x3pa_per_game": 1.0, "pts_per_game": 8.0},
                advanced={**_evidence().advanced, "usg_percent": 12.0, "ts_percent": 0.480},
            )
        )

        self.assertNotEqual(base.values["Attributes/3POINT"].value, changed.values["Attributes/3POINT"].value)
        self.assertNotEqual(base.values["Tendencies/TOUCHES"].value, changed.values["Tendencies/TOUCHES"].value)
        self.assertNotEqual(base.values["Attributes/OFFENSIVECONSISTENCY"].value, changed.values["Attributes/OFFENSIVECONSISTENCY"].value)

    def test_changed_team_context_changes_offensive_consistency_attribute(self) -> None:
        base = derive_player_rule_values(_evidence())
        changed = derive_player_rule_values(_evidence(team_summary={"abbreviation": "NYK", "o_rtg": 92.0, "d_rtg": 120.0, "pace": 94.0}))

        self.assertNotEqual(base.values["Attributes/OFFENSIVECONSISTENCY"].value, changed.values["Attributes/OFFENSIVECONSISTENCY"].value)

    def test_missing_modern_sources_skip_unsupported_formulas_without_fabricating_values(self) -> None:
        evidence = _evidence(
            per_100={},
            shooting={},
            play_by_play={},
            per_game={**_evidence().per_game, "x3p_percent": None, "x3pa_per_game": None},
            missing_sources=("Player Shooting", "Player Play by Play"),
        )

        result = derive_player_rule_values(evidence)

        self.assertNotIn("Attributes/3POINT", result.values)
        self.assertNotIn("Tendencies/3POINTSHOT", result.values)
        self.assertIn("Attributes/3POINT", result.skipped)
        self.assertIn("Tendencies/3POINTSHOT", result.skipped)

    def test_player_rules_module_has_no_random_excel_or_live_memory_dependency(self) -> None:
        import player_rules

        source = inspect.getsource(player_rules)
        for banned in ("import random", "openpyxl", "pandas", "xlrd", "xlsxwriter", "GameMemory"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
