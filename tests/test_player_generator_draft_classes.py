from __future__ import annotations

import sys
import unittest
from collections import Counter
from importlib import import_module
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = REPO_ROOT / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

player_generator = import_module("player_generator")
contracts = import_module("contracts")
DraftClassMode = player_generator.DraftClassMode


class PlayerGeneratorDraftClassTests(unittest.TestCase):
    def test_draft_pick_mode_uses_draft_order_and_metadata(self) -> None:
        draft_class = player_generator.generate_draft_class_proposals(1984, mode=DraftClassMode.DRAFT_PICKS)

        self.assertEqual(1984, draft_class.draft_year)
        self.assertEqual(1985, draft_class.rookie_season)
        self.assertEqual(DraftClassMode.DRAFT_PICKS, draft_class.mode)
        self.assertGreaterEqual(len(draft_class.proposals), 12)
        self.assertEqual(
            ["olajuha01", "bowiesa01", "jordami01", "perkisa01", "barklch01"],
            [proposal.player_id for proposal in draft_class.proposals[:5]],
        )
        jordan = draft_class.proposals[2]
        self.assertEqual("Michael Jordan", jordan.identity["player"])
        self.assertEqual(3, jordan.identity["draft_overall_pick"])
        self.assertEqual(1, jordan.identity["draft_round"])
        self.assertEqual("CHI", jordan.identity["draft_team"])
        self.assertEqual("draft_picks", jordan.identity["draft_class_mode"])

    def test_rookie_year_mode_uses_players_whose_rookie_year_matches(self) -> None:
        draft_pick_class = player_generator.generate_draft_class_proposals(1984, mode=DraftClassMode.DRAFT_PICKS)
        rookie_year_class = player_generator.generate_draft_class_proposals(1984, mode=DraftClassMode.ROOKIE_YEAR)

        self.assertEqual(DraftClassMode.ROOKIE_YEAR, rookie_year_class.mode)
        self.assertEqual("rookie_year", rookie_year_class.proposals[0].identity["draft_class_mode"])
        draft_pick_ids = {proposal.player_id for proposal in draft_pick_class.proposals}
        rookie_year_ids = {proposal.player_id for proposal in rookie_year_class.proposals}
        self.assertGreater(len(rookie_year_ids), 0)
        self.assertNotEqual(draft_pick_ids, rookie_year_ids)
        self.assertIn("jordami01", rookie_year_ids)
        self.assertNotIn("abdulka01", rookie_year_ids)

    def test_1947_tot_rows_collapse_to_one_context_key_per_player(self) -> None:
        context = player_generator.season_context_index(
            contracts.GeneratorInputContract(
                season=1947,
                source_root=GENERATOR_DIR / "NBA Player Data",
                output_target=contracts.OutputTarget.PREVIEW,
            )
        )

        player_id_counts = Counter(player_id for player_id, _team in context.player_keys())

        self.assertEqual([], [player_id for player_id, count in player_id_counts.items() if count > 1])
        self.assertEqual(("GRENEAL01N", "TCB"), next(key for key in context.player_keys() if key[0] == "GRENEAL01N"))


if __name__ == "__main__":
    unittest.main()
