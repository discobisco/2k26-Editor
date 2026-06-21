from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


class PlayerGeneratorDisplayTests(unittest.TestCase):
    def test_display_facade_loads_source_options_without_ui_state_index(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")

        state = display.load_generator_display_state(selected_season=2025)

        self.assertTrue(state.source_loaded)
        self.assertEqual("2025", state.selected_season)
        self.assertIn("GSW", state.source_team_filters)
        self.assertTrue(any("Stephen Curry | GSW | curryst01" == player for player in state.players))
        player_ids = [player.rsplit(" | ", 1)[-1] for player in state.players]
        self.assertEqual(len(player_ids), len(set(player_ids)))
        self.assertEqual(state.players[0], state.selected_player)
        self.assertEqual((), state.rows)

    def test_display_selection_keeps_visible_player_value_after_team_change(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")

        state = display.load_generator_display_state(selected_season=2025)
        state = display.update_generator_display_selection(state, selected_source_team="GSW")

        self.assertGreater(len(state.players), 0)
        self.assertEqual(state.players[0], state.selected_player)
        self.assertIn(" | GSW | ", state.selected_player)

    def test_display_facade_generates_player_table_rows(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")

        state = display.load_generator_display_state(selected_season=2025)
        state = display.update_generator_display_selection(state, selected_source_team="GSW")
        state = display.generate_generator_preview_display_state(state)

        self.assertGreater(len(state.player_rows), 10)
        self.assertGreaterEqual(len(state.field_columns), 175)
        curry = next(row for row in state.player_rows if row.player == "Stephen Curry")
        self.assertEqual("GSW", curry.source_team)
        self.assertEqual("curryst01", curry.player_id)
        self.assertEqual(len(state.field_columns), len(curry.values))
        self.assertIn("Vitals / ID / First Name", state.field_columns)
        displayed_keys = {(row.player_id, row.source_team) for row in state.player_rows}
        generated_keys = {(proposal.player_id, proposal.team) for proposal in state.generated_proposals}
        self.assertEqual(generated_keys, displayed_keys)

    def test_all_source_display_rows_match_generated_context_keys_for_2026(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")

        state = display.load_generator_display_state(selected_season=2026)
        state = display.generate_generator_preview_display_state(state)

        displayed_keys = {(row.player_id, row.source_team) for row in state.player_rows}
        generated_keys = {(proposal.player_id, proposal.team) for proposal in state.generated_proposals}
        self.assertEqual(582, len(displayed_keys))
        self.assertEqual(generated_keys, displayed_keys)
        self.assertFalse(any(all(value == "" for value in row.values) for row in state.player_rows))

    def test_dropdown_refresh_preserves_preview_when_selection_is_unchanged(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")

        state = display.load_generator_display_state(selected_season=2025)
        state = display.update_generator_display_selection(state, selected_source_team="GSW")
        state = display.generate_generator_preview_display_state(state)
        generated_proposals = state.generated_proposals
        player_rows = state.player_rows

        refreshed = display.update_generator_display_selection(
            state,
            selected_season=state.selected_season,
            selected_source_team=state.selected_source_team,
            selected_player=state.selected_player,
        )

        self.assertEqual(generated_proposals, refreshed.generated_proposals)
        self.assertEqual(player_rows, refreshed.player_rows)

    def test_import_facade_calls_existing_game_port_import(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")
        display._ensure_generator_import_path()
        game_port = import_module("game_port")
        calls: list[tuple[Any, Any, tuple[Any, ...], str | None, bool]] = []

        def fake_import(model: object, contract: object, *, generated_players: tuple[Any, ...] = (), team_filter: str | None = None, match_existing_player_names: bool = False) -> object:
            calls.append((model, contract, tuple(generated_players), team_filter, match_existing_player_names))
            return SimpleNamespace(apply_result=SimpleNamespace(applied_players=2, generated_count=2, succeeded=350, failed=0))

        original_import = getattr(game_port, "import_generated_players_to_game")
        try:
            setattr(game_port, "import_generated_players_to_game", fake_import)
            model = object()
            state = display.load_generator_display_state(selected_season=2025)
            state = display.update_generator_display_selection(state, selected_source_team="GSW")
            state = display.generate_generator_preview_display_state(state)
            generated_proposals = state.generated_proposals

            state = display.import_generator_to_game_display_state(model, state)
        finally:
            setattr(game_port, "import_generated_players_to_game", original_import)

        self.assertEqual(1, len(calls))
        called_model, contract, generated_players, team_filter, match_existing_player_names = calls[0]
        self.assertIs(model, called_model)
        self.assertEqual(2025, contract.season)
        self.assertEqual("overwrite_current_roster", contract.output_target.value)
        self.assertEqual("Player Generator 2025", contract.roster_label)
        self.assertEqual(generated_proposals, generated_players)
        self.assertEqual("GSW", team_filter)
        self.assertFalse(match_existing_player_names)
        self.assertIn("Imported 2/2 generated players", state.status)

    def test_import_facade_requires_displayed_preview_before_import(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")
        display._ensure_generator_import_path()
        game_port = import_module("game_port")
        calls: list[tuple[Any, ...]] = []

        def fake_import(model: object, contract: object, *, generated_players: tuple[Any, ...] = (), team_filter: str | None = None, match_existing_player_names: bool = False) -> object:
            calls.append((model, contract, tuple(generated_players), team_filter, match_existing_player_names))
            return SimpleNamespace(apply_result=SimpleNamespace(applied_players=len(tuple(generated_players)), generated_count=len(tuple(generated_players)), succeeded=350, failed=0))

        original_import = getattr(game_port, "import_generated_players_to_game")
        try:
            setattr(game_port, "import_generated_players_to_game", fake_import)
            state = display.load_generator_display_state(selected_season=2025)
            state = display.update_generator_display_selection(state, selected_source_team="GSW")

            state = display.import_generator_to_game_display_state(object(), state)
        finally:
            setattr(game_port, "import_generated_players_to_game", original_import)

        self.assertEqual([], calls)
        self.assertEqual((), state.generated_proposals)
        self.assertIn("Display preview before importing", state.status)

    def test_import_facade_can_request_existing_player_name_matching(self) -> None:
        display = import_module("nba2k_editor.Player Generator.display")
        display._ensure_generator_import_path()
        game_port = import_module("game_port")
        calls: list[dict[str, object]] = []

        def fake_import(model: object, contract: object, **kwargs: object) -> object:
            calls.append(dict(kwargs))
            return SimpleNamespace(apply_result=SimpleNamespace(applied_players=2, generated_count=2, succeeded=350, failed=0))

        original_import = getattr(game_port, "import_generated_players_to_game")
        try:
            setattr(game_port, "import_generated_players_to_game", fake_import)
            state = display.load_generator_display_state(selected_season=2025)
            state = display.update_generator_display_selection(state, selected_source_team="GSW")
            state = display.generate_generator_preview_display_state(state)
            state = display.import_generator_to_game_display_state(object(), state, match_existing_player_names=True)
        finally:
            setattr(game_port, "import_generated_players_to_game", original_import)

        self.assertEqual(1, len(calls))
        self.assertTrue(calls[0]["match_existing_player_names"])
        self.assertEqual(state.generated_proposals, calls[0]["generated_players"])
        self.assertEqual("GSW", calls[0]["team_filter"])
        self.assertIn("matching loaded Players names", state.status)

    def test_dpg_grid_text_uses_padded_columns_not_tabs(self) -> None:
        editor = import_module("nba2k_editor.ui.dpg_editor")
        app = editor.DpgEditorApp(SimpleNamespace())
        rows = (
            SimpleNamespace(player="A", source_team="GSW", player_id="one", values=("1", "long")),
            SimpleNamespace(player="Long Player", source_team="NYK", player_id="two", values=("22", "x")),
        )

        text = app._generator_grid_text(("Short", "Long Header"), rows)

        self.assertNotIn("\t", text)
        lines = text.splitlines()
        self.assertEqual(lines[0].index("|"), lines[2].index("|"))
        self.assertEqual(lines[0].rindex("|"), lines[3].rindex("|"))

    def test_dpg_editor_contains_display_screen_without_generator_business_imports(self) -> None:
        source = (REPO_ROOT / "nba2k_editor" / "ui" / "dpg_editor.py").read_text(encoding="utf-8")

        self.assertIn('PLAYER_GENERATOR_SCREEN = "Player Generator"', source)
        self.assertIn('import_module("nba2k_editor.Player Generator.display")', source)
        self.assertIn("def _build_player_generator_screen", source)
        self.assertIn("def _import_generator_to_game_display", source)
        build_source = source[source.find("def _build_player_generator_screen"): source.find("def _build_players_screen")]
        self.assertIn('label="Import Generated Players"', build_source)
        self.assertIn('label="Import Matched Names"', build_source)
        self.assertNotIn("dpg.table", build_source)
        self.assertIn("_generator_table_tag", build_source)
        self.assertNotIn("_generator_player_tag", source)
        self.assertNotIn("GENERATOR_FIELD_PREVIEW_ROWS", source)
        self.assertIn("multiline=True", build_source)
        self.assertFalse((REPO_ROOT / "nba2k_editor" / "ui" / "player_generator_screen.py").exists())
        forbidden = (
            "workbook_sqlite",
            "ensure_workbook_sqlite_database",
            "iter_workbook_sqlite_sheet_rows",
            "season_context_index",
            "generate_player_proposal_from_contract",
            "GeneratorInputContract",
            "OutputTarget",
            "game_port",
            "apply_generated",
            "cache_clear",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()

