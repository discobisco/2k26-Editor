from __future__ import annotations

import unittest
from collections import OrderedDict
from typing import Any

from nba2k_editor.core.field_io import _display_to_raw_value, _raw_to_display_value
from nba2k_editor.models.data_model import EDITOR_DOMAINS, EditorDataModel
from nba2k_editor.models.schema import FieldEntry, RecordListItem


class RosterSlotModel(EditorDataModel):
    def __init__(self) -> None:
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.target_executable = "NBA2K26.exe"
        self.team = RecordListItem("Teams", 0, 0x5000, "Golden State Warriors")
        self.player_a = RecordListItem("Players", 2, 0x1200, "Alpha")
        self.player_b = RecordListItem("Players", 3, 0x1300, "Beta")
        self.loaded_items["Teams"] = {self.team.label: self.team}
        self.loaded_items["Players"] = {
            self.player_a.display_label: self.player_a,
            self.player_b.display_label: self.player_b,
        }
        self.slot_entries = [
            FieldEntry("Teams", "Team Players", "Team Players", 0, {"normalized_name": "PLAYER10"}),
            FieldEntry("Teams", "Team Players", "Team Players", 1, {"normalized_name": "PLAYER1"}),
            FieldEntry("Teams", "Team Players", "Team Players", 2, {"normalized_name": "2WAYPLAYER1"}),
            FieldEntry("Teams", "Team Players", "Team Players", 3, {"normalized_name": "PLAYER2"}),
        ]
        self.current_team_reads = 0
        self.writes: list[tuple[str, int, Any]] = []

    def grouped_fields(self, domain: str):  # type: ignore[override]
        if domain == "Teams":
            return OrderedDict({"Team Players": OrderedDict({"Team Players": self.slot_entries})})
        return OrderedDict()

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:  # type: ignore[override]
        if entry.domain == "Players" and entry.normalized_name == "CURRENTTEAM":
            self.current_team_reads += 1
            raise AssertionError("team export must not scan Players/CURRENTTEAM")
        slot_values = {"PLAYER1": self.player_a.address, "PLAYER2": self.player_b.address, "PLAYER10": 0}
        return {"raw_value": slot_values.get(entry.normalized_name, 0), "display_value": slot_values.get(entry.normalized_name, 0)}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None) -> None:  # type: ignore[override]
        self.writes.append((entry.normalized_name, index, value))

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

        rows = model.player_roster_slot_items_for_team_items((model.team,))

        self.assertEqual([model.player_a, model.player_b], [player for player, _placement in rows])
        self.assertEqual(
            [
                {"team_index": 0, "team_label": "Golden State Warriors", "team_slot": 1, "team_slot_field": "PLAYER1"},
                {"team_index": 0, "team_label": "Golden State Warriors", "team_slot": 2, "team_slot_field": "PLAYER2"},
            ],
            [placement for _player, placement in rows],
        )
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

    def test_weight_from_pounds_metadata_does_not_convert_in_field_io(self) -> None:
        field = {"display_name": "Weight", "normalized_name": "WEIGHT"}
        payload = {"type": "float", "from_pounds": True}

        self.assertEqual(225.0, _raw_to_display_value("Vitals", field, payload, 225.0))
        self.assertEqual(225.0, _display_to_raw_value("Vitals", field, payload, 225.0))

    def test_wingspan_uses_same_raw_inches_conversion_as_height(self) -> None:
        field = {"display_name": "Wingspan", "normalized_name": "WINGSPAN"}
        payload = {"type": "ushort"}

        self.assertEqual(81, _raw_to_display_value("Vitals", field, payload, 20553))
        self.assertEqual(20574, _display_to_raw_value("Vitals", field, payload, 81))


if __name__ == "__main__":
    unittest.main()
