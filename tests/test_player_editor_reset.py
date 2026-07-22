from __future__ import annotations

import unittest
from collections import OrderedDict
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel
from nba2k_editor.models.resetleaguemodel import ResetLeagueModel
from nba2k_editor.models.schema import FieldEntry, RecordListItem


def _entry(section: str, normalized_name: str, ordinal: int, **field_extra: Any) -> FieldEntry:
    field = {"normalized_name": normalized_name, "display_name": normalized_name}
    group = str(field_extra.pop("group", "Season IDs" if section == "Stats" else "Test"))
    field.update(field_extra)
    return FieldEntry(
        domain="Players",
        section=section,
        group=group,
        ordinal=ordinal,
        field=field,
    )


class ResetRecordingModel(EditorDataModel):
    def __init__(self) -> None:
        self.writes: list[tuple[int, str, str, Any, object | None]] = []
        self.target_executable = "NBA2K26.exe"
        self.entries = [
            _entry("Vitals", "FIRSTNAME", 1),
            _entry("Vitals", "LASTNAME", 2),
            _entry("Vitals", "BIRTHYEAR", 3),
            _entry("Vitals", "CUSTOMAGEATSETYEAR", 4),
            _entry("Vitals", "POSITION", 5),
            _entry("Attributes", "MIDRANGE", 6),
            _entry("Tendencies", "SHOT", 7),
            _entry("Badges", "BULLDOZER", 8),
            _entry("Stats", "CURRENTYEARSTATID", 9, stat_role="season_id_selector"),
            *[_entry("Stats", f"STATSID{i}", 9 + i, stat_role="season_id_selector") for i in range(1, 32)],
            _entry(
                "Stats",
                "POINTS",
                41,
                stat_role="season_id_detail",
                selected_record_source={"base_pointer": "PlayerSeasonStats", "stride": "playerSeasonStatsSize"},
            ),
        ]

    def grouped_fields(self, domain: str):  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        grouped = OrderedDict()
        for entry in self.entries:
            grouped.setdefault(entry.section, OrderedDict()).setdefault(entry.group, []).append(entry)
        return grouped

    def _field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        if "selected_record_source" in field:
            return {"address": 0, "type": "ushort"}
        return {"address": 0, "type": "ushort"}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None):  # type: ignore[override]
        self.writes.append((index, entry.section, entry.normalized_name, value, stat_selector))
        return {"display_value": value}


class ResetSnapshotModel:
    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return entry.field.get("stat_role") == "season_id_detail"

    def player_season_stat_id_options(self, player_index: int) -> list[str]:
        return ["[42] STATS ID#1", "-- STATS ID#2 (65535)", "[99] CURRENTYEARSTATID"]


class PlayerEditorResetTests(unittest.TestCase):
    def test_reset_model_does_not_include_stat_fields(self) -> None:
        entries = [
            _entry("Vitals", "FIRSTNAME", 1),
            _entry("Stats", "STATSID1", 2, stat_role="season_id_selector"),
            _entry("Stats", "POINTS", 3, stat_role="season_id_detail", selected_record_source={"base_pointer": "PlayerSeasonStats", "stride": "playerSeasonStatsSize"}),
            _entry("Stats", "ISUSED", 4, stat_role="season_id_detail", selected_record_source={"base_pointer": "PlayerSeasonStats", "stride": "playerSeasonStatsSize"}),
        ]
        item = RecordListItem("Players", 12, 0x1000, "Alpha")

        snapshots = ResetLeagueModel(ResetSnapshotModel()).player_editor_reset_snapshots(item, entries, stat_selector_for_entry=lambda _entry: "[active]")

        self.assertEqual(1, len(snapshots))
        self.assertEqual(({"records": [{"index": 12, "fields": {"Vitals/FIRSTNAME": {"display_value": "A"}}}]}, None), snapshots[0])
        fields = snapshots[0][0]["records"][0]["fields"]
        self.assertNotIn("Stats/STATSID1", fields)
        self.assertNotIn("Stats/POINTS", fields)
        self.assertNotIn("Stats/ISUSED", fields)


    def test_apply_player_roster_snapshot_ignores_stats_by_default(self) -> None:
        model = ResetRecordingModel()

        result = model.apply_player_roster_snapshot(
            {
                "records": [
                    {
                        "index": 12,
                        "fields": {
                            "Vitals/FIRSTNAME": {"display_value": "B"},
                            "Stats/STATSID1": {"display_value": 65535},
                            "Stats/POINTS": {"display_value": 0},
                        },
                    }
                ]
            },
            stat_selector="[42] Active",
        )

        self.assertEqual(1, result["attempted"])
        self.assertEqual(1, result["succeeded"])
        self.assertEqual(2, result["skipped"])
        self.assertEqual([(12, "Vitals", "FIRSTNAME", "B", "[42] Active")], model.writes)

    def test_set_all_players_stat_ids_writes_65535_to_each_stat_id_field_without_failure_accounting(self) -> None:
        model = ResetRecordingModel()
        players = (RecordListItem("Players", 12, 0x1000, "Alpha"),)
        progress: list[tuple[int, int, str]] = []

        result = model.set_all_players_stat_ids_to_no_stats(player_items=players, progress_callback=lambda *args: progress.append(args))

        expected_names = ["CURRENTYEARSTATID", *(f"STATSID{i}" for i in range(1, 32))]
        self.assertEqual({"players": 1, "stat_id_fields": len(expected_names), "written": len(expected_names)}, result)
        self.assertEqual(
            [(12, "Stats", name, 65535, None) for name in expected_names],
            model.writes,
        )
        self.assertNotIn("POINTS", [write[2] for write in model.writes])
        self.assertNotIn("failed", result)
        self.assertEqual((len(expected_names), len(expected_names), "Setting player stat IDs: 32/32"), progress[-1])


if __name__ == "__main__":
    unittest.main()
