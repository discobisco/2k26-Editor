from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from importlib import import_module

from nba2k_editor.franchise_manager.display import FranchiseManagerFacade
from nba2k_editor.franchise_manager.models import DraftClassMode, DraftProspect, ImportedDataKind, ImportedSnapshot

REPO_ROOT = Path(__file__).resolve().parents[1]


class StubDraftDependency:
    def __init__(self) -> None:
        self.calls: list[tuple[int, DraftClassMode]] = []

    def generate_draft_class(self, draft_year: int, *, mode: DraftClassMode = DraftClassMode.DRAFT_PICKS) -> tuple[DraftProspect, ...]:
        self.calls.append((draft_year, mode))
        return (DraftProspect(draft_year, draft_year + 1, "stub01", "Stub Prospect", "SG", "BOS", metadata={"draft_class_mode": mode.value}),)


class FranchiseManagerDisplayTests(unittest.TestCase):
    def test_facade_exposes_requested_ui_contract_methods(self) -> None:
        facade = FranchiseManagerFacade(Path(tempfile.gettempdir()) / "franchise_contract_method_test.sqlite")
        for method_name in (
            "CreateFranchise",
            "LoadFranchise",
            "SaveFranchise",
            "AdvancePhase",
            "Import2KDataFromOffsets",
            "ImportManualLeagueSnapshotFile",
            "ImportManualStandingsText",
            "GenerateDraftClass",
            "RunOwnerEvaluations",
            "RunGMEvaluations",
            "RunPlayerProgression",
            "GetNextSimStop",
            "GetLeagueDashboard",
            "GetTeamDashboard",
            "GetOwnerReport",
            "GetGMReport",
            "GetDraftReport",
            "GetHistoryReport",
        ):
            self.assertTrue(callable(getattr(facade, method_name)))
        facade.close()

    def test_default_franchise_database_lives_in_repo_parent_folder(self) -> None:
        facade = FranchiseManagerFacade()
        try:
            self.assertEqual(REPO_ROOT / "nba2k_editor" / "franchise_manager.sqlite", facade.db_path)
        finally:
            facade.close()

    def test_facade_returns_lightweight_dashboard_view_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dependency = StubDraftDependency()
            facade = FranchiseManagerFacade(Path(tmp) / "franchise.sqlite", draft_dependency=dependency)
            try:
                dashboard = facade.create_franchise(start_season=1962)
                self.assertTrue(dashboard.loaded)
                self.assertEqual("1961-62", dashboard.overview.current_season)
                self.assertIn("Opening Night", dashboard.next_sim_stop.reason)

                self.assertIsNotNone(facade.store)
                assert facade.store is not None
                facade.store.import_2k_data(ImportedSnapshot(1962, None, ImportedDataKind.STANDINGS, {"USER": {"wins": 50, "losses": 20}, "CPU": {"wins": 12, "losses": 58}}))
                dashboard = facade.get_league_dashboard(status="Imported fixture standings.")
                self.assertIn("USER: 50-20", dashboard.league_snapshot.top_teams)
                self.assertIn("CPU: 12-58", dashboard.league_snapshot.worst_teams)

                dashboard = facade.run_gm_evaluations()
                self.assertTrue(any("GM" in alert or "gm" in alert for alert in dashboard.gm_alerts))
                dashboard = facade.generate_draft_class(1962)
                self.assertEqual([(1962, DraftClassMode.DRAFT_PICKS)], dependency.calls)
                self.assertIn("by draft picks", dashboard.status)
            finally:
                facade.close()

    def test_facade_imports_manual_league_snapshot_file_without_live_offsets_and_resolves_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "manual_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "standings": {
                            "Boston Celtics": {"wins": 44, "losses": 12},
                            "New York Knicks": {"wins": 20, "losses": 36},
                        },
                        "team_stats": {
                            "Boston Celtics": {"points": 6120, "points_allowed": 5600},
                            "New York Knicks": {"points": 5010, "points_allowed": 5450},
                        },
                    }
                ),
                encoding="utf-8",
            )
            facade = FranchiseManagerFacade(Path(tmp) / "franchise.sqlite")
            try:
                facade.create_franchise(start_season=2026)
                before_stop = facade.get_next_sim_stop()
                dashboard = facade.import_manual_league_snapshot_file(snapshot_path, resolve_stop=True)
                after_stop = facade.get_next_sim_stop()
                snapshots = facade.store.snapshots_for_season(2026) if facade.store is not None else ()
                history = facade.get_history_report()
            finally:
                facade.close()

        self.assertEqual("Opening Night", before_stop.reason)
        self.assertNotEqual("Opening Night", after_stop.reason)
        self.assertIn("Imported manual league snapshot", dashboard.status)
        self.assertIn("Resolved current stop", dashboard.status)
        self.assertIn("Boston Celtics: 44-12", dashboard.league_snapshot.top_teams)
        self.assertIn("New York Knicks: 20-36", dashboard.league_snapshot.worst_teams)
        self.assertEqual(2, len(snapshots))
        self.assertEqual((ImportedDataKind.STANDINGS, ImportedDataKind.TEAM_STATS), tuple(snapshot.kind for snapshot in snapshots))
        self.assertEqual({"wins": 44, "losses": 12}, snapshots[0].payload["Boston Celtics"])
        self.assertEqual(6120, snapshots[1].payload["Boston Celtics"]["points"])
        self.assertTrue(any("manual_import" in item for item in history))

    def test_facade_imports_manual_standings_text_from_pasted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = FranchiseManagerFacade(Path(tmp) / "franchise.sqlite")
            try:
                facade.create_franchise(start_season=2026)
                dashboard = facade.import_manual_standings_text(
                    "Team, Wins, Losses\nBoston Celtics, 44, 12\nNew York Knicks 20-36\nLos Angeles Lakers 30 26"
                )
                snapshots = facade.store.snapshots_for_season(2026) if facade.store is not None else ()
                history = facade.get_history_report()
            finally:
                facade.close()

        self.assertIn("Imported manual standings text: 3 standings rows", dashboard.status)
        self.assertIn("Boston Celtics: 44-12", dashboard.league_snapshot.top_teams)
        self.assertEqual((ImportedDataKind.STANDINGS,), tuple(snapshot.kind for snapshot in snapshots))
        self.assertEqual({"wins": 20, "losses": 36}, snapshots[0].payload["New York Knicks"])
        self.assertTrue(any("manual_standings_import" in item for item in history))

    def test_manual_league_snapshot_file_requires_standings_wins_and_losses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "bad_manual_snapshot.json"
            snapshot_path.write_text(json.dumps({"standings": {"Boston Celtics": {"wins": 44}}}), encoding="utf-8")
            facade = FranchiseManagerFacade(Path(tmp) / "franchise.sqlite")
            try:
                facade.create_franchise(start_season=2026)
                with self.assertRaisesRegex(ValueError, "requires wins and losses"):
                    facade.import_manual_league_snapshot_file(snapshot_path)
            finally:
                facade.close()

    def test_dpg_text_rendering_uses_dashboard_view_model_fields(self) -> None:
        editor = import_module("nba2k_editor.ui.dpg_editor")
        app = editor.DpgEditorApp(SimpleNamespace())
        dashboard = SimpleNamespace(
            overview=SimpleNamespace(
                current_season="1961-62",
                current_phase="Regular Season",
                league_champion="Boston Celtics",
                upcoming_draft="1962 Draft",
                active_user_team="User Franchise",
                user_role="Owner + GM",
            ),
            next_sim_stop=SimpleNamespace(date_label="1962-01-15", reason="Midseason Evaluation", priority="required", teams_requesting_review=7),
            league_snapshot=SimpleNamespace(
                standings_summary=("BOS: 40-10",),
                top_teams=("BOS: 40-10",),
                worst_teams=("NYK: 10-40",),
                mvp_race=("Bill Russell",),
                rookie_race=("Rookie",),
                championship_favorites=("BOS",),
            ),
        )

        self.assertIn("Current Season: 1961-62", app._franchise_overview_text(dashboard))
        self.assertIn("Teams Requesting Review: 7", app._franchise_next_stop_text(dashboard))
        self.assertIn("Championship Favorites", app._franchise_snapshot_text(dashboard))


if __name__ == "__main__":
    unittest.main()
