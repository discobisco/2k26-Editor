from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Iterable

from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nba2k_editor.models.background_operations import BackgroundOperationWorker
from nba2k_editor.models.data_model import (
    EDITOR_DOMAINS,
    PLAYER_TEAM_FILTER_ALL,
    PLAYER_TEAM_FILTER_BASE_TEAMS,
    PLAYER_TEAM_FILTER_DRAFT_CLASS,
    EditorDataModel,
    FieldEntry,
    RecordListItem,
    verify_edits,
)
from nba2k_editor.models.player_movement import PlayerMovement
from nba2k_editor.models.view_data import DomainRefreshView, PlayerListRequest, PlayerListView
from nba2k_editor.models.team_record_routing import (
    TEAM_RECORD_SECTION_STAT_TABS,
    TEAM_RECORD_SIDE_NAV,
    team_record_indexes,
    team_record_row_group,
    team_record_rows,
)
APP_TITLE = "Offline Player Data Editor"
APP_VIEWPORT_WIDTH = 1600
APP_VIEWPORT_HEIGHT = 900
PLAYER_GENERATOR_SCREEN = "Player Generator"
FRANCHISE_SCREEN = "Franchise"
TARGET_CHOICES: tuple[str, ...] = ("NBA 2K22", "NBA 2K23", "NBA 2K24", "NBA 2K25", "NBA 2K26")
PLAYER_ROSTER_EXPORT_MODES: tuple[str, ...] = (
    "Full Loaded Roster",
    "Draft Class",
    "Players From Team Range",
    "Players From Single Team",
    "Selected Players",
)
PLAYER_ROSTER_EXPORTS_DIR = Path("outputs") / "exports"
PLAYER_ROSTER_DEFAULT_EXPORT_FILE = "player_roster_snapshot.json"


HISTORY_SIDE_NAV: tuple[str, ...] = ("Season Awards", "Past Champions", "League Leaders", "Hall of Famers")
HISTORY_AWARD_TABS: tuple[str, ...] = (
    "Most Valuable Player",
    "Rookie of the Year",
    "Sixth Man of the Year",
    "Defensive Player",
    "Most Improved Player",
    "KIA Clutch Player of the Year",
    "All-NBA 1st Team",
    "All-NBA 2nd Team",
    "All-NBA 3rd Team",
    "All-Defensive 1st Team",
    "All-Defensive 2nd Team",
    "All-Rookie 1st Team",
    "All-Rookie 2nd Team",
    "Coach of the Year",
)
RECORD_SIDE_NAV: tuple[str, ...] = ("Single Game (Regular)", "Single Game (Playoffs)", "Season", "Career")
RECORD_BASE_STAT_TABS: tuple[str, ...] = (
    "Points",
    "FG Made",
    "3PT Made",
    "FT Made",
    "Rebounds",
    "Assists",
    "Blocks",
    "Steals",
    "Minutes",
    "Turnovers",
)
RECORD_EXTENDED_STAT_TABS: tuple[str, ...] = (
    *RECORD_BASE_STAT_TABS,
    "PPG",
    "FG%",
    "3PT%",
    "FT%",
    "RPG",
    "APG",
    "BPG",
    "SPG",
    "MPG",
    "Games Played",
    "Fouls",
    "40+ Point Games",
    "50+ Point Games",
    "60+ Point Games",
    "Triple Doubles",
)
RECORD_SECTION_STAT_TABS: dict[str, tuple[str, ...]] = {
    "Single Game (Regular)": RECORD_BASE_STAT_TABS,
    "Single Game (Playoffs)": RECORD_BASE_STAT_TABS,
    "Season": RECORD_EXTENDED_STAT_TABS,
    "Career": RECORD_EXTENDED_STAT_TABS,
}
HISTORY_SECTION_TABS: dict[str, tuple[str, ...]] = {
    "Season Awards": HISTORY_AWARD_TABS,
    "Past Champions": ("NBA Championship", "FMVP"),
    "League Leaders": ("Points/Game", "Rebounds/Game", "Assists/Game", "Steals/Game", "Blocks/Game", "Minutes/Game"),
    "Hall of Famers": ("All Hall of Famers",),
}
RECORD_SECTION_ROW_LAYOUT: dict[str, tuple[int, int]] = {
    "Single Game (Regular)": (0, 5),
    "Single Game (Playoffs)": (50, 5),
    "Season": (100, 10),
    "Career": (350, 100),
}
HISTORY_AWARD_TYPES: dict[str, int] = {
    "Most Valuable Player": 8,
    "Rookie of the Year": 9,
    "Sixth Man of the Year": 10,
    "Defensive Player": 11,
    "Most Improved Player": 12,
    "KIA Clutch Player of the Year": 13,
    "All-NBA 1st Team": 14,
    "All-NBA 2nd Team": 15,
    "All-NBA 3rd Team": 16,
    "All-Defensive 1st Team": 17,
    "All-Defensive 2nd Team": 18,
    "All-Rookie 1st Team": 19,
    "All-Rookie 2nd Team": 20,
    "Coach of the Year": 21,
}
HISTORY_SECTION_DEFAULT_TYPES: dict[str, int | None] = {
    "Season Awards": 8,
    "Past Champions": 1,
    "League Leaders": 2,
    "Hall of Famers": None,
}
HISTORY_SECTION_TAB_TYPES: dict[str, dict[str, int | None]] = {
    "Past Champions": {"NBA Championship": 1, "FMVP": 1},
    "League Leaders": {
        "Points/Game": 2,
        "Rebounds/Game": 3,
        "Assists/Game": 4,
        "Steals/Game": 5,
        "Blocks/Game": 6,
        "Minutes/Game": 7,
    },
    "Hall of Famers": {"All Hall of Famers": None},
}
DOMAIN_LABELS: dict[str, str] = {"Stadiums": "Stadium"}


@dataclass
class EditorUiState:
    current_screen: str = "Home"
    history_section: str = "Season Awards"
    history_award: str = "Most Valuable Player"
    history_tabs: dict[str, str] = field(default_factory=lambda: {section: tabs[0] for section, tabs in HISTORY_SECTION_TABS.items()})
    record_section: str = "Single Game (Regular)"
    record_stat: str = "Points"
    team_record_section: str = "Single Game (Regular)"
    team_record_stat: str = "Points"
    player_team_filter: str | int = "All Players"
    player_search_text: str = ""
    player_roster_export_folder: str = str(PLAYER_ROSTER_EXPORTS_DIR)
    player_roster_snapshot_filename: str = PLAYER_ROSTER_DEFAULT_EXPORT_FILE
    player_roster_export_mode: str = PLAYER_ROSTER_EXPORT_MODES[0]
    player_roster_team_start: str = "0"
    player_roster_team_end: str = "29"
    selected_item_indexes: dict[str, set[int]] = field(default_factory=dict)
    selection_anchors: dict[str, int | None] = field(default_factory=dict)
    pending_trade_player_index: int | None = None
    pending_trade_team_index: int | None = None
    dirty_rows: set[str] = field(default_factory=set)
    open_rows: dict[str, Any] = field(default_factory=dict)
    row_raw_values: dict[str, Any] = field(default_factory=dict)
    player_season_stat_id_selection: dict[tuple[str, int, str], str] = field(default_factory=dict)

from nba2k_editor.ui.qt_theme import apply_qt_theme
from nba2k_editor.ui.qt_widgets import DetailRow, EditableFieldRow, NavButton, OperationDialog, RecordListWidget, configure_combo_box, configure_output_text, configure_table

NAV_ORDER: tuple[str, ...] = (
    "Players",
    "Teams",
    FRANCHISE_SCREEN,
    PLAYER_GENERATOR_SCREEN,
    "NBA History",
    "NBA Records",
    "Staff",
    "Stadiums",
    "Jerseys",
    "Shoes",
)
APP_SCREENS: tuple[str, ...] = ("Home", *EDITOR_DOMAINS, FRANCHISE_SCREEN, PLAYER_GENERATOR_SCREEN)
_QT_APPLICATION: QApplication | None = None


def _target_executable(label: str) -> str:
    digits = "".join(ch for ch in label if ch.isdigit())[-2:] or "26"
    return f"NBA2K{digits}.exe"


def _ensure_qapplication() -> QApplication:
    global _QT_APPLICATION
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APPLICATION = app
    return app


class QtEditorApp(QMainWindow):
    def __new__(cls, *args: object, **kwargs: object) -> "QtEditorApp":
        _ensure_qapplication()
        return super().__new__(cls)

    def __init__(self, model: EditorDataModel) -> None:
        super().__init__()
        apply_qt_theme(_ensure_qapplication())
        self.model = model
        self.state = EditorUiState()
        self.setWindowTitle(APP_TITLE)
        self.resize(APP_VIEWPORT_WIDTH, APP_VIEWPORT_HEIGHT)
        self.stack = QStackedWidget(self)
        self.nav_buttons: dict[str, NavButton] = {}
        self.screen_widgets: dict[str, QWidget] = {}
        self.domain_lists: dict[str, RecordListWidget] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.count_labels: dict[str, QLabel] = {}
        self.dashboard_metric_labels: dict[str, QLabel] = {}
        self._domain_counts: dict[str, int] = {domain: 0 for domain in EDITOR_DOMAINS}
        self.detail_titles: dict[str, QLabel] = {}
        self.detail_addresses: dict[str, QLabel] = {}
        self.player_detail_rows: dict[str, DetailRow] = {}
        self.table_row_items: dict[str, list[RecordListItem]] = {}
        self.editor_stat_selectors: dict[tuple[str, int, str], QComboBox] = {}
        self.team_summary_inputs: dict[str, QLineEdit] = {}
        self.team_record_table: QTableWidget | None = None
        self.player_filter_combo: QComboBox | None = None
        self.player_search_input: QLineEdit | None = None
        self.player_movement = PlayerMovement(model)
        self.operation_dialog: OperationDialog | None = None
        self.operation_worker = BackgroundOperationWorker()
        self._operation_targets_by_request: dict[int, str] = {}
        self._latest_operation_request_ids: dict[str, int] = {}
        self._operation_progress_requests: set[int] = set()
        self._pending_player_list_request: tuple[int, PlayerListRequest] | None = None
        self._player_list_request_serial = 0
        self.player_generator_display = import_module("nba2k_editor.Player Generator.display")
        self.player_generator_state = self.player_generator_display.empty_generator_display_state()
        self.generator_text: QTextEdit | None = None
        self.generator_year_combo: QComboBox | None = None
        self.generator_league_combo: QComboBox | None = None
        self.generator_position_combo: QComboBox | None = None
        self.generator_source_team_combo: QComboBox | None = None
        self.generator_player_combo: QComboBox | None = None
        self._build_ui()
        self.operation_timer = QTimer(self)
        self.operation_timer.timeout.connect(self._poll_background_operation)

    @property
    def generator_display_state(self) -> Any:
        return self.player_generator_state

    @generator_display_state.setter
    def generator_display_state(self, value: Any) -> None:
        self.player_generator_state = value

    def _generator_display_module(self) -> Any:
        return self.player_generator_display

    def _display_label(self, domain: str) -> str:
        return DOMAIN_LABELS.get(domain, domain)

    def _sidebar_label(self, screen: str) -> str:
        return {
            "Home": "▦  Dashboard",
            "Players": "⌕  Players",
            "Teams": "⌘  Teams",
            FRANCHISE_SCREEN: "▤  Franchise",
            PLAYER_GENERATOR_SCREEN: "◇  Player Gen",
            "NBA History": "◷  NBA History",
            "NBA Records": "▥  NBA Records",
            "Staff": "♙  Staff",
            "Stadiums": "⌂  Stadium",
            "Jerseys": "▣  Jerseys",
            "Shoes": "◈  Shoes",
        }.get(screen, self._display_label(screen))

    def _game_status_text(self) -> str:
        return self.model.runtime_status_text()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("EditorRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        nav_widget = QWidget()
        nav_widget.setObjectName("Sidebar")
        nav_widget.setFixedWidth(152)
        nav = QVBoxLayout(nav_widget)
        nav.setContentsMargins(0, 0, 4, 0)
        nav.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 8, 6, 8)
        logo = QLabel("2K")
        logo.setObjectName("AppLogo")
        brand_text = QVBoxLayout()
        brand_title = QLabel("NBA2K EDITOR")
        brand_title.setObjectName("SidebarTitle")
        brand_subtitle = QLabel("DATA TOOL")
        brand_subtitle.setObjectName("SidebarSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_subtitle)
        brand.addWidget(logo)
        brand.addLayout(brand_text, 1)
        nav.addLayout(brand)
        section = QLabel("MAIN")
        section.setObjectName("SidebarSection")
        nav.addWidget(section)
        nav.addWidget(NavButton(self._sidebar_label("Home"), lambda: self._show_screen("Home")))
        self.nav_buttons["Home"] = nav.itemAt(2).widget()  # type: ignore[assignment]
        for screen in NAV_ORDER:
            if screen in APP_SCREENS:
                button = NavButton(self._sidebar_label(screen), lambda checked=False, s=screen: self._show_screen(s))
                self.nav_buttons[screen] = button
                nav.addWidget(button)
        nav.addStretch(1)
        footer = QLabel("● Local session")
        footer.setObjectName("SidebarFooter")
        nav.addWidget(footer)
        layout.addWidget(nav_widget, 0)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._add_screen("Home", self._build_home_screen())
        for screen in APP_SCREENS:
            if screen == "Home":
                continue
            self._add_screen(screen, self._build_domain_screen(screen))
        self._show_screen("Home")

    def _add_screen(self, screen: str, widget: QWidget) -> None:
        if widget.layout() is not None:
            widget.layout().setContentsMargins(0, 0, 0, 0)
            widget.layout().setSpacing(6)
        self.screen_widgets[screen] = widget
        self.stack.addWidget(widget)

    def _add_split_body(self, layout: QVBoxLayout, left: QWidget, right: QWidget, *, left_width: int = 420) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([left_width, max(700, APP_VIEWPORT_WIDTH - left_width - 220)])
        layout.addWidget(splitter, 1)

    def _show_screen(self, screen: str) -> None:
        self.state.current_screen = screen
        widget = self.screen_widgets.get(screen)
        if widget is not None:
            self.stack.setCurrentWidget(widget)
        for name, button in self.nav_buttons.items():
            button.setChecked(name == screen)
        if screen == PLAYER_GENERATOR_SCREEN:
            self._sync_player_generator_status()
            if not getattr(self.player_generator_state, "source_loaded", False) and not self.operation_worker.is_running():
                self._load_player_generator_source()
        if screen == FRANCHISE_SCREEN:
            franchise_widget = self.screen_widgets.get(FRANCHISE_SCREEN)
            if franchise_widget is not None and hasattr(franchise_widget, "refresh_entry_menu"):
                franchise_widget.refresh_entry_menu()
        if screen == "NBA Records":
            self._show_record_screen_rows()

    def _build_home_screen(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("DashboardScreen")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("COMMAND CENTER")
        eyebrow.setObjectName("DashboardEyebrow")
        title = QLabel("DASHBOARD")
        title.setObjectName("DashboardTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header.addLayout(heading, 1)
        self.home_status = QLabel("Using packaged offsets.")
        self.home_status.setObjectName("DashboardStatus")
        self.home_target_status = QLabel(self._game_status_text())
        self.home_target_status.setObjectName("LiveStatusChip")
        target = configure_combo_box(QComboBox())
        target.addItems(TARGET_CHOICES)
        target.currentTextChanged.connect(lambda text: self._set_target(text))
        header.addWidget(QLabel("Target"))
        header.addWidget(target)
        header.addWidget(QPushButton("Attach", clicked=lambda: self._attach()))
        header.addWidget(QPushButton("Attach + Load All", clicked=lambda: self._attach_and_load_all()))
        header.addWidget(self.home_status)
        header.addWidget(self.home_target_status)
        layout.addLayout(header)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(8)
        for column, (key, label) in enumerate((
            ("domains", "Loaded Domains"),
            ("players", "Loaded Players"),
            ("teams", "Loaded Teams"),
            ("records", "Loaded Records"),
        )):
            card, value_label = self._build_dashboard_metric_card("0", label)
            self.dashboard_metric_labels[key] = value_label
            metrics.addWidget(card, 0, column)
        layout.addLayout(metrics)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_dashboard_navigation_panel(), 0)
        body.addWidget(self._build_dashboard_updates_panel(), 1)
        layout.addLayout(body, 1)

        self._refresh_dashboard_metrics()
        return widget

    def _build_dashboard_metric_card(self, value: str, label: str) -> tuple[QWidget, QLabel]:
        card = QWidget()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        value_label = QLabel(value)
        value_label.setObjectName("MetricValue")
        caption = QLabel(label)
        caption.setObjectName("MetricCaption")
        layout.addWidget(value_label)
        layout.addWidget(caption)
        return card, value_label

    def _build_dashboard_navigation_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("DashboardPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        heading = QLabel("NAVIGATE")
        heading.setObjectName("PanelEyebrow")
        layout.addWidget(heading)
        for label, screen in (
            ("◇  Player Gen", PLAYER_GENERATOR_SCREEN),
            ("▤  Franchise", FRANCHISE_SCREEN),
            ("⌕  Players", "Players"),
            ("⌘  Teams", "Teams"),
            ("◷  NBA History", "NBA History"),
            ("▥  NBA Records", "NBA Records"),
        ):
            button = QPushButton(label, clicked=lambda checked=False, s=screen: self._show_screen(s))
            button.setObjectName("DashboardLinkButton")
            layout.addWidget(button)
        layout.addStretch(1)
        return panel

    def _build_dashboard_updates_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("DashboardPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        eyebrow = QLabel("APP UPDATES")
        eyebrow.setObjectName("PanelEyebrow")
        title = QLabel("What's New")
        title.setObjectName("PanelTitle")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        header.addLayout(title_box, 1)
        header.addWidget(QPushButton("Refresh Lists", clicked=lambda: self._attach_and_load_all()))
        layout.addLayout(header)
        for badge, title_text, body in (
            ("FEATURE", "Players", "Roster list, team filter, selected-player details, and editor launch."),
            ("FEATURE", "Records / History", "Loaded rows render into editable Records and selectable History tables."),
            ("UPDATE", "Player Generator", "Generate, preview, and import through the existing generator display state."),
        ):
            layout.addWidget(self._build_dashboard_update_item(badge, title_text, body))
        layout.addStretch(1)
        return panel

    def _build_dashboard_update_item(self, badge: str, title: str, body: str) -> QWidget:
        item = QWidget()
        item.setObjectName("UpdateItem")
        layout = QVBoxLayout(item)
        layout.setContentsMargins(10, 8, 10, 8)
        label = QLabel(badge)
        label.setObjectName("UpdateBadge")
        label.setFixedWidth(58)
        title_label = QLabel(title)
        title_label.setObjectName("UpdateTitle")
        body_label = QLabel(body)
        body_label.setObjectName("UpdateBody")
        body_label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        return item

    def _build_domain_screen(self, domain: str) -> QWidget:
        if domain == "Players":
            return self._build_players_screen()
        if domain == "Teams":
            return self._build_teams_screen()
        if domain == "NBA History":
            return self._build_history_screen()
        if domain == "NBA Records":
            return self._build_records_screen()
        if domain == PLAYER_GENERATOR_SCREEN:
            return self._build_player_generator_screen()
        if domain == FRANCHISE_SCREEN:
            return import_module("nba2k_editor.franchise.qt_screen").build_franchise_screen(self.model)
        return self._build_generic_domain_screen(domain)

    def _base_domain_screen(self, domain: str) -> tuple[QWidget, QVBoxLayout]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(QLabel(self._display_label(domain)))
        count = QLabel(f"{self._display_label(domain)}: 0")
        status = QLabel(self._game_status_text())
        self.count_labels[domain] = count
        self.status_labels[domain] = status
        header.addWidget(count)
        header.addWidget(status, 1)
        header.addWidget(QPushButton("Refresh", clicked=lambda: self._attach_and_scan((domain,))))
        layout.addLayout(header)
        return widget, layout

    def _build_generic_domain_screen(self, domain: str) -> QWidget:
        widget, layout = self._base_domain_screen(domain)
        record_list = RecordListWidget(lambda indexes, current, d=domain: self._select_item_indexes(d, indexes, current))
        self.domain_lists[domain] = record_list
        detail_widget = QWidget()
        detail = QVBoxLayout(detail_widget)
        detail.setContentsMargins(6, 0, 0, 0)
        detail.setSpacing(6)
        title = QLabel(f"Select a {self._display_label(domain).lower()}")
        address = QLabel("--")
        self.detail_titles[domain] = title
        self.detail_addresses[domain] = address
        detail.addWidget(title)
        detail.addWidget(QLabel("Record address"))
        detail.addWidget(address)
        detail.addWidget(QPushButton(f"Edit {self._display_label(domain)}", clicked=lambda _checked=False, d=domain: self._open_selected(d)))
        detail.addStretch(1)
        self._add_split_body(layout, record_list, detail_widget, left_width=430)
        return widget

    def _build_players_screen(self) -> QWidget:
        widget, layout = self._base_domain_screen("Players")
        controls = QHBoxLayout()
        player_filter_combo = configure_combo_box(QComboBox())
        for label, value in self.model.player_team_filter_options():
            player_filter_combo.addItem(label, value)
        player_filter_combo.currentIndexChanged.connect(lambda _index: self._set_player_team_filter(player_filter_combo.currentData()))
        player_search_input = QLineEdit()
        player_search_input.setPlaceholderText("Search players")
        player_search_input.textChanged.connect(self._set_player_search_text)
        self.player_filter_combo = player_filter_combo
        self.player_search_input = player_search_input
        controls.addWidget(QLabel("Team"))
        controls.addWidget(player_filter_combo)
        controls.addWidget(QLabel("Search"))
        controls.addWidget(player_search_input)
        layout.addLayout(controls)
        record_list = RecordListWidget(
            lambda indexes, current: self._select_item_indexes("Players", indexes, current),
            self._show_player_movement_menu,
        )
        self.domain_lists["Players"] = record_list
        detail_widget = QWidget()
        detail = QVBoxLayout(detail_widget)
        detail.setContentsMargins(6, 0, 0, 0)
        detail.setSpacing(6)
        title = QLabel("Select a player")
        address = QLabel("--")
        self.detail_titles["Players"] = title
        self.detail_addresses["Players"] = address
        detail.addWidget(title)
        detail.addWidget(QLabel("Record address"))
        detail.addWidget(address)
        for label in self.model.player_detail_labels():
            row = DetailRow(label)
            self.player_detail_rows[label] = row
            detail.addWidget(row)
        detail.addWidget(QPushButton("Edit Player", clicked=lambda: self._open_selected("Players")))
        detail.addWidget(QPushButton("Set All Loaded Current Stat IDs To 65535", clicked=self._set_all_players_stat_ids_to_no_stats))
        detail.addWidget(self._build_roster_snapshot_box())
        detail.addStretch(1)
        self._add_split_body(layout, record_list, detail_widget, left_width=520)
        return widget


    def _build_roster_snapshot_box(self) -> QWidget:
        box = QGroupBox("Player Roster Snapshot")
        form = QFormLayout(box)
        self.roster_folder_input = QLineEdit(self.state.player_roster_export_folder)
        self.roster_file_input = QLineEdit(self.state.player_roster_snapshot_filename)
        self.roster_mode_combo = configure_combo_box(QComboBox())
        self.roster_mode_combo.addItems(PLAYER_ROSTER_EXPORT_MODES)
        self.roster_start_input = QLineEdit(self.state.player_roster_team_start)
        self.roster_end_input = QLineEdit(self.state.player_roster_team_end)
        form.addRow("Folder", self.roster_folder_input)
        form.addRow("File", self.roster_file_input)
        form.addRow("Mode", self.roster_mode_combo)
        form.addRow("Team Start", self.roster_start_input)
        form.addRow("Team End", self.roster_end_input)
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Export Snapshot", clicked=self._export_player_roster_snapshot))
        buttons.addWidget(QPushButton("Apply Snapshot", clicked=self._apply_player_roster_snapshot))
        form.addRow(buttons)
        return box

    def _build_teams_screen(self) -> QWidget:
        widget, layout = self._base_domain_screen("Teams")
        record_list = RecordListWidget(lambda indexes, current: self._select_item_indexes("Teams", indexes, current))
        self.domain_lists["Teams"] = record_list
        detail_widget = QWidget()
        detail = QVBoxLayout(detail_widget)
        detail.setContentsMargins(6, 0, 0, 0)
        detail.setSpacing(6)
        title = QLabel("Select a team")
        address = QLabel("--")
        self.detail_titles["Teams"] = title
        self.detail_addresses["Teams"] = address
        detail.addWidget(title)
        detail.addWidget(QLabel("Record address"))
        detail.addWidget(address)
        for label in self.model.team_summary_labels():
            edit = QLineEdit()
            self.team_summary_inputs[label] = edit
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(edit)
            detail.addLayout(row)
        detail.addWidget(QPushButton("Save Team Summary", clicked=self._save_team_summary))
        detail.addWidget(QPushButton("Edit Team", clicked=lambda: self._open_selected("Teams")))
        detail.addStretch(1)
        self._add_split_body(layout, record_list, detail_widget, left_width=430)
        return widget

    def _build_team_records_widget(self) -> QWidget:
        records_box = QGroupBox("Team Records")
        records_layout = QVBoxLayout(records_box)
        record_controls = QHBoxLayout()
        record_section = configure_combo_box(QComboBox())
        record_section.addItems(TEAM_RECORD_SIDE_NAV)
        record_stat = configure_combo_box(QComboBox())
        record_stat.addItems(TEAM_RECORD_SECTION_STAT_TABS[self.state.team_record_section])
        record_section.currentTextChanged.connect(lambda value: self._set_team_record_section(value, record_stat))
        record_stat.currentTextChanged.connect(lambda value: self._set_team_record_stat(value))
        record_controls.addWidget(record_section)
        record_controls.addWidget(record_stat)
        record_controls.addWidget(QPushButton("Load Team Records", clicked=self._show_team_record_rows))
        record_controls.addWidget(QPushButton("Save Team Record Data", clicked=self._save_team_record_data_values))
        record_controls.addWidget(QPushButton("Zero All Team Record Data", clicked=self._zero_all_team_record_data_values))
        records_layout.addLayout(record_controls)
        team_record_table = QTableWidget(0, 0)
        configure_table(team_record_table, editable=True)
        self.team_record_table = team_record_table
        records_layout.addWidget(team_record_table, 1)
        return records_box

    def _build_history_screen(self) -> QWidget:
        widget, layout = self._base_domain_screen("NBA History")
        controls = QHBoxLayout()
        section = configure_combo_box(QComboBox())
        section.addItems(HISTORY_SIDE_NAV)
        tab = configure_combo_box(QComboBox())
        tab.addItems(HISTORY_SECTION_TABS[self.state.history_section])
        section.currentTextChanged.connect(lambda value: self._set_history_section(value, tab))
        tab.currentTextChanged.connect(lambda value: self._set_history_tab(value))
        controls.addWidget(section)
        controls.addWidget(tab)
        controls.addWidget(QPushButton("Load Rows", clicked=self._load_history_screen_rows))
        controls.addWidget(QPushButton("Edit Selected History Row", clicked=lambda: self._open_selected("NBA History")))
        layout.addLayout(controls)
        self.history_table = QTableWidget(0, 0)
        configure_table(self.history_table)
        self.history_table.itemSelectionChanged.connect(lambda: self._select_table_row("NBA History", self.history_table))
        layout.addWidget(self.history_table, 1)
        return widget

    def _build_records_screen(self) -> QWidget:
        widget, layout = self._base_domain_screen("NBA Records")
        controls = QHBoxLayout()
        section = configure_combo_box(QComboBox())
        section.addItems(RECORD_SIDE_NAV)
        stat = configure_combo_box(QComboBox())
        stat.addItems(RECORD_SECTION_STAT_TABS[self.state.record_section])
        section.currentTextChanged.connect(lambda value: self._set_record_section(value, stat))
        stat.currentTextChanged.connect(lambda value: self._set_record_stat(value))
        controls.addWidget(section)
        controls.addWidget(stat)
        controls.addWidget(QPushButton("Load Rows", clicked=self._show_record_screen_rows))
        controls.addWidget(QPushButton("Save Data Values", clicked=self._save_record_data_values))
        controls.addWidget(QPushButton("Zero Data Values", clicked=self._zero_record_data_values))
        controls.addWidget(QPushButton("Edit Selected Record", clicked=lambda: self._open_selected("NBA Records")))
        layout.addLayout(controls)
        self.record_table = QTableWidget(0, 0)
        configure_table(self.record_table, editable=True)
        self.record_table.itemSelectionChanged.connect(lambda: self._select_table_row("NBA Records", self.record_table))
        layout.addWidget(self.record_table, 1)
        return widget

    def _build_player_generator_screen(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        selectors = QHBoxLayout()
        year_combo = configure_combo_box(QComboBox())
        league_combo = configure_combo_box(QComboBox())
        position_combo = configure_combo_box(QComboBox())
        source_team_combo = configure_combo_box(QComboBox())
        player_combo = configure_combo_box(QComboBox())
        year_combo.currentTextChanged.connect(lambda _value: self._refresh_player_generator_dropdowns())
        league_combo.currentTextChanged.connect(lambda _value: self._refresh_player_generator_dropdowns())
        position_combo.currentTextChanged.connect(lambda _value: self._refresh_player_generator_dropdowns())
        source_team_combo.currentTextChanged.connect(lambda _value: self._refresh_player_generator_dropdowns())
        player_combo.currentTextChanged.connect(lambda _value: self._refresh_player_generator_dropdowns())
        self.generator_year_combo = year_combo
        self.generator_league_combo = league_combo
        self.generator_position_combo = position_combo
        self.generator_source_team_combo = source_team_combo
        self.generator_player_combo = player_combo
        selectors.addWidget(QLabel("Season"))
        selectors.addWidget(year_combo)
        selectors.addWidget(QLabel("League"))
        selectors.addWidget(league_combo)
        selectors.addWidget(QLabel("Position"))
        selectors.addWidget(position_combo)
        selectors.addWidget(QLabel("Source Team"))
        selectors.addWidget(source_team_combo)
        selectors.addWidget(QLabel("Player"))
        selectors.addWidget(player_combo, 1)
        layout.addLayout(selectors)
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Load Source", clicked=self._load_player_generator_source))
        buttons.addWidget(QPushButton("Check Roster", clicked=self._check_player_generator_roster))
        buttons.addWidget(QPushButton("Add Current Roster to Pool SQL", clicked=self._add_current_roster_to_player_pool))
        buttons.addWidget(QPushButton("Sync Player Pool SQL", clicked=self._sync_player_generator_pool))
        buttons.addWidget(QPushButton("Display Preview", clicked=self._display_generator_preview))
        buttons.addWidget(QPushButton("Build Draft Class", clicked=self._build_generator_draft_class))
        buttons.addWidget(QPushButton("Import Draft Class", clicked=self._import_generator_draft_class))
        buttons.addWidget(QPushButton("Import By Team Matching", clicked=self._import_generator_to_game_display))
        buttons.addWidget(QPushButton("Import Matched Names", clicked=lambda: self._import_generator_to_game_display(match_existing_player_names=True)))
        buttons.addWidget(QPushButton("Add Missing Players", clicked=self._import_missing_generator_to_game_display))
        layout.addLayout(buttons)
        generator_text = QTextEdit()
        generator_text.setReadOnly(True)
        configure_output_text(generator_text)
        self.generator_text = generator_text
        layout.addWidget(generator_text, 1)
        return widget

    def _set_target(self, selected: str) -> None:
        self.model.select_target_executable(_target_executable(str(selected)))
        self.state.selected_item_indexes.clear()
        self.state.selection_anchors.clear()
        self.state.pending_trade_player_index = None
        self.state.pending_trade_team_index = None
        self._refresh_status_labels()
        for domain, record_list in self.domain_lists.items():
            record_list.set_records([])
            self._set_count(domain, f"{self._display_label(domain)}: 0")
        self._sync_player_team_filter()
        self._sync_player_list()
        self._update_detail_panel("Teams")

    def _refresh_status_labels(self) -> None:
        status = self._game_status_text()
        self.home_status.setText("Using packaged offsets.")
        self.home_target_status.setText(status)
        for label in self.status_labels.values():
            label.setText(status)
        self._refresh_dashboard_metrics()

    def _refresh_dashboard_metrics(self) -> None:
        if not self.dashboard_metric_labels:
            return
        domain_counts = self._domain_counts
        loaded_domains = sum(1 for domain in EDITOR_DOMAINS if domain_counts.get(domain, 0) > 0)
        total_domains = max(1, len(EDITOR_DOMAINS))
        metrics = {
            "domains": f"{loaded_domains} / {total_domains}",
            "teams": f"{domain_counts.get('Teams', 0)} / 30",
            "players": str(domain_counts.get("Players", 0)),
            "records": str(domain_counts.get("NBA Records", 0)),
        }
        for key, value in metrics.items():
            if key in self.dashboard_metric_labels:
                self.dashboard_metric_labels[key].setText(value)

    def _attach(self) -> None:
        self.model.attach()
        self._refresh_status_labels()

    def _attach_and_scan(self, domains: tuple[str, ...]) -> None:
        self._start_background_scan(domains)

    def _attach_and_load_all(self) -> None:
        self._start_background_scan(EDITOR_DOMAINS)

    def _scan_domains_for_request(self, domains: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(domains))

    def _start_background_scan(self, domains: tuple[str, ...]) -> None:
        scan_domains = self._scan_domains_for_request(domains)
        self.home_target_status.setText("Loading record lists...")
        for domain in scan_domains:
            if domain in self.status_labels:
                self.status_labels[domain].setText("Queued for scan...")

        def worker() -> object:
            return self.model.refresh_domains(scan_domains, progress_callback=self._background_operation_progress)

        self._start_background_operation(
            "Load Record Lists",
            worker,
            done_callback=self._apply_domain_refresh_views,
            presentation_target="domain-refresh",
        )

    def _apply_domain_refresh_views(self, result: object) -> None:
        views = tuple(result) if isinstance(result, tuple) else ()
        if not all(isinstance(view, DomainRefreshView) for view in views):
            raise TypeError("domain refresh did not return DomainRefreshView payloads")
        for view in views:
            domain = view.domain
            items = view.items
            self._domain_counts[domain] = len(items)
            player_filter_active = domain == "Players" and (
                self.state.player_team_filter != PLAYER_TEAM_FILTER_ALL or self.state.player_search_text.strip()
            )
            if not player_filter_active:
                self._set_count(domain, f"{self._display_label(domain)}: {len(items)}")
            if domain in self.status_labels:
                self.status_labels[domain].setText(view.status)
            if domain in self.domain_lists:
                selected = self.state.selected_item_indexes.get(domain, set())
                records = [(int(item.index), item.display_label) for item in items]
                if domain == "Players":
                    visible_indexes = self.domain_lists[domain].visible_indexes() if player_filter_active else None
                    self.domain_lists[domain].set_all_records(
                        records,
                        selected,
                        visible_indexes=visible_indexes,
                    )
                else:
                    self.domain_lists[domain].set_records(records, selected)
        if any(view.domain == "Teams" for view in views):
            self._sync_player_team_filter()
        if any(view.domain == "Players" for view in views) and (
            self.state.player_team_filter != PLAYER_TEAM_FILTER_ALL or self.state.player_search_text.strip()
        ):
            self._request_player_list_view()
        self.home_target_status.setText("Record lists loaded.")
        self._refresh_dashboard_metrics()

    def _set_count(self, domain: str, text: str) -> None:
        if domain in self.count_labels:
            self.count_labels[domain].setText(text)

    def _sync_domain_list(self, domain: str) -> None:
        items = self.model.domain_items(domain)
        self._domain_counts[domain] = len(items)
        self._set_count(domain, f"{self._display_label(domain)}: {self.model.domain_item_count(domain)}")
        if domain in self.status_labels:
            self.status_labels[domain].setText(self.model.domain_status(domain))
        if domain == "NBA History":
            self._show_history_screen_rows()
            self._refresh_dashboard_metrics()
            return
        if domain == "NBA Records":
            self._show_record_screen_rows()
            self._refresh_dashboard_metrics()
            return
        selected = self.state.selected_item_indexes.get(domain, set())
        if domain in self.domain_lists:
            self.domain_lists[domain].set_records([(int(item.index), item.display_label) for item in items], selected)
        self._update_detail_panel(domain)
        self._refresh_dashboard_metrics()

    def _sync_player_team_filter(self) -> None:
        if self.player_filter_combo is None:
            return
        options = list(self.model.player_team_filter_options())
        option_values = {value for _label, value in options}
        current = self.state.player_team_filter if self.state.player_team_filter in option_values else (options[0][1] if options else PLAYER_TEAM_FILTER_ALL)
        self.player_filter_combo.blockSignals(True)
        self.player_filter_combo.clear()
        for label, value in options:
            self.player_filter_combo.addItem(label, value)
        self.player_filter_combo.setCurrentIndex(self.player_filter_combo.findData(current))
        self.player_filter_combo.blockSignals(False)
        self.state.player_team_filter = current

    def _sync_player_list(self) -> None:
        self._request_player_list_view()

    def _request_player_list_view(self) -> None:
        self._player_list_request_serial += 1
        request = PlayerListRequest(
            filter_key=self.state.player_team_filter,
            query=self.state.player_search_text,
        )
        self._pending_player_list_request = (self._player_list_request_serial, request)
        self._start_pending_player_list_request()

    def _start_pending_player_list_request(self) -> None:
        if self._pending_player_list_request is None or self.operation_worker.is_running():
            return
        serial, request = self._pending_player_list_request
        self._pending_player_list_request = None

        def worker() -> object:
            return self.model.prepare_player_list_view(request.filter_key, request.query)

        self._start_background_operation(
            "Prepare Player List",
            worker,
            done_callback=lambda result: self._apply_player_list_view(serial, result),
            presentation_target="player-list",
            show_progress=False,
            warn_if_busy=False,
        )

    def _apply_player_list_view(self, serial: int, result: object) -> None:
        if serial != self._player_list_request_serial:
            return
        if not isinstance(result, PlayerListView):
            raise TypeError("player list request did not return PlayerListView")
        self._set_count("Players", f"Players: {len(result.items)}")
        selected = self.state.selected_item_indexes.get("Players", set())
        if "Players" in self.domain_lists:
            self.domain_lists["Players"].set_visible_records(
                [(int(item.index), item.display_label) for item in result.items],
                selected,
            )

    def _select_item_indexes(self, domain: str, selected_indexes: set[int], current_index: int | None = None) -> None:
        self.state.selected_item_indexes[domain] = set(selected_indexes)
        if not selected_indexes:
            self.model.select_item_by_index(domain, None)
            self._update_detail_panel(domain)
            return
        primary_index = current_index if current_index in selected_indexes else next(iter(selected_indexes))
        self.model.select_item_by_index(
            domain,
            primary_index,
            player_team_filter=self.state.player_team_filter if domain == "Players" else None,
        )
        self._update_detail_panel(domain)

    def _set_player_team_filter(self, value: object) -> None:
        self.state.player_team_filter = value if isinstance(value, (str, int)) else PLAYER_TEAM_FILTER_ALL
        self._sync_player_list()

    def _set_player_search_text(self, value: str) -> None:
        self.state.player_search_text = value
        self._sync_player_list()

    def _update_detail_panel(self, domain: str) -> None:
        item = self.model.selected_item(domain) if hasattr(self.model, "selected_item") else None
        title = self.detail_titles.get(domain)
        address = self.detail_addresses.get(domain)
        if title is not None:
            title.setText(self.model.selected_detail_title(domain, self._display_label(domain)) if item is not None else f"Select a {self._display_label(domain).lower()}")
        if address is not None:
            address.setText(self.model.selected_record_address_text(domain) if item is not None and hasattr(self.model, "selected_record_address_text") else "--")
        if domain == "Teams" and item is not None:
            for label, value in self.model.selected_team_summary_values().items():
                if label in self.team_summary_inputs:
                    self.team_summary_inputs[label].setText(str(value))
            self._show_team_record_rows()
        elif domain == "Teams":
            self._show_team_record_rows()
        if domain == "Players" and item is not None:
            for label, value in self.model.selected_player_detail_values().items():
                if label in self.player_detail_rows:
                    self.player_detail_rows[label].set_value(value)

    def _save_team_summary(self) -> None:
        values = {label: edit.text() for label, edit in self.team_summary_inputs.items()}
        result = self.model.save_selected_team_summary(values)
        QMessageBox.information(self, "Team Summary", str(result))

    def _selected_table_item(self, domain: str, table: QTableWidget) -> RecordListItem | None:
        row = table.currentRow()
        items = self.table_row_items.get(domain, [])
        if row < 0 or row >= len(items):
            return None
        return items[row]

    def _open_selected(self, domain: str) -> None:
        item = None
        if domain == "NBA Records" and hasattr(self, "record_table"):
            item = self._selected_table_item(domain, self.record_table)
        else:
            item = self.model.selected_item(domain)
        if item is None:
            QMessageBox.warning(self, "No selection", f"Select a {self._display_label(domain).lower()} first.")
            return
        self._open_editor_window(item)

    def _row_key(self, item: RecordListItem, entry: FieldEntry) -> str:
        return f"{entry.domain}:{item.index}:{entry.ordinal}"

    def _mark_row_dirty(self, row_key: str) -> None:
        self.state.dirty_rows.add(row_key)

    def _selected_editor_items(self, source: RecordListItem) -> list[RecordListItem]:
        indexes = self.state.selected_item_indexes.get(source.domain, set())
        if source.domain == "Players":
            items = self.model.player_items_for_team_filter(self.state.player_team_filter)
        else:
            items = getattr(self.model, "loaded_items", {}).get(source.domain, {})
        return [items[index] for index in sorted(indexes) if index in items]

    def _player_movement_items(self, indexes: Iterable[int]) -> list[RecordListItem]:
        items = self.model.loaded_items.get("Players", {})
        return [items[index] for index in sorted(set(indexes)) if index in items]

    def _show_player_movement_menu(self, player_index: int, position: QPoint) -> None:
        items = self.model.player_items_for_team_filter(self.state.player_team_filter)
        if player_index not in items:
            return
        selected_indexes = self.state.selected_item_indexes.get("Players", set())
        if player_index not in selected_indexes:
            selected_indexes = {player_index}
            self._select_item_indexes("Players", selected_indexes, player_index)

        menu = QMenu(self)
        menu.setObjectName("PlayerMovementContextMenu")
        add_menu = menu.addMenu("Add to Team")
        add_menu.menuAction().setObjectName("AddPlayerToTeamMenu")
        teams = self.model.domain_items("Teams")
        add_menu.setEnabled(bool(teams))
        for team in teams:
            action = add_menu.addAction(team.display_label)
            action.setData(int(team.index))
            action.triggered.connect(
                lambda _checked=False, p=player_index, t=int(team.index): self._add_player_to_team(p, t)
            )

        remove_action = menu.addAction("Remove from Team")
        remove_action.setObjectName("RemovePlayerFromTeamAction")
        remove_action.triggered.connect(lambda _checked=False, p=player_index: self._remove_player_from_team(p))

        pending_index = self.state.pending_trade_player_index
        if pending_index is None:
            trade_menu = menu.addMenu("Trade Player")
            trade_menu.menuAction().setObjectName("TradePlayerMenu")
            trade_menu.setEnabled(bool(teams))
            for team in teams:
                action = trade_menu.addAction(team.display_label)
                action.setData(int(team.index))
                action.triggered.connect(
                    lambda _checked=False, p=player_index, t=int(team.index): self._begin_player_trade(p, t)
                )
        else:
            trade_action = menu.addAction("Trade Player")
            trade_action.setObjectName("TradePlayerAction")
            trade_action.triggered.connect(lambda _checked=False, p=player_index: self._complete_player_trade(p))
        menu.exec(position)

    def _begin_player_trade(self, player_index: int, team_index: int) -> None:
        player = self.model.loaded_items.get("Players", {}).get(player_index)
        team = self.model.loaded_items.get("Teams", {}).get(team_index)
        if player is None or team is None:
            QMessageBox.warning(self, "Player Movement", "The selected player or destination team is not loaded.")
            return
        self.state.pending_trade_player_index = player_index
        self.state.pending_trade_team_index = team_index
        self.state.selected_item_indexes["Players"] = set()
        self.model.select_item_by_index("Players", None)
        self.state.player_team_filter = team_index
        self.state.player_search_text = ""
        if self.player_search_input is not None:
            self.player_search_input.blockSignals(True)
            self.player_search_input.clear()
            self.player_search_input.blockSignals(False)
        self._sync_player_team_filter()
        self._sync_player_list()
        QMessageBox.information(
            self,
            "Player Movement",
            f"Select a player on {team.label}, right-click, and choose Trade Player.",
        )

    def _add_player_to_team(self, player_index: int, team_index: int) -> None:
        players = self._player_movement_items((player_index,))
        team = self.model.loaded_items.get("Teams", {}).get(team_index)
        if len(players) != 1 or team is None:
            QMessageBox.warning(self, "Player Movement", "The selected player or team is not loaded.")
            return
        try:
            placement = self.player_movement.add_player(players[0], team)
        except Exception as exc:
            QMessageBox.warning(self, "Player Movement", str(exc))
            return
        self._sync_player_list()
        QMessageBox.information(self, "Player Movement", f"Added {players[0].label} to {team.label} PLAYER{placement.slot}.")

    def _remove_player_from_team(self, player_index: int) -> None:
        players = self._player_movement_items((player_index,))
        if len(players) != 1:
            QMessageBox.warning(self, "Player Movement", "The selected player is not loaded.")
            return
        try:
            placement = self.player_movement.remove_player(players[0])
        except Exception as exc:
            QMessageBox.warning(self, "Player Movement", str(exc))
            return
        self._sync_player_list()
        QMessageBox.information(self, "Player Movement", f"Removed {players[0].label} from {placement.team.label}.")

    def _complete_player_trade(self, second_player_index: int) -> None:
        first_player_index = self.state.pending_trade_player_index
        destination_team_index = self.state.pending_trade_team_index
        if first_player_index is None or destination_team_index is None:
            QMessageBox.warning(self, "Player Movement", "Choose a destination team for the first player.")
            return
        destination_items = self.model.player_items_for_team_filter(destination_team_index)
        if second_player_index not in destination_items:
            QMessageBox.warning(self, "Player Movement", "Select a player from the chosen destination team.")
            return
        players = self._player_movement_items((first_player_index, second_player_index))
        if len(players) != 2 or first_player_index == second_player_index:
            QMessageBox.warning(self, "Player Movement", "Select a different loaded player to complete the trade.")
            return
        try:
            self.player_movement.trade_players(players[0], players[1])
        except Exception as exc:
            QMessageBox.warning(self, "Player Movement", str(exc))
            return
        self.state.pending_trade_player_index = None
        self.state.pending_trade_team_index = None
        self.state.selected_item_indexes["Players"] = set()
        self.model.select_item_by_index("Players", None)
        self._sync_player_list()
        QMessageBox.information(self, "Player Movement", f"Traded {players[0].label} and {players[1].label}.")

    def _editor_window_label(self, source: RecordListItem) -> str:
        items = self._selected_editor_items(source)
        if len(items) > 1:
            return f"{source.domain} [{len(items)} selected]"
        return f"{source.domain} [{source.index}] {source.label}"

    def _selected_season_stat_selector(self, entry: FieldEntry, item: RecordListItem) -> str | None:
        key = (entry.domain, item.index, entry.group)
        return self.state.player_season_stat_id_selection.get(key)

    def _season_stat_selector_key(self, entry: FieldEntry, item: RecordListItem) -> tuple[str, int, str]:
        return (entry.domain, item.index, entry.group)

    def _season_stat_selector_options(self, entry: FieldEntry, item: RecordListItem) -> list[str]:
        return list(self.model.player_season_stat_id_options(item.index))

    def _set_season_stat_selector(self, entry: FieldEntry, item: RecordListItem, selected: str) -> None:
        self.state.player_season_stat_id_selection[self._season_stat_selector_key(entry, item)] = selected

    def _ensure_season_stat_selector(self, entry: FieldEntry, item: RecordListItem, options: list[str]) -> str | None:
        if not options:
            return None
        current = self._selected_season_stat_selector(entry, item)
        if current not in options:
            current = options[0]
            self._set_season_stat_selector(entry, item, current)
        return current

    def _row_stat_selector_for_item(self, entry: FieldEntry, item: RecordListItem, source: RecordListItem) -> str | None:
        selected = self._selected_season_stat_selector(entry, item)
        if selected is not None:
            return selected
        return self._selected_season_stat_selector(entry, source)

    def _refresh_stat_detail_rows(self, source: RecordListItem, group: str, row_widgets: dict[str, EditableFieldRow]) -> None:
        for row_key, row in row_widgets.items():
            entry = self.state.open_rows[row_key]
            if entry.domain != source.domain or entry.group != group or not self.model.is_player_selected_stat_detail_entry(entry):
                continue
            try:
                selector = self._selected_season_stat_selector(entry, source)
                value_info = self.model.read_entry_value_for_item(entry, source, stat_selector=selector)
                display = str(value_info.get("display_value", ""))
                row.current.setText(display)
                row.new_value.setText(display)
                row.status.setText("")
                self.state.dirty_rows.discard(row_key)
            except Exception as exc:
                row.current.setText(f"ERROR: {exc}")
                row.new_value.setText("")
                row.status.setText(str(exc))

    def _add_season_stat_selector(
        self,
        layout: QVBoxLayout,
        source: RecordListItem,
        entries: list[FieldEntry],
        row_widgets: dict[str, EditableFieldRow],
    ) -> None:
        detail_entries = [entry for entry in entries if self.model.is_player_selected_stat_detail_entry(entry)]
        if not detail_entries:
            return
        selector_entry = detail_entries[0]
        options = self._season_stat_selector_options(selector_entry, source)
        selected = self._ensure_season_stat_selector(selector_entry, source, options)
        row = QHBoxLayout()
        combo = configure_combo_box(QComboBox())
        combo.addItems(options)
        if selected is not None:
            combo.setCurrentText(selected)
        combo.currentTextChanged.connect(
            lambda value, entry=selector_entry, item=source, group=selector_entry.group, widgets=row_widgets: (
                self._set_season_stat_selector(entry, item, value),
                self._refresh_stat_detail_rows(item, group, widgets),
            )
        )
        self.editor_stat_selectors[self._season_stat_selector_key(selector_entry, source)] = combo
        row.addWidget(QLabel("Active Season Stat ID"))
        row.addWidget(combo, 1)
        layout.addLayout(row)

    def _open_editor_window(self, source: RecordListItem) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._editor_window_label(source))
        dialog.resize(820, 560)
        dialog.setMinimumSize(520, 360)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        row_widgets: dict[str, EditableFieldRow] = {}
        for section, groups in self.model.grouped_fields(source.domain).items():
            section_widget = QWidget()
            section_layout = QVBoxLayout(section_widget)
            group_tabs = QTabWidget()
            for group, entries in groups.items():
                group_widget = QWidget()
                group_layout = QVBoxLayout(group_widget)
                self._add_season_stat_selector(group_layout, source, entries, row_widgets)
                row_entries = [entry for entry in entries if not self.model.is_player_season_id_selector_entry(entry)]
                for entry in row_entries:
                    row_key = self._row_key(source, entry)
                    stat_selector = self._selected_season_stat_selector(entry, source)
                    try:
                        value_info = self.model.read_entry_value_for_item(entry, source, stat_selector=stat_selector)
                        display = str(value_info.get("display_value", ""))
                    except Exception as exc:
                        display = f"ERROR: {exc}"
                    options = self.model.field_options(entry) if hasattr(self.model, "field_options") else []
                    row = EditableFieldRow(entry.display_name, display, self._mark_row_dirty, row_key, options)
                    row_widgets[row_key] = row
                    self.state.open_rows[row_key] = entry
                    group_layout.addWidget(row)
                group_layout.addStretch(1)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setMinimumSize(360, 220)
                scroll.setWidget(group_widget)
                group_tabs.addTab(scroll, str(group))
            section_layout.addWidget(group_tabs)
            tabs.addTab(section_widget, str(section))
        if source.domain == "Teams":
            select_item = getattr(self.model, "select_item", None)
            if callable(select_item):
                select_item("Teams", source)
            tabs.addTab(self._build_team_records_widget(), "Team Records")
            self._show_team_record_rows()
        layout.addWidget(tabs, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Save", clicked=lambda: self._save_item_editor(source, row_widgets)))
        if source.domain == "Players":
            buttons.addWidget(QPushButton("Reset", clicked=lambda: self._reset_item_editor(source, row_widgets)))
        buttons.addWidget(QPushButton("Close", clicked=dialog.accept))
        layout.addLayout(buttons)
        dialog.show()

    def _save_item_editor(self, source: RecordListItem, row_widgets: dict[str, EditableFieldRow]) -> None:
        targets = self._selected_editor_items(source)
        for row_key, row in row_widgets.items():
            entry = self.state.open_rows[row_key]
            if row_key not in self.state.dirty_rows:
                continue
            value = row.value_text()
            succeeded = 0
            for item in targets:
                stat_selector = self._row_stat_selector_for_item(entry, item, source)
                self.model.write_entry_value_for_item(entry, item, value=value, stat_selector=stat_selector)
                succeeded += 1
            row.status.setText(f"saved {succeeded} records")
            self.state.dirty_rows.discard(row_key)

    def _reset_item_editor(self, source: RecordListItem, row_widgets: dict[str, EditableFieldRow]) -> None:
        targets = self._selected_editor_items(source)
        results: list[dict[str, int]] = []
        stat_entry = next(
            (
                entry
                for entry in self.state.open_rows.values()
                if entry.domain == source.domain and self.model.is_player_selected_stat_detail_entry(entry)
            ),
            None,
        )
        for item in targets:
            stat_selector = self._row_stat_selector_for_item(stat_entry, item, source) if stat_entry is not None else None
            results.append(self.model.reset_player_editor_values(item=item, stat_selector=stat_selector))
        attempted = sum(result.get("attempted", 0) for result in results)
        succeeded = sum(result.get("succeeded", 0) for result in results)
        failed = sum(result.get("failed", 0) for result in results)
        summary = {"players": len(targets), "attempted": attempted, "succeeded": succeeded, "failed": failed}
        for row in row_widgets.values():
            row.status.setText(str(summary))

    def _record_row_group(self, section: str, stat: str) -> tuple[int, int]:
        section_start, row_count = RECORD_SECTION_ROW_LAYOUT.get(section, RECORD_SECTION_ROW_LAYOUT["Single Game (Regular)"])
        tabs = RECORD_SECTION_STAT_TABS.get(section, RECORD_BASE_STAT_TABS)
        stat_index = tabs.index(stat) if stat in tabs else 0
        return section_start + stat_index * row_count, row_count

    def _active_record_row_group(self) -> tuple[int, int]:
        return self._record_row_group(self.state.record_section, self.state.record_stat)

    def _active_record_indexes(self) -> tuple[int, ...]:
        start, count = self._active_record_row_group()
        return tuple(start + index for index in range(count))

    def _all_record_indexes(self) -> tuple[int, ...]:
        indexes: list[int] = []
        for section, stats in RECORD_SECTION_STAT_TABS.items():
            for stat in stats:
                start, count = self._record_row_group(section, stat)
                indexes.extend(start + index for index in range(count))
        return tuple(dict.fromkeys(indexes))

    def _all_team_record_indexes(self) -> tuple[int, ...]:
        team_items = getattr(self.model, "loaded_items", {}).get("Teams", {}).values()
        indexes: list[int] = []
        for team in team_items:
            indexes.extend(team_record_indexes(self.model, team))
        return tuple(dict.fromkeys(indexes))

    def _active_team_record_indexes(self) -> tuple[int, ...]:
        team = self.model.selected_item("Teams")
        if team is None:
            return ()
        indexes = tuple(team_record_indexes(self.model, team))
        row_start, row_count = team_record_row_group(self.state.team_record_section, self.state.team_record_stat)
        return indexes[row_start : row_start + row_count]

    def _table_data_value(self, table: QTableWidget | None, row: int) -> str:
        if table is None or table.columnCount() <= 0:
            return ""
        data_column = table.columnCount() - 1
        for column in range(table.columnCount()):
            header = table.horizontalHeaderItem(column)
            if header is not None and header.text().strip().casefold() == "data":
                data_column = column
                break
        item = table.item(row, data_column)
        return "" if item is None else item.text()

    def _show_team_record_rows(self) -> None:
        if self.team_record_table is None:
            return
        team = self.model.selected_item("Teams")
        if team is None:
            self.table_row_items["Team Records"] = []
            self._fill_table(self.team_record_table, [{"Status": "Select a team."}])
            return
        try:
            rows = team_record_rows(self.model, team, self.state.team_record_section, self.state.team_record_stat)
            active_indexes = self._active_team_record_indexes()
            self.table_row_items["Team Records"] = [
                RecordListItem("NBA Records", index, self.model.record_address("NBA Records", index), f"{team.display_label} {self.state.team_record_section} {self.state.team_record_stat} #{row + 1}")
                for row, index in enumerate(active_indexes[: len(rows)])
            ]
        except Exception as exc:
            rows = [{"Status": f"Team Records unavailable: {exc}"}]
            self.table_row_items["Team Records"] = []
        self._fill_table(self.team_record_table, rows)

    def _save_team_record_data_values(self) -> None:
        team = self.model.selected_item("Teams")
        if team is None:
            QMessageBox.warning(self, "No selection", "Select a team first.")
            return
        data_entry = self.model._field_by_normalized_name("NBA Records", "DATA")
        if data_entry is None:
            QMessageBox.warning(self, "Team Records", "DATA field is not available for NBA Records.")
            return
        active_indexes = self._active_team_record_indexes()
        visible_count = self.team_record_table.rowCount() if self.team_record_table is not None else len(active_indexes)
        saved = 0
        for row, index in enumerate(active_indexes[:visible_count]):
            self.model.write_entry_value(data_entry, index=index, value=self._table_data_value(self.team_record_table, row))
            saved += 1
        QMessageBox.information(self, "Team Records", f"saved {saved}/{len(active_indexes)}")

    def _record_data_value(self, row: int) -> str:
        if not hasattr(self, "record_table"):
            return ""
        item = self.record_table.item(row, self.record_table.columnCount() - 1)
        return "" if item is None else item.text()

    def _save_record_data_values(self) -> None:
        active_indexes = self._active_record_indexes()
        visible_count = self.record_table.rowCount() if hasattr(self, "record_table") else len(active_indexes)
        values = {index: self._record_data_value(row) for row, index in enumerate(active_indexes[:visible_count])}
        result = self.model.save_record_data_values(values)
        QMessageBox.information(self, "NBA Records", str(result))

    def _zero_record_data_values(self) -> None:
        data_entry = self.model._field_by_normalized_name("NBA Records", "DATA")
        if data_entry is None:
            QMessageBox.warning(self, "NBA Records", "DATA field is not available for NBA Records.")
            return
        indexes = tuple(dict.fromkeys((*self._all_record_indexes(), *self._all_team_record_indexes())))
        for index in indexes:
            self.model.write_entry_value(data_entry, index=index, value=0)
        QMessageBox.information(self, "NBA Records", f"zeroed {len(indexes)} records")
        self._show_record_screen_rows()

    def _zero_all_team_record_data_values(self) -> None:
        team = self.model.selected_item("Teams")
        if team is None:
            QMessageBox.warning(self, "No selection", "Select a team first.")
            return
        indexes = team_record_indexes(self.model, team)
        data_entry = self.model._field_by_normalized_name("NBA Records", "DATA")
        if data_entry is None:
            QMessageBox.warning(self, "Team Records", "DATA field is not available for NBA Records.")
            return
        for index in indexes:
            self.model.write_entry_value(data_entry, index=index, value=0)
        QMessageBox.information(self, "Team Records", f"zeroed {len(indexes)}/{len(indexes)}")
        self._show_team_record_rows()

    def _set_history_section(self, section: str, tab_combo: QComboBox) -> None:
        self.state.history_section = section
        tabs = HISTORY_SECTION_TABS[section]
        tab_combo.blockSignals(True)
        tab_combo.clear()
        tab_combo.addItems(tabs)
        tab_combo.blockSignals(False)
        self.state.history_tabs[section] = tabs[0]
        self._show_history_screen_rows()

    def _set_history_tab(self, tab: str) -> None:
        self.state.history_tabs[self.state.history_section] = tab
        self._show_history_screen_rows()

    def _history_type_for_tab(self, section: str, tab: str) -> int | None:
        if section == "Season Awards":
            return HISTORY_AWARD_TYPES[tab]
        return HISTORY_SECTION_TAB_TYPES.get(section, {}).get(tab, HISTORY_SECTION_DEFAULT_TYPES.get(section))

    def _active_history_type(self) -> int | None:
        return self._history_type_for_tab(self.state.history_section, self.state.history_tabs[self.state.history_section])

    def _set_record_section(self, section: str, stat_combo: QComboBox) -> None:
        self.state.record_section = section
        stats = RECORD_SECTION_STAT_TABS[section]
        stat_combo.blockSignals(True)
        stat_combo.clear()
        stat_combo.addItems(stats)
        stat_combo.blockSignals(False)
        self.state.record_stat = stats[0]
        self._show_record_screen_rows()

    def _set_record_stat(self, stat: str) -> None:
        self.state.record_stat = stat
        self._show_record_screen_rows()

    def _set_team_record_section(self, section: str, stat_combo: QComboBox) -> None:
        self.state.team_record_section = section
        stats = TEAM_RECORD_SECTION_STAT_TABS[section]
        stat_combo.blockSignals(True)
        stat_combo.clear()
        stat_combo.addItems(stats)
        stat_combo.blockSignals(False)
        self.state.team_record_stat = stats[0]
        self._show_team_record_rows()

    def _set_team_record_stat(self, stat: str) -> None:
        self.state.team_record_stat = stat
        self._show_team_record_rows()

    def _load_history_screen_rows(self) -> None:
        if getattr(self.model, "domain_item_count")("NBA History") <= 0:
            self._start_background_scan(("NBA History",))
            return
        self._show_history_screen_rows()

    def _history_table_items(self, history_type: int | None) -> list[RecordListItem]:
        items = list(getattr(self.model, "loaded_items", {}).get("NBA History", {}).values())
        read_raw_int = getattr(self.model, "_read_named_raw_int", None)
        if callable(read_raw_int):
            def season_key(item: RecordListItem) -> int:
                value = read_raw_int("NBA History", item, "SEASON")
                return int(str(value)) if value is not None else -1

            if history_type is not None:
                items = [item for item in items if read_raw_int("NBA History", item, "TYPE") == history_type]
            items = sorted(items, key=season_key, reverse=True)
        return items

    def _show_history_screen_rows(self) -> None:
        tab = self.state.history_tabs[self.state.history_section]
        history_type = self._active_history_type()
        try:
            rows = self.model.refresh_history_screen_rows(self.state.history_section, tab, history_type)
            self.table_row_items["NBA History"] = self._history_table_items(history_type)
        except Exception as exc:
            rows = [{"Status": f"NBA History unavailable: {exc}"}]
            self.table_row_items["NBA History"] = []
        self._fill_table(self.history_table, rows)

    def _show_record_screen_rows(self) -> None:
        start, count = self._active_record_row_group()
        try:
            rows = self.model.refresh_record_screen_rows(
                self.state.record_section,
                self.state.record_stat,
                record_row_start=start,
                record_row_count=count,
            )
            self.table_row_items["NBA Records"] = [
                RecordListItem("NBA Records", index, self.model.record_address("NBA Records", index), f"{self.state.record_section} {self.state.record_stat} #{row + 1}")
                for row, index in enumerate(self._active_record_indexes())
            ]
        except Exception as exc:
            rows = [{"Status": f"NBA Records unavailable: {exc}"}]
            self.table_row_items["NBA Records"] = []
        self._fill_table(self.record_table, rows)

    def _select_table_row(self, domain: str, table: QTableWidget) -> None:
        item = self._selected_table_item(domain, table)
        if item is None:
            return
        if domain == "NBA Records":
            return
        self.model.select_item_by_index(domain, int(item.index))
        self._update_detail_panel(domain)

    def _fill_table(self, table: QTableWidget, rows: list[dict[str, str]]) -> None:
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, column in enumerate(columns):
                table.setItem(row_index, col_index, QTableWidgetItem(str(row.get(column, ""))))

    def _player_roster_snapshot_path(self) -> Path:
        self.state.player_roster_export_folder = self.roster_folder_input.text()
        self.state.player_roster_snapshot_filename = self.roster_file_input.text() or PLAYER_ROSTER_DEFAULT_EXPORT_FILE
        return Path(self.state.player_roster_export_folder) / self.state.player_roster_snapshot_filename

    def _player_roster_export_mode(self) -> str:
        self.state.player_roster_export_mode = self.roster_mode_combo.currentText()
        return self.state.player_roster_export_mode

    def _player_roster_team_range(self) -> tuple[int, int]:
        self.state.player_roster_team_start = self.roster_start_input.text()
        self.state.player_roster_team_end = self.roster_end_input.text()
        return int(self.state.player_roster_team_start), int(self.state.player_roster_team_end)

    def _team_items_by_index_range(self, start: int, end: int) -> list[RecordListItem]:
        return [item for item in self.model.domain_items("Teams") if start <= int(item.index) <= end]

    def _team_item_by_index(self, index: int) -> RecordListItem | None:
        return self.model.loaded_items.get("Teams", {}).get(int(index))

    def _player_roster_export_items(self, mode: str) -> tuple[str, list[RecordListItem], Iterable[dict[str, Any] | None] | None]:
        if mode == "Draft Class":
            return mode, list(self.model.player_items_for_team_filter(PLAYER_TEAM_FILTER_DRAFT_CLASS).values()), None
        if mode == "Selected Players":
            selected_indexes = self.state.selected_item_indexes.get("Players", set())
            items = [item for index, item in self.model.player_items_for_team_filter(PLAYER_TEAM_FILTER_ALL).items() if int(index) in selected_indexes]
            return mode, items, None
        if mode in {"Players From Team Range", "Players From Single Team"}:
            start, end = self._player_roster_team_range()
            if mode == "Players From Single Team":
                selected = self.state.player_team_filter
                if not isinstance(selected, int):
                    raise ValueError("select a loaded team in the Team dropdown for single-team export")
                team = self._team_item_by_index(selected)
                if team is None:
                    raise ValueError(f"selected team index is not loaded: {selected}")
                teams = [team]
            else:
                teams = self._team_items_by_index_range(start, end)
            roster_rows = self.model.player_roster_slot_items_for_team_items(teams)
            players = [player for player, _placement in roster_rows]
            placements = [placement for _player, placement in roster_rows]
            return mode, players, placements
        return mode, list(self.model.player_items_for_team_filter(PLAYER_TEAM_FILTER_ALL).values()), None

    def _player_roster_apply_target_items(self, mode: str) -> list[RecordListItem] | None:
        if mode == "Draft Class":
            return list(self.model.player_items_for_team_filter(PLAYER_TEAM_FILTER_DRAFT_CLASS).values())
        if mode == "Selected Players":
            indexes = self.state.selected_item_indexes.get("Players", set())
            return [item for index, item in self.model.player_items_for_team_filter(PLAYER_TEAM_FILTER_ALL).items() if int(index) in indexes]
        return None

    def _export_player_roster_snapshot(self) -> None:
        mode = self._player_roster_export_mode()
        path = self._player_roster_snapshot_path()
        export_mode, items, placements = self._player_roster_export_items(mode)
        items = list(items)
        placements = list(placements) if placements is not None else None

        def worker() -> str:
            snapshot = self.model.export_player_roster_snapshot_for_items(
                items,
                mode=export_mode,
                placements=placements,
                progress_callback=self._background_operation_progress,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            return f"Exported {snapshot.get('record_count', len(items))} records to {path}"

        self._start_background_operation("Roster Snapshot Export", worker)

    def _apply_player_roster_snapshot(self) -> None:
        mode = self._player_roster_export_mode()
        path = self._player_roster_snapshot_path()
        target_items = self._player_roster_apply_target_items(mode)
        target_items = list(target_items) if target_items is not None else None

        def worker() -> str:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            result = self.model.apply_player_roster_snapshot(
                snapshot,
                target_items=target_items,
                progress_callback=self._background_operation_progress,
            )
            return f"Roster snapshot apply complete: {result}"

        self._start_background_operation("Roster Snapshot Apply", worker)

    def _raise_if_operation_cancelled(self) -> None:
        self.operation_worker.raise_if_cancelled()

    def _request_operation_cancel(self) -> None:
        self.operation_worker.request_cancel()
        if self.operation_dialog is not None:
            self.operation_dialog.message.setText("Cancelling...")
            self.operation_dialog.cancel_button.setEnabled(False)

    def _start_background_operation(
        self,
        title: str,
        worker: Callable[[], object],
        *,
        done_callback: Callable[[object], None] | None = None,
        presentation_target: str | None = None,
        show_progress: bool = True,
        warn_if_busy: bool = True,
    ) -> int | None:
        request_id = self.operation_worker.start(title, worker, done_callback=done_callback)
        if request_id is None:
            if warn_if_busy:
                QMessageBox.warning(self, title, "Another operation is already running.")
            return None
        target = presentation_target or title
        self._operation_targets_by_request[request_id] = target
        self._latest_operation_request_ids[target] = request_id
        if show_progress:
            self._operation_progress_requests.add(request_id)
            self._show_operation_popup(f"{title}...", progress=0.0, overlay="0%")
        if not self.operation_timer.isActive():
            self.operation_timer.start(50)
        return request_id

    def _show_operation_popup(self, message: str, *, progress: float = 0.0, overlay: str = "") -> None:
        if self.operation_dialog is None:
            self.operation_dialog = OperationDialog(self._request_operation_cancel)
        total = 100
        current = int(progress * 100)
        self.operation_dialog.update_progress(message, current, total, done=overlay in {"complete", "failed", "cancelled"})
        self.operation_dialog.show()

    def _background_operation_progress(self, current: int, total: int, message: str) -> None:
        self.operation_worker.report_progress(current, total, message)

    def _pop_operation_events(self) -> list[tuple[str, Any]]:
        return self.operation_worker.pop_events()

    def _poll_background_operation(self) -> None:
        for event, value in self._pop_operation_events():
            if event == "progress":
                request_id, current, total, message = value
                if request_id in self._operation_progress_requests:
                    progress = 1.0 if total <= 0 else max(0.0, min(1.0, current / total))
                    self._show_operation_popup(message, progress=progress, overlay=f"{int(round(progress * 100))}%")
            elif event == "done":
                request_id, result, overlay, done_callback = value
                show_progress = request_id in self._operation_progress_requests
                self._operation_progress_requests.discard(request_id)
                target = self._operation_targets_by_request.pop(request_id, "")
                is_current = not target or self._latest_operation_request_ids.get(target) == request_id
                message = str(result)
                if overlay == "complete":
                    if is_current and done_callback is not None:
                        done_callback(result)
                    if show_progress and self.operation_dialog is not None:
                        self.operation_dialog.hide()
                    if self.operation_timer.isActive():
                        self.operation_timer.stop()
                    continue
                if show_progress:
                    self._show_operation_popup(message, progress=1.0, overlay=overlay)
                else:
                    self.home_target_status.setText(message)
                if self.operation_timer.isActive():
                    self.operation_timer.stop()
        self._start_pending_player_list_request()
        if self.operation_worker.is_running() and not self.operation_timer.isActive():
            self.operation_timer.start(50)

    def _refresh_player_generator_display(self) -> None:
        if self.generator_text is not None:
            self.generator_text.setPlainText(str(self._generator_display_text()))

    def _load_player_generator_source(self) -> None:
        display = self._generator_display_module()

        def worker() -> str:
            try:
                self.player_generator_state = display.load_generator_display_state()
            except Exception as exc:
                self.player_generator_state = display.empty_generator_display_state(f"Load failed: {exc}")
                raise
            return str(getattr(self.player_generator_state, "status", "Loaded player generator source."))

        self._start_background_operation("Load Player Generator Source", worker, done_callback=self._sync_player_generator_status)

    def _refresh_player_generator_dropdowns(self) -> None:
        if not getattr(self.player_generator_state, "source_loaded", False):
            self._sync_player_generator_status()
            return
        display = self._generator_display_module()
        if not hasattr(display, "update_generator_display_selection"):
            self._sync_player_generator_status()
            return
        season = self.generator_year_combo.currentText() if self.generator_year_combo is not None else getattr(self.player_generator_state, "selected_season", "")
        league = self.generator_league_combo.currentText() if self.generator_league_combo is not None else getattr(self.player_generator_state, "selected_league", "")
        position = self.generator_position_combo.currentText() if self.generator_position_combo is not None else getattr(self.player_generator_state, "selected_position", "")
        source_team = self.generator_source_team_combo.currentText() if self.generator_source_team_combo is not None else getattr(self.player_generator_state, "selected_source_team", "")
        selected_player = self.generator_player_combo.currentText() if self.generator_player_combo is not None else getattr(self.player_generator_state, "selected_player", "")
        try:
            state = display.update_generator_display_selection(
                self.player_generator_state,
                selected_season=season or None,
                selected_league=league or None,
                selected_position=position or None,
                selected_source_team=source_team or None,
            )
            if selected_player in getattr(state, "players", ()):
                state = display.update_generator_display_selection(state, selected_player=selected_player)
            self.player_generator_state = state
        except Exception as exc:
            self.player_generator_state = display.empty_generator_display_state(f"Selection failed: {exc}")
        self._sync_player_generator_status()

    def _display_generator_preview(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "generate_generator_preview_display_state"):
            if getattr(self.player_generator_state, "source_loaded", False):
                self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    state = state_snapshot
                    if not getattr(state, "source_loaded", False):
                        state = display.load_generator_display_state()
                    self.player_generator_state = display.generate_generator_preview_display_state(state)
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Preview failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Preview generated."))

            self._start_background_operation("Display Player Generator Preview", worker, done_callback=self._sync_player_generator_status)

    def _check_player_generator_roster(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "check_loaded_roster_display_state"):
            if getattr(self.player_generator_state, "source_loaded", False):
                self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    state = state_snapshot
                    if not getattr(state, "source_loaded", False):
                        state = display.load_generator_display_state()
                    self.player_generator_state = display.check_loaded_roster_display_state(
                        self.model,
                        state,
                        progress_callback=self._background_operation_progress,
                    )
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Roster check failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Roster check complete."))

            self._start_background_operation("Check Player Generator Roster", worker, done_callback=self._sync_player_generator_status)

    def _build_generator_draft_class(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "generate_draft_class_display_state"):
            if getattr(self.player_generator_state, "source_loaded", False):
                self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    state = state_snapshot
                    if not getattr(state, "source_loaded", False):
                        state = display.load_generator_display_state()
                    self.player_generator_state = display.generate_draft_class_display_state(state)
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Draft class build failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Draft class built."))

            self._start_background_operation("Build Player Generator Draft Class", worker, done_callback=self._sync_player_generator_status)

    def _import_generator_draft_class(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "import_draft_class_display_state"):
            self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    self.player_generator_state = display.import_draft_class_display_state(
                        self.model,
                        state_snapshot,
                        progress_callback=self._background_operation_progress,
                    )
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Draft class import failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Draft class import complete."))

            self._start_background_operation("Import Player Generator Draft Class", worker, done_callback=self._sync_player_generator_status)

    def _sync_player_generator_pool(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "sync_generator_pool_display_state"):
            if getattr(self.player_generator_state, "source_loaded", False):
                self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    state = state_snapshot
                    if not getattr(state, "source_loaded", False):
                        state = display.load_generator_display_state()
                    self.player_generator_state = display.sync_generator_pool_display_state(state, progress_callback=self._background_operation_progress)
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Pool SQL sync failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Player pool SQL sync complete."))

            self._start_background_operation("Sync Player Pool SQL", worker, done_callback=self._sync_player_generator_status)

    def _add_current_roster_to_player_pool(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "add_current_roster_to_pool_display_state"):
            if getattr(self.player_generator_state, "source_loaded", False):
                self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    state = state_snapshot
                    if not getattr(state, "source_loaded", False):
                        state = display.load_generator_display_state()
                    self.player_generator_state = display.add_current_roster_to_pool_display_state(self.model, state, progress_callback=self._background_operation_progress)
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Add to pool SQL failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Added current roster to pool SQL."))

            self._start_background_operation("Add Current Roster to Pool SQL", worker, done_callback=self._sync_player_generator_status)

    def _import_generator_to_game_display(self, *, match_existing_player_names: bool = False) -> None:
        display = self._generator_display_module()
        if hasattr(display, "import_generator_to_game_display_state"):
            self._refresh_player_generator_dropdowns()
            state_snapshot = self.player_generator_state

            def worker() -> str:
                try:
                    self.player_generator_state = display.import_generator_to_game_display_state(
                        self.model,
                        state_snapshot,
                        match_existing_player_names=match_existing_player_names,
                        progress_callback=self._background_operation_progress,
                    )
                except Exception as exc:
                    self.player_generator_state = display.empty_generator_display_state(f"Import failed: {exc}")
                    raise
                return str(getattr(self.player_generator_state, "status", "Import complete."))

            self._start_background_operation("Import Generated Players", worker, done_callback=self._sync_player_generator_status)

    def _confirm_missing_generator_import(self, summary: dict[str, Any], on_accept: Callable[[], None]) -> None:
        names = tuple(str(name) for name in summary.get("names", ()))
        missing_count = int(summary.get("missing_count") or len(names))
        target_count = int(summary.get("target_count") or 0)
        skipped_existing = int(summary.get("skipped_existing") or 0)
        if missing_count <= 0:
            QMessageBox.information(self, "Add Missing Players", f"No missing generated players found. Skipped {skipped_existing} generated players already active.")
            return
        if target_count <= 0:
            QMessageBox.warning(self, "Add Missing Players", "No active A Z players are available as import targets.")
            return
        import_count = min(missing_count, target_count)
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Missing Players")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Import {import_count}/{missing_count} missing generated players onto active A Z players?"))
        if target_count < missing_count:
            layout.addWidget(QLabel(f"Only {target_count} active A Z targets are available."))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(names))
        configure_output_text(text)
        layout.addWidget(text, 1)
        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        import_button = QPushButton("Import Listed Players")
        cancel_button.clicked.connect(dialog.reject)
        import_button.clicked.connect(dialog.accept)
        dialog.accepted.connect(on_accept)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(import_button)
        layout.addLayout(buttons)
        dialog.resize(560, 420)
        dialog.show()

    def _import_missing_generator_to_game_display(self) -> None:
        display = self._generator_display_module()
        if hasattr(display, "import_missing_generator_to_game_display_state"):
            self._refresh_player_generator_dropdowns()

            def start_import() -> None:
                state_snapshot = self.player_generator_state

                def worker() -> str:
                    try:
                        self.player_generator_state = display.import_missing_generator_to_game_display_state(
                            self.model,
                            state_snapshot,
                            progress_callback=self._background_operation_progress,
                        )
                    except Exception as exc:
                        self.player_generator_state = display.empty_generator_display_state(f"Add missing players failed: {exc}")
                        raise
                    return str(getattr(self.player_generator_state, "status", "Add missing players complete."))

                self._start_background_operation("Add Missing Players", worker, done_callback=self._sync_player_generator_status)

            if hasattr(display, "missing_generator_import_preview"):
                try:
                    summary = display.missing_generator_import_preview(self.model, self.player_generator_state)
                except Exception as exc:
                    QMessageBox.warning(self, "Add Missing Players", str(exc))
                    return
                self._confirm_missing_generator_import(summary, start_import)
                return
            start_import()

    def _generator_grid_text(self) -> str:
        return str(getattr(self.player_generator_state, "player_rows", ""))

    def _generator_source_options_text(self) -> str:
        return str(getattr(self.player_generator_state, "players", ""))

    def _generator_display_text(self) -> str:
        display = self._generator_display_module()
        state = self.player_generator_state
        parts = [str(getattr(state, "status", ""))]
        rows = getattr(state, "player_rows", ())
        columns = getattr(state, "field_columns", ())
        if rows:
            parts.append("\nPreview:")
            parts.extend(self._generator_preview_table_lines(rows, columns))
        roster_check_season = str(getattr(state, "roster_check_season", ""))
        if roster_check_season:
            missing_players = tuple(getattr(state, "roster_check_missing_players", ()))
            parts.append(f"\nSource players not loaded for {roster_check_season} ({len(missing_players)}):")
            parts.extend(str(player) for player in missing_players)
            if not missing_players:
                parts.append("None")
        return "\n".join(part for part in parts if part)

    def _generator_preview_table_lines(self, rows: tuple[Any, ...], columns: tuple[Any, ...]) -> list[str]:
        headers = ["Player", "Team", "Player ID", *(str(column) for column in columns)]
        body = [[str(row.player), str(row.source_team), str(row.player_id), *(str(value) for value in row.values)] for row in rows]
        widths = [len(header) for header in headers]
        for body_row in body:
            if len(body_row) < len(widths):
                body_row.extend("" for _ in range(len(widths) - len(body_row)))
            for index, cell in enumerate(body_row[: len(widths)]):
                widths[index] = max(widths[index], len(cell))
        separator = " | "
        lines = [separator.join(headers[index].ljust(widths[index]) for index in range(len(headers)))]
        lines.extend(separator.join(row[index].ljust(widths[index]) for index in range(len(headers))) for row in body)
        return lines

    def _sync_player_generator_status(self, _result: object | None = None) -> None:
        state = self.player_generator_state
        combo_values = (
            (self.generator_year_combo, list(getattr(state, "seasons", ())), str(getattr(state, "selected_season", ""))),
            (self.generator_league_combo, list(getattr(state, "league_filters", ())), str(getattr(state, "selected_league", ""))),
            (self.generator_position_combo, list(getattr(state, "position_filters", ())), str(getattr(state, "selected_position", ""))),
            (self.generator_source_team_combo, list(getattr(state, "source_team_filters", ())), str(getattr(state, "selected_source_team", ""))),
            (self.generator_player_combo, list(getattr(state, "players", ())), str(getattr(state, "selected_player", ""))),
        )
        for combo, items, selected in combo_values:
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            if selected:
                combo.setCurrentText(selected)
            combo.blockSignals(False)
        self._refresh_player_generator_display()

    def _set_all_players_stat_ids_to_no_stats(self) -> None:
        def worker() -> str:
            result = self.model.set_all_players_stat_ids_to_no_stats(progress_callback=self._background_operation_progress)
            return str(result)

        self._start_background_operation("Set All Loaded Current Stat IDs To 65535", worker)

    def run(self, *, load_on_start: bool = True) -> int:
        app = _ensure_qapplication()
        apply_qt_theme(app)
        self.show()
        print("QT_OPENED NBA2K Editor", flush=True)
        if load_on_start:
            self._attach_and_load_all()
        self.operation_timer.start(50)
        return int(app.exec())


__all__ = [
    "QtEditorApp",
    "APP_TITLE",
    "APP_VIEWPORT_WIDTH",
    "APP_VIEWPORT_HEIGHT",
    "EDITOR_DOMAINS",
    "RecordListItem",
    "PLAYER_ROSTER_EXPORT_MODES",
    "FRANCHISE_SCREEN",
    "NAV_ORDER",
    "APP_SCREENS",
    "verify_edits",
]
