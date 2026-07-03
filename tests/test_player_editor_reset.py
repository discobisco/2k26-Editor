from __future__ import annotations

import unittest
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel
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
        return {"Players": {"Test": self.entries}}

    def _field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        if "selected_record_source" in field:
            return {"address": 0, "type": "ushort"}
        return {"address": 0, "type": "ushort"}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None):  # type: ignore[override]
        self.writes.append((index, entry.section, entry.normalized_name, value, stat_selector))
        return {"display_value": value}


class PlayerEditorResetTests(unittest.TestCase):
    def test_reset_player_editor_values_uses_backend_owned_defaults(self) -> None:
        model = ResetRecordingModel()

        result = model.reset_player_editor_values(index=12, stat_selector="[42] Active")

        self.assertEqual({"attempted": 7, "succeeded": 7, "failed": 0}, result)
        self.assertEqual(
            [
                (12, "Vitals", "FIRSTNAME", "A", "[42] Active"),
                (12, "Vitals", "LASTNAME", "Z", "[42] Active"),
                (12, "Vitals", "BIRTHYEAR", 2006, "[42] Active"),
                (12, "Attributes", "MIDRANGE", 25, "[42] Active"),
                (12, "Tendencies", "SHOT", 0, "[42] Active"),
                (12, "Badges", "BULLDOZER", 0, "[42] Active"),
                (12, "Stats", "POINTS", 0, "[42] Active"),
            ],
            model.writes,
        )

    def test_reset_player_editor_values_does_not_zero_stat_details_without_active_stat_selector(self) -> None:
        model = ResetRecordingModel()

        result = model.reset_player_editor_values(index=12)

        self.assertEqual({"attempted": 6, "succeeded": 6, "failed": 0}, result)
        self.assertNotIn("POINTS", [write[2] for write in model.writes])
        self.assertNotIn("STATSID1", [write[2] for write in model.writes])

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
