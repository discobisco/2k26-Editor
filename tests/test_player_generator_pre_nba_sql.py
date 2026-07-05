from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = PROJECT_ROOT / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from contracts import GeneratorInputContract, OutputTarget
from display import load_generator_display_state, update_generator_display_selection
from player_generator import generate_player_proposals_from_index, season_context_index
from pre_nba_source import pre_nba_database_available, pre_nba_seasons


class PlayerGeneratorPreNbaSqlTests(unittest.TestCase):
    def test_pre_nba_sql_seasons_are_available_to_generator_display(self) -> None:
        source_root = GENERATOR_DIR / "NBA Player Data"
        self.assertTrue(pre_nba_database_available(source_root))
        self.assertIn(1942, pre_nba_seasons(source_root))
        self.assertIn(1895, pre_nba_seasons(source_root))

        state = load_generator_display_state(selected_season=1942)

        self.assertEqual("1942", state.selected_season)
        self.assertIn("ABERDEEN ARMY ORDNANCE", state.source_team_filters)
        self.assertGreater(len(state.players), 0)

    def test_pre_nba_sql_builds_sparse_generator_context(self) -> None:
        source_root = GENERATOR_DIR / "NBA Player Data"
        context = season_context_index(GeneratorInputContract(1942, source_root, OutputTarget.PREVIEW))

        self.assertEqual(1942, context.season)
        self.assertGreater(len(context.player_keys()), 0)
        self.assertIn("ABERDEEN ARMY ORDNANCE", {team for _player_id, team in context.player_keys()})

        state = load_generator_display_state(selected_season=1942)
        state = update_generator_display_selection(state, selected_source_team="ABERDEEN ARMY ORDNANCE")
        batch = generate_player_proposals_from_index(context, team_filter="ABERDEEN ARMY ORDNANCE")

        self.assertEqual(len(state.players), len(batch.proposals))
        self.assertGreater(len(batch.proposals[0].field_candidates), 0)
        first_key = context.player_keys(team_filter="ABERDEEN ARMY ORDNANCE")[0]
        self.assertEqual("pre_nba.sqlite", context.evidence_for(player_id=first_key[0], team=first_key[1]).source_context.get("source"))
        self.assertEqual("pre_nba.sqlite", batch.proposals[0].identity.get("source"))

    def test_all_players_xlsx_extends_pre_nba_context_with_bio_rows(self) -> None:
        source_root = GENERATOR_DIR / "NBA Player Data"
        context = season_context_index(GeneratorInputContract(1896, source_root, OutputTarget.PREVIEW))

        evidence = context.evidence_for(player_id="$ABADIEBO0001", team="NEW YORK 23RD ST. YMCA")

        self.assertEqual("Bob Abadie", evidence.identity.get("player"))
        self.assertEqual("Feb 19, 1876", evidence.identity.get("born"))
        self.assertEqual("New York, NY", evidence.identity.get("home_town"))
        self.assertEqual("pre_nba.sqlite", evidence.source_context.get("source"))
        self.assertIn("pre_nba_all_players.statistics_and_history_summary", evidence.source_context)


if __name__ == "__main__":
    unittest.main()
