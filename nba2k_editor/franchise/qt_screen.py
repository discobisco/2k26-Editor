from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nba2k_editor.franchise.draft_room import (
    available_players,
    build_active_player_draft_pool,
    draft_position,
    draft_turn_owner,
    find_available_player,
    find_available_player_by_index,
    league_team_indexes,
    stored_pick_from_player,
    team_labels_from_model,
)
from nba2k_editor.franchise.llm_pick_runner import LlmDraftPickResult, run_llm_fantasy_draft_pick
from nba2k_editor.franchise.models import FantasyDraftState, FranchiseRecord, FranchiseSetup, FranchiseTeamOption
from nba2k_editor.franchise.storage import DEFAULT_FRANCHISE_DB_PATH, FranchiseRepository, team_options_from_model

FRANCHISE_SCREEN_TITLE = "Franchise"


class FranchiseScreen(QWidget):
    def __init__(self, model: Any, *, db_path: str | Path = DEFAULT_FRANCHISE_DB_PATH) -> None:
        super().__init__()
        self.model = model
        self.repository = FranchiseRepository(db_path)
        self.team_options: tuple[FranchiseTeamOption, ...] = ()
        self.team_checkboxes: dict[int, QCheckBox] = {}
        self.user_team_combo: QComboBox | None = None
        self.start_year_input: QLineEdit | None = None
        self.full_league_save_checkbox: QCheckBox | None = None
        self.fantasy_draft_checkbox: QCheckBox | None = None
        self.dashboard_text: QTextEdit | None = None
        self.draft_status_text: QTextEdit | None = None
        self.draft_player_combo: QComboBox | None = None
        self.draft_action_buttons: list[QPushButton] = []
        self._llm_pick_thread: threading.Thread | None = None
        self._llm_pick_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._llm_pick_timer = QTimer(self)
        self._llm_pick_timer.setInterval(100)
        self._llm_pick_timer.timeout.connect(self._poll_llm_pick)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(12, 10, 12, 12)
        self.root_layout.setSpacing(8)
        self._body: QWidget | None = None
        self.refresh_entry_menu()

    def refresh_entry_menu(self) -> None:
        if self.repository.exists():
            self._show_existing_franchise_menu()
        else:
            self._show_new_franchise_setup()

    def _replace_body(self, widget: QWidget) -> None:
        if self._body is not None:
            self.root_layout.removeWidget(self._body)
            self._body.deleteLater()
        self._body = widget
        self.root_layout.addWidget(widget, 1)

    def _header(self, title: str, body: str) -> QWidget:
        header = QWidget()
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("DashboardTitle")
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        return header

    def _show_existing_franchise_menu(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._header(
                "Franchise",
                f"Existing franchise SQL found: {self.repository.db_path}. Choose New to replace setup, or Load to enter it.",
            )
        )
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("New", clicked=self._show_new_franchise_setup))
        buttons.addWidget(QPushButton("Load", clicked=self._load_franchise_dashboard))
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self._replace_body(widget)

    def _show_new_franchise_setup(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._header(
                "New Franchise Setup",
                "Set the true franchise start year, select your team, choose whether to save the full loaded league dataset, select AI league teams, and mark fantasy draft starts.",
            )
        )
        self.team_options = team_options_from_model(self.model)
        form_box = QGroupBox("League Setup")
        form = QFormLayout(form_box)
        self.start_year_input = QLineEdit("2025")
        user_team_combo = QComboBox()
        for option in self.team_options:
            user_team_combo.addItem(option.display_label, option.team_index)
        user_team_combo.currentIndexChanged.connect(lambda _index: self._sync_user_team_llm_checkbox())
        self.user_team_combo = user_team_combo
        self.full_league_save_checkbox = QCheckBox("Keep a full loaded league save using all known offsets")
        self.fantasy_draft_checkbox = QCheckBox("League starts with a fantasy draft")
        form.addRow("Start Year", self.start_year_input)
        form.addRow("Your Team", self.user_team_combo)
        form.addRow("Full League Save", self.full_league_save_checkbox)
        form.addRow("Fantasy Draft", self.fantasy_draft_checkbox)
        layout.addWidget(form_box)
        layout.addWidget(self._build_team_checkbox_box(self.team_options), 1)
        self._sync_user_team_llm_checkbox()
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Start Franchise", clicked=self._start_franchise))
        if self.repository.exists():
            buttons.addWidget(QPushButton("Back", clicked=self._show_existing_franchise_menu))
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._replace_body(widget)

    def _build_team_checkbox_box(self, options: tuple[FranchiseTeamOption, ...]) -> QWidget:
        box = QGroupBox("AI League Teams")
        box_layout = QVBoxLayout(box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        team_widget = QWidget()
        team_layout = QVBoxLayout(team_widget)
        self.team_checkboxes = {}
        for option in options:
            checkbox = QCheckBox(option.display_label)
            checkbox.setProperty("team_index", option.team_index)
            checkbox.setProperty("team_label", option.label)
            self.team_checkboxes[option.team_index] = checkbox
            team_layout.addWidget(checkbox)
        team_layout.addStretch(1)
        scroll.setWidget(team_widget)
        box_layout.addWidget(scroll)
        return box

    def _selected_team_indexes(self) -> tuple[int, ...]:
        return tuple(sorted(index for index, checkbox in self.team_checkboxes.items() if checkbox.isChecked()))

    def _selected_user_team_index(self) -> int:
        if self.user_team_combo is None:
            return 0
        data = self.user_team_combo.currentData()
        return int(data) if data is not None else int(self.user_team_combo.currentIndex())

    def _sync_user_team_llm_checkbox(self) -> None:
        user_team_index = self._selected_user_team_index()
        for team_index, checkbox in self.team_checkboxes.items():
            is_user_team = team_index == user_team_index
            if is_user_team:
                checkbox.setChecked(False)
            checkbox.setEnabled(not is_user_team)
            checkbox.setToolTip("User-controlled team" if is_user_team else "Checked teams join the league as AI-controlled teams; unchecked teams are excluded")

    def _current_setup(self) -> FranchiseSetup:
        if self.start_year_input is None or self.full_league_save_checkbox is None or self.fantasy_draft_checkbox is None:
            raise ValueError("franchise setup form is not active")
        start_year_text = self.start_year_input.text().strip()
        if not start_year_text.isdigit():
            raise ValueError("Start Year must be a number")
        return FranchiseSetup(
            start_year=int(start_year_text),
            keep_full_league_save=self.full_league_save_checkbox.isChecked(),
            llm_gm_team_indexes=self._selected_team_indexes(),
            fantasy_draft=self.fantasy_draft_checkbox.isChecked(),
            user_team_index=self._selected_user_team_index(),
        )

    def _start_franchise(self) -> None:
        try:
            setup = self._current_setup()
        except ValueError as exc:
            QMessageBox.warning(self, "Franchise setup", str(exc))
            return
        snapshot = None
        if setup.keep_full_league_save:
            snapshot = self.model.app_dataset_snapshot() if hasattr(self.model, "app_dataset_snapshot") else {}
        teams = team_options_from_model(self.model)
        self.repository.replace_franchise(
            setup,
            teams,
            league_snapshot=snapshot,
            target_executable=str(getattr(self.model, "target_executable", "")),
        )
        self._load_franchise_dashboard()

    def _load_franchise_dashboard(self) -> None:
        record = self.repository.load()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self._header("Franchise Loaded", f"Database: {record.database_path}"))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text.setMaximumHeight(220)
        lines = [
            "# Franchise",
            f"Start Year: {record.setup.start_year}",
            f"User Team: {self._team_label(record.setup.user_team_index)}",
            f"Full League Save: {'yes' if record.setup.keep_full_league_save else 'no'}",
            f"Saved League Snapshots: {record.full_league_save_count}",
            f"Fantasy Draft Start: {'yes' if record.setup.fantasy_draft else 'no'}",
            f"Created: {record.created_at}",
            f"Updated: {record.updated_at}",
            "",
            "## League Teams",
            f"User: {self._team_label(record.setup.user_team_index)}",
            "",
            "## AI League Teams",
        ]
        if not record.team_options:
            lines.append("None selected")
        for team in record.team_options:
            lines.append(f"[{team.team_index}] {team.label}")
        lines.append("")
        lines.append("Unchecked teams are excluded from this franchise league.")
        text.setPlainText("\n".join(lines))
        self.dashboard_text = text
        layout.addWidget(text)
        if record.setup.fantasy_draft:
            layout.addWidget(self._build_fantasy_draft_widget(record), 1)
            self._refresh_draft_room()
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("New", clicked=self._show_new_franchise_setup))
        buttons.addWidget(QPushButton("Entry Menu", clicked=self.refresh_entry_menu))
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._replace_body(widget)

    def _build_fantasy_draft_widget(self, _record: FranchiseRecord) -> QWidget:
        box = QGroupBox("Fantasy Draft Room")
        layout = QVBoxLayout(box)
        controls = QHBoxLayout()
        self.draft_action_buttons = []
        for label, callback in (
            ("Start / Reset Draft", self._start_or_reset_fantasy_draft),
            ("Refresh Draft Room", self._refresh_draft_room),
            ("Run LLM Pick", self._run_llm_draft_pick),
            ("Mark Selected Pick", self._mark_selected_draft_pick),
        ):
            button = QPushButton(label, clicked=callback)
            button.setEnabled(not self._llm_pick_running())
            self.draft_action_buttons.append(button)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        player_combo = QComboBox()
        self.draft_player_combo = player_combo
        layout.addWidget(QLabel("Available player for user/manual pick"))
        layout.addWidget(player_combo)
        status = QTextEdit()
        status.setReadOnly(True)
        status.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.draft_status_text = status
        layout.addWidget(status, 1)
        return box

    def _league_team_indexes(self, record: FranchiseRecord) -> tuple[int, ...]:
        return league_team_indexes(record)

    def _team_count(self, record: FranchiseRecord | None = None) -> int:
        if record is None:
            record = self.repository.load()
        return len(self._league_team_indexes(record))

    def _start_or_reset_fantasy_draft(self) -> None:
        record = self.repository.load()
        self.repository.start_fantasy_draft(team_count=self._team_count(record), user_team_index=record.setup.user_team_index)
        self._refresh_draft_room()

    def _ensure_fantasy_draft_state(self, record: FranchiseRecord) -> FantasyDraftState:
        state = self.repository.load_fantasy_draft_state()
        if state is None:
            state = self.repository.start_fantasy_draft(team_count=self._team_count(record), user_team_index=record.setup.user_team_index)
        return state

    def _draft_position(self, state: FantasyDraftState, record: FranchiseRecord):
        return draft_position(
            state.current_pick_number,
            team_count=state.team_count,
            user_team_index=state.user_team_index,
            team_labels=team_labels_from_model(self.model, team_count=30),
            team_order=self._league_team_indexes(record),
        )

    def _draft_context(self):
        record = self.repository.load()
        state = self._ensure_fantasy_draft_state(record)
        position = self._draft_position(state, record)
        picks = self.repository.list_fantasy_draft_picks()
        pool = build_active_player_draft_pool(self.model, team_count=state.team_count)
        available = available_players(pool, picks)
        owner = draft_turn_owner(position, record)
        return record, state, position, picks, pool, available, owner

    def _refresh_draft_room(self) -> None:
        if self.draft_status_text is None or self.draft_player_combo is None:
            return
        try:
            state = self.repository.load_fantasy_draft_state()
            record = self.repository.load()
            if state is None:
                self.draft_player_combo.clear()
                self.draft_status_text.setPlainText("Fantasy draft has not been started. Click Start / Reset Draft.")
                return
            position = self._draft_position(state, record)
            picks = self.repository.list_fantasy_draft_picks()
            pool = build_active_player_draft_pool(self.model, team_count=state.team_count)
            available = available_players(pool, picks)
            owner = draft_turn_owner(position, record)
        except Exception as exc:
            self.draft_player_combo.clear()
            self.draft_status_text.setPlainText(f"Draft room needs loaded Teams and Players. Error: {exc}")
            return
        self.draft_player_combo.clear()
        for player in available:
            self.draft_player_combo.addItem(player.player_label, player.player_index)
        lines = [
            "# Fantasy Draft Room",
            "Pool source: Players/ISACTIVE active player offset",
            "Uses the in-game draft page active-player flag.",
            f"Current Pick: {position.pick_number}",
            f"Round: {position.round_number}",
            f"On Clock: Team {position.team_index} {position.team_label}",
            f"Turn Owner: {owner}",
            f"User Team: {self._team_label(record.setup.user_team_index)}",
            f"League Teams: {', '.join(str(index) for index in self._league_team_indexes(record))}",
            f"AI League Teams: {', '.join(str(index) for index in record.setup.llm_gm_team_indexes) or 'none'}",
            f"Pool Count: {len(pool)}",
            f"Available Count: {len(available)}",
            "",
            "## Picks",
        ]
        if not picks:
            lines.append("None")
        for pick in picks[-30:]:
            lines.append(f"Pick {pick.pick_number} R{pick.round_number} Team {pick.team_index} {pick.team_label}: {pick.player_label} ({pick.picked_by})")
            if pick.rationale:
                lines.append(f"  Rationale: {pick.rationale}")
        self.draft_status_text.setPlainText("\n".join(lines))

    def _selected_draft_player(self, pool, picks):
        if self.draft_player_combo is None:
            return None
        data = self.draft_player_combo.currentData()
        if data is None:
            return None
        return find_available_player_by_index(pool, picks, int(data))

    def _mark_selected_draft_pick(self) -> None:
        if self._llm_pick_running():
            QMessageBox.warning(self, "Fantasy draft", "Wait for the running LLM pick to finish.")
            return
        try:
            record, _state, position, picks, pool, _available, owner = self._draft_context()
            player = self._selected_draft_player(pool, picks)
            if player is None:
                QMessageBox.warning(self, "Fantasy draft", "No available player selected.")
                return
            picked_by = "user" if owner == "user" else "manual"
            self.repository.record_fantasy_draft_pick(stored_pick_from_player(player, position=position, picked_by=picked_by))
        except Exception as exc:
            QMessageBox.warning(self, "Fantasy draft", str(exc))
            return
        self._refresh_draft_room()

    def _run_llm_draft_pick(self) -> None:
        if self._llm_pick_running():
            QMessageBox.warning(self, "Fantasy draft", "An LLM pick is already running.")
            return
        try:
            record, _state, position, picks, _pool, available, owner = self._draft_context()
            if owner != "llm":
                QMessageBox.warning(self, "Fantasy draft", "The current pick is not controlled by an AI league team.")
                return
        except Exception as exc:
            QMessageBox.warning(self, "Fantasy draft", str(exc))
            return
        self._set_llm_pick_running(True)
        self._append_draft_status("\nLLM pick running through Hermes API Server...")

        def worker() -> None:
            try:
                result = run_llm_fantasy_draft_pick(
                    record=record,
                    position=position,
                    available_players=tuple(available),
                    drafted_picks=tuple(picks),
                )
                self._llm_pick_events.put(("done", result))
            except Exception as exc:
                self._llm_pick_events.put(("error", str(exc)))

        self._llm_pick_thread = threading.Thread(target=worker, name="nba2k-franchise-llm-pick", daemon=True)
        self._llm_pick_thread.start()
        self._llm_pick_timer.start()

    def _llm_pick_running(self) -> bool:
        return self._llm_pick_thread is not None and self._llm_pick_thread.is_alive()

    def _set_llm_pick_running(self, running: bool) -> None:
        for button in self.draft_action_buttons:
            button.setEnabled(not running)

    def _append_draft_status(self, message: str) -> None:
        if self.draft_status_text is None:
            return
        current = self.draft_status_text.toPlainText()
        self.draft_status_text.setPlainText(current + message)

    def _poll_llm_pick(self) -> None:
        handled = False
        while not self._llm_pick_events.empty():
            kind, payload = self._llm_pick_events.get()
            handled = True
            if kind == "done":
                self._finish_llm_pick(payload)
            else:
                QMessageBox.warning(self, "Fantasy draft", str(payload))
        if handled or not self._llm_pick_running():
            self._llm_pick_timer.stop()
            self._llm_pick_thread = None
            self._set_llm_pick_running(False)

    def _finish_llm_pick(self, payload: object) -> None:
        if not isinstance(payload, LlmDraftPickResult):
            QMessageBox.warning(self, "Fantasy draft", "Invalid LLM pick result.")
            return
        try:
            _record, _state, position, picks, pool, _available, owner = self._draft_context()
            if owner != "llm":
                raise ValueError("The draft pick changed before the LLM result returned.")
            player = find_available_player_by_index(pool, picks, payload.selected_player_index)
            if player is None:
                player = find_available_player(pool, picks, payload.selected_player_label)
            if player is None:
                raise ValueError("LLM selected a player that is not available")
            self.repository.record_fantasy_draft_pick(
                stored_pick_from_player(
                    player,
                    position=position,
                    picked_by="llm",
                    raw_llm_response=payload.response,
                    rationale=payload.rationale,
                )
            )
        except Exception as exc:
            QMessageBox.warning(self, "Fantasy draft", str(exc))
            return
        self._refresh_draft_room()

    def _team_label(self, team_index: int) -> str:
        for option in team_options_from_model(self.model):
            if option.team_index == int(team_index):
                return option.display_label
        return f"[{int(team_index)}] Team {int(team_index)}"


def build_franchise_screen(model: Any, *, db_path: str | Path = DEFAULT_FRANCHISE_DB_PATH) -> FranchiseScreen:
    return FranchiseScreen(model, db_path=db_path)


__all__ = ["FRANCHISE_SCREEN_TITLE", "FranchiseScreen", "build_franchise_screen"]
