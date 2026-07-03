from __future__ import annotations

import os
import threading
import unittest
from dataclasses import dataclass, replace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from tests.test_qt_editor_players_screen import PlayerScreenModel
from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@dataclass(frozen=True)
class GeneratorState:
    source_loaded: bool = False
    seasons: tuple[str, ...] = ()
    selected_season: str = ""
    source_team_filters: tuple[str, ...] = ("All source teams",)
    selected_source_team: str = "All source teams"
    players: tuple[str, ...] = ()
    selected_player: str = ""
    status: str = "empty"
    field_columns: tuple[str, ...] = ()
    player_rows: tuple[Any, ...] = ()


class FakeGeneratorDisplay:
    def __init__(self) -> None:
        self.import_match_flags: list[bool] = []
        self.selections: list[tuple[str | int | None, str | None, str | None]] = []
        self.add_started = threading.Event()
        self.add_release = threading.Event()
        self.block_add = False

    def empty_generator_display_state(self, status: str = "empty") -> GeneratorState:
        return GeneratorState(status=status)

    def load_generator_display_state(self, *, selected_season: str | int | None = None) -> GeneratorState:
        return GeneratorState(
            source_loaded=True,
            seasons=("2026", "2025"),
            selected_season="2026",
            source_team_filters=("All source teams", "PHI"),
            selected_source_team="All source teams",
            players=("1 | PHI | Alpha", "2 | PHI | Beta"),
            selected_player="1 | PHI | Alpha",
            status="loaded",
        )

    def update_generator_display_selection(
        self,
        state: GeneratorState,
        *,
        selected_season: str | int | None = None,
        selected_source_team: str | None = None,
        selected_player: str | None = None,
    ) -> GeneratorState:
        self.selections.append((selected_season, selected_source_team, selected_player))
        players = ("3 | PHI | Gamma",) if selected_source_team == "PHI" else state.players
        selected = selected_player if selected_player in players else players[0]
        return replace(
            state,
            selected_season=str(selected_season or state.selected_season),
            selected_source_team=selected_source_team or state.selected_source_team,
            players=players,
            selected_player=selected,
            status="selection updated",
        )

    def generate_generator_preview_display_state(self, state: GeneratorState) -> GeneratorState:
        return replace(state, status="preview", field_columns=("Attributes/OVR",), player_rows=())

    def sync_generator_pool_display_state(self, state: GeneratorState, *, progress_callback: Any | None = None) -> GeneratorState:
        if progress_callback is not None:
            progress_callback(1, 1, "synced")
        return replace(state, status="synced")

    def add_current_roster_to_pool_display_state(self, model: Any, state: GeneratorState, *, progress_callback: Any | None = None) -> GeneratorState:
        self.add_started.set()
        if self.block_add:
            self.add_release.wait(2)
        if progress_callback is not None:
            progress_callback(1, 1, "added")
        return replace(state, status="added")

    def import_generator_to_game_display_state(
        self,
        model: Any,
        state: GeneratorState,
        *,
        match_existing_player_names: bool = False,
        progress_callback: Any | None = None,
    ) -> GeneratorState:
        self.import_match_flags.append(match_existing_player_names)
        if progress_callback is not None:
            progress_callback(1, 1, "imported")
        return replace(state, status="imported matched" if match_existing_player_names else "imported")


class QtEditorGeneratorScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def _app_with_fake_display(self) -> tuple[QtEditorApp, FakeGeneratorDisplay]:
        app = QtEditorApp(PlayerScreenModel())  # type: ignore[arg-type]
        display = FakeGeneratorDisplay()
        app.player_generator_display = display
        app.player_generator_state = display.empty_generator_display_state()
        return app, display

    def _finish_operation(self, app: QtEditorApp) -> None:
        thread = app.operation_thread
        self.assertIsNotNone(thread)
        assert thread is not None
        thread.join(2)
        app._poll_background_operation()

    def test_load_source_populates_generator_selectors_without_relisting_players_in_output(self) -> None:
        app, _display = self._app_with_fake_display()

        app._load_player_generator_source()
        self._finish_operation(app)

        self.assertEqual("2026", app.generator_year_combo.currentText())
        self.assertEqual("All source teams", app.generator_source_team_combo.currentText())
        self.assertEqual("1 | PHI | Alpha", app.generator_player_combo.currentText())
        self.assertNotIn("\nPlayers:", app.generator_text.toPlainText())
        self.assertNotIn("1 | PHI | Alpha", app.generator_text.toPlainText())

    def test_generator_source_team_selection_updates_display_state(self) -> None:
        app, display = self._app_with_fake_display()
        app._load_player_generator_source()
        self._finish_operation(app)

        app.generator_source_team_combo.setCurrentText("PHI")

        self.assertIn(("2026", "PHI", None), display.selections)
        self.assertEqual("PHI", app.player_generator_state.selected_source_team)
        self.assertEqual("3 | PHI | Gamma", app.generator_player_combo.currentText())
        self.assertNotIn("3 | PHI | Gamma", app.generator_text.toPlainText())

    def test_import_matched_names_passes_explicit_match_flag(self) -> None:
        app, display = self._app_with_fake_display()
        app._load_player_generator_source()
        self._finish_operation(app)

        app._import_generator_to_game_display(match_existing_player_names=True)
        self._finish_operation(app)

        self.assertEqual([True], display.import_match_flags)
        self.assertEqual("imported matched", app.player_generator_state.status)

    def test_add_current_roster_to_pool_runs_off_ui_thread_with_progress_dialog(self) -> None:
        app, display = self._app_with_fake_display()
        app.player_generator_state = display.load_generator_display_state()
        app._sync_player_generator_status()
        display.block_add = True

        app._add_current_roster_to_player_pool()

        self.assertIsNotNone(app.operation_dialog)
        self.assertTrue(display.add_started.wait(1))
        thread = app.operation_thread
        self.assertIsNotNone(thread)
        assert thread is not None
        self.assertTrue(thread.is_alive())

        display.add_release.set()
        self._finish_operation(app)
        self.assertEqual("added", app.player_generator_state.status)


if __name__ == "__main__":
    unittest.main()
