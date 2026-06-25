from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nba2k_editor.franchise_manager import FranchiseStore, FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.world import DraftPickAsset, FranchisePlayer, InjuryStatus, PlayerContract


class FranchiseManagerStoreWorldStateTests(unittest.TestCase):
    def test_store_round_trips_persistent_world_state_by_season_and_team(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                store.upsert_franchise_players(
                    2026,
                    (
                        FranchisePlayer("p1", "SEA", name="Primary Star", age=28, overall=91, potential=92, minutes=35, morale=72, development=1, position="SG"),
                        FranchisePlayer("p2", "SEA", name="Bench Big", age=24, overall=75, potential=83, minutes=18, morale=61, development=4, position="C"),
                        FranchisePlayer("p3", "POR", name="Other Team", age=30, overall=80),
                    ),
                )
                store.upsert_contracts(
                    2026,
                    (
                        PlayerContract("p1", "SEA", salary=42_000_000, years_remaining=3),
                        PlayerContract("p2", "SEA", salary=8_000_000, years_remaining=2),
                    ),
                )
                store.upsert_draft_picks(
                    2026,
                    (
                        DraftPickAsset("SEA", 2027, round=1, protection="top 4"),
                        DraftPickAsset("SEA", 2028, round=2),
                        DraftPickAsset("POR", 2027, round=1),
                    ),
                )
                store.upsert_injuries(2026, (InjuryStatus("p1", "SEA", severity=55, games_remaining=6, description="ankle"),))
                store.upsert_team_finances(2026, "SEA", payroll=50_000_000, salary_cap=141_000_000, luxury_tax_line=171_000_000, budget=185_000_000)
                tx_id = store.add_transaction(2026, "SEA", "trade", {"description": "Acquired defensive wing", "teams": ["SEA", "DAL"]})

                self.assertGreater(tx_id, 0)
                self.assertEqual(("p1", "p2"), tuple(player.player_id for player in store.list_franchise_players(season=2026, team_id="SEA")))
                self.assertEqual(("p1", "p2"), tuple(contract.player_id for contract in store.list_contracts(season=2026, team_id="SEA")))
                self.assertEqual((2027, 2028), tuple(pick.year for pick in store.list_draft_picks(season=2026, team_id="SEA")))
                self.assertEqual(("p1",), tuple(injury.player_id for injury in store.list_injuries(season=2026, team_id="SEA")))
                self.assertEqual(50_000_000, store.list_team_finances(season=2026, team_id="SEA")["payroll"])
                self.assertEqual("Acquired defensive wing", store.list_transactions(season=2026, team_id="SEA")[0]["description"])
            finally:
                store.close()

    def test_team_context_can_be_built_from_persisted_world_state(self) -> None:
        team = FranchiseTeam(
            team_id="SEA",
            display_name="Seattle Supersonics",
            owner=OwnerProfile(name="Owner", patience=38, championship_expectations=88, spending_willingness=40, market_pressure_sensitivity=80),
            gm=GMProfile(name="GM", aggression=82, trade_frequency=70),
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                store.add_team(team)
                store.import_2k_data(ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 50, "losses": 32, "expected_wins": 56, "market_pressure": 86}}))
                store.upsert_franchise_players(
                    2026,
                    (
                        FranchisePlayer("star", "SEA", name="Franchise Star", age=29, overall=94, potential=95, minutes=36, morale=76),
                        FranchisePlayer("kid", "SEA", name="Development Guard", age=21, overall=73, potential=86, minutes=16, morale=64, development=5),
                    ),
                )
                store.upsert_contracts(
                    2026,
                    (
                        PlayerContract("star", "SEA", salary=57_000_000, years_remaining=3),
                        PlayerContract("kid", "SEA", salary=5_000_000, years_remaining=3),
                        PlayerContract("exp", "SEA", salary=114_000_000, years_remaining=1, expiring=True),
                    ),
                )
                store.upsert_draft_picks(2026, (DraftPickAsset("SEA", 2027, round=1), DraftPickAsset("SEA", 2029, round=1, protection="top 8")))
                store.upsert_injuries(2026, (InjuryStatus("star", "SEA", severity=70, games_remaining=9, description="back"),))
                store.upsert_team_finances(2026, "SEA", payroll=176_000_000, salary_cap=141_000_000, luxury_tax_line=171_000_000)
                store.add_transaction(2026, "SEA", "trade", {"description": "Moved second for veteran center"})

                context = store.build_team_context(season=2026, team=team)
                evaluation = store.evaluate_all_teams(2026)[0]
            finally:
                store.close()

        self.assertEqual((50, 32), (context.record.wins, context.record.losses))
        self.assertEqual(56, context.record.expected_wins)
        self.assertEqual(94, context.roster.star_quality)
        self.assertEqual(1, context.injuries.active_count)
        self.assertEqual(2, context.draft_assets.future_firsts)
        self.assertGreater(context.cap.payroll, context.cap.luxury_tax_line)
        self.assertEqual(1, context.recent_transactions.count)
        self.assertEqual(TeamDirection.CONTEND, evaluation.direction)
        self.assertIn("luxury", " | ".join(evaluation.recommended_actions).lower())


if __name__ == "__main__":
    unittest.main()
