from __future__ import annotations

import unittest
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel
from nba2k_editor.models.schema import FieldEntry


def _entry(section: str, normalized_name: str, ordinal: int, **field_extra: Any) -> FieldEntry:
    field = {"normalized_name": normalized_name, "display_name": normalized_name}
    field.update(field_extra)
    return FieldEntry(
        domain="Players",
        section=section,
        group="Test",
        ordinal=ordinal,
        field=field,
    )


class ResetRecordingModel(EditorDataModel):
    def __init__(self) -> None:
        self.writes: list[tuple[int, str, str, Any, object | None]] = []
        self.entries = [
            _entry("Vitals", "FIRSTNAME", 1),
            _entry("Vitals", "LASTNAME", 2),
            _entry("Vitals", "BIRTHYEAR", 3),
            _entry("Vitals", "CUSTOMAGEATSETYEAR", 4),
            _entry("Vitals", "POSITION", 5),
            _entry("Attributes", "MIDRANGE", 6),
            _entry("Tendencies", "SHOT", 7),
            _entry("Badges", "BULLDOZER", 8),
            _entry("Stats", "STATSID1", 9, stat_role="season_id_selector"),
            _entry("Stats", "POINTS", 10),
        ]

    def grouped_fields(self, domain: str):  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        return {"Players": {"Test": self.entries}}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None):  # type: ignore[override]
        self.writes.append((index, entry.section, entry.normalized_name, value, stat_selector))
        return {"display_value": value}


class PlayerEditorResetTests(unittest.TestCase):
    def test_reset_player_editor_values_uses_backend_owned_defaults(self) -> None:
        model = ResetRecordingModel()

        result = model.reset_player_editor_values(index=12, stat_selector="[65535] Active")

        self.assertEqual({"attempted": 8, "succeeded": 8, "failed": 0}, result)
        self.assertEqual(
            [
                (12, "Vitals", "FIRSTNAME", "A", "[65535] Active"),
                (12, "Vitals", "LASTNAME", "Z", "[65535] Active"),
                (12, "Vitals", "BIRTHYEAR", 2006, "[65535] Active"),
                (12, "Vitals", "CUSTOMAGEATSETYEAR", 0, "[65535] Active"),
                (12, "Attributes", "MIDRANGE", 25, "[65535] Active"),
                (12, "Tendencies", "SHOT", 0, "[65535] Active"),
                (12, "Badges", "BULLDOZER", 0, "[65535] Active"),
                (12, "Stats", "STATSID1", 65535, "[65535] Active"),
            ],
            model.writes,
        )


if __name__ == "__main__":
    unittest.main()
