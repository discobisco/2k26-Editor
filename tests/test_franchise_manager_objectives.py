from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nba2k_editor.franchise_manager import FranchiseStore, FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.ai import evaluate_team_at_stop
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.objectives import (
    ObjectiveDirective,
    assign_preseason_directives,
    evaluate_objective_progress,
    owner_end_season_review,
)
from nba2k_editor.franchise_manager.world import DraftPickAsset, FranchisePlayer, build_team_context


class FranchiseManagerObjectivesTests(unittest.TestCase):
    def test_preseason_directives_match_contender_and_rebuild_contexts(self) -> None:
        contender = _contender_context()
        rebuild = _rebuild_context()

        contender_directives = assign_preseason_directives(contender, TeamDirection.CONTEND)
        rebuild_directives = assign_preseason_directives(rebuild, TeamDirection.REBUILD)

        self.assertEqual("make_playoffs", contender_directives[0].objective_type)
        self.assertTrue(any(item.objective_type == "manage_luxury_tax" for item in contender_directives))
        self.assertEqual("develop_young_core", rebuild_directives[0].objective_type)
        self.assertTrue(any(item.objective_type == "acquire_first_round_pick" for item in rebuild_directives))

    def test_objective_progress_pass_fail_uses_record_roster_tax_and_pick_state(self) -> None:
        contender = _contender_context()
        rebuild = _rebuild_context()
        objectives = (
            ObjectiveDirective("SEA", 2026, "make_playoffs", "primary", target={"min_wins": 45}),
            ObjectiveDirective("SEA", 2026, "manage_luxury_tax", "secondary", target={"max_tax_overage": 0}),
            ObjectiveDirective("SEA", 2026, "develop_young_core", "primary", target={"min_young_core": 2}),
            ObjectiveDirective("SEA", 2026, "acquire_first_round_pick", "secondary", target={"min_future_firsts": 2}),
        )

        contender_results = evaluate_objective_progress(contender, objectives[:2])
        rebuild_results = evaluate_objective_progress(rebuild, objectives[2:])

        self.assertEqual("passed", contender_results[0].status)
        self.assertEqual("failed", contender_results[1].status)
        self.assertEqual("passed", rebuild_results[0].status)
        self.assertEqual("failed", rebuild_results[1].status)

    def test_owner_review_raises_firing_risk_and_budget_cut_on_failed_primary_goal(self) -> None:
        context = _rebuild_context(owner=OwnerProfile("Impatient", patience=25, firing_threshold=45, rebuild_tolerance=30, market_pressure_sensitivity=80))
        objectives = (ObjectiveDirective("SEA", 2026, "make_playoffs", "primary", target={"min_wins": 45}),)

        review = owner_end_season_review(context, objectives, TeamDirection.REBUILD)

        self.assertGreaterEqual(review.firing_risk, 70)
        self.assertLess(review.budget_delta, 0)
        self.assertIn("failed primary", review.summary.lower())

    def test_store_round_trips_objectives_and_evaluation_reads_objective_snapshot(self) -> None:
        team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", patience=30, championship_expectations=85, firing_threshold=45), GMProfile("GM"))
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                store.add_team(team)
                store.import_2k_data(ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 30, "losses": 52, "expected_wins": 33, "market_pressure": 80}}))
                store.upsert_franchise_players(2026, (FranchisePlayer("p1", "SEA", name="Only Vet", age=31, overall=80, potential=80, minutes=30),))
                store.upsert_objectives(
                    2026,
                    "SEA",
                    (ObjectiveDirective("SEA", 2026, "make_playoffs", "primary", target={"min_wins": 45}),),
                )

                stored = store.list_objectives(season=2026, team_id="SEA")
                evaluation = store.evaluate_all_teams(2026)[0]
            finally:
                store.close()

        self.assertEqual(("make_playoffs",), tuple(item.objective_type for item in stored))
        owner_evidence = evaluation.reason_logs[0].evidence
        self.assertIn("objective_review", owner_evidence)
        self.assertGreaterEqual(owner_evidence["objective_review"]["firing_risk"], 50)
        self.assertIn("directive", evaluation.owner_report.lower())

    def test_direct_snapshot_evaluation_includes_objective_review_evidence(self) -> None:
        context = _contender_context()
        team = context.team
        snapshots = _contender_snapshots() + (
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.OBJECTIVES,
                {"objectives": [{"team_id": "SEA", "season": 2026, "objective_type": "make_playoffs", "priority": "primary", "target": {"min_wins": 45}}]},
            ),
        )

        evaluation = evaluate_team_at_stop(season=2026, team=team, snapshots=snapshots)

        self.assertIn("objective_review", evaluation.reason_logs[0].evidence)
        self.assertEqual("passed", evaluation.reason_logs[0].evidence["objective_review"]["results"][0]["status"])


def _contender_context():
    return build_team_context(
        season=2026,
        team=FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", patience=45, championship_expectations=90, spending_willingness=40), GMProfile("GM")),
        snapshots=_contender_snapshots(),
    )


def _contender_snapshots() -> tuple[ImportedSnapshot, ...]:
    return (
        ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 50, "losses": 32, "expected_wins": 53, "market_pressure": 78}}),
        ImportedSnapshot(2026, None, ImportedDataKind.PLAYER_STATS, {"players": [{"player_id": "star", "team_id": "SEA", "name": "Star", "age": 29, "overall": 92, "potential": 92, "minutes": 35}]}),
        ImportedSnapshot(2026, None, ImportedDataKind.CONTRACTS, {"salary_cap": 141_000_000, "luxury_tax_line": 171_000_000, "contracts": [{"player_id": "star", "team_id": "SEA", "salary": 180_000_000, "years_remaining": 3}], "draft_picks": [{"team_id": "SEA", "year": 2027, "round": 1}]}),
    )


def _rebuild_context(owner: OwnerProfile | None = None):
    return build_team_context(
        season=2026,
        team=FranchiseTeam("SEA", "Seattle", owner or OwnerProfile("Owner", rebuild_tolerance=85, patience=70), GMProfile("GM", prospect_preference=85)),
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 20, "losses": 62, "expected_wins": 24, "market_pressure": 70}}),
            ImportedSnapshot(2026, None, ImportedDataKind.PLAYER_STATS, {"players": [
                {"player_id": "kid1", "team_id": "SEA", "name": "Young One", "age": 21, "overall": 74, "potential": 88, "minutes": 26},
                {"player_id": "kid2", "team_id": "SEA", "name": "Young Two", "age": 22, "overall": 72, "potential": 84, "minutes": 24},
            ]}),
            ImportedSnapshot(2026, None, ImportedDataKind.CONTRACTS, {"salary_cap": 141_000_000, "luxury_tax_line": 171_000_000, "draft_picks": [DraftPickAsset("SEA", 2027, round=1).__dict__]}),
        ),
    )


if __name__ == "__main__":
    unittest.main()
