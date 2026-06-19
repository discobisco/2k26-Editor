from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nba2k_editor.franchise_manager import (
    ControlMode,
    DraftClassMode,
    DraftProspect,
    FranchiseStore,
    FranchiseTeam,
    GMProfile,
    ImportedDataKind,
    ImportedSnapshot,
    OwnerProfile,
    SeasonPhase,
    StopPriority,
    TeamControl,
    TeamDirection,
    default_stop_points,
    dynamic_stop_request,
    season_label,
)


class StubDraftDependency:
    def __init__(self) -> None:
        self.calls: list[tuple[int, DraftClassMode]] = []

    def generate_draft_class(self, draft_year: int, *, mode: DraftClassMode = DraftClassMode.DRAFT_PICKS) -> tuple[DraftProspect, ...]:
        self.calls.append((draft_year, mode))
        return (
            DraftProspect(
                draft_year=draft_year,
                rookie_season=draft_year + 1,
                player_id="rookie01",
                name="Rookie One",
                position="PG",
                historical_team="BOS",
                ratings={"SPEED": 88},
                tendencies={"SHOT": 72},
                badges={"General/Alpha Dog": 1},
                metadata={"source": "existing-player-generator-stub"},
            ),
        )


class FranchiseManagerCoreTests(unittest.TestCase):
    def test_season_flow_and_default_stop_points_do_not_simulate_games(self) -> None:
        self.assertEqual("1946-47", season_label(1947))
        stops = default_stop_points(1954)

        self.assertEqual(11, len(stops))
        self.assertEqual("1953-11-01", stops[0].date_label)
        self.assertEqual("Opening Night", stops[0].reason)
        trade_deadline = next(stop for stop in stops if stop.reason == "Trade Deadline Evaluation")
        self.assertEqual(SeasonPhase.REGULAR_SEASON, trade_deadline.phase)
        self.assertEqual(StopPriority.REQUIRED, trade_deadline.priority)
        self.assertTrue(all("simulate" not in stop.reason.lower() for stop in stops))

    def test_dynamic_ai_stop_request_records_team_priority_and_reason(self) -> None:
        stop = dynamic_stop_request(
            2026,
            team_id="NYK",
            reason="Major Injury",
            priority=StopPriority.EMERGENCY,
            date_label="2026-01-10",
        )

        self.assertEqual("NYK", stop.team_id)
        self.assertEqual("Major Injury", stop.reason)
        self.assertEqual(StopPriority.EMERGENCY, stop.priority)
        self.assertEqual("2026-01-10", stop.date_label)

    def test_store_persists_team_control_imports_evaluations_and_reason_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                store.initialize_franchise(start_season=2026, end_season=2050, commissioner_mode=True)
                result = store.next_stop(2026)
                self.assertIsNotNone(result)
                assert result is not None
                stop_id, next_stop = result
                self.assertEqual("Opening Night", next_stop.reason)

                store.add_team(
                    FranchiseTeam(
                        team_id="BOS",
                        display_name="Boston Celtics",
                        owner=OwnerProfile(name="Owner", patience=35, championship_expectations=80, rebuild_tolerance=30),
                        gm=GMProfile(name="GM", aggression=85, trade_frequency=70, position_preferences=("C",), team_building_style="contender"),
                        control=TeamControl(owner=ControlMode.AI, gm=ControlMode.AI),
                    )
                )
                imported_id = store.import_2k_data(
                    ImportedSnapshot(
                        season=2026,
                        stop_id=stop_id,
                        kind=ImportedDataKind.STANDINGS,
                        payload={"BOS": {"wins": 35, "losses": 12}},
                    )
                )
                self.assertGreater(imported_id, 0)

                evaluations = store.evaluate_all_teams(2026)
                self.assertEqual(1, len(evaluations))
                self.assertEqual(TeamDirection.CONTEND, evaluations[0].direction)
                self.assertIn("veteran upgrade", evaluations[0].recommended_actions[0].lower())
                logs = store.reason_logs(season=2026, team_id="BOS")
                self.assertEqual(2, len(logs))
                self.assertTrue(any("35-12" in log.message for log in logs))
            finally:
                store.close()

    def test_draft_class_is_built_through_dependency_not_second_generator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            dependency = StubDraftDependency()
            try:
                prospects = store.build_draft_class(1984, dependency)
                saved = store.list_draft_class(1984)
            finally:
                store.close()

        self.assertEqual([(1984, DraftClassMode.DRAFT_PICKS)], dependency.calls)
        self.assertEqual(prospects, saved)
        self.assertEqual(1985, saved[0].rookie_season)
        self.assertEqual("Rookie One", saved[0].name)
        self.assertEqual(88, saved[0].ratings["SPEED"])
        self.assertEqual(72, saved[0].tendencies["SHOT"])


if __name__ == "__main__":
    unittest.main()
