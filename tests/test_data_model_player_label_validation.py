from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel
from nba2k_editor.models.schema import FieldEntry


class ScanStopModel(EditorDataModel):
    def __init__(self) -> None:
        self.memory = SimpleNamespace(hproc=object(), base_addr=0x1)
        self.target_executable = "NBA2K26.exe"
        self.values = {0: "Alpha", 1: "@@@", 2: "Beta"}
        self.entry = FieldEntry("Players", "Vitals", "ID", 0, {"normalized_name": "FIRSTNAME"})

    def _domain_record_count_limit(self, domain: str) -> int | None:  # type: ignore[override]
        return 3

    def domain_base(self, domain: str) -> int:  # type: ignore[override]
        return 0x1000

    def domain_stride(self, domain: str) -> int:  # type: ignore[override]
        return 0x100

    def _label_entries(self, domain: str) -> list[FieldEntry]:  # type: ignore[override]
        return [self.entry]

    def _read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        index = (record_addr - 0x1000) // 0x100
        return {"display_value": self.values[index]}


class PlayerLabelValidationTests(unittest.TestCase):
    def test_player_label_rejects_question_mark_placeholder(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertFalse(model._valid_label_values("Players", 0x1000, ["??????"], ["??????"]))

    def test_player_label_rejects_symbol_garbage(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertFalse(model._valid_label_values("Players", 0x1000, ["@@@"], ["@@@"]))
        self.assertFalse(model._valid_label_values("Players", 0x1000, ["☠☠"], ["☠☠"]))

    def test_player_label_accepts_names_with_letters(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertTrue(model._valid_label_values("Players", 0x1000, ["Allen", "Iverson"], ["Allen", "Iverson"]))
        self.assertTrue(model._valid_label_values("Players", 0x1000, ["A", "Z"], ["A", "Z"]))

    def test_non_player_domains_reject_invalid_labels_too(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertFalse(model._valid_label_values("Teams", 0x1000, ["??????"], ["??????"]))
        self.assertFalse(model._valid_label_values("Staff", 0x1000, ["@@@"], ["@@@"]))

    def test_non_player_domains_accept_normal_labels(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertTrue(model._valid_label_values("Teams", 0x1000, ["Philadelphia", "76ers"], ["Philadelphia", "76ers"]))
        self.assertTrue(model._valid_label_values("Staff", 0x1000, ["Pat", "Riley"], ["Pat", "Riley"]))

    def test_scan_stops_on_first_non_valid_non_blank_entry(self) -> None:
        model = ScanStopModel()

        items = model.scan_records("Players")

        self.assertEqual(["[0] Alpha"], [item.display_label for item in items])


if __name__ == "__main__":
    unittest.main()
