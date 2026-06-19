from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from nba2k_editor.franchise_manager.display import FranchiseManagerFacade
from nba2k_editor.franchise_manager.imports import import_team_offsets
from nba2k_editor.franchise_manager.models import ImportedDataKind
from nba2k_editor.models.schema import FieldEntry, RecordListItem


class FakeTeamOffsetModel:
    target_executable = "NBA2K26.exe"

    def __init__(self, rows: tuple[dict[str, Any], ...], *, missing_fields: tuple[str, ...] = ()) -> None:
        self.rows = rows
        self.missing_fields = set(missing_fields)
        self.reads: list[tuple[str, int]] = []

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        self.last_scan = (domain, limit)
        source = self.rows if limit is None else self.rows[:limit]
        return [RecordListItem(domain=domain, index=index, address=0x1000 + index * 0x10, label=str(row["label"])) for index, row in enumerate(source)]

    def grouped_fields(self, domain: str):
        fields = []
        for name in (
            "W",
            "L",
            "POINTS",
            "PA",
            "MADE",
            "ATTEMPTED",
            "3POINTMADE",
            "3POINTATTEMPTED",
            "FREETHROWMADE",
            "FREETHROWATTEMPTED",
            "OFFENSIVEREBOUNDS",
            "DEFENSEREBOUNDS",
            "ASSISTS",
            "STEALS",
            "BLOCKS",
            "FOUL",
            "TURNOVER",
            "POSS",
            "PACE",
        ):
            if name in self.missing_fields:
                continue
            fields.append(FieldEntry(domain=domain, section="Team Stats Edit", group="Teams", ordinal=len(fields), field={"normalized_name": name, "display_name": name}))
        return {"Team Stats Edit": {"Teams": fields}}

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        self.reads.append((entry.normalized_name, index))
        return {"display_value": self.rows[index].get(entry.normalized_name, 0), "raw_value": self.rows[index].get(entry.normalized_name, 0)}


class FranchiseManagerImportTests(unittest.TestCase):
    def test_import_team_offsets_reads_standings_and_team_stats_from_authored_team_fields(self) -> None:
        model = FakeTeamOffsetModel(
            (
                {"label": "Boston Celtics", "W": 44, "L": 12, "POINTS": 6120, "PA": 5600, "ASSISTS": 1520, "PACE": 98},
                {"label": "New York Knicks", "W": 20, "L": 36, "POINTS": 5010, "PA": 5450, "ASSISTS": 1200, "PACE": 94},
            )
        )

        result = import_team_offsets(model, team_limit=30)

        self.assertEqual(("Teams", 30), model.last_scan)
        self.assertEqual({"wins": 44, "losses": 12}, result.standings_payload["Boston Celtics"])
        self.assertEqual({"wins": 20, "losses": 36}, result.standings_payload["New York Knicks"])
        self.assertEqual(6120, result.team_stats_payload["Boston Celtics"]["points"])
        self.assertEqual(5600, result.team_stats_payload["Boston Celtics"]["points_allowed"])
        self.assertEqual(1520, result.team_stats_payload["Boston Celtics"]["assists"])
        self.assertEqual(0, result.team_stats_payload["Boston Celtics"]["turnovers"])
        self.assertIn(("W", 0), model.reads)
        self.assertIn(("L", 1), model.reads)

    def test_import_team_offsets_requires_win_loss_offsets(self) -> None:
        model = FakeTeamOffsetModel(({"label": "Boston Celtics", "W": 44, "L": 12},), missing_fields=("L",))

        with self.assertRaisesRegex(RuntimeError, "missing active Teams offsets.*L"):
            import_team_offsets(model)

    def test_facade_imports_current_team_offsets_into_standings_and_team_stat_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = FranchiseManagerFacade(Path(tmp) / "franchise.sqlite")
            model = FakeTeamOffsetModel(({"label": "Boston Celtics", "W": 44, "L": 12, "POINTS": 6120, "PA": 5600},))
            try:
                facade.create_franchise(start_season=2026)
                dashboard = facade.import_2k_data_from_offsets(model)
                snapshots = facade.store.snapshots_for_season(2026) if facade.store is not None else ()
            finally:
                facade.close()

        self.assertIn("Imported 2K team offsets: 1 standings rows, 1 team stat rows.", dashboard.status)
        self.assertEqual((ImportedDataKind.STANDINGS, ImportedDataKind.TEAM_STATS), tuple(snapshot.kind for snapshot in snapshots))
        self.assertEqual({"wins": 44, "losses": 12}, snapshots[0].payload["Boston Celtics"])
        self.assertEqual(6120, snapshots[1].payload["Boston Celtics"]["points"])


if __name__ == "__main__":
    unittest.main()
