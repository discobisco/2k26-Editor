from __future__ import annotations

import unittest
from collections import OrderedDict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from nba2k_editor.core.field_io import _display_to_raw_value, _raw_to_display_value
from nba2k_editor.models.data_model import EDITOR_DOMAINS, EditorDataModel, PLAYER_TEAM_FILTER_BASE_TEAMS
from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.qt_app import QtEditorApp, PLAYER_ROSTER_EXPORT_MODES


class RosterSlotModel(EditorDataModel):
    def __init__(self) -> None:
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.target_executable = "NBA2K26.exe"
        self.team = RecordListItem("Teams", 0, 0x5000, "Golden State Warriors")
        self.expansion_team = RecordListItem("Teams", 30, 0x6000, "Expansion Team")
        self.player_a = RecordListItem("Players", 2, 0x1200, "Alpha")
        self.player_b = RecordListItem("Players", 3, 0x1300, "Beta")
        self.player_c = RecordListItem("Players", 4, 0x1400, "Gamma")
        self.draft_player = RecordListItem("Players", 5, 0x2500, "Draft Alpha")
        self.loaded_items["Teams"] = {self.team.index: self.team, self.expansion_team.index: self.expansion_team}
        self.loaded_items["Players"] = {
            self.player_a.index: self.player_a,
            self.player_b.index: self.player_b,
            self.player_c.index: self.player_c,
        }
        self.loaded_items.setdefault("NBA History", {})
        self.loaded_items.setdefault("NBA Records", {})
        self.selected_items = {domain: None for domain in self.loaded_items}
        self.domain_statuses = {domain: "loaded" for domain in self.loaded_items}
        self.memory = type("Memory", (), {"hproc": None})()
        self.slot_entries = [
            FieldEntry("Teams", "Team Players", "Team Players", 0, {"normalized_name": "PLAYER10"}),
            FieldEntry("Teams", "Team Players", "Team Players", 1, {"normalized_name": "PLAYER1"}),
            FieldEntry("Teams", "Team Players", "Team Players", 2, {"normalized_name": "2WAYPLAYER1"}),
            FieldEntry("Teams", "Team Players", "Team Players", 3, {"normalized_name": "PLAYER2"}),
        ]
        self.current_team_reads = 0
        self.writes: list[tuple[str, int, Any]] = []
        self.address_reads: list[tuple[str, int, str]] = []
        self.address_writes: list[tuple[str, int, str, Any]] = []
        self._data_version = 0
        self._player_team_pointer_cache: dict[int, int] = {}
        self._player_filter_items_by_key: dict[str | int, tuple[RecordListItem, ...]] = {}
        self._player_search_keys: dict[int, str] = {}
        self._player_filter_index_ready = False
        self.build_player_filter_index(include_free_agents=False)

    def grouped_fields(self, domain: str):  # type: ignore[override]
        if domain == "Teams":
            return OrderedDict({"Team Players": OrderedDict({"Team Players": self.slot_entries})})
        return OrderedDict()

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:  # type: ignore[override]
        if entry.domain == "Players" and entry.normalized_name == "CURRENTTEAM":
            self.current_team_reads += 1
            raise AssertionError("team export must not scan Players/CURRENTTEAM")
        if index == self.expansion_team.index:
            slot_values = {"PLAYER1": self.player_c.address}
        else:
            slot_values = {"PLAYER1": self.player_a.address, "PLAYER2": self.player_b.address, "PLAYER10": 0}
        return {"raw_value": slot_values.get(entry.normalized_name, 0), "display_value": slot_values.get(entry.normalized_name, 0)}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None) -> None:  # type: ignore[override]
        self.writes.append((entry.normalized_name, index, value))

    def _read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        name = str(field.get("normalized_name"))
        self.address_reads.append((domain, record_addr, name))
        if record_addr == self.draft_player.address:
            value = "Draft Alpha"
        elif name == "CURRENTTEAM":
            return {"raw_value": self.team.address, "display_value": self.team.label}
        else:
            value = "Alpha"
        return {"raw_value": value, "display_value": value}

    def _write_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any], value: Any) -> Any:  # type: ignore[override]
        self.address_writes.append((domain, record_addr, str(field.get("normalized_name")), value))
        return value

    def _read_player_current_team_pointer(self, item: RecordListItem) -> int:  # type: ignore[override]
        self.current_team_reads += 1
        return self.expansion_team.address if item is self.player_c else self.team.address

    def _read_player_is_active(self, item: RecordListItem) -> bool:  # type: ignore[override]
        return True

    def _scan_records_from_base_key(self, domain: str, base_key: str, *, limit=None):  # type: ignore[override]
        return [self.draft_player]

    def _field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        return dict(field.get("payload", {}))

    def _portable_player_roster_entries(self) -> list[FieldEntry]:  # type: ignore[override]
        return [
            FieldEntry("Players", "Vitals", "Vitals", 10, {"normalized_name": "FIRSTNAME", "payload": {"type": "string"}}),
            FieldEntry("Players", "Vitals", "Team", 11, {"normalized_name": "CURRENTTEAM", "payload": {"type": "uint64", "team_address_dropdown": True}}),
        ]

    def _player_record_address_for_index(self, index: int) -> int:  # type: ignore[override]
        if index == self.player_a.index:
            return self.player_a.address
        if index == self.player_b.index:
            return self.player_b.address
        raise KeyError(index)


class PlayerRosterSnapshotExportTests(unittest.TestCase):
    def test_team_exports_use_team_player_slots_not_currentteam_scan(self) -> None:
        model = RosterSlotModel()
        initial_current_team_reads = model.current_team_reads

        rows = model.player_roster_slot_items_for_team_items((model.team,))

        self.assertEqual([model.player_a, model.player_b], [player for player, _placement in rows])
        self.assertEqual(
            [
                {"team_index": 0, "team_label": "Golden State Warriors", "team_slot": 1, "team_slot_field": "PLAYER1"},
                {"team_index": 0, "team_label": "Golden State Warriors", "team_slot": 2, "team_slot_field": "PLAYER2"},
            ],
            [placement for _player, placement in rows],
        )
        self.assertEqual(initial_current_team_reads, model.current_team_reads)

    def test_base_team_filter_lists_only_players_in_team_slots_zero_to_twenty_nine(self) -> None:
        model = RosterSlotModel()

        labels = model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_BASE_TEAMS)
        items = model.player_items_for_team_filter(PLAYER_TEAM_FILTER_BASE_TEAMS)

        self.assertIn((PLAYER_TEAM_FILTER_BASE_TEAMS, PLAYER_TEAM_FILTER_BASE_TEAMS), model.player_team_filter_options())
        self.assertEqual([model.player_a.display_label, model.player_b.display_label], labels)
        self.assertEqual({model.player_a.index: model.player_a, model.player_b.index: model.player_b}, items)
        self.assertNotIn(model.player_c.display_label, labels)
        self.assertEqual(0, model.current_team_reads)

    def test_base_team_filter_searches_within_zero_to_twenty_nine_team_slot_players(self) -> None:
        model = RosterSlotModel()

        labels = model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_BASE_TEAMS, "bet")

        self.assertEqual([model.player_b.display_label], labels)
        self.assertEqual(0, model.current_team_reads)

    def test_export_records_raw_values_and_team_slot_metadata(self) -> None:
        model = RosterSlotModel()
        first_name_entry = model._portable_player_roster_entries()[0]
        current_team_entry = model._portable_player_roster_entries()[1]

        def read_value(entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
            if entry is first_name_entry or entry.normalized_name == "FIRSTNAME":
                return {"raw_value": "Alpha", "display_value": "Alpha"}
            if entry is current_team_entry or entry.normalized_name == "CURRENTTEAM":
                return {"raw_value": 0x5000, "display_value": "Golden State Warriors"}
            raise AssertionError(entry)

        model.read_entry_value = read_value  # type: ignore[method-assign]
        snapshot = model.export_player_roster_snapshot_for_items(
            (model.player_a,),
            mode="Players From Team Range",
            placements=({"team_index": 0, "team_label": "Golden State Warriors", "team_slot": 1, "team_slot_field": "PLAYER1"},),
        )

        row = snapshot["records"][0]
        self.assertEqual(0, row["team_index"])
        self.assertEqual(1, row["team_slot"])
        self.assertEqual("PLAYER1", row["team_slot_field"])
        self.assertEqual({"display_value": "Alpha", "raw_value": "Alpha"}, row["fields"]["Vitals/FIRSTNAME"])
        self.assertEqual(
            {"display_value": "Golden State Warriors", "raw_value": 0x5000},
            row["fields"]["Vitals/CURRENTTEAM"],
        )

    def test_draft_class_snapshot_export_reads_player_body_at_draft_address(self) -> None:
        model = RosterSlotModel()

        snapshot = model.export_player_roster_snapshot_for_items((model.draft_player,), mode="Draft Class")

        self.assertEqual("Draft Class", snapshot["mode"])
        self.assertEqual("Players", snapshot["domain"])
        self.assertEqual(1, snapshot["record_count"])
        self.assertEqual({"display_value": "Draft Alpha", "raw_value": "Draft Alpha"}, snapshot["records"][0]["fields"]["Vitals/FIRSTNAME"])
        self.assertIn(("Players", model.draft_player.address, "FIRSTNAME"), model.address_reads)

    def test_draft_class_snapshot_apply_writes_player_body_at_draft_address(self) -> None:
        model = RosterSlotModel()
        snapshot = {"mode": "Draft Class", "records": [{"fields": {"Vitals/FIRSTNAME": {"display_value": "Draft Beta"}}}]}

        result = model.apply_player_roster_snapshot(snapshot, target_items=(model.draft_player,))

        self.assertEqual(1, result["succeeded"])
        self.assertEqual([], model.writes)
        self.assertEqual([("Players", model.draft_player.address, "FIRSTNAME", "Draft Beta")], model.address_writes)

    def test_draft_class_is_roster_snapshot_mode_and_routes_to_draft_items(self) -> None:
        model = RosterSlotModel()
        app = QtEditorApp(model)

        mode, items, placements = app._player_roster_export_items("Draft Class")

        self.assertIn("Draft Class", PLAYER_ROSTER_EXPORT_MODES)
        self.assertEqual("Draft Class", mode)
        self.assertEqual([model.draft_player], items)
        self.assertIsNone(placements)

    def test_export_snapshot_starts_background_operation(self) -> None:
        model = RosterSlotModel()
        app = QtEditorApp(model)
        with TemporaryDirectory() as temp_dir:
            app.roster_mode_combo.setCurrentText("Draft Class")
            app.roster_folder_input.setText(temp_dir)
            app.roster_file_input.setText("snapshot.json")

            app._export_player_roster_snapshot()

            operation_thread = app.operation_worker._thread
            self.assertIsNotNone(operation_thread)
            assert operation_thread is not None
            operation_thread.join(timeout=5)
            app._poll_background_operation()
            self.assertFalse(operation_thread.is_alive())
            self.assertTrue((Path(temp_dir) / "snapshot.json").exists())

    def test_apply_uses_target_team_address_without_replaying_team_slot(self) -> None:
        model = RosterSlotModel()
        snapshot = {
            "records": [
                {
                    "index": 999,
                    "team_index": model.team.index,
                    "team_label": model.team.label,
                    "team_slot": 1,
                    "team_slot_field": "PLAYER1",
                    "fields": {
                        "Vitals/FIRSTNAME": {"display_value": "Alpha"},
                        "Vitals/CURRENTTEAM": {"display_value": "Wrong Source Label", "raw_value": 0xDEADBEEF},
                    },
                }
            ]
        }

        result = model.apply_player_roster_snapshot(snapshot, target_items=(model.player_a,))

        self.assertEqual(2, result["succeeded"])
        self.assertEqual(0, result["placement_succeeded"])
        self.assertEqual(
            [("FIRSTNAME", model.player_a.index, "Alpha"), ("CURRENTTEAM", model.player_a.index, model.team.address)],
            model.writes,
        )

    def test_team_snapshot_without_target_items_writes_once_to_team_slot_player(self) -> None:
        model = RosterSlotModel()
        snapshot = {
            "records": [
                {
                    "index": 999,
                    "team_index": model.team.index,
                    "team_slot": 1,
                    "team_slot_field": "PLAYER1",
                    "fields": {"Vitals/FIRSTNAME": {"display_value": "Alpha"}},
                }
            ]
        }

        result = model.apply_player_roster_snapshot(snapshot)

        self.assertEqual(1, result["attempted"])
        self.assertEqual(1, result["succeeded"])
        self.assertEqual(0, result["placement_succeeded"])
        self.assertEqual([("FIRSTNAME", model.player_a.index, "Alpha")], model.writes)

    def test_weight_from_pounds_metadata_preserves_college_filler_weight(self) -> None:
        field = {"display_name": "Weight", "normalized_name": "WEIGHT"}
        payload = {"type": "float", "from_pounds": True}

        self.assertEqual(100.0, _raw_to_display_value("Vitals", field, payload, 100.0))
        self.assertEqual(100.0, _display_to_raw_value("Vitals", field, payload, 100.0))
        self.assertEqual(100.0, _display_to_raw_value("Vitals", field, payload, 99.0))

    def test_wingspan_uses_same_raw_inches_conversion_as_height(self) -> None:
        field = {"display_name": "Wingspan", "normalized_name": "WINGSPAN"}
        payload = {"type": "ushort"}

        self.assertEqual(81, _raw_to_display_value("Vitals", field, payload, 20553))
        self.assertEqual(20574, _display_to_raw_value("Vitals", field, payload, 81))


if __name__ == "__main__":
    unittest.main()
