from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nba2k_editor.franchise_manager import FranchiseStore, FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.ai import evaluate_team_at_stop
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.transactions import recommend_team_transactions
from nba2k_editor.franchise_manager.world import build_team_context


class FranchiseManagerWorldEngineTests(unittest.TestCase):
    def test_team_context_uses_roster_contracts_injuries_draft_assets_and_recent_transactions(self) -> None:
        team = FranchiseTeam(
            team_id="BOS",
            display_name="Boston Celtics",
            owner=OwnerProfile(name="Owner", patience=40, championship_expectations=85, spending_willingness=35, market_pressure_sensitivity=75),
            gm=GMProfile(name="GM", aggression=80, trade_frequency=75, contract_discipline=35, prospect_preference=30),
        )
        snapshots = _rich_boston_snapshots()

        context = build_team_context(season=2026, team=team, snapshots=snapshots)

        self.assertEqual((52, 30), (context.record.wins, context.record.losses))
        self.assertEqual(58, context.record.expected_wins)
        self.assertGreater(context.roster.star_quality, 88)
        self.assertGreater(context.roster.average_age, 28)
        self.assertEqual(1, context.injuries.active_count)
        self.assertGreater(context.cap.payroll, context.cap.luxury_tax_line)
        self.assertGreater(context.draft_assets.future_firsts, 1)
        self.assertEqual(1, context.recent_transactions.count)

    def test_evaluation_is_context_driven_not_just_win_loss_record(self) -> None:
        team = FranchiseTeam(
            team_id="BOS",
            display_name="Boston Celtics",
            owner=OwnerProfile(name="Owner", patience=35, championship_expectations=90, spending_willingness=30, market_pressure_sensitivity=80),
            gm=GMProfile(name="GM", aggression=85, trade_frequency=80, contract_discipline=30, prospect_preference=25),
        )

        evaluation = evaluate_team_at_stop(season=2026, team=team, snapshots=_rich_boston_snapshots())

        self.assertEqual(TeamDirection.CONTEND, evaluation.direction)
        joined_actions = " | ".join(evaluation.recommended_actions).lower()
        self.assertIn("luxury", joined_actions)
        self.assertIn("injury", joined_actions)
        self.assertIn("veteran", joined_actions)
        owner_evidence = evaluation.reason_logs[0].evidence
        gm_evidence = evaluation.reason_logs[1].evidence
        for key in ("expected_wins", "roster_average_age", "star_quality", "active_injuries", "payroll", "luxury_tax_line", "future_firsts", "recent_transactions"):
            self.assertIn(key, owner_evidence)
        self.assertIn("asset_score", gm_evidence)
        self.assertIn("cap_space", gm_evidence)

    def test_transaction_engine_ranks_trade_free_agency_roster_and_rotation_actions(self) -> None:
        team = FranchiseTeam(
            team_id="ORL",
            display_name="Orlando Magic",
            owner=OwnerProfile(name="Owner", rebuild_tolerance=85, patience=70, spending_willingness=55),
            gm=GMProfile(name="GM", prospect_preference=85, draft_skill=80, aggression=45, trade_frequency=45),
        )
        snapshots = (
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"ORL": {"wins": 18, "losses": 42, "expected_wins": 24}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {
                    "players": [
                        {"player_id": "vet1", "team_id": "ORL", "name": "Expensive Vet", "age": 34, "overall": 79, "potential": 79, "minutes": 31, "morale": 45, "development": -2},
                        {"player_id": "kid1", "team_id": "ORL", "name": "Young Guard", "age": 21, "overall": 74, "potential": 88, "minutes": 17, "morale": 62, "development": 5},
                    ]
                },
            ),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.CONTRACTS,
                {
                    "salary_cap": 141_000_000,
                    "luxury_tax_line": 171_000_000,
                    "contracts": [
                        {"player_id": "vet1", "team_id": "ORL", "salary": 34_000_000, "years_remaining": 2, "expiring": False},
                        {"player_id": "kid1", "team_id": "ORL", "salary": 6_000_000, "years_remaining": 3, "expiring": False},
                    ],
                    "draft_picks": [
                        {"team_id": "ORL", "year": 2027, "round": 1, "protection": "top 5"},
                        {"team_id": "ORL", "year": 2028, "round": 1},
                    ],
                },
            ),
        )
        context = build_team_context(season=2026, team=team, snapshots=snapshots)

        recommendations = recommend_team_transactions(context)
        by_kind = {item.kind: item for item in recommendations}

        self.assertIn("trade", by_kind)
        self.assertIn("rotation", by_kind)
        self.assertIn("free_agency", by_kind)
        self.assertIn("draft", by_kind)
        self.assertIn("veteran", by_kind["trade"].message.lower())
        self.assertIn("Young Guard", by_kind["rotation"].message)

    def test_store_creates_franchise_world_tables_for_persistent_backend_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                table_names = {
                    row[0]
                    for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
            finally:
                store.close()

        for table_name in (
            "franchise_players",
            "franchise_contracts",
            "franchise_draft_picks",
            "franchise_transactions",
            "franchise_injuries",
            "team_finances",
            "staff_profiles",
            "facility_profiles",
            "franchise_objectives",
            "franchise_events",
            "playoff_brackets",
        ):
            self.assertIn(table_name, table_names)


def _rich_boston_snapshots() -> tuple[ImportedSnapshot, ...]:
    return (
        ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"BOS": {"wins": 52, "losses": 30, "expected_wins": 58, "market_pressure": 82}}),
        ImportedSnapshot(
            2026,
            None,
            ImportedDataKind.PLAYER_STATS,
            {
                "players": [
                    {"player_id": "star1", "team_id": "BOS", "name": "Aging Star", "age": 34, "overall": 93, "potential": 93, "minutes": 34, "morale": 70, "development": -1},
                    {"player_id": "star2", "team_id": "BOS", "name": "Second Star", "age": 31, "overall": 89, "potential": 90, "minutes": 33, "morale": 65, "development": 0},
                    {"player_id": "bench1", "team_id": "BOS", "name": "Young Bench", "age": 22, "overall": 72, "potential": 84, "minutes": 14, "morale": 55, "development": 3},
                ]
            },
        ),
        ImportedSnapshot(
            2026,
            None,
            ImportedDataKind.INJURIES,
            {"injuries": [{"player_id": "star2", "team_id": "BOS", "severity": 80, "games_remaining": 12, "description": "knee"}]},
        ),
        ImportedSnapshot(
            2026,
            None,
            ImportedDataKind.CONTRACTS,
            {
                "salary_cap": 141_000_000,
                "luxury_tax_line": 171_000_000,
                "contracts": [
                    {"player_id": "star1", "team_id": "BOS", "salary": 58_000_000, "years_remaining": 3},
                    {"player_id": "star2", "team_id": "BOS", "salary": 49_000_000, "years_remaining": 2},
                    {"player_id": "bench1", "team_id": "BOS", "salary": 4_000_000, "years_remaining": 2},
                    {"player_id": "role1", "team_id": "BOS", "salary": 75_000_000, "years_remaining": 1, "expiring": True},
                ],
                "draft_picks": [
                    {"team_id": "BOS", "year": 2027, "round": 1, "protection": "top 8"},
                    {"team_id": "BOS", "year": 2029, "round": 1},
                    {"team_id": "BOS", "year": 2027, "round": 2},
                ],
            },
        ),
        ImportedSnapshot(
            2026,
            None,
            ImportedDataKind.TRADES,
            {"transactions": [{"team_id": "BOS", "type": "trade", "description": "Moved future second for veteran wing", "date": "2026-02-01"}]},
        ),
    )


if __name__ == "__main__":
    unittest.main()
