from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from game_port import (  # noqa: E402
    _MATCHED_NAME_IMPORT_FIELD_KEYS,
    _MATCHED_NAME_IMPORT_SECTIONS,
    _generated_player_name_matches,
    _generated_rows_for_import,
    apply_generated_players_to_game,
    missing_generated_players_and_active_placeholder_indices,
)
from display import GeneratorDisplayState, missing_generator_import_preview  # noqa: E402
from nba2k_editor.models.schema import FieldEntry, RecordListItem  # noqa: E402


class MissingImportModel:
    def __init__(self) -> None:
        self.players = (
            RecordListItem("Players", 1, 0x1000, "John Doe"),
            RecordListItem("Players", 2, 0x2000, "A Z"),
            RecordListItem("Players", 3, 0x3000, "A Z"),
            RecordListItem("Players", 4, 0x4000, "Jane Roe"),
        )
        self.loaded_items = {"Players": {player.display_label: player for player in self.players}}
        self.active_by_index = {1: True, 2: True, 3: True, 4: False}
        self.names_by_index = {
            1: ("John", "Doe"),
            2: ("A", "Z"),
            3: ("A", "Z"),
            4: ("Jane", "Roe"),
        }
        self.entry = FieldEntry("Players", "Vitals", "Identity", 0, {"normalized_name": "FIRSTNAME", "display_name": "First Name"})
        self.writes: list[tuple[int, str]] = []

    def _read_player_is_active(self, item: RecordListItem) -> bool:
        return self.active_by_index[item.index]

    def _read_named_value(self, _domain: str, item: RecordListItem, candidates: tuple[str, ...]) -> str:
        first, last = self.names_by_index[item.index]
        return first if candidates[0] == "FIRSTNAME" else last

    def grouped_fields(self, domain: str):
        if domain != "Players":
            raise AssertionError(domain)
        return {"Vitals": {"Identity": [self.entry]}}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: str):
        if entry is not self.entry:
            raise AssertionError(entry)
        self.writes.append((index, value))
        return {"display_value": value}


def generated_player(name: str, value: str):
    return SimpleNamespace(
        identity={"player": name},
        field_candidates=(
            SimpleNamespace(
                field_key="Vitals/FIRSTNAME",
                section="Vitals",
                group="Identity",
                normalized_name="FIRSTNAME",
                display_name="First Name",
                display_value=value,
            ),
        ),
    )


class PlayerGeneratorMissingImportTests(unittest.TestCase):
    def test_matched_name_import_includes_age_and_positions_from_vitals(self) -> None:
        generated = SimpleNamespace(
            field_candidates=(
                SimpleNamespace(field_key="Vitals/FIRSTNAME", section="Vitals", display_value="John"),
                SimpleNamespace(field_key="Vitals/AGE", section="Vitals", display_value=27),
                SimpleNamespace(field_key="Vitals/POSITION", section="Vitals", display_value="PG"),
                SimpleNamespace(field_key="Vitals/SECONDARYPOSITION", section="Vitals", display_value="SG"),
                SimpleNamespace(field_key="Vitals/HEIGHT", section="Vitals", display_value=78),
                SimpleNamespace(field_key="Attributes/HANDS", section="Attributes", display_value=80),
                SimpleNamespace(field_key="Tendencies/SHOT", section="Tendencies", display_value=75),
            )
        )

        rows = tuple(
            _generated_rows_for_import(
                generated,
                _MATCHED_NAME_IMPORT_SECTIONS,
                _MATCHED_NAME_IMPORT_FIELD_KEYS,
            )
        )

        self.assertEqual(
            (
                "Vitals/AGE",
                "Vitals/POSITION",
                "Vitals/SECONDARYPOSITION",
                "Attributes/HANDS",
                "Tendencies/SHOT",
            ),
            tuple(row.field_key for row in rows),
        )
        self.assertEqual(27, rows[0].display_value)

    def test_matched_name_import_writes_age_and_positions_without_other_vitals(self) -> None:
        entries = {
            "Vitals/AGE": FieldEntry("Players", "Vitals", "Identity", 0, {"normalized_name": "AGE", "display_name": "Age"}),
            "Vitals/POSITION": FieldEntry("Players", "Vitals", "Identity", 1, {"normalized_name": "POSITION", "display_name": "Position"}),
            "Vitals/SECONDARYPOSITION": FieldEntry("Players", "Vitals", "Identity", 2, {"normalized_name": "SECONDARYPOSITION", "display_name": "Secondary Position"}),
            "Vitals/HEIGHT": FieldEntry("Players", "Vitals", "Body", 3, {"normalized_name": "HEIGHT", "display_name": "Height"}),
            "Attributes/HANDS": FieldEntry("Players", "Attributes", "General", 4, {"normalized_name": "HANDS", "display_name": "Hands"}),
            "Tendencies/SHOT": FieldEntry("Players", "Tendencies", "General", 5, {"normalized_name": "SHOT", "display_name": "Shot"}),
        }

        class MatchedAgeModel:
            def __init__(self) -> None:
                self.writes: list[tuple[int, str, int]] = []

            def grouped_fields(self, domain: str):
                assert domain == "Players"
                return {
                    "Vitals": {
                        "Identity": [
                            entries["Vitals/AGE"],
                            entries["Vitals/POSITION"],
                            entries["Vitals/SECONDARYPOSITION"],
                        ],
                        "Body": [entries["Vitals/HEIGHT"]],
                    },
                    "Attributes": {"General": [entries["Attributes/HANDS"]]},
                    "Tendencies": {"General": [entries["Tendencies/SHOT"]]},
                }

            def write_entry_value(self, entry: FieldEntry, *, index: int, value: int):
                self.writes.append((index, f"{entry.section}/{entry.normalized_name}", value))
                return {"display_value": value}

        generated = SimpleNamespace(
            field_candidates=(
                SimpleNamespace(field_key="Vitals/AGE", section="Vitals", display_value=27),
                SimpleNamespace(field_key="Vitals/POSITION", section="Vitals", display_value="PG"),
                SimpleNamespace(field_key="Vitals/SECONDARYPOSITION", section="Vitals", display_value="SG"),
                SimpleNamespace(field_key="Vitals/HEIGHT", section="Vitals", display_value=78),
                SimpleNamespace(field_key="Attributes/HANDS", section="Attributes", display_value=80),
                SimpleNamespace(field_key="Tendencies/SHOT", section="Tendencies", display_value=75),
            )
        )
        model = MatchedAgeModel()

        result = apply_generated_players_to_game(
            model,
            (generated,),
            player_indices=(9,),
            include_sections=_MATCHED_NAME_IMPORT_SECTIONS,
            include_field_keys=_MATCHED_NAME_IMPORT_FIELD_KEYS,
            stop_on_error=True,
        )

        self.assertTrue(result.ok)
        self.assertCountEqual(
            (
                (9, "Vitals/AGE", 27),
                (9, "Vitals/POSITION", "PG"),
                (9, "Vitals/SECONDARYPOSITION", "SG"),
                (9, "Attributes/HANDS", 80),
                (9, "Tendencies/SHOT", 75),
            ),
            tuple(model.writes),
        )
        self.assertNotIn((9, "Vitals/HEIGHT", 78), model.writes)

    def test_missing_import_skips_active_existing_players_and_targets_active_a_z(self) -> None:
        model = MissingImportModel()
        generated = (
            generated_player("John Doe", "John"),
            generated_player("Jane Roe", "Jane"),
            generated_player("Sam Foo", "Sam"),
        )

        missing, target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, generated, placeholder_name="A Z")
        result = apply_generated_players_to_game(model, missing, player_indices=target_indices)

        self.assertEqual(1, skipped_existing)
        self.assertEqual(("Jane Roe", "Sam Foo"), tuple(item.identity["player"] for item in missing))
        self.assertEqual((2, 3), target_indices)
        self.assertEqual([(2, "Jane"), (3, "Sam")], model.writes)
        self.assertEqual(2, result.applied_players)
        self.assertEqual(2, result.generated_count)
        self.assertEqual(2, result.succeeded)
        self.assertEqual(0, result.failed)

    def test_missing_import_does_not_reuse_stale_a_z_label_after_live_name_changes(self) -> None:
        model = MissingImportModel()
        model.names_by_index[2] = ("Jane", "Roe")
        generated = (
            generated_player("Jane Roe", "Jane"),
            generated_player("Sam Foo", "Sam"),
            generated_player("Sam Foo", "Sam duplicate"),
        )

        missing, target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, generated, placeholder_name="A Z")
        result = apply_generated_players_to_game(model, missing, player_indices=target_indices)

        self.assertEqual(2, skipped_existing)
        self.assertEqual(("Sam Foo",), tuple(item.identity["player"] for item in missing))
        self.assertEqual((3,), target_indices)
        self.assertEqual([(3, "Sam")], model.writes)
        self.assertEqual(1, result.applied_players)

    def test_missing_import_treats_con_profane_filter_variants_as_existing(self) -> None:
        model = MissingImportModel()
        model.names_by_index[1] = ("Chuck", "Co nnors")
        generated = (
            generated_player("Chuck Conners", "Chuck"),
            generated_player("Chuck Conner", "Chuck"),
            generated_player("Sam Foo", "Sam"),
        )

        missing, target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, generated, placeholder_name="A Z")

        self.assertEqual(2, skipped_existing)
        self.assertEqual(("Sam Foo",), tuple(item.identity["player"] for item in missing))
        self.assertEqual((2, 3), target_indices)

    def test_missing_import_treats_fuc_profane_filter_variants_as_existing(self) -> None:
        model = MissingImportModel()
        model.names_by_index[1] = ("Max", "Fu chs")
        generated = (
            generated_player("Max Fuchs", "Max"),
            generated_player("Sam Foo", "Sam"),
        )

        missing, _target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, generated, placeholder_name="A Z")

        self.assertEqual(1, skipped_existing)
        self.assertEqual(("Sam Foo",), tuple(item.identity["player"] for item in missing))

    def test_regular_name_matching_uses_live_con_filter_variant(self) -> None:
        model = MissingImportModel()
        model.names_by_index[1] = ("Chuck", "Co nnors")

        matches = _generated_player_name_matches(model, (generated_player("Chuck Conners", "Chuck"),))

        self.assertEqual((1,), tuple(index for _generated, index in matches))

    def test_regular_name_matching_uses_live_fuc_filter_variant(self) -> None:
        model = MissingImportModel()
        model.names_by_index[1] = ("Max", "Fu chs")

        matches = _generated_player_name_matches(model, (generated_player("Max Fuchs", "Max"),))

        self.assertEqual((1,), tuple(index for _generated, index in matches))

    def test_missing_preview_returns_names_for_confirmation_dialog(self) -> None:
        model = MissingImportModel()
        state = GeneratorDisplayState(
            source_loaded=True,
            seasons=("2026",),
            selected_season="2026",
            league_filters=("All leagues",),
            selected_league="All leagues",
            position_filters=("All positions",),
            selected_position="All positions",
            source_team_filters=("All source teams",),
            selected_source_team="All source teams",
            players=(),
            selected_player="",
            status="",
            generated_proposals=(generated_player("John Doe", "John"), generated_player("Sam Foo", "Sam")),
        )

        summary = missing_generator_import_preview(model, state)

        self.assertEqual(("Sam Foo",), summary["names"])
        self.assertEqual(1, summary["missing_count"])
        self.assertEqual(2, summary["target_count"])
        self.assertEqual(1, summary["skipped_existing"])


if __name__ == "__main__":
    unittest.main()
