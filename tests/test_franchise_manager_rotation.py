from __future__ import annotations

import unittest

from nba2k_editor.franchise_manager import FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.rotation import build_rotation_plan, rotation_recommendations
from nba2k_editor.franchise_manager.transactions import recommend_team_transactions
from nba2k_editor.franchise_manager.world import build_team_context


class FranchiseManagerRotationTests(unittest.TestCase):
    def test_rebuild_rotation_opens_minutes_for_young_core_and_cuts_veteran_minutes(self) -> None:
        context = _rebuild_context()

        plan = build_rotation_plan(context, direction=TeamDirection.REBUILD)
        by_player = {item.player_id: item for item in plan.recommendations}

        self.assertGreaterEqual(by_player["kid"].recommended_minutes, 26)
        self.assertLess(by_player["vet"].recommended_minutes, 26)
        self.assertIn("development", by_player["kid"].reasons[0].lower())
        self.assertTrue(any("veteran" in warning.lower() for warning in plan.warnings))

    def test_contender_rotation_replaces_injured_star_minutes_with_depth(self) -> None:
        context = _contender_injury_context()

        plan = build_rotation_plan(context, direction=TeamDirection.CONTEND)
        by_player = {item.player_id: item for item in plan.recommendations}

        self.assertEqual("injured", by_player["star"].role)
        self.assertEqual(0, by_player["star"].recommended_minutes)
        self.assertGreater(by_player["depth"].recommended_minutes, by_player["depth"].current_minutes)
        self.assertTrue(any("injury" in warning.lower() for warning in plan.warnings))

    def test_morale_minutes_mismatch_generates_warning_and_priority(self) -> None:
        context = _morale_mismatch_context()

        plan = build_rotation_plan(context, direction=TeamDirection.EVALUATE)
        target = next(item for item in plan.recommendations if item.player_id == "unhappy")

        self.assertGreaterEqual(target.recommended_minutes, 24)
        self.assertGreaterEqual(target.priority, 70)
        self.assertIn("morale", " ".join(target.reasons).lower())

    def test_rotation_recommendations_return_rotation_only_items(self) -> None:
        context = _rebuild_context()

        items = rotation_recommendations(context, direction=TeamDirection.REBUILD)

        self.assertTrue(items)
        self.assertTrue(all(item.kind == "rotation" for item in items))
        self.assertIn("rotation_plan_priority", items[0].evidence)

    def test_transaction_recommendation_includes_rotation_plan_evidence(self) -> None:
        context = _contender_injury_context()

        rotation = next(item for item in recommend_team_transactions(context, TeamDirection.CONTEND) if item.kind == "rotation")

        self.assertIn("rotation_plan_priority", rotation.evidence)
        self.assertIn("top_rotation_action", rotation.evidence)
        self.assertGreater(rotation.evidence["rotation_plan_priority"], 0)


def _rebuild_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", rebuild_tolerance=90), GMProfile("GM", prospect_preference=90))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 18, "losses": 48, "expected_wins": 22}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {"players": [
                    {"player_id": "vet", "team_id": "SEA", "name": "Expensive Vet", "age": 34, "overall": 80, "potential": 80, "minutes": 33, "morale": 49},
                    {"player_id": "kid", "team_id": "SEA", "name": "Young Guard", "age": 21, "overall": 74, "potential": 88, "minutes": 16, "morale": 66, "development": 5},
                    {"player_id": "bench", "team_id": "SEA", "name": "Bench Wing", "age": 25, "overall": 72, "potential": 76, "minutes": 14, "morale": 55},
                ]},
            ),
        ),
    )


def _contender_injury_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner"), GMProfile("GM"))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 53, "losses": 29, "expected_wins": 56}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {"players": [
                    {"player_id": "star", "team_id": "SEA", "name": "Star Guard", "age": 29, "overall": 93, "potential": 93, "minutes": 36, "morale": 75},
                    {"player_id": "starter", "team_id": "SEA", "name": "Starter Wing", "age": 28, "overall": 82, "potential": 82, "minutes": 31, "morale": 65},
                    {"player_id": "depth", "team_id": "SEA", "name": "Depth Guard", "age": 26, "overall": 76, "potential": 77, "minutes": 12, "morale": 58},
                ]},
            ),
            ImportedSnapshot(2026, None, ImportedDataKind.INJURIES, {"injuries": [{"player_id": "star", "team_id": "SEA", "severity": 80, "games_remaining": 10, "description": "knee"}]}),
        ),
    )


def _morale_mismatch_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner"), GMProfile("GM"))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 37, "losses": 35, "expected_wins": 38}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {"players": [
                    {"player_id": "unhappy", "team_id": "SEA", "name": "Unhappy Sixth", "age": 27, "overall": 79, "potential": 80, "minutes": 15, "morale": 32},
                    {"player_id": "starter", "team_id": "SEA", "name": "Starter", "age": 28, "overall": 84, "potential": 84, "minutes": 34, "morale": 70},
                    {"player_id": "depth", "team_id": "SEA", "name": "Depth", "age": 25, "overall": 71, "potential": 74, "minutes": 12, "morale": 55},
                ]},
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
