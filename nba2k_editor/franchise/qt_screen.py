from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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

from nba2k_editor.franchise.college_dynasty import (
    PROJECTION_STAGE_SEASON,
    PROJECTION_STAGE_SWEET16,
    CollegeDynastyRepository,
    load_college_catalog,
    load_college_player_updates,
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
from nba2k_editor.franchise.models import (
    LEAGUE_MODE_COLLEGE,
    LEAGUE_MODE_NBA,
    FantasyDraftState,
    FranchiseRecord,
    FranchiseSetup,
    FranchiseTeamOption,
    TeamRecommendation,
    league_mode_label,
)
from nba2k_editor.franchise.profile_generation import (
    build_team_profile_generation_requests,
    generate_team_profiles,
    missing_team_profile_indexes,
    team_profiles_complete,
)
from nba2k_editor.franchise.recommendations import build_team_recommendation_requests, run_team_recommendation_requests
from nba2k_editor.franchise.sim_phases import (
    STATUS_READY,
    STATUS_WAITING_FOR_GAME_ADVANCE,
    STATUS_WAITING_FOR_USER_TRADE,
    franchise_phase_sequence,
    phase_label,
)
from nba2k_editor.franchise.storage import DEFAULT_FRANCHISE_DB_PATH, FranchiseRepository, team_options_from_model
from nba2k_editor.models.background_operations import BackgroundOperationWorker

FRANCHISE_SCREEN_TITLE = "Franchise"
DEFAULT_USER_TEAM_INDEX = 13


class FranchiseScreen(QWidget):
    def __init__(
        self,
        model: Any,
        *,
        db_path: str | Path = DEFAULT_FRANCHISE_DB_PATH,
        profile_client: Any | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.profile_client = profile_client
        self.repository = FranchiseRepository(db_path)
        self.team_options: tuple[FranchiseTeamOption, ...] = ()
        self.team_checkboxes: dict[int, QCheckBox] = {}
        self.user_team_combo: QComboBox | None = None
        self.start_year_input: QLineEdit | None = None
        self.league_mode_combo: QComboBox | None = None
        self.full_league_save_checkbox: QCheckBox | None = None
        self.fantasy_draft_checkbox: QCheckBox | None = None
        self.dashboard_text: QTextEdit | None = None
        self.profile_status_text: QTextEdit | None = None
        self.profile_action_buttons: list[QPushButton] = []
        self._profile_worker = BackgroundOperationWorker()
        self._profile_generation_franchise_id = ""
        self._profile_timer = QTimer(self)
        self._profile_timer.setInterval(100)
        self._profile_timer.timeout.connect(self._poll_team_profile_generation)
        self.phase_status_text: QTextEdit | None = None
        self.phase_combo: QComboBox | None = None
        self.phase_year_input: QLineEdit | None = None
        self.phase_expansion_checkbox: QCheckBox | None = None
        self.phase_action_buttons: list[QPushButton] = []
        self.recommendation_text: QTextEdit | None = None
        self.recommendation_action_buttons: list[QPushButton] = []
        self._recommendation_thread: threading.Thread | None = None
        self._recommendation_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._recommendation_timer = QTimer(self)
        self._recommendation_timer.setInterval(100)
        self._recommendation_timer.timeout.connect(self._poll_team_recommendations)
        self.draft_status_text: QTextEdit | None = None
        self.draft_player_combo: QComboBox | None = None
        self.draft_action_buttons: list[QPushButton] = []
        self.college_status_text: QTextEdit | None = None
        self.college_program_combo: QComboBox | None = None
        self.college_seed_input: QLineEdit | None = None
        self.college_playoff_indexes_input: QLineEdit | None = None
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
            old_body = self._body
            self.root_layout.removeWidget(old_body)
            old_body.hide()
            old_body.setParent(None)
            old_body.deleteLater()
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
                "Choose NBA or College mode, set the true start year, select your program/team, choose whether to save the full loaded league dataset, and select AI-controlled teams.",
            )
        )
        self.team_options = team_options_from_model(self.model)
        form_box = QGroupBox("League Setup")
        form = QFormLayout(form_box)
        self.start_year_input = QLineEdit("2025")
        league_mode_combo = QComboBox()
        league_mode_combo.addItem("NBA", LEAGUE_MODE_NBA)
        league_mode_combo.addItem("College", LEAGUE_MODE_COLLEGE)
        league_mode_combo.currentIndexChanged.connect(lambda _index: self._sync_league_mode_controls())
        self.league_mode_combo = league_mode_combo
        user_team_combo = QComboBox()
        for option in self.team_options:
            user_team_combo.addItem(option.display_label, option.team_index)
        for combo_index in range(user_team_combo.count()):
            if int(user_team_combo.itemData(combo_index)) == DEFAULT_USER_TEAM_INDEX:
                user_team_combo.setCurrentIndex(combo_index)
                break
        user_team_combo.currentIndexChanged.connect(lambda _index: self._sync_user_team_llm_checkbox())
        self.user_team_combo = user_team_combo
        self.full_league_save_checkbox = QCheckBox("Keep a full loaded league save using all known offsets")
        self.fantasy_draft_checkbox = QCheckBox("League starts with a fantasy draft")
        form.addRow("League Mode", self.league_mode_combo)
        form.addRow("Start Year", self.start_year_input)
        form.addRow("Your Team", self.user_team_combo)
        form.addRow("Full League Save", self.full_league_save_checkbox)
        form.addRow("Fantasy Draft", self.fantasy_draft_checkbox)
        layout.addWidget(form_box)
        layout.addWidget(self._build_team_checkbox_box(self.team_options), 1)
        for checkbox in self.team_checkboxes.values():
            checkbox.setChecked(True)
        self._sync_user_team_llm_checkbox()
        self._sync_league_mode_controls()
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

    def _selected_league_mode(self) -> str:
        if self.league_mode_combo is None or self.league_mode_combo.currentData() is None:
            return LEAGUE_MODE_NBA
        return str(self.league_mode_combo.currentData())

    def _sync_league_mode_controls(self) -> None:
        if self.fantasy_draft_checkbox is None:
            return
        college_mode = self._selected_league_mode() == LEAGUE_MODE_COLLEGE
        if college_mode:
            self.fantasy_draft_checkbox.setChecked(False)
        self.fantasy_draft_checkbox.setEnabled(not college_mode)
        self.fantasy_draft_checkbox.setToolTip(
            "College mode uses its own program calendar and does not use the NBA fantasy draft workflow."
            if college_mode
            else "Start this NBA franchise with a fantasy draft."
        )

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
            league_mode=self._selected_league_mode(),
        )

    def _start_franchise(self) -> None:
        if self._profile_generation_running():
            QMessageBox.warning(self, "Franchise setup", "Wait for the current franchise team-profile generation to finish.")
            return
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
        self._run_missing_team_profile_generation()

    def _load_franchise_dashboard(self) -> None:
        record = self.repository.load()
        if not team_profiles_complete(record):
            self._show_team_profile_generation_page(record)
            return
        if record.setup.fantasy_draft:
            self._show_fantasy_draft_page(record)
            return
        self._show_franchise_systems_page(record)

    def _show_team_profile_generation_page(self, record: FranchiseRecord) -> None:
        self.dashboard_text = None
        self.phase_status_text = None
        self.recommendation_text = None
        self.draft_status_text = None
        widget = QWidget()
        layout = QVBoxLayout(widget)
        college_mode = record.setup.league_mode == LEAGUE_MODE_COLLEGE
        layout.addWidget(
            self._header(
                "College Program Profiles" if college_mode else "Franchise Team Profiles",
                (
                    "Every active program receives persistent athletic-department, program-decision, coaching, and recruiting context before the session begins."
                    if college_mode
                    else "Every active team receives persistent Owner, GM, Coach, and Scout context before the franchise session begins. The user controls only the selected team's GM role."
                ),
            )
        )
        controls = QHBoxLayout()
        self.profile_action_buttons = []
        generate_button = QPushButton("Generate Missing Profiles", clicked=self._run_missing_team_profile_generation)
        new_button = QPushButton("New", clicked=self._show_new_franchise_setup)
        entry_button = QPushButton("Entry Menu", clicked=self.refresh_entry_menu)
        self.profile_action_buttons.extend((generate_button, new_button, entry_button))
        controls.addWidget(generate_button)
        controls.addWidget(new_button)
        controls.addWidget(entry_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        status = QTextEdit()
        status.setReadOnly(True)
        status.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.profile_status_text = status
        layout.addWidget(status, 1)
        self._replace_body(widget)
        self._refresh_team_profile_generation_status(record)

    def _refresh_team_profile_generation_status(self, record: FranchiseRecord | None = None) -> None:
        if self.profile_status_text is None:
            return
        record = record or self.repository.load()
        lines = [
            "# Persistent Team Profile Setup",
            f"Franchise ID: {record.franchise_id or 'not configured'}",
            f"Profile Directory: {record.profile_directory or 'not configured'}",
            f"User Team Index: {record.setup.user_team_index}",
            "",
            "## Required Profiles",
        ]
        missing = set(missing_team_profile_indexes(record)) if record.profile_directory else set()
        if not record.team_options:
            lines.append("No franchise-scoped active teams are stored. Start a new franchise to generate profiles.")
        for team in record.team_options:
            team_index = int(team.team_index)
            gm_control = "human user" if team_index == int(record.setup.user_team_index) else "LLM"
            status = "missing" if team_index in missing else "ready"
            if record.setup.league_mode == LEAGUE_MODE_COLLEGE:
                role_status = f"Athletic Department=LLM, Program={gm_control}, Coaching=LLM, Recruiting=LLM"
            else:
                role_status = f"Owner=LLM, GM={gm_control}, Coach=LLM, Scout=LLM"
            lines.append(f"[{status}] [{team_index}] {team.label}: {role_status}")
        if self._profile_generation_running():
            lines.extend(("", "Generating missing profiles through Hermes API Server..."))
        elif missing:
            lines.extend(("", f"Missing Profiles: {len(missing)}"))
        elif team_profiles_complete(record):
            lines.extend(("", "All required profiles are ready."))
        self.profile_status_text.setPlainText("\n".join(lines))
        can_generate = bool(record.franchise_id and record.profile_directory and record.team_options and missing)
        running = self._profile_generation_running()
        if self.profile_action_buttons:
            self.profile_action_buttons[0].setEnabled(can_generate and not running)
            for button in self.profile_action_buttons[1:]:
                button.setEnabled(not running)

    def _run_missing_team_profile_generation(self) -> None:
        if self._profile_generation_running():
            QMessageBox.warning(self, "Team profile generation", "Team profiles are already being generated.")
            return
        try:
            record = self.repository.load()
            missing = missing_team_profile_indexes(record)
            if not record.franchise_id or not record.profile_directory or not record.team_options:
                raise ValueError("This saved franchise predates franchise-scoped team profiles. Start a new franchise to generate them.")
            if not missing:
                self._load_franchise_dashboard()
                return
            requests = build_team_profile_generation_requests(record, self.model, team_indexes=missing)
        except Exception as exc:
            QMessageBox.warning(self, "Team profile generation", str(exc))
            return
        self._profile_generation_franchise_id = record.franchise_id

        def task() -> str:
            generated = generate_team_profiles(record, requests, client=self.profile_client)
            return f"Generated {len(generated)} persistent team profiles."

        if not self._profile_worker.start("Franchise team profiles", task):
            QMessageBox.warning(self, "Team profile generation", "Team profiles are already being generated.")
            return
        self._set_profile_generation_running(True)
        self._refresh_team_profile_generation_status(record)
        self._profile_timer.start()

    def _profile_generation_running(self) -> bool:
        return self._profile_worker.is_running()

    def _set_profile_generation_running(self, running: bool) -> None:
        for button in self.profile_action_buttons:
            button.setEnabled(not running)

    def _poll_team_profile_generation(self) -> None:
        handled = False
        for kind, payload in self._profile_worker.pop_events():
            if kind != "done":
                continue
            handled = True
            _request_id, message, status, _done_callback = payload
            launched_franchise_id = self._profile_generation_franchise_id
            self._profile_generation_franchise_id = ""
            try:
                record = self.repository.load()
            except Exception:
                continue
            if record.franchise_id != launched_franchise_id:
                continue
            if status == "failed":
                QMessageBox.warning(self, "Team profile generation", str(message))
                self._refresh_team_profile_generation_status(record)
            elif status == "complete":
                if team_profiles_complete(record):
                    self._load_franchise_dashboard()
                else:
                    self._refresh_team_profile_generation_status(record)
        if handled or not self._profile_generation_running():
            self._profile_timer.stop()
            self._set_profile_generation_running(False)
            if self.profile_status_text is not None:
                self._refresh_team_profile_generation_status()

    def _show_franchise_systems_page(self, record: FranchiseRecord) -> None:
        self.profile_status_text = None
        self.profile_action_buttons = []
        self.draft_status_text = None
        self.draft_player_combo = None
        self.draft_action_buttons = []
        widget = QWidget()
        layout = QVBoxLayout(widget)
        page_title = "College Program Systems" if record.setup.league_mode == LEAGUE_MODE_COLLEGE else "Franchise Systems"
        layout.addWidget(self._header(page_title, f"Database: {record.database_path}"))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text.setMaximumHeight(220)
        lines = [
            "# College Program" if record.setup.league_mode == LEAGUE_MODE_COLLEGE else "# Franchise",
            f"League Mode: {league_mode_label(record.setup.league_mode)}",
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
        ai_team_indexes = set(record.setup.llm_gm_team_indexes)
        ai_teams = tuple(team for team in record.team_options if team.team_index in ai_team_indexes)
        if not ai_teams:
            lines.append("None selected")
        for team in ai_teams:
            lines.append(f"[{team.team_index}] {team.label}")
        lines.append("")
        lines.append(
            "Unchecked teams are excluded from this college league."
            if record.setup.league_mode == LEAGUE_MODE_COLLEGE
            else "Unchecked teams are excluded from this franchise league."
        )
        text.setPlainText("\n".join(lines))
        self.dashboard_text = text
        layout.addWidget(text)
        if record.setup.league_mode == LEAGUE_MODE_COLLEGE:
            layout.addWidget(self._build_college_dynasty_widget(record), 1)
        layout.addWidget(self._build_phase_controller_widget(record))
        layout.addWidget(self._build_team_recommendations_widget(record), 1)
        self._refresh_phase_controller()
        self._refresh_team_recommendations()
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("New", clicked=self._show_new_franchise_setup))
        buttons.addWidget(QPushButton("Entry Menu", clicked=self.refresh_entry_menu))
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._replace_body(widget)

    def _show_fantasy_draft_page(self, record: FranchiseRecord) -> None:
        self.profile_status_text = None
        self.profile_action_buttons = []
        self.dashboard_text = None
        self.recommendation_text = None
        self.recommendation_action_buttons = []
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._header(
                "Fantasy Draft",
                f"Database: {record.database_path}. This franchise is in fantasy draft mode, so only the draft room is active on this page.",
            )
        )
        layout.addWidget(self._build_fantasy_draft_widget(record), 1)
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("New", clicked=self._show_new_franchise_setup))
        buttons.addWidget(QPushButton("Entry Menu", clicked=self.refresh_entry_menu))
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._replace_body(widget)
        self._refresh_draft_room()

    def _college_repository(self) -> CollegeDynastyRepository:
        return CollegeDynastyRepository(self.repository)

    def _build_college_dynasty_widget(self, record: FranchiseRecord) -> QWidget:
        box = QGroupBox("College Dynasty Universe")
        box.setObjectName("CollegeDynastyUniverse")
        layout = QVBoxLayout(box)
        form = QFormLayout()
        program_combo = QComboBox()
        self.college_program_combo = program_combo
        seed_input = QLineEdit(str(record.setup.start_year))
        self.college_seed_input = seed_input
        playoff_indexes = QLineEdit()
        playoff_indexes.setPlaceholderText("16 unique team indexes, comma-separated")
        self.college_playoff_indexes_input = playoff_indexes
        form.addRow("User Program", program_combo)
        form.addRow("Season Selection Seed", seed_input)
        form.addRow("Sweet 16 Playoff Team Indexes", playoff_indexes)
        layout.addLayout(form)

        first_controls = QHBoxLayout()
        for label, callback in (
            ("Import 365-Program Catalog", self._import_college_catalog),
            ("Import Player Updates", self._import_college_player_updates),
            ("Plan 30-Team Season", self._plan_college_season),
            ("Capture 450 Linked Slots", self._capture_college_season_slots),
        ):
            first_controls.addWidget(QPushButton(label, clicked=callback))
        first_controls.addStretch(1)
        layout.addLayout(first_controls)

        second_controls = QHBoxLayout()
        for label, callback in (
            ("Sync Season Players Out", self._sync_college_players_out),
            ("Record FA Departures", self._record_college_fa_departures),
            ("Advance Eligibility", self._advance_college_eligibility),
            ("Import 64-Team Bracket", self._import_college_bracket),
            ("Import Opening-Round Results", self._import_college_opening_results),
            ("Import In-Game Playoff Results", self._import_college_ingame_results),
        ):
            second_controls.addWidget(QPushButton(label, clicked=callback))
        second_controls.addStretch(1)
        layout.addLayout(second_controls)

        third_controls = QHBoxLayout()
        for label, callback in (
            ("Map Sweet 16", self._map_college_sweet16),
            ("Capture 240 Sweet 16 Slots", self._capture_college_sweet16_slots),
            ("Refresh", self._refresh_college_dynasty),
        ):
            third_controls.addWidget(QPushButton(label, clicked=callback))
        third_controls.addStretch(1)
        layout.addLayout(third_controls)

        status = QTextEdit()
        status.setReadOnly(True)
        status.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        status.setMaximumHeight(320)
        self.college_status_text = status
        layout.addWidget(status)
        self._refresh_college_dynasty()
        return box

    def _college_true_sim_year(self) -> int:
        return int(self.repository.ensure_sim_state().sim_year)

    def _selected_college_program_id(self) -> str:
        if self.college_program_combo is None or self.college_program_combo.currentData() is None:
            raise ValueError("Import the 365-program catalog and select a user program first.")
        return str(self.college_program_combo.currentData())

    def _selected_college_seed(self) -> int:
        if self.college_seed_input is None:
            raise ValueError("Season selection seed is unavailable.")
        text = self.college_seed_input.text().strip()
        if not text or not text.lstrip("-").isdigit():
            raise ValueError("Season Selection Seed must be an integer.")
        return int(text)

    def _selected_playoff_team_indexes(self) -> tuple[int, ...]:
        if self.college_playoff_indexes_input is None:
            raise ValueError("Sweet 16 playoff team indexes are unavailable.")
        values = tuple(
            int(part.strip())
            for part in self.college_playoff_indexes_input.text().split(",")
            if part.strip()
        )
        if len(values) != 16:
            raise ValueError("Enter exactly 16 comma-separated in-game playoff team indexes.")
        return values

    def _refresh_college_dynasty(self) -> None:
        if self.college_status_text is None or self.college_program_combo is None:
            return
        college = self._college_repository()
        conference_count, program_count, player_count = college.catalog_counts()
        prior_program_id = self.college_program_combo.currentData()
        programs = college.list_programs()
        self.college_program_combo.blockSignals(True)
        self.college_program_combo.clear()
        for program in programs:
            self.college_program_combo.addItem(program.name, program.program_id)
        if prior_program_id is not None:
            prior_index = self.college_program_combo.findData(prior_program_id)
            if prior_index >= 0:
                self.college_program_combo.setCurrentIndex(prior_index)
        year = self._college_true_sim_year()
        season_projection = college.list_team_projection(year)
        if season_projection:
            user_projection = next((row for row in season_projection if row.selection_reason == "user"), None)
            if user_projection is not None:
                user_index = self.college_program_combo.findData(user_projection.program_id)
                if user_index >= 0:
                    self.college_program_combo.setCurrentIndex(user_index)
        self.college_program_combo.blockSignals(False)
        season_players = college.list_player_projection(year, stage=PROJECTION_STAGE_SEASON)
        round_one = college.list_tournament_games(year, round_number=1)
        round_two = college.list_tournament_games(year, round_number=2)
        in_game_rounds = tuple(
            game
            for round_number in range(3, 7)
            for game in college.list_tournament_games(year, round_number=round_number)
        )
        sweet16 = college.sweet16_program_ids(year)
        sweet16_mapping = college.list_sweet16_projection(year)
        sweet16_players = college.list_player_projection(year, stage=PROJECTION_STAGE_SWEET16)
        lines = [
            "# Canonical College Universe",
            f"True Sim Year: {year}",
            f"Conferences: {conference_count}/31",
            f"Programs: {program_count}/365",
            f"Canonical Players: {player_count}",
            f"Season Teams: {len(season_projection)}/30",
            f"Reserved Season Player Records: {len(season_players)}/450",
            "",
            "## External Tournament",
            f"Round 1: {sum(game.winner_program_id is not None for game in round_one)}/{len(round_one) or 32} results",
            f"Round 2: {sum(game.winner_program_id is not None for game in round_two)}/{len(round_two) or 16} results",
            f"Sweet 16 Winners: {len(sweet16)}/16",
            f"Sweet 16 Team Mapping: {len(sweet16_mapping)}/16",
            f"Reserved Sweet 16 Player Records: {len(sweet16_players)}/240",
            f"In-Game Playoff Results Reconciled: {sum(game.winner_program_id is not None for game in in_game_rounds)}/15",
            f"National Champion: {college.champion_program_id(year) or 'pending'}",
            "",
            "The first two tournament rounds are recorded outside NBA 2K. Only the Sweet 16 is projected into the game's 16 playoff teams.",
        ]
        self.college_status_text.setPlainText("\n".join(lines))

    def _import_college_catalog(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import College Catalog",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            conferences, programs, players = load_college_catalog(path)
            self._college_repository().replace_catalog(conferences, programs, players)
        except Exception as exc:
            QMessageBox.warning(self, "College catalog", str(exc))
            return
        self._refresh_college_dynasty()

    def _import_college_player_updates(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import College Player Updates",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            players = load_college_player_updates(path)
            updated = self._college_repository().upsert_players(players)
        except Exception as exc:
            QMessageBox.warning(self, "College player updates", str(exc))
            return
        QMessageBox.information(self, "College player updates", f"Updated {len(updated)} canonical players.")
        self._refresh_college_dynasty()

    def _plan_college_season(self) -> None:
        try:
            self._college_repository().plan_season(
                true_sim_year=self._college_true_sim_year(),
                user_program_id=self._selected_college_program_id(),
                random_seed=self._selected_college_seed(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "College season projection", str(exc))
            return
        self._refresh_college_dynasty()


    def _capture_college_projection_slots(self, stage: str) -> None:
        try:
            self._college_repository().capture_projection_slots(
                self.model,
                true_sim_year=self._college_true_sim_year(),
                stage=stage,
            )
        except Exception as exc:
            QMessageBox.warning(self, "College projection slots", str(exc))
            return
        self._refresh_college_dynasty()

    def _capture_college_season_slots(self) -> None:
        self._capture_college_projection_slots(PROJECTION_STAGE_SEASON)

    def _capture_college_sweet16_slots(self) -> None:
        self._capture_college_projection_slots(PROJECTION_STAGE_SWEET16)


    def _sync_college_players_out(self) -> None:
        try:
            synced = self._college_repository().sync_projected_players_from_game(
                self.model,
                true_sim_year=self._college_true_sim_year(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "College player sync", str(exc))
            return
        QMessageBox.information(self, "College player sync", f"Synced {len(synced)} projected players into canonical storage.")
        self._refresh_college_dynasty()

    def _record_college_fa_departures(self) -> None:
        try:
            departed = self._college_repository().record_free_agent_departures(
                self.model,
                true_sim_year=self._college_true_sim_year(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "College departures", str(exc))
            return
        QMessageBox.information(self, "College departures", f"Recorded {len(departed)} Free Agency departures.")
        self._refresh_college_dynasty()

    def _advance_college_eligibility(self) -> None:
        answer = QMessageBox.question(
            self,
            "Advance College Eligibility",
            "Advance every active canonical player by one eligibility year? This can run only once for the current true sim year.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            exhausted = self._college_repository().advance_eligibility(
                true_sim_year=self._college_true_sim_year()
            )
        except Exception as exc:
            QMessageBox.warning(self, "College eligibility", str(exc))
            return
        QMessageBox.information(self, "College eligibility", f"Eligibility advanced; {len(exhausted)} players exhausted eligibility.")
        self._refresh_college_dynasty()

    def _load_json_file(self, title: str) -> dict[str, Any] | None:
        path, _selected_filter = QFileDialog.getOpenFileName(self, title, str(Path.cwd()), "JSON Files (*.json)")
        if not path:
            return None
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON root must be an object")
        return payload

    def _import_college_bracket(self) -> None:
        try:
            payload = self._load_json_file("Import 64-Team College Bracket")
            if payload is None:
                return
            program_ids = payload.get("bracket_program_ids")
            if not isinstance(program_ids, list):
                raise ValueError("bracket JSON requires bracket_program_ids array")
            self._college_repository().create_tournament(
                true_sim_year=self._college_true_sim_year(),
                bracket_program_ids=(str(value) for value in program_ids),
            )
        except Exception as exc:
            QMessageBox.warning(self, "College tournament", str(exc))
            return
        self._refresh_college_dynasty()

    def _import_college_opening_results(self) -> None:
        try:
            payload = self._load_json_file("Import College Opening-Round Results")
            if payload is None:
                return
            results = payload.get("results")
            if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
                raise ValueError("results JSON requires an array of result objects")
            if any(int(row["round_number"]) not in {1, 2} for row in results):
                raise ValueError("opening-round results may contain only rounds 1 and 2")
            college = self._college_repository()
            for row in sorted(results, key=lambda item: (int(item["round_number"]), int(item["game_number"]))):
                college.record_tournament_winner(
                    true_sim_year=self._college_true_sim_year(),
                    round_number=int(row["round_number"]),
                    game_number=int(row["game_number"]),
                    winner_program_id=str(row["winner_program_id"]),
                )
        except Exception as exc:
            QMessageBox.warning(self, "College tournament results", str(exc))
            return
        self._refresh_college_dynasty()

    def _import_college_ingame_results(self) -> None:
        try:
            payload = self._load_json_file("Import In-Game College Playoff Results")
            if payload is None:
                return
            results = payload.get("results")
            if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
                raise ValueError("results JSON requires an array of result objects")
            if any(int(row["round_number"]) not in {3, 4, 5, 6} for row in results):
                raise ValueError("in-game playoff results may contain only rounds 3 through 6")
            college = self._college_repository()
            for row in sorted(results, key=lambda item: (int(item["round_number"]), int(item["game_number"]))):
                college.record_tournament_winner(
                    true_sim_year=self._college_true_sim_year(),
                    round_number=int(row["round_number"]),
                    game_number=int(row["game_number"]),
                    winner_program_id=str(row["winner_program_id"]),
                )
        except Exception as exc:
            QMessageBox.warning(self, "In-game college playoff results", str(exc))
            return
        self._refresh_college_dynasty()

    def _map_college_sweet16(self) -> None:
        try:
            self._college_repository().plan_sweet16_projection(
                true_sim_year=self._college_true_sim_year(),
                playoff_team_indexes=self._selected_playoff_team_indexes(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Sweet 16 projection", str(exc))
            return
        self._refresh_college_dynasty()

    def _build_phase_controller_widget(self, _record: FranchiseRecord) -> QWidget:
        college_mode = _record.setup.league_mode == LEAGUE_MODE_COLLEGE
        box = QGroupBox("College Program Phase Controller" if college_mode else "Franchise Phase Controller")
        box.setObjectName("FranchisePhaseController")
        layout = QVBoxLayout(box)

        sync_form = QFormLayout()
        year_input = QLineEdit()
        self.phase_year_input = year_input
        phase_combo = QComboBox()
        for phase in franchise_phase_sequence(
            expansion_draft_required=False,
            league_mode=_record.setup.league_mode,
        ):
            phase_combo.addItem(phase.label, phase.key)
        self.phase_combo = phase_combo
        expansion_checkbox = QCheckBox("An expansion team was added; run Expansion Draft before NBA Draft")
        expansion_checkbox.clicked.connect(self._set_phase_expansion_draft)
        self.phase_expansion_checkbox = expansion_checkbox
        expansion_checkbox.setVisible(not college_mode)
        sync_form.addRow("Observed True Sim Year", year_input)
        sync_form.addRow("Observed Game Phase", phase_combo)
        sync_form.addRow("Conditional Expansion", expansion_checkbox)
        layout.addLayout(sync_form)

        controls = QHBoxLayout()
        self.phase_action_buttons = []
        for label, callback in (
            ("Refresh", self._refresh_phase_controller),
            ("Sync Selected Game Phase", self._sync_selected_game_phase),
            ("CPU Phase Complete", self._complete_current_phase),
            ("Trade Resolved / Resume", self._resume_after_user_trade),
        ):
            button = QPushButton(label, clicked=callback)
            self.phase_action_buttons.append(button)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)

        status = QTextEdit()
        status.setReadOnly(True)
        status.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        status.setMaximumHeight(280)
        self.phase_status_text = status
        layout.addWidget(status)
        return box

    def _selected_phase_key(self) -> str:
        if self.phase_combo is None or self.phase_combo.currentData() is None:
            raise ValueError("No observed game phase is selected.")
        return str(self.phase_combo.currentData())

    def _selected_phase_year(self) -> int:
        if self.phase_year_input is None:
            raise ValueError("Observed true sim year is unavailable.")
        text = self.phase_year_input.text().strip()
        if not text.isdigit():
            raise ValueError("Observed True Sim Year must be a number.")
        return int(text)

    def _set_phase_expansion_draft(self, checked: bool) -> None:
        try:
            self.repository.set_expansion_draft_required(bool(checked))
        except Exception as exc:
            QMessageBox.warning(self, "Franchise phase", str(exc))
        self._refresh_phase_controller()

    def _sync_selected_game_phase(self) -> None:
        try:
            state = self.repository.ensure_sim_state()
            observed_phase = self._selected_phase_key()
            observed_year = self._selected_phase_year()
            if state.status == STATUS_WAITING_FOR_GAME_ADVANCE:
                self.repository.sync_and_resume(observed_phase=observed_phase, observed_sim_year=observed_year)
            elif state.status == STATUS_READY:
                self.repository.sync_sim_state(sim_year=observed_year, current_phase=observed_phase)
            else:
                raise ValueError("Resolve the user-team trade before syncing another game phase.")
        except Exception as exc:
            QMessageBox.warning(self, "Franchise phase", str(exc))
        self._refresh_phase_controller()

    def _complete_current_phase(self) -> None:
        try:
            self.repository.pause_for_game_advance()
        except Exception as exc:
            QMessageBox.warning(self, "Franchise phase", str(exc))
        self._refresh_phase_controller()

    def _resume_after_user_trade(self) -> None:
        try:
            self.repository.resume_after_user_trade()
        except Exception as exc:
            QMessageBox.warning(self, "Franchise phase", str(exc))
        self._refresh_phase_controller()

    def _refresh_phase_controller(self) -> None:
        if (
            self.phase_status_text is None
            or self.phase_combo is None
            or self.phase_year_input is None
            or self.phase_expansion_checkbox is None
        ):
            return
        record = self.repository.load()
        state = self.repository.ensure_sim_state()
        displayed_phase = state.expected_next_phase if state.status == STATUS_WAITING_FOR_GAME_ADVANCE else state.current_phase
        displayed_year = state.expected_next_year if state.status == STATUS_WAITING_FOR_GAME_ADVANCE else state.sim_year
        combo_index = self.phase_combo.findData(displayed_phase)
        if combo_index >= 0:
            self.phase_combo.setCurrentIndex(combo_index)
        self.phase_year_input.setText(str(displayed_year))
        self.phase_expansion_checkbox.blockSignals(True)
        self.phase_expansion_checkbox.setChecked(state.expansion_draft_required)
        self.phase_expansion_checkbox.blockSignals(False)

        status_labels = {
            STATUS_READY: "READY FOR CPU TEAM WORK",
            STATUS_WAITING_FOR_GAME_ADVANCE: "WAITING FOR USER TO PROGRESS NBA 2K",
            STATUS_WAITING_FOR_USER_TRADE: "WAITING FOR USER-TEAM TRADE DECISION",
        }
        lines = [
            "# College Program Phase Controller" if record.setup.league_mode == LEAGUE_MODE_COLLEGE else "# Franchise Phase Controller",
            f"League Mode: {league_mode_label(record.setup.league_mode)}",
            f"True Sim Year: {state.sim_year}",
            f"Current Phase: {phase_label(state.current_phase, league_mode=record.setup.league_mode)}",
            f"Status: {status_labels[state.status]}",
        ]
        if record.setup.league_mode != LEAGUE_MODE_COLLEGE:
            lines.append(f"Expansion Draft This Offseason: {'yes' if state.expansion_draft_required else 'no'}")
        if state.expected_next_phase:
            lines.append(
                f"Expected Next Phase: {phase_label(state.expected_next_phase, league_mode=record.setup.league_mode)}"
            )
            lines.append(f"Expected True Sim Year: {state.expected_next_year}")
        if state.required_user_action:
            lines.extend(("", "Required User Action:", state.required_user_action))
        lines.extend(("", "## Active Simulation Sequence"))
        for phase in franchise_phase_sequence(
            expansion_draft_required=state.expansion_draft_required,
            league_mode=record.setup.league_mode,
        ):
            marker = ">" if phase.key == state.current_phase else " "
            lines.append(f"{marker} {phase.label}")
        self.phase_status_text.setPlainText("\n".join(lines))

        self.phase_action_buttons[1].setEnabled(state.status != STATUS_WAITING_FOR_USER_TRADE)
        self.phase_action_buttons[2].setEnabled(state.status == STATUS_READY)
        self.phase_action_buttons[3].setEnabled(state.status == STATUS_WAITING_FOR_USER_TRADE)
        self.phase_expansion_checkbox.setEnabled(
            state.status == STATUS_READY and record.setup.league_mode != LEAGUE_MODE_COLLEGE
        )

    def _build_team_recommendations_widget(self, _record: FranchiseRecord) -> QWidget:
        college_mode = _record.setup.league_mode == LEAGUE_MODE_COLLEGE
        box = QGroupBox("College Program Recommendations" if college_mode else "Team GM Recommendations")
        box.setObjectName("TeamGMRecommendationsPage")
        layout = QVBoxLayout(box)
        controls = QHBoxLayout()
        self.recommendation_action_buttons = []
        for label, callback in (
            ("Generate Program Recommendations" if college_mode else "Generate Team Recommendations", self._run_team_recommendations),
            ("Refresh Recommendations", self._refresh_team_recommendations),
        ):
            button = QPushButton(label, clicked=callback)
            button.setEnabled(not self._recommendations_running())
            self.recommendation_action_buttons.append(button)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.recommendation_text = text
        layout.addWidget(text, 1)
        return box

    def _refresh_team_recommendations(self) -> None:
        if self.recommendation_text is None:
            return
        record = self.repository.load()
        sim_state = self.repository.ensure_sim_state()
        recommendations = self.repository.list_team_recommendations()
        college_mode = record.setup.league_mode == LEAGUE_MODE_COLLEGE
        lines = [
            "# College Program Recommendations" if college_mode else "# Team GM Recommendations",
            "Mode: recommendation-only. No game-memory write, preview, apply, save, import, trade, signing, release, or roster move is performed here.",
            f"League Mode: {league_mode_label(record.setup.league_mode)}",
            f"True Sim Year: {sim_state.sim_year}",
            f"Current Phase: {phase_label(sim_state.current_phase, league_mode=record.setup.league_mode)}",
            f"User Team: {self._team_label(record.setup.user_team_index)}",
            f"AI Teams: {', '.join(str(index) for index in record.setup.llm_gm_team_indexes) or 'none'}",
            "",
            "## Saved Recommendations",
        ]
        if not recommendations:
            lines.append("None")
        for recommendation in recommendations[-30:]:
            approval = "yes" if recommendation.owner_approval_required else "no"
            approval_label = "athletic approval" if college_mode else "owner approval"
            lines.append(
                f"#{recommendation.recommendation_id} Team {recommendation.team_index} {recommendation.team_label} "
                f"[{recommendation.status}] {approval_label}: {approval}"
            )
            lines.append(f"Action: {recommendation.recommended_action}")
            lines.append(f"Reasoning: {recommendation.reasoning}")
            if recommendation.trade_with_user_team:
                lines.append("Pause: proposed trade involves the user-controlled team")
            if recommendation.blocked_reason:
                lines.append(f"Blocked: {recommendation.blocked_reason}")
            lines.append("")
        self.recommendation_text.setPlainText("\n".join(lines))

    def _run_team_recommendations(self) -> None:
        if self._recommendations_running():
            QMessageBox.warning(self, "Team GM recommendations", "Recommendations are already running.")
            return
        try:
            record = self.repository.load()
            sim_state = self.repository.ensure_sim_state()
            if sim_state.status != STATUS_READY:
                raise ValueError("Resolve the current Franchise Phase Controller pause before running CPU teams.")
            requests = build_team_recommendation_requests(record, self.model, sim_state=sim_state)
            if not requests:
                QMessageBox.warning(self, "Team GM recommendations", "No AI league teams selected.")
                return
        except Exception as exc:
            QMessageBox.warning(self, "Team GM recommendations", str(exc))
            return
        self._set_recommendations_running(True)
        self._append_recommendation_status("\nLLM team recommendations running through Hermes API Server...")

        def worker() -> None:
            try:
                result = run_team_recommendation_requests(requests)
                self._recommendation_events.put(("done", result))
            except Exception as exc:
                self._recommendation_events.put(("error", str(exc)))

        self._recommendation_thread = threading.Thread(target=worker, name="nba2k-franchise-recommendations", daemon=True)
        self._recommendation_thread.start()
        self._recommendation_timer.start()

    def _recommendations_running(self) -> bool:
        return self._recommendation_thread is not None and self._recommendation_thread.is_alive()

    def _set_recommendations_running(self, running: bool) -> None:
        for button in self.recommendation_action_buttons:
            button.setEnabled(not running)

    def _append_recommendation_status(self, message: str) -> None:
        if self.recommendation_text is None:
            return
        current = self.recommendation_text.toPlainText()
        self.recommendation_text.setPlainText(current + message)

    def _poll_team_recommendations(self) -> None:
        handled = False
        while not self._recommendation_events.empty():
            kind, payload = self._recommendation_events.get()
            handled = True
            if kind == "done":
                self._finish_team_recommendations(payload)
            else:
                QMessageBox.warning(self, "Team GM recommendations", str(payload))
        if handled or not self._recommendations_running():
            self._recommendation_timer.stop()
            self._recommendation_thread = None
            self._set_recommendations_running(False)

    def _finish_team_recommendations(self, payload: object) -> None:
        if not isinstance(payload, tuple) or not all(isinstance(item, TeamRecommendation) for item in payload):
            QMessageBox.warning(self, "Team GM recommendations", "Invalid recommendation result.")
            return
        saved_recommendations = tuple(self.repository.record_team_recommendation(recommendation) for recommendation in payload)
        user_trade_recommendations = tuple(
            recommendation for recommendation in saved_recommendations if recommendation.trade_with_user_team
        )
        if user_trade_recommendations:
            offers = "; ".join(
                f"{recommendation.team_label}: {recommendation.recommended_action}"
                for recommendation in user_trade_recommendations
            )
            self.repository.pause_for_user_trade(
                "Review, accept, reject, or counter the following proposed trade involving the user-controlled team: "
                + offers
                + ". Then click Trade Resolved / Resume."
            )
        self._refresh_phase_controller()
        self._refresh_team_recommendations()

    def _build_fantasy_draft_widget(self, _record: FranchiseRecord) -> QWidget:
        box = QGroupBox("Fantasy Draft Room")
        box.setObjectName("FantasyDraftRoomPage")
        layout = QVBoxLayout(box)
        controls = QHBoxLayout()
        self.draft_action_buttons = []
        for label, callback in (
            ("Start / Reset Draft", self._start_or_reset_fantasy_draft),
            ("Refresh Draft Room", self._refresh_draft_room),
            ("Run LLM Pick", self._run_llm_draft_pick),
            ("Go Back One AI Pick", self._go_back_one_ai_draft_pick),
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

    def _go_back_one_ai_draft_pick(self) -> None:
        if self._llm_pick_running():
            QMessageBox.warning(self, "Fantasy draft", "Wait for the running LLM pick to finish.")
            return
        try:
            undone = self.repository.undo_last_fantasy_draft_pick(picked_by="llm")
        except Exception as exc:
            QMessageBox.warning(self, "Fantasy draft", str(exc))
            return
        if undone is None:
            QMessageBox.warning(self, "Fantasy draft", "The latest draft pick is not an AI pick.")
            return
        self._refresh_draft_room()
        self._append_draft_status(f"\nUndid AI pick {undone.pick_number}: {undone.player_label}")

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
