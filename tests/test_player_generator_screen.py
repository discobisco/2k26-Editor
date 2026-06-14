from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nba2k_editor.ui.player_generator_screen import (
    ALL_TEAMS_FILTER,
    MAX_PREVIEW_ROWS,
    PLAYER_GENERATOR_SCREEN,
    PlayerGeneratorScreenState,
    PlayerGeneratorBatchPreview,
    PlayerGeneratorPreview,
    PlayerGeneratorPreviewRow,
    apply_batch_to_game,
    apply_preview_to_game,
    build_player_generator_preview,
    generate_preview_from_option_into_state,
    generate_preview_into_state,
    generate_year_into_state,
    generator_player_options,
    generator_team_filter_options,
    generator_year_options,
    select_generated_preview_into_state,
)
from nba2k_editor.ui import dpg_editor


class FakeDpg:
    def __init__(self) -> None:
        self.values = {
            "Player_Generator__year": "2025",
            "Player_Generator__team_filter": "NYK",
            "Player_Generator__player": "Jalen Brunson (brunsja01) — NYK",
        }

    def get_value(self, tag: str) -> str:
        return self.values[tag]

    def set_value(self, tag: str, value: str) -> None:
        self.values[tag] = value

    def does_item_exist(self, tag: str) -> bool:
        return True

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.values[f"{tag}:config"] = str(kwargs)


class FakeGameModel:
    def __init__(self) -> None:
        self.writes: list[tuple[str, int, object]] = []

    def write_entry_value(self, entry, *, index: int, value: object, stat_selector: object | None = None) -> dict[str, object]:
        self.writes.append((f"{entry.section}/{entry.normalized_name}", index, value))
        return {"display_value": value}


def _fake_proposal(player_id: str, team: str, player: str) -> SimpleNamespace:
    return SimpleNamespace(
        player_id=player_id,
        season=2025,
        team=team,
        identity={"player": player},
        field_candidates=(
            SimpleNamespace(
                field_key="Attributes/3POINT",
                section="Attributes",
                group="Offense",
                display_name="3pt Shot",
                display_value=85,
                source_rule="test",
            ),
        ),
        warnings=(),
    )


class PlayerGeneratorScreenTests(unittest.TestCase):
    def test_player_generator_screen_is_registered_as_preview_only_nav_screen(self) -> None:
        self.assertIn(PLAYER_GENERATOR_SCREEN, dpg_editor.NAV_ORDER)
        self.assertNotIn(PLAYER_GENERATOR_SCREEN, dpg_editor.EDITOR_DOMAINS)
        self.assertIn(PLAYER_GENERATOR_SCREEN, dpg_editor.APP_SCREENS)

    def test_import_generator_scope_controls_and_nonblocking_worker_are_wired(self) -> None:
        module_source = inspect.getsource(dpg_editor)
        source = inspect.getsource(dpg_editor.DpgEditorApp)
        generator_source = source[source.find("def _build_player_generator_screen"): source.find("def _add_button_strip")]
        self.assertIn('dpg.add_text("Import Generator")', generator_source)
        self.assertIn('dpg.add_text("Import Scope")', generator_source)
        self.assertIn('dpg.add_text("Roster")', generator_source)
        self.assertIn('dpg.add_text("Player")', generator_source)
        self.assertIn('tag=self._player_generator_scope_group_tag("roster"), show=False', generator_source)
        self.assertIn('tag=self._player_generator_scope_group_tag("player"), show=False', generator_source)
        self.assertIn('show=import_scope in {"Roster", "Player"}', generator_source)
        self.assertIn('show=import_scope == "Player"', generator_source)
        self.assertIn('label="Generate"', generator_source)
        self.assertIn('label="Apply Generated"', generator_source)
        self.assertIn('"Full Season", "Roster", "Player", "Draft Class"', module_source)
        self.assertNotIn('label="Generate Player"', generator_source)
        self.assertNotIn('label="Apply To Selected Player"', generator_source)
        self.assertNotIn('label="Generate Team"', generator_source)
        self.assertNotIn('label="Apply Team"', generator_source)
        self.assertNotIn('label="Generate Preview"', generator_source)
        self.assertNotIn('dpg.add_text("Preview Player")', generator_source)
        self.assertNotIn('with dpg.table', generator_source)
        self.assertIn("threading.Thread", generator_source)
        self.assertIn("apply_selected_generated_player_to_game", source)
        self.assertIn("apply_batch_to_game", generator_source)

    def test_actual_player_preview_uses_generator_proposal_without_live_write(self) -> None:
        preview = build_player_generator_preview(season=2025, player_id="brunsja01", team="NYK")

        self.assertEqual(preview.player_id, "brunsja01")
        self.assertEqual(preview.player_name, "Jalen Brunson")
        self.assertEqual(preview.season, 2025)
        self.assertEqual(preview.team, "NYK")
        self.assertGreater(len(preview.rows), 100)
        by_key = {row.field_key: row for row in preview.rows}
        self.assertIn("Attributes/3POINT", by_key)
        self.assertIn("Tendencies/TOUCHES", by_key)
        shot3 = int(by_key["Attributes/3POINT"].value)
        touches = int(by_key["Tendencies/TOUCHES"].value)
        self.assertGreaterEqual(shot3, 25)
        self.assertLessEqual(shot3, 99)
        self.assertGreaterEqual(touches, 0)
        self.assertLessEqual(touches, 100)

        source = inspect.getsource(dpg_editor)
        self.assertNotIn("write_entry_value", source[source.find("def _build_player_generator_screen"): source.find("def run")])

    def test_year_team_and_player_dropdowns_use_actual_workbook_rows(self) -> None:
        years = generator_year_options()
        teams = generator_team_filter_options(season=2025)
        nyk_players = generator_player_options(season=2025, team_filter="NYK")

        self.assertIn(2025, years)
        self.assertIn(ALL_TEAMS_FILTER, teams)
        self.assertIn("NYK", teams)
        self.assertNotIn("2TM", teams)
        self.assertNotIn("3TM", teams)
        brunson = next(option for option in nyk_players if option.player_id == "brunsja01")
        self.assertEqual(brunson.team, "NYK")
        self.assertIn("Jalen Brunson", brunson.label)
        self.assertFalse(any(option.player_id == "beaucma01" for option in nyk_players))
        self.assertTrue(any(option.player_id == "beaucma01" for option in generator_player_options(season=2025, team_filter="LAC")))

    def test_generate_preview_from_dropdown_option_updates_state(self) -> None:
        state = PlayerGeneratorScreenState()
        brunson = next(option for option in generator_player_options(season=2025, team_filter="NYK") if option.player_id == "brunsja01")

        preview = generate_preview_from_option_into_state(
            state,
            season=2025,
            team_filter="NYK",
            player_option_label=brunson.label,
        )

        self.assertIs(state.preview, preview)
        self.assertEqual(state.team_filter, "NYK")
        self.assertEqual(state.player_option, brunson.label)
        self.assertEqual(state.player_id, "brunsja01")
        self.assertEqual(state.team, "NYK")
        self.assertEqual(preview.player_name, "Jalen Brunson")

    def test_generate_year_into_state_generates_selected_team_and_shows_selected(self) -> None:
        state = PlayerGeneratorScreenState()
        brunson = next(option for option in generator_player_options(season=2025, team_filter="NYK") if option.player_id == "brunsja01")
        fake_batch = SimpleNamespace(
            season=2025,
            proposals=(
                _fake_proposal("brunsja01", "NYK", "Jalen Brunson"),
                _fake_proposal("hartjo01", "NYK", "Josh Hart"),
            ),
        )

        with patch("player_generator.generate_player_proposals_for_contract", return_value=fake_batch) as batch_call:
            batch = generate_year_into_state(state, season=2025, team_filter="NYK", player_option_label=brunson.label)

        self.assertIs(state.batch, batch)
        self.assertEqual(state.generated_count, 2)
        self.assertIsNotNone(state.preview)
        self.assertEqual(state.preview.player_id, "brunsja01")
        self.assertIn("Generated 2 players for 2025 roster NYK", state.status)
        batch_call.assert_called_once()
        self.assertEqual(batch_call.call_args.kwargs["team_filter"], "NYK")

    def test_select_generated_preview_switches_display_without_regenerating(self) -> None:
        state = PlayerGeneratorScreenState(season=2025, team_filter="NYK")
        brunson = next(option for option in generator_player_options(season=2025, team_filter="NYK") if option.player_id == "brunsja01")
        hart = next(option for option in generator_player_options(season=2025, team_filter="NYK") if option.player_id == "hartjo01")
        fake_batch = SimpleNamespace(
            season=2025,
            proposals=(
                _fake_proposal("brunsja01", "NYK", "Jalen Brunson"),
                _fake_proposal("hartjo01", "NYK", "Josh Hart"),
            ),
        )
        with patch("player_generator.generate_player_proposals_for_contract", return_value=fake_batch):
            generate_year_into_state(state, season=2025, team_filter="NYK", player_option_label=brunson.label)

        preview = select_generated_preview_into_state(state, player_option_label=hart.label)

        if preview is None:
            self.fail("expected generated preview")
        self.assertEqual(preview.player_id, "hartjo01")
        self.assertEqual(preview.player_name, "Josh Hart")
        self.assertIn("Generated 2 players for 2025 roster NYK", state.status)

    def test_generate_preview_updates_state(self) -> None:
        state = PlayerGeneratorScreenState()
        preview = generate_preview_into_state(state, season=2025, player_id="brunsja01", team="nyk")

        self.assertIs(state.preview, preview)
        self.assertEqual(state.team, "NYK")
        self.assertIn("Generated player", state.status)
        self.assertLessEqual(min(len(preview.rows), MAX_PREVIEW_ROWS), MAX_PREVIEW_ROWS)

    def test_apply_preview_to_game_writes_preview_rows_to_selected_player_index(self) -> None:
        state = PlayerGeneratorScreenState(
            preview=PlayerGeneratorPreview(
                player_id="brunsja01",
                season=2025,
                team="NYK",
                player_name="Jalen Brunson",
                rows=(
                    PlayerGeneratorPreviewRow(field_key="Vitals/FIRSTNAME", section="Vitals", group="ID", field="First Name", value="Jalen", source_rule="test"),
                    PlayerGeneratorPreviewRow(field_key="Attributes/3POINT", section="Attributes", group="Offense", field="3pt Shot", value=88, source_rule="test"),
                ),
                warnings=(),
            )
        )
        model = FakeGameModel()

        result = apply_preview_to_game(model, state, player_index=12)

        self.assertTrue(result.ok)
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(model.writes, [("Vitals/FIRSTNAME", 12, "Jalen"), ("Attributes/3POINT", 12, 88)])
        self.assertIn("Applied 2/2 generated fields", state.status)

    def test_apply_batch_to_game_writes_generated_players_to_index_mapping(self) -> None:
        first = PlayerGeneratorPreview(
            player_id="one",
            season=2025,
            team="NYK",
            player_name="One",
            rows=(PlayerGeneratorPreviewRow(field_key="Vitals/FIRSTNAME", section="Vitals", group="ID", field="First Name", value="One", source_rule="test"),),
            warnings=(),
        )
        second = PlayerGeneratorPreview(
            player_id="two",
            season=2025,
            team="NYK",
            player_name="Two",
            rows=(PlayerGeneratorPreviewRow(field_key="Vitals/FIRSTNAME", section="Vitals", group="ID", field="First Name", value="Two", source_rule="test"),),
            warnings=(),
        )
        state = PlayerGeneratorScreenState(batch=PlayerGeneratorBatchPreview(season=2025, previews=(first, second)))
        model = FakeGameModel()

        result = apply_batch_to_game(model, state, player_indices=(20, 21))

        self.assertTrue(result.ok)
        self.assertEqual(result.applied_players, 2)
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(model.writes, [("Vitals/FIRSTNAME", 20, "One"), ("Vitals/FIRSTNAME", 21, "Two")])
        self.assertIn("Applied 2 generated players", state.status)


if __name__ == "__main__":
    unittest.main()
