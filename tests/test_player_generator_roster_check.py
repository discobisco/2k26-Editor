from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

import display  # type: ignore[import-not-found]  # noqa: E402
from nba2k_editor.models.schema import RecordListItem  # noqa: E402
from nba2k_editor.ui.qt_app import QtEditorApp  # noqa: E402


class RosterCheckModel:
    def __init__(self) -> None:
        self.players = (
            RecordListItem("Players", 1, 0x1000, "John Doe"),
            RecordListItem("Players", 2, 0x2000, "A Z"),
            RecordListItem("Players", 3, 0x3000, "Jane Roe"),
        )
        self.loaded_items = {"Players": {player.index: player for player in self.players}}
        self.active_by_index = {1: True, 2: True, 3: False}
        self.names_by_index = {1: ("John", "Doe"), 2: ("A", "Z"), 3: ("Jane", "Roe")}

    def _read_player_is_active(self, item: RecordListItem) -> bool:
        return self.active_by_index[item.index]

    def _read_named_value(self, _domain: str, item: RecordListItem, candidates: tuple[str, ...]) -> str:
        first, last = self.names_by_index[item.index]
        return first if candidates[0] == "FIRSTNAME" else last


def source_player(name: str, player_id: str, team: str = "AAA") -> display.GeneratorSourceRosterPlayer:
    return display.GeneratorSourceRosterPlayer(name, (team,), player_id)


def generator_state() -> display.GeneratorDisplayState:
    return display.GeneratorDisplayState(
        source_loaded=True,
        seasons=("2026",),
        selected_season="2026",
        league_filters=("All leagues",),
        selected_league="All leagues",
        position_filters=("All positions",),
        selected_position="All positions",
        source_team_filters=("All source teams", "AAA"),
        selected_source_team="AAA",
        players=("John Doe | AAA | john01",),
        selected_player="John Doe | AAA | john01",
        status="Loaded",
    )


def test_display_roster_check_reuses_missing_player_check_for_full_selected_year(monkeypatch) -> None:
    all_year_players = (
        source_player("John Doe", "john01", "AAA"),
        source_player("Jane Roe", "jane01", "BBB"),
        source_player("Sam Foo", "sam01", "CCC"),
    )
    monkeypatch.setattr(display, "_source_roster_players_for_season", lambda season: all_year_players if season == 2026 else ())
    monkeypatch.setattr(display, "update_generator_display_selection", lambda state, **_kwargs: state)

    checked = display.check_loaded_roster_display_state(RosterCheckModel(), generator_state())

    assert checked.roster_check_season == "2026"
    assert checked.roster_check_source_count == 3
    assert checked.roster_check_loaded_count == 1
    assert checked.roster_check_missing_players == (
        "Jane Roe | BBB | jane01",
        "Sam Foo | CCC | sam01",
    )
    assert checked.status == "Checked loaded roster for 2026: 1/3 source players loaded; 2 not loaded."


def test_display_roster_check_requires_loaded_player_records(monkeypatch) -> None:
    model = SimpleNamespace(loaded_items={"Players": {}})
    monkeypatch.setattr(display, "_source_roster_players_for_season", lambda _season: (source_player("Sam Foo", "sam01"),))
    monkeypatch.setattr(display, "update_generator_display_selection", lambda state, **_kwargs: state)

    checked = display.check_loaded_roster_display_state(model, generator_state())

    assert checked.status == "Load Players before checking the loaded roster."
    assert checked.roster_check_season == ""
    assert checked.roster_check_missing_players == ()


def test_generator_output_lists_nonloaded_source_players() -> None:
    state = generator_state()
    state = SimpleNamespace(
        **{
            **state.__dict__,
            "status": "Checked loaded roster for 2026: 1/3 source players loaded; 2 not loaded.",
            "roster_check_season": "2026",
            "roster_check_missing_players": ("Jane Roe | BBB | jane01", "Sam Foo | CCC | sam01"),
        }
    )
    app_stub = SimpleNamespace(
        player_generator_state=state,
        _generator_display_module=lambda: display,
    )

    text = QtEditorApp._generator_display_text(app_stub)  # type: ignore[arg-type]

    assert "Source players not loaded for 2026 (2):" in text
    assert "Jane Roe | BBB | jane01" in text
    assert "Sam Foo | CCC | sam01" in text


def test_check_roster_button_runs_the_roster_check_action() -> None:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

    qt_application = QApplication.instance() or QApplication([])
    window = QtEditorApp.__new__(QtEditorApp)
    QMainWindow.__init__(window)
    window.model = SimpleNamespace()
    window.player_generator_state = display.empty_generator_display_state()
    window.generator_text = None
    window.generator_year_combo = None
    window.generator_league_combo = None
    window.generator_position_combo = None
    window.generator_source_team_combo = None
    window.generator_player_combo = None
    calls: list[tuple[str, int]] = []

    fake_display = SimpleNamespace(
        load_generator_display_state=lambda: generator_state(),
        check_loaded_roster_display_state=lambda _model, state, progress_callback=None: (
            calls.append((state.selected_season, 1))
            or replace(
                state,
                status="Checked loaded roster for 2026: 1/3 source players loaded; 2 not loaded.",
                roster_check_season="2026",
                roster_check_source_count=3,
                roster_check_loaded_count=1,
                roster_check_missing_players=("Jane Roe | BBB | jane01", "Sam Foo | CCC | sam01"),
            )
        ),
        empty_generator_display_state=display.empty_generator_display_state,
    )
    window.player_generator_display = fake_display
    window._start_background_operation = lambda _title, worker, done_callback=None: (
        done_callback(worker()) if done_callback is not None else worker()
    )

    screen = window._build_player_generator_screen()
    button = next(button for button in screen.findChildren(QPushButton) if button.text() == "Check Roster")
    button.click()
    qt_application.processEvents()

    assert calls == [("2026", 1)]
    assert window.player_generator_state.roster_check_missing_players == (
        "Jane Roe | BBB | jane01",
        "Sam Foo | CCC | sam01",
    )
    assert "Source players not loaded for 2026 (2):" in window.generator_text.toPlainText()
