from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nba2k_editor.franchise_manager import FranchiseStore, InGamePlayerSnapshot
from nba2k_editor.franchise_manager.progression import (
    HistoricalPlayerBaseline,
    HistoricalPlayerStatLink,
    evaluate_player_progression,
)


class FakeHistoricalProvider:
    def __init__(self, *, three_pct: float = 0.28) -> None:
        self.three_pct = three_pct
        self.calls: list[tuple[str, int]] = []

    def player_baseline(self, *, player_id: str, season: int) -> HistoricalPlayerBaseline:
        self.calls.append((player_id, season))
        return HistoricalPlayerBaseline(
            link=HistoricalPlayerStatLink(
                player_id=player_id,
                season=season,
                source_database="historical.sqlite",
                source_tables=("Player Info", "Player Season Info", "Player Per Game"),
            ),
            player_info={"player_id": player_id},
            season_info={"player_id": player_id, "season": season, "team": "ORL"},
            per_game={"x3p_percent": self.three_pct},
        )


class FranchiseManagerProgressionTests(unittest.TestCase):
    def test_open_spot_up_role_allows_three_point_growth_without_copying_irl_stats(self) -> None:
        snapshot = InGamePlayerSnapshot(
            season=1995,
            player_id="onealsh01",
            team_id="ORL",
            attributes={"3POINT": 40},
            tendencies={"3POINTSPOTUPSHOT": 20, "DRIVEPULLUP3POINT": 5, "STEPBACKJUMPER3POINT": 2},
            in_game_stats={"3POINTERSMADE": 18, "3POINTERSATTEMPTED": 40},
            role={"role_name": "center spot-up spacer", "open_look_quality": 0.9, "shot_creation_load": 0.05, "team_quality": 0.8},
        )

        report = evaluate_player_progression(snapshot, FakeHistoricalProvider(three_pct=0.12))

        self.assertEqual("onealsh01", report.historical_link.player_id)
        self.assertEqual(1995, report.historical_link.season)
        self.assertEqual("center spot-up spacer", report.role_summary["role_name"])
        self.assertIn("Player Per Game", report.historical_link.source_tables)
        by_field = {(item.category, item.field_name): item for item in report.progression}
        self.assertEqual(1, by_field[("Attributes", "3POINT")].delta)
        self.assertEqual(41, by_field[("Attributes", "3POINT")].target_value)
        self.assertEqual(2, by_field[("Tendencies", "3POINTSPOTUPSHOT")].delta)

    def test_bad_percentage_in_hard_creation_role_reduces_tough_tendencies_not_actual_skill(self) -> None:
        snapshot = InGamePlayerSnapshot(
            season=1996,
            player_id="onealsh01",
            team_id="BAD",
            attributes={"3POINT": 42},
            tendencies={"3POINTSPOTUPSHOT": 10, "DRIVEPULLUP3POINT": 55, "STEPBACKJUMPER3POINT": 40},
            in_game_stats={"3POINTERSMADE": 10, "3POINTERSATTEMPTED": 80},
            role={"role_name": "forced creator", "open_look_quality": 0.1, "shot_creation_load": 0.9, "team_quality": 0.1},
        )

        report = evaluate_player_progression(snapshot, FakeHistoricalProvider(three_pct=0.33))

        self.assertFalse(any(item.category == "Attributes" and item.field_name == "3POINT" and item.delta < 0 for item in report.regression))
        by_field = {(item.category, item.field_name): item for item in report.regression}
        self.assertEqual(-2, by_field[("Tendencies", "DRIVEPULLUP3POINT")].delta)
        self.assertEqual(-2, by_field[("Tendencies", "STEPBACKJUMPER3POINT")].delta)
        self.assertTrue(any("attribute protected" in reason.lower() for reason in report.reasons))

    def test_store_tracks_in_game_snapshot_and_report_without_storing_irl_stat_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FranchiseStore(Path(tmp) / "franchise.sqlite")
            try:
                snapshot = InGamePlayerSnapshot(
                    season=1995,
                    player_id="onealsh01",
                    team_id="ORL",
                    attributes={"3POINT": 40},
                    tendencies={"3POINTSPOTUPSHOT": 20},
                    in_game_stats={"3POINTERSMADE": 18, "3POINTERSATTEMPTED": 40},
                    role={"open_look_quality": 0.9, "shot_creation_load": 0.05},
                )
                report = store.evaluate_player_progression_snapshot(snapshot, FakeHistoricalProvider(three_pct=0.12345), historical_season=1995)
                saved_snapshots = store.player_stat_snapshots(season=1995, player_id="onealsh01")
                saved_reports = store.player_progression_reports(season=1995, player_id="onealsh01")
                raw_report_json = store._conn.execute("SELECT report_json FROM player_progression_reports").fetchone()["report_json"]
            finally:
                store.close()

        self.assertEqual(1, len(saved_snapshots))
        self.assertEqual(snapshot, saved_snapshots[0][1])
        self.assertEqual(1, len(saved_reports))
        self.assertEqual(report.player_id, saved_reports[0].player_id)
        self.assertIn("historical_link", raw_report_json)
        self.assertIn("Player Per Game", raw_report_json)
        self.assertNotIn("x3p_percent", raw_report_json)
        self.assertNotIn("0.12345", raw_report_json)


if __name__ == "__main__":
    unittest.main()
