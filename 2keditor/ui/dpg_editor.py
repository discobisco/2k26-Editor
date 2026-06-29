from __future__ import annotations

import json
import re
import threading
from importlib import import_module
from pathlib import Path
from typing import Any

from nba2k_editor.core.conversions import parse_id_prefixed_option
from nba2k_editor.models.team_record_routing import (
    TEAM_RECORD_SECTION_STAT_TABS,
    TEAM_RECORD_SIDE_NAV,
    team_record_indexes,
    team_record_rows,
)
from nba2k_editor.models.data_model import (
    EDITOR_DOMAINS,
    EditorDataModel,
    FieldEntry,
    PLAYER_TEAM_FILTER_ALL,
    PLAYER_TEAM_FILTER_BASE_TEAMS,
    PLAYER_TEAM_FILTER_DRAFT_CLASS,
    RecordListItem,
    target_display_label,
    verify_edits,
)


APP_TITLE = "Offline Player Data Editor"
APP_VIEWPORT_WIDTH = 1600
APP_VIEWPORT_HEIGHT = 900


class _OperationCancelled(Exception):
    pass
RECORD_LIST_ROW_HEIGHT = 19
RECORD_LIST_VERTICAL_MARGIN = 140
MIN_RECORD_LIST_ROWS = 8
PLAYER_GENERATOR_SCREEN = "Player Generator"
FRANCHISE_MANAGER_SCREEN = "Franchise Manager"
TARGET_CHOICES: tuple[str, ...] = ("NBA 2K22", "NBA 2K23", "NBA 2K24", "NBA 2K25", "NBA 2K26")
PLAYER_ROSTER_EXPORT_MODES: tuple[str, ...] = ("Full Loaded Roster", "Draft Class", "Players From Team Range", "Players From Single Team", "Selected Players")
PLAYER_ROSTER_EXPORTS_DIR = Path("outputs") / "exports"
PLAYER_ROSTER_DEFAULT_EXPORT_FILE = "player_roster_snapshot.json"
RECORD_PREVIEW_CARDS = 100
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
RECORD_CARD_LABELS: tuple[str, ...] = ("First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data")
RECORD_CAREER_TABLE_LABELS: tuple[str, ...] = ("Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data")
TEAM_RECORD_TABLE_LABELS: tuple[str, ...] = RECORD_CAREER_TABLE_LABELS
HISTORY_SECTION_DEFAULT_TYPES: dict[str, int | None] = {
    "Season Awards": 8,
    "Past Champions": 1,
    "League Leaders": 2,
    "Hall of Famers": None,
}
HISTORY_SECTION_TABS: dict[str, tuple[str, ...]] = {
    "Season Awards": HISTORY_AWARD_TABS,
    "Past Champions": ("NBA Championship", "FMVP"),
    "League Leaders": ("Points/Game", "Rebounds/Game", "Assists/Game", "Steals/Game", "Blocks/Game", "Minutes/Game"),
    "Hall of Famers": ("All Hall of Famers",),
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
HISTORY_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "Season Awards": ("Rank", "Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name"),
    "Past Champions": ("Rank", "Season", "Team Logo", "Winner Team City", "Winner Team Name", "Result", "Loser Team City", "Loser Team Name", "First Name", "Last Name"),
    "League Leaders": ("Rank", "Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name", "Data"),
    "Hall of Famers": ("Rank", "Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name"),
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
DOMAIN_LABELS: dict[str, str] = {
    "Stadiums": "Stadium",
}
NAV_ORDER: tuple[str, ...] = (
    "Players",
    "Teams",
    PLAYER_GENERATOR_SCREEN,
    FRANCHISE_MANAGER_SCREEN,
    "NBA History",
    "NBA Records",
    "Staff",
    "Stadiums",
    "Jerseys",
    "Shoes",
)
APP_SCREENS: tuple[str, ...] = ("Home", *EDITOR_DOMAINS, PLAYER_GENERATOR_SCREEN, FRANCHISE_MANAGER_SCREEN)

def _tag(*parts: object) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", "__".join(str(part) for part in parts))


def _target_executable(label: str) -> str:
    digits = "".join(ch for ch in label if ch.isdigit())[-2:] or "26"
    return f"NBA2K{digits}.exe"



class DpgEditorApp:
    def __init__(self, model: EditorDataModel) -> None:
        self.model = model
        self.current_screen = "Home"
        self.open_rows: dict[str, FieldEntry] = {}
        self.row_raw_values: dict[str, Any] = {}
        self.nav_button_tags: dict[str, str] = {}
        self.item_themes: dict[str, str] = {}
        self.history_section = "Season Awards"
        self.history_award = "Most Valuable Player"
        self.history_tabs: dict[str, str] = {section: tabs[0] for section, tabs in HISTORY_SECTION_TABS.items()}
        self.record_section = "Single Game (Regular)"
        self.record_stat = "Points"
        self.team_record_section = "Single Game (Regular)"
        self.team_record_stat = "Points"
        self.player_team_filter = PLAYER_TEAM_FILTER_ALL
        self.player_search_text = ""
        self.player_roster_export_folder = str(PLAYER_ROSTER_EXPORTS_DIR)
        self.player_roster_snapshot_filename = PLAYER_ROSTER_DEFAULT_EXPORT_FILE
        self.player_roster_snapshot_path = str(Path(self.player_roster_export_folder) / self.player_roster_snapshot_filename)
        self.player_roster_export_mode = PLAYER_ROSTER_EXPORT_MODES[0]
        self.player_roster_team_start = "0"
        self.player_roster_team_end = "29"
        self.operation_cancel_requested = False
        self.operation_thread: threading.Thread | None = None
        self.operation_events: list[tuple[str, Any]] = []
        self.operation_events_lock = threading.Lock()
        self.selected_item_labels: dict[str, set[str]] = {}
        self.selection_anchors: dict[str, str | None] = {}
        self.dirty_rows: set[str] = set()
        self.player_season_stat_id_selection: dict[tuple[int, str], str] = {}
        self.player_generator_display = import_module("nba2k_editor.Player Generator.display")
        self.player_generator_state = self.player_generator_display.empty_generator_display_state()
        self.franchise_display = import_module("nba2k_editor.franchise_manager.display")
        self.franchise_facade = self.franchise_display.FranchiseManagerFacade()
        self.franchise_dashboard = self.franchise_facade.load_franchise()
        self.franchise_manual_standings_text = "Team, Wins, Losses\n"

    @property
    def generator_display_state(self) -> Any:
        return self.player_generator_state

    @generator_display_state.setter
    def generator_display_state(self, value: Any) -> None:
        self.player_generator_state = value

    def _generator_display_module(self) -> Any:
        return self.player_generator_display

    def _screen_tag(self, domain: str) -> str:
        return _tag(domain, "screen")

    def _app_screen_tag(self, screen: str) -> str:
        return _tag("home", "screen") if screen == "Home" else self._screen_tag(screen)

    def _home_status_tag(self) -> str:
        return _tag("home", "status")

    def _home_target_status_tag(self) -> str:
        return _tag("home", "target_status")

    def _status_tag(self, domain: str) -> str:
        return _tag(domain, "status")

    def _count_tag(self, domain: str) -> str:
        return _tag(domain, "count")

    def _list_content_tag(self, domain: str) -> str:
        return _tag(domain, "list", "content")

    def _list_row_tag(self, domain: str, label: str) -> str:
        return _tag(domain, "row", label)

    def _player_team_filter_tag(self) -> str:
        return _tag("Players", "team_filter")

    def _player_search_tag(self) -> str:
        return _tag("Players", "search")

    def _player_roster_snapshot_path_tag(self) -> str:
        return _tag("Players", "roster_snapshot_path")

    def _player_roster_export_folder_tag(self) -> str:
        return _tag("Players", "roster_export_folder")

    def _player_roster_snapshot_filename_tag(self) -> str:
        return _tag("Players", "roster_snapshot_filename")

    def _player_roster_export_mode_tag(self) -> str:
        return _tag("Players", "roster_export_mode")

    def _player_roster_team_start_tag(self) -> str:
        return _tag("Players", "roster_team_start")

    def _player_roster_team_end_tag(self) -> str:
        return _tag("Players", "roster_team_end")


    def _detail_tag(self, domain: str, name: str) -> str:
        return _tag(domain, "detail", name)

    def _preview_tag(self, domain: str, row: int, label: str) -> str:
        return _tag(domain, "preview", row, label)

    def _record_card_tag(self, row: int) -> str:
        return _tag("NBA Records", "preview", row, "card")

    def _record_cards_container_tag(self) -> str:
        return _tag("NBA Records", "preview", "cards")

    def _record_career_table_tag(self) -> str:
        return _tag("NBA Records", "preview", "career_table")

    def _record_career_cell_tag(self, row: int, label: str) -> str:
        return _tag("NBA Records", "career", row, label)

    def _record_stat_group_tag(self, section: str) -> str:
        return _tag("NBA Records", "stats", section)

    def _history_tab_group_tag(self, section: str) -> str:
        return _tag("NBA History", "tabs", section)

    def _history_table_group_tag(self, section: str) -> str:
        return _tag("NBA History", "table", section)

    def _history_table_content_tag(self, section: str) -> str:
        return _tag("NBA History", "table", section, "content")

    def _history_preview_tag(self, section: str, row: int, label: str) -> str:
        return _tag("NBA History", section, "preview", row, label)

    def _record_card_title_tag(self, row: int) -> str:
        return _tag("NBA Records", "preview", row, "title")

    def _heading_tag(self, domain: str) -> str:
        return _tag(domain, "heading")

    def _team_input_tag(self, label: str) -> str:
        return _tag("Teams", "summary_input", label)

    def _player_generator_tag(self, *parts: object) -> str:
        return _tag(PLAYER_GENERATOR_SCREEN, *parts)

    def _generator_table_tag(self) -> str:
        return self._player_generator_tag("table")

    def _operation_popup_tag(self) -> str:
        return _tag("operation", "popup")

    def _operation_message_tag(self) -> str:
        return _tag("operation", "message")

    def _operation_progress_tag(self) -> str:
        return _tag("operation", "progress")

    def _operation_cancel_tag(self) -> str:
        return _tag("operation", "cancel")

    def _nav_tag(self, screen: str) -> str:
        return _tag("nav", screen)

    def _display_label(self, domain: str) -> str:
        return DOMAIN_LABELS.get(domain, domain)

    def _game_status_text(self) -> str:
        return self.model.runtime_status_text()

    def _dpg_value_or_default(self, dpg: Any, tag: str, default: object) -> object:
        try:
            if hasattr(dpg, "does_item_exist") and not dpg.does_item_exist(tag):
                return default
            value = dpg.get_value(tag)
        except Exception:
            return default
        return default if value is None else value

    def _safe_set(self, dpg: Any, tag: str, value: object) -> None:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, str(value))

    def _safe_configure(self, dpg: Any, tag: str, **kwargs: object) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, **kwargs)

    def _safe_delete_children(self, dpg: Any, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag, children_only=True)

    def _request_operation_cancel(self, dpg: Any) -> None:
        self.operation_cancel_requested = True
        self._safe_set(dpg, self._operation_message_tag(), "Cancelling...")
        self._safe_configure(dpg, self._operation_cancel_tag(), enabled=False)

    def _reset_operation_cancel(self, dpg: Any) -> None:
        self.operation_cancel_requested = False
        self._safe_configure(dpg, self._operation_cancel_tag(), enabled=True)

    def _raise_if_operation_cancelled(self) -> None:
        if self.operation_cancel_requested:
            raise _OperationCancelled("operation cancelled")

    def _show_operation_popup(self, dpg: Any, message: str, *, progress: float = 0.0, overlay: str = "") -> None:
        if not hasattr(dpg, "window") or not hasattr(dpg, "configure_item"):
            return
        popup = self._operation_popup_tag()
        message_tag = self._operation_message_tag()
        progress_tag = self._operation_progress_tag()
        cancel_tag = self._operation_cancel_tag()
        if not dpg.does_item_exist(popup):
            with dpg.window(tag=popup, label="Operation Progress", modal=False, show=True, width=560, height=220, no_scrollbar=True):
                dpg.add_text(message, tag=message_tag)
                dpg.add_spacer(height=10)
                dpg.add_progress_bar(tag=progress_tag, default_value=progress, overlay=overlay, width=-1)
                dpg.add_spacer(height=10)
                dpg.add_button(label="Cancel", tag=cancel_tag, width=100, callback=lambda *_args: self._request_operation_cancel(dpg))
        else:
            dpg.configure_item(popup, show=True, width=560, height=220, no_scrollbar=True)
        self._safe_set(dpg, message_tag, message)
        if dpg.does_item_exist(progress_tag):
            dpg.set_value(progress_tag, progress)
        self._safe_configure(dpg, progress_tag, overlay=overlay)
        self._safe_configure(dpg, cancel_tag, enabled=overlay not in {"complete", "failed", "cancelled"})
        if hasattr(dpg, "focus_item"):
            dpg.focus_item(popup)

    def _update_operation_progress(self, dpg: Any, current: int, total: int, message: str) -> None:
        self._raise_if_operation_cancelled()
        progress = 1.0 if total <= 0 else max(0.0, min(1.0, current / total))
        overlay = f"{int(round(progress * 100))}%"
        self._show_operation_popup(dpg, message, progress=progress, overlay=overlay)

    def _queue_operation_event(self, event: str, value: Any) -> None:
        with self.operation_events_lock:
            self.operation_events.append((event, value))

    def _pop_operation_events(self) -> list[tuple[str, Any]]:
        with self.operation_events_lock:
            events = list(self.operation_events)
            self.operation_events.clear()
        return events

    def _background_operation_progress(self, current: int, total: int, message: str) -> None:
        self._raise_if_operation_cancelled()
        self._queue_operation_event("progress", (current, total, message))

    def _start_operation_thread(self, dpg: Any, label: str, worker: Any) -> None:
        if self.operation_thread is not None and self.operation_thread.is_alive():
            self._show_operation_popup(dpg, "Operation already running...", progress=0.0, overlay="busy")
            return
        self._reset_operation_cancel(dpg)
        with self.operation_events_lock:
            self.operation_events.clear()
        self._show_operation_popup(dpg, label, progress=0.0, overlay="0%")
        self.operation_thread = threading.Thread(target=worker, daemon=True)
        self.operation_thread.start()

    def _poll_background_operation(self, dpg: Any) -> None:
        for event, value in self._pop_operation_events():
            if event == "progress":
                current, total, message = value
                progress = 1.0 if total <= 0 else max(0.0, min(1.0, current / total))
                self._show_operation_popup(dpg, message, progress=progress, overlay=f"{int(round(progress * 100))}%")
            elif event == "players_status":
                self._safe_set(dpg, self._status_tag("Players"), str(value))
            elif event == "generator_status":
                self._safe_set(dpg, self._player_generator_tag("status"), str(value))
            elif event == "done":
                message, overlay = value
                self._show_operation_popup(dpg, message, progress=1.0, overlay=overlay)

    def _bind_item_theme(self, dpg: Any, item: str, theme: str) -> None:
        if theme and dpg.does_item_exist(item) and dpg.does_item_exist(theme):
            dpg.bind_item_theme(item, theme)

    def _refresh_nav_state(self, dpg: Any) -> None:
        for screen, tag in self.nav_button_tags.items():
            theme_key = "nav_selected" if screen == self.current_screen else "nav"
            self._bind_item_theme(dpg, tag, self.item_themes.get(theme_key, ""))

    def _show_screen(self, dpg: Any, domain: str) -> None:
        self.current_screen = domain
        for candidate in APP_SCREENS:
            tag = self._app_screen_tag(candidate)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=candidate == domain)
        self._refresh_nav_state(dpg)

    def _set_target(self, dpg: Any, selected: str) -> None:
        self.model.select_target_executable(_target_executable(str(selected)))
        self.selected_item_labels.clear()
        self.selection_anchors.clear()
        self._refresh_status_labels(dpg)
        for domain in EDITOR_DOMAINS:
            self._safe_delete_children(dpg, self._list_content_tag(domain))
            self._safe_set(dpg, self._count_tag(domain), f"{self._display_label(domain)}: 0")
        self._sync_player_team_filter(dpg)
        self._sync_player_list(dpg)
        self._update_detail_panel(dpg, "Teams")

    def _refresh_status_labels(self, dpg: Any) -> None:
        status = self._game_status_text()
        self._safe_set(dpg, self._home_status_tag(), "Using packaged offsets.")
        self._safe_set(dpg, self._home_target_status_tag(), status)
        for domain in EDITOR_DOMAINS:
            self._safe_set(dpg, self._status_tag(domain), status)
        self._safe_set(dpg, self._detail_tag("Teams", "status"), status)

    def _attach(self, dpg: Any) -> None:
        self.model.attach()
        self._refresh_status_labels(dpg)

    def _attach_and_scan(self, dpg: Any, domain: str) -> None:
        self._start_background_scan(dpg, (domain,))

    def _attach_and_load_all(self, dpg: Any) -> None:
        self._start_background_scan(dpg, EDITOR_DOMAINS)

    def _scan_domains_for_request(self, domains: tuple[str, ...]) -> tuple[str, ...]:
        expanded: list[str] = []
        for domain in domains:
            if domain not in expanded:
                expanded.append(domain)
            if domain == "Players" and "Draft Class" not in expanded:
                expanded.append("Draft Class")
        return tuple(expanded)

    def _start_background_scan(self, dpg: Any, domains: tuple[str, ...]) -> None:
        scan_domains = self._scan_domains_for_request(domains)
        if not self.model.start_background_refresh(scan_domains):
            self._safe_set(dpg, self._home_target_status_tag(), "Scan already running...")
            return
        self._safe_set(dpg, self._home_target_status_tag(), "Loading record lists...")
        for domain in scan_domains:
            self._safe_set(dpg, self._status_tag(domain), "Queued for scan...")

    def _poll_background_scan(self, dpg: Any) -> None:
        for event, value in self.model.pop_refresh_events():
            if event == "status":
                self._refresh_status_labels(dpg)
            elif event == "start":
                self._safe_set(dpg, self._status_tag(value), "Loading records...")
                self._safe_set(dpg, self._home_target_status_tag(), f"Loading {self._display_label(value)}...")
            elif event == "domain":
                self._sync_domain_list(dpg, value)
            elif event == "error":
                self._safe_set(dpg, self._home_target_status_tag(), f"scan failed: {value}")
            elif event == "done":
                self._safe_set(dpg, self._home_target_status_tag(), self._game_status_text())
                print("DPG_LOADED_LISTS NBA2K Editor", flush=True)

    def _sync_domain_list(self, dpg: Any, domain: str) -> None:
        if domain in {"Players", "Draft Class"}:
            self._sync_player_list(dpg)
            return
        labels = self.model.domain_item_labels(domain)
        self._safe_set(dpg, self._count_tag(domain), f"{self._display_label(domain)}: {self.model.domain_item_count(domain)}")
        selected = self.model.selected_item(domain)
        self._sync_selection_state(domain, labels, selected.display_label if selected is not None else "")
        self._safe_set(dpg, self._status_tag(domain), self.model.domain_status(domain))
        self._render_selectable_list(dpg, domain, labels)
        if domain == "Teams":
            self._sync_player_team_filter(dpg)
            self._sync_player_list(dpg)
        self._update_detail_panel(dpg, domain)

    def _sync_player_team_filter(self, dpg: Any) -> None:
        options = list(self.model.player_team_filter_options())
        if self.player_team_filter not in options:
            self.player_team_filter = PLAYER_TEAM_FILTER_ALL
        self._safe_configure(dpg, self._player_team_filter_tag(), items=options)
        self._safe_set(dpg, self._player_team_filter_tag(), self.player_team_filter)

    def _sync_player_list(self, dpg: Any) -> None:
        domain = "Players"
        self._sync_player_team_filter(dpg)
        labels = self.model.player_item_labels_for_team_filter(self.player_team_filter, self.player_search_text)
        self._safe_set(dpg, self._player_search_tag(), self.player_search_text)
        filtered_items = self.model.player_items_for_team_filter(self.player_team_filter)
        total_count = len(filtered_items) if self.player_team_filter in {PLAYER_TEAM_FILTER_BASE_TEAMS, PLAYER_TEAM_FILTER_DRAFT_CLASS} else self.model.domain_item_count(domain)
        visible_count = len(labels)
        has_filter = self.player_team_filter != PLAYER_TEAM_FILTER_ALL or bool(self.player_search_text.strip())
        count_text = f"Players: {visible_count} / {total_count}" if has_filter else f"Players: {visible_count}"
        self._safe_set(dpg, self._count_tag(domain), count_text)
        selected = self.model.selected_item(domain)
        self._sync_selection_state(domain, labels, selected.display_label if selected is not None else "")
        self._safe_set(dpg, self._status_tag(domain), self.model.domain_status(domain))
        self._render_selectable_list(dpg, domain, labels)
        self._update_detail_panel(dpg, domain)

    def _sync_selection_state(self, domain: str, labels: list[str], selected_label: str) -> None:
        selected_labels = self.selected_item_labels.setdefault(domain, set())
        selected_labels.intersection_update(set(labels))
        if self.selection_anchors.get(domain) not in labels:
            self.selection_anchors[domain] = None
        if selected_label and labels and selected_label not in labels:
            selected_item = self.model.select_item_by_label(domain, labels[0])
            selected_label = selected_item.display_label if selected_item is not None else ""
        elif not labels:
            self.model.select_item_by_label(domain, None)
            selected_label = ""
        if selected_label and not selected_labels:
            selected_labels.add(selected_label)
            self.selection_anchors[domain] = selected_label

    def _render_selectable_list(self, dpg: Any, domain: str, labels: list[str]) -> None:
        content_tag = self._list_content_tag(domain)
        if not dpg.does_item_exist(content_tag):
            return
        dpg.delete_item(content_tag, children_only=True)
        selected_labels = self.selected_item_labels.setdefault(domain, set())
        with dpg.table(parent=content_tag, header_row=False, resizable=False, policy=dpg.mvTable_SizingStretchProp):
            dpg.add_table_column()
            for label in labels:
                with dpg.table_row():
                    dpg.add_selectable(
                        label=label,
                        tag=self._list_row_tag(domain, label),
                        default_value=label in selected_labels,
                        span_columns=True,
                        callback=lambda *_args, d=domain, selected=label: self._select_item_label(dpg, d, selected),
                    )

    def _modifier_down(self, dpg: Any, names: tuple[str, ...]) -> bool:
        return any((key := getattr(dpg, name, None)) is not None and dpg.is_key_down(key) for name in names)

    def _sync_selection_rows(self, dpg: Any, domain: str, labels: list[str]) -> None:
        selected_labels = self.selected_item_labels.setdefault(domain, set())
        for label in labels:
            tag = self._list_row_tag(domain, label)
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, label in selected_labels)

    def _select_item_label(self, dpg: Any, domain: str, selected: str) -> None:
        labels = self.model.player_item_labels_for_team_filter(self.player_team_filter, self.player_search_text) if domain == "Players" else self.model.domain_item_labels(domain)
        if selected not in labels:
            return
        selected_labels = self.selected_item_labels.setdefault(domain, set())
        ctrl = self._modifier_down(dpg, ("mvKey_LControl", "mvKey_RControl", "mvKey_Control"))
        shift = self._modifier_down(dpg, ("mvKey_LShift", "mvKey_RShift", "mvKey_Shift"))
        anchor = self.selection_anchors.get(domain)
        if shift and anchor in labels:
            start = labels.index(anchor)
            end = labels.index(selected)
            selected_range = set(labels[min(start, end) : max(start, end) + 1])
            self.selected_item_labels[domain] = selected_labels | selected_range if ctrl else selected_range
        elif ctrl:
            selected_labels.symmetric_difference_update({selected})
            self.selection_anchors[domain] = selected
        else:
            self.selected_item_labels[domain] = {selected}
            self.selection_anchors[domain] = selected
        self.model.select_item_by_label(domain, selected)
        self._sync_selection_rows(dpg, domain, labels)
        self._update_detail_panel(dpg, domain)

    def _set_player_team_filter(self, dpg: Any, selected: str | None) -> None:
        self.player_team_filter = str(selected or PLAYER_TEAM_FILTER_ALL)
        self._sync_player_list(dpg)

    def _set_player_search_text(self, dpg: Any, search_text: str | None) -> None:
        self.player_search_text = str(search_text or "")
        self._sync_player_list(dpg)

    def _sync_record_screen_rows(self, dpg: Any, domain: str) -> None:
        if domain == "NBA Records":
            self.model.clear_record_screen_rows()
            record_row_start, record_row_count = self._active_record_row_group()
            self.model.refresh_record_screen_rows(
                self.record_section,
                self.record_stat,
                record_row_start=record_row_start,
                record_row_count=record_row_count,
            )
            self._show_record_screen_rows(dpg)
            return

        if domain == "NBA History":
            self.model.clear_history_screen_rows()
            selected_tab = self.history_tabs.get(self.history_section, self.history_award)
            self.model.refresh_history_screen_rows(self.history_section, selected_tab, self._active_history_type())
            self._show_history_screen_rows(dpg)

    def _show_record_screen_rows(self, dpg: Any) -> None:
        record_row_start, record_row_count = self._active_record_row_group()
        rows = self.model.record_screen_rows(
            self.record_section,
            self.record_stat,
            record_row_start=record_row_start,
            record_row_count=record_row_count,
        )
        visible_rows = min(len(rows), RECORD_PREVIEW_CARDS)
        career_mode = self.record_section == "Career"
        for section in RECORD_SIDE_NAV:
            self._safe_configure(dpg, self._record_stat_group_tag(section), show=section == self.record_section)
        self._safe_configure(dpg, self._record_cards_container_tag(), show=not career_mode)
        self._safe_configure(dpg, self._record_career_table_tag(), show=career_mode)
        if career_mode:
            for row_index in range(RECORD_PREVIEW_CARDS):
                row_values = rows[row_index] if row_index < visible_rows else {}
                for label in RECORD_CAREER_TABLE_LABELS:
                    value = str(row_index + 1) if label == "Rank" and row_values else row_values.get(label, "--")
                    self._safe_set(dpg, self._record_career_cell_tag(row_index, label), value)
            return

        for row_index in range(RECORD_PREVIEW_CARDS):
            row_values = rows[row_index] if row_index < visible_rows else {}
            self._safe_configure(dpg, self._record_card_tag(row_index), show=row_index < visible_rows)
            self._safe_set(dpg, self._record_card_title_tag(row_index), f"Record #{row_index + 1}" if row_values else f"Record #{row_index + 1}")
            for label in RECORD_CARD_LABELS:
                self._safe_set(dpg, self._preview_tag("NBA Records", row_index, label), row_values.get(label, "--"))

    def _active_record_indexes(self) -> list[int]:
        record_row_start, record_row_count = self._active_record_row_group()
        return [int(record_row_start) + offset for offset in range(int(record_row_count))]

    def _record_data_value_tag(self, row_index: int) -> str:
        if self.record_section == "Career":
            return self._record_career_cell_tag(row_index, "Data")
        return self._preview_tag("NBA Records", row_index, "Data")

    def _save_record_data_values(self, dpg: Any) -> None:
        indexes = self._active_record_indexes()
        values = {index: str(dpg.get_value(self._record_data_value_tag(row_offset)) or "0") for row_offset, index in enumerate(indexes)}
        try:
            saved = self.model.save_record_data_values(values)
            self.model.clear_record_screen_rows()
            self.model.refresh_record_screen_rows(
                self.record_section,
                self.record_stat,
                record_row_start=indexes[0] if indexes else 0,
                record_row_count=len(indexes),
            )
            self._show_record_screen_rows(dpg)
            self._safe_set(dpg, self._status_tag("NBA Records"), f"saved {saved} Data values")
        except Exception as exc:
            self._safe_set(dpg, self._status_tag("NBA Records"), str(exc))

    def _zero_record_data_values(self, dpg: Any) -> None:
        indexes = [int(item.index) for item in self.model.loaded_items.get("NBA Records", {}).values()]
        try:
            saved = self.model.zero_record_data_values(indexes)
            self.model.clear_record_screen_rows()
            self._show_record_screen_rows(dpg)
            self._safe_set(dpg, self._status_tag("NBA Records"), f"zeroed {saved} Data values")
        except Exception as exc:
            self._safe_set(dpg, self._status_tag("NBA Records"), str(exc))

    def _zero_all_team_record_data_values(self, dpg: Any) -> None:
        indexes: list[int] = []
        for team in self.model.loaded_items.get("Teams", {}).values():
            indexes.extend(team_record_indexes(self.model, team))
        try:
            saved = self.model.zero_record_data_values(indexes)
            self._safe_set(dpg, self._status_tag("Teams"), f"zeroed {saved} Team Records Data values")
        except Exception as exc:
            self._safe_set(dpg, self._status_tag("Teams"), str(exc))

    def _show_history_screen_rows(self, dpg: Any) -> None:
        for section in HISTORY_SIDE_NAV:
            self._safe_configure(dpg, self._history_tab_group_tag(section), show=section == self.history_section)
            self._safe_configure(dpg, self._history_table_group_tag(section), show=section == self.history_section)
        selected_tab = self.history_tabs.get(self.history_section, self.history_award)
        rows = self.model.history_screen_rows(self.history_section, selected_tab, self._active_history_type())
        labels = HISTORY_TABLE_COLUMNS.get(self.history_section, HISTORY_TABLE_COLUMNS["Season Awards"])
        self._render_history_table(dpg, self.history_section, labels, rows)

    def _render_history_table(self, dpg: Any, section: str, labels: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        content_tag = self._history_table_content_tag(section)
        self._safe_delete_children(dpg, content_tag)
        with dpg.table(parent=content_tag, header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
            for label in labels:
                dpg.add_table_column(label=label)
            for row_index, row_values in enumerate(rows):
                with dpg.table_row():
                    for label in labels:
                        value = str(row_index + 1) if label == "Rank" else self._history_cell_value(row_values, label)
                        dpg.add_text(value, tag=self._history_preview_tag(section, row_index, label))

    def _history_cell_value(self, row_values: dict[str, str], label: str) -> str:
        source_label = {
            "Winner Team City": "Team City",
            "Winner Team Name": "Team Name",
        }.get(label, label)
        return row_values.get(source_label, "--")

    def _history_type_for_tab(self, section: str, tab: str) -> int | None:
        if section == "Season Awards":
            return HISTORY_AWARD_TYPES.get(tab)
        section_map = HISTORY_SECTION_TAB_TYPES.get(section, {})
        return section_map.get(tab, HISTORY_SECTION_DEFAULT_TYPES.get(section))

    def _active_history_type(self) -> int | None:
        selected_tab = self.history_tabs.get(self.history_section, self.history_award)
        return self._history_type_for_tab(self.history_section, selected_tab)

    def _record_row_group(self, section: str, stat: str) -> tuple[int, int]:
        section_start, row_count = RECORD_SECTION_ROW_LAYOUT.get(section, RECORD_SECTION_ROW_LAYOUT["Single Game (Regular)"])
        tabs = RECORD_SECTION_STAT_TABS.get(section, RECORD_BASE_STAT_TABS)
        stat_index = tabs.index(stat) if stat in tabs else 0
        return section_start + stat_index * row_count, row_count

    def _active_record_row_group(self) -> tuple[int, int]:
        return self._record_row_group(self.record_section, self.record_stat)

    def _set_history_section(self, dpg: Any, label: str) -> None:
        self.history_section = label
        self._safe_set(dpg, self._heading_tag("NBA History"), label)
        self._show_history_screen_rows(dpg)

    def _set_history_tab(self, dpg: Any, label: str) -> None:
        self.history_tabs[self.history_section] = label
        if self.history_section == "Season Awards":
            self.history_award = label
        self._show_history_screen_rows(dpg)

    def _set_record_section(self, dpg: Any, label: str) -> None:
        self.record_section = label
        tabs = RECORD_SECTION_STAT_TABS.get(self.record_section, RECORD_BASE_STAT_TABS)
        if self.record_stat not in tabs:
            self.record_stat = tabs[0]
        self._safe_set(dpg, self._heading_tag("NBA Records"), self.record_section)
        self._show_record_screen_rows(dpg)

    def _set_record_stat(self, dpg: Any, label: str) -> None:
        self.record_stat = label
        self._safe_set(dpg, self._heading_tag("NBA Records"), self.record_section)
        self._show_record_screen_rows(dpg)

    def _select_current(self, dpg: Any, domain: str, selected_label: str | None = None) -> None:
        self._select_item_label(dpg, domain, str(selected_label or ""))

    def _open_selected(self, dpg: Any, domain: str) -> None:
        item = self.model.selected_item(domain)
        if item is None:
            self._safe_set(dpg, self._status_tag(domain), f"select a {self._display_label(domain).lower()} first")
            return
        self._open_editor_window(dpg, item)

    def _update_detail_panel(self, dpg: Any, domain: str) -> None:
        if domain == "Players":
            self._safe_set(dpg, self._detail_tag(domain, "title"), self.model.selected_detail_title(domain, "player"))
            for label, value in self.model.selected_player_detail_values().items():
                self._safe_set(dpg, self._detail_tag(domain, label), value)
            return
        if domain == "Teams":
            self._safe_set(dpg, self._detail_tag(domain, "title"), self.model.selected_detail_title(domain, "team"))
            for label, value in self.model.selected_team_summary_values().items():
                self._safe_set(dpg, self._team_input_tag(label), value)
            return
        if domain in {"NBA History", "NBA Records"}:
            self._safe_set(dpg, self._detail_tag(domain, "title"), self.model.selected_detail_title(domain, self._display_label(domain)))
            for label, value in self.model.selected_record_summary_values(domain).items():
                self._safe_set(dpg, self._detail_tag(domain, label), value)
            return
        self._safe_set(dpg, self._detail_tag(domain, "title"), self.model.selected_detail_title(domain, self._display_label(domain)))
        self._safe_set(dpg, self._detail_tag(domain, "address"), self.model.selected_record_address_text(domain))

    def _save_team_summary(self, dpg: Any) -> None:
        values = {label: str(dpg.get_value(self._team_input_tag(label)) or "") for label in self.model.team_summary_labels()}
        try:
            saved, failed = self.model.save_selected_team_summary(values)
            self._safe_set(dpg, self._status_tag("Teams"), f"saved {saved} fields, {failed} failed")
        except Exception as exc:
            self._safe_set(dpg, self._status_tag("Teams"), str(exc))
        self._update_detail_panel(dpg, "Teams")

    def _row_current_tag(self, item: RecordListItem, entry: FieldEntry) -> str:
        return _tag("editor", item.domain, item.index, entry.ordinal, "current")

    def _row_new_tag(self, item: RecordListItem, entry: FieldEntry) -> str:
        return _tag("editor", item.domain, item.index, entry.ordinal, "new")

    def _row_status_tag(self, item: RecordListItem, entry: FieldEntry) -> str:
        return _tag("editor", item.domain, item.index, entry.ordinal, "status")

    def _editor_status_tag(self, item: RecordListItem) -> str:
        return _tag("editor", item.domain, item.index, "status")

    def _season_stat_selector_key(self, item: RecordListItem) -> tuple[int, str]:
        return (item.index, "Stats")

    def _season_stat_selector_tag(self, item: RecordListItem) -> str:
        return _tag("editor", item.domain, item.index, "Stats", "active_season_stat_id")

    def _selected_season_stat_selector(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> str | None:
        if not self.model.is_player_selected_stat_detail_entry(entry):
            return None
        selected = str(dpg.get_value(self._season_stat_selector_tag(item)) or self.player_season_stat_id_selection.get(self._season_stat_selector_key(item), ""))
        if not selected:
            raise ValueError("missing active Season Stat ID selector")
        return selected

    def _set_player_season_stat_id(self, dpg: Any, item: RecordListItem, selected: str | None) -> None:
        selected_text = str(selected or "")
        self.player_season_stat_id_selection[self._season_stat_selector_key(item)] = selected_text
        self._safe_set(dpg, self._season_stat_selector_tag(item), selected_text)
        self._load_item_editor(dpg, item)

    def _read_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> dict[str, Any]:
        return self.model.read_entry_value(entry, index=item.index, stat_selector=self._selected_season_stat_selector(dpg, item, entry))

    def _write_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry, value: str) -> dict[str, Any]:
        return self.model.write_entry_value(entry, index=item.index, value=value, stat_selector=self._selected_season_stat_selector(dpg, item, entry))

    def _mark_row_dirty(self, row_key: str) -> None:
        self.dirty_rows.add(row_key)

    def _selected_editor_items(self, domain: str, fallback_item: RecordListItem) -> list[RecordListItem]:
        selected_labels = self.selected_item_labels.get(domain, set())
        loaded_items = self.model.player_items_for_team_filter(self.player_team_filter) if domain == "Players" else self.model.loaded_items.get(domain, {})
        ordered_labels = self.model.player_item_labels_for_team_filter(self.player_team_filter, self.player_search_text) if domain == "Players" else self.model.domain_item_labels(domain)
        items = [loaded_items[label] for label in ordered_labels if label in selected_labels and label in loaded_items]
        if not items:
            return [fallback_item]
        if fallback_item not in items:
            items.insert(0, fallback_item)
        return items

    def _editor_window_label(self, item: RecordListItem) -> str:
        target_count = len(self._selected_editor_items(item.domain, item))
        if target_count > 1:
            return f"{item.domain} [{target_count} selected]"
        return f"{item.domain} [{item.index}] {item.label}"

    def _load_item_editor(self, dpg: Any, item: RecordListItem) -> None:
        loaded = 0
        failed = 0
        prefix = f"{item.domain}:{item.index}:"
        rows = [(row_key, entry) for row_key, entry in self.open_rows.items() if row_key.startswith(prefix)]
        for row_key, entry in rows:
            try:
                value = self._read_editor_entry_value(dpg, item, entry)
                self.row_raw_values[row_key] = value.get("raw_value")
                text = str(value["display_value"])
                dpg.set_value(self._row_current_tag(item, entry), text)
                dpg.set_value(self._row_new_tag(item, entry), text)
                dpg.set_value(self._row_status_tag(item, entry), f"0x{value['address']:X}")
                loaded += 1
            except Exception as exc:
                self.row_raw_values.pop(row_key, None)
                dpg.set_value(self._row_current_tag(item, entry), "")
                dpg.set_value(self._row_new_tag(item, entry), "")
                dpg.set_value(self._row_status_tag(item, entry), str(exc)[:90])
                failed += 1
        self._safe_set(dpg, self._editor_status_tag(item), f"loaded {loaded} fields, {failed} unavailable")

    def _save_item_editor(self, dpg: Any, item: RecordListItem) -> None:
        saved = 0
        target_items = self._selected_editor_items(item.domain, item)
        prefix = f"{item.domain}:{item.index}:"
        for row_key, entry in self.open_rows.items():
            if not row_key.startswith(prefix):
                continue
            old_text = str(dpg.get_value(self._row_current_tag(item, entry)) or "")
            new_text = str(dpg.get_value(self._row_new_tag(item, entry)) or "")
            if new_text == old_text and row_key not in self.dirty_rows:
                continue
            field_saved = 0
            source_readback: dict[str, Any] | None = None
            for target_item in target_items:
                readback = self._write_editor_entry_value(dpg, target_item, entry, new_text)
                if target_item == item and isinstance(readback, dict):
                    source_readback = readback
                field_saved += 1
            saved += field_saved
            if source_readback is not None:
                self.row_raw_values[row_key] = source_readback.get("raw_value")
                text = str(source_readback["display_value"])
                dpg.set_value(self._row_current_tag(item, entry), text)
                dpg.set_value(self._row_new_tag(item, entry), text)
                dpg.set_value(self._row_status_tag(item, entry), f"saved {field_saved} records @ 0x{source_readback['address']:X}")
            else:
                dpg.set_value(self._row_status_tag(item, entry), f"saved {field_saved} records")
            self.dirty_rows.discard(row_key)
        record_text = "record" if len(target_items) == 1 else "records"
        message = f"saved {saved} field writes across {len(target_items)} {record_text}"
        self._safe_set(dpg, self._editor_status_tag(item), message)
        if len(target_items) > 1 and saved:
            self._show_operation_popup(dpg, message, progress=1.0, overlay="complete")

    def _reset_item_editor(self, dpg: Any, item: RecordListItem) -> None:
        target_items = self._selected_editor_items(item.domain, item)
        total_succeeded = 0
        total_failed = 0
        for target_item in target_items:
            result = self.model.reset_player_editor_values(
                index=target_item.index,
                stat_selector=self.player_season_stat_id_selection.get(self._season_stat_selector_key(item)),
            )
            total_succeeded += int(result.get("succeeded", 0))
            total_failed += int(result.get("failed", 0))
        message = f"reset {total_succeeded} fields across {len(target_items)} records, {total_failed} failed"
        self._safe_set(dpg, self._editor_status_tag(item), message)
        if len(target_items) > 1:
            self._show_operation_popup(dpg, message, progress=1.0, overlay="complete")

    def _open_editor_window(self, dpg: Any, item: RecordListItem) -> None:
        win_tag = _tag("editor", item.domain, item.index, "window")
        window_label = self._editor_window_label(item)
        if dpg.does_item_exist(win_tag):
            dpg.configure_item(win_tag, show=True, label=window_label)
            dpg.focus_item(win_tag)
            return

        def options_for(entry: FieldEntry) -> list[str]:
            return self.model.field_options(entry)

        def render_table(render_entries: list[FieldEntry]) -> None:
            with dpg.table(header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(label="Field")
                dpg.add_table_column(label="Current")
                dpg.add_table_column(label="New")
                dpg.add_table_column(label="Address / Status")
                for entry in render_entries:
                    row_key = f"{item.domain}:{item.index}:{entry.ordinal}"
                    self.open_rows[row_key] = entry
                    with dpg.table_row():
                        dpg.add_text(entry.display_name)
                        dpg.add_input_text(tag=self._row_current_tag(item, entry), readonly=True, width=-1)
                        options = options_for(entry)
                        if options:
                            dpg.add_combo(options, tag=self._row_new_tag(item, entry), width=-1)
                        else:
                            dpg.add_input_text(tag=self._row_new_tag(item, entry), width=-1)
                        dpg.add_text("", tag=self._row_status_tag(item, entry))

        def render_team_records() -> None:
            prefix = _tag("editor", item.domain, item.index, "team_records")

            def local_tag(*parts: object) -> str:
                return _tag(prefix, *parts)

            def heading_tag() -> str:
                return local_tag("heading")

            def count_tag() -> str:
                return local_tag("count")

            def stat_group_tag(section: str) -> str:
                return local_tag("stats", section)

            def cards_container_tag() -> str:
                return local_tag("cards")

            def card_tag(row: int) -> str:
                return local_tag("card", row)

            def card_title_tag(row: int) -> str:
                return local_tag("card", row, "title")

            def preview_tag(row: int, label: str) -> str:
                return local_tag("preview", row, label)

            def career_table_tag() -> str:
                return local_tag("career_table")

            def career_cell_tag(row: int, label: str) -> str:
                return local_tag("career", row, label)

            def show_team_record_rows() -> None:
                tabs = TEAM_RECORD_SECTION_STAT_TABS.get(self.team_record_section, ())
                if tabs and self.team_record_stat not in tabs:
                    self.team_record_stat = tabs[0]
                try:
                    rows = team_record_rows(self.model, item, self.team_record_section, self.team_record_stat)
                except Exception:
                    rows = []
                visible_rows = min(len(rows), RECORD_PREVIEW_CARDS)
                career_mode = self.team_record_section == "Career"
                for section in TEAM_RECORD_SIDE_NAV:
                    self._safe_configure(dpg, stat_group_tag(section), show=section == self.team_record_section)
                self._safe_set(dpg, heading_tag(), self.team_record_section)
                self._safe_set(dpg, count_tag(), f"Team Records: {len(rows)}")
                self._safe_configure(dpg, cards_container_tag(), show=not career_mode)
                self._safe_configure(dpg, career_table_tag(), show=career_mode)
                if career_mode:
                    for row_index in range(RECORD_PREVIEW_CARDS):
                        row_values = rows[row_index] if row_index < visible_rows else {}
                        for label in TEAM_RECORD_TABLE_LABELS:
                            value = str(row_index + 1) if label == "Rank" and row_values else row_values.get(label, "--")
                            self._safe_set(dpg, career_cell_tag(row_index, label), value)
                    return
                for row_index in range(RECORD_PREVIEW_CARDS):
                    row_values = rows[row_index] if row_index < visible_rows else {}
                    self._safe_configure(dpg, card_tag(row_index), show=row_index < visible_rows)
                    self._safe_set(dpg, card_title_tag(row_index), f"Record #{row_index + 1}")
                    for label in RECORD_CARD_LABELS:
                        self._safe_set(dpg, preview_tag(row_index, label), row_values.get(label, "--"))

            def set_team_record_section(label: str) -> None:
                self.team_record_section = label
                tabs = TEAM_RECORD_SECTION_STAT_TABS.get(label, ())
                if tabs and self.team_record_stat not in tabs:
                    self.team_record_stat = tabs[0]
                elif not tabs:
                    self.team_record_stat = ""
                show_team_record_rows()

            def set_team_record_stat(label: str) -> None:
                self.team_record_stat = label
                show_team_record_rows()

            with dpg.group(horizontal=True):
                with dpg.child_window(width=260, height=-1, border=False):
                    for label in TEAM_RECORD_SIDE_NAV:
                        dpg.add_button(label=label, width=-1, height=34, callback=lambda *_args, selected=label: set_team_record_section(selected))
                        dpg.add_spacer(height=6)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text(self.team_record_section, tag=heading_tag())
                    dpg.add_spacer(height=14)
                    for section, tabs in TEAM_RECORD_SECTION_STAT_TABS.items():
                        with dpg.group(tag=stat_group_tag(section), show=section == self.team_record_section):
                            self._add_button_strip(dpg, tabs, per_row=13, callback=set_team_record_stat)
                    dpg.add_spacer(height=8)
                    dpg.add_text("Team Records: 0", tag=count_tag())
                    dpg.add_spacer(height=10)
                    with dpg.child_window(width=-1, height=-1, border=True):
                        with dpg.group(tag=cards_container_tag(), show=True):
                            labels = RECORD_CARD_LABELS
                            for row_index in range(RECORD_PREVIEW_CARDS):
                                with dpg.group(tag=card_tag(row_index), show=False):
                                    dpg.add_text(f"Record #{row_index + 1}", tag=card_title_tag(row_index))
                                    dpg.add_spacer(height=8)
                                    for start in range(0, len(labels), 3):
                                        with dpg.group(horizontal=True):
                                            for label in labels[start : start + 3]:
                                                with dpg.group():
                                                    dpg.add_text(f"{label}:")
                                                    dpg.add_input_text(tag=preview_tag(row_index, label), readonly=True, width=280)
                                        dpg.add_spacer(height=8)
                                    dpg.add_spacer(height=18)
                        with dpg.group(tag=career_table_tag(), show=False):
                            with dpg.table(header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
                                for label in TEAM_RECORD_TABLE_LABELS:
                                    dpg.add_table_column(label=label)
                                for row_index in range(RECORD_PREVIEW_CARDS):
                                    with dpg.table_row():
                                        for label in TEAM_RECORD_TABLE_LABELS:
                                            dpg.add_text("--", tag=career_cell_tag(row_index, label))
            show_team_record_rows()

        with dpg.window(label=window_label, tag=win_tag, width=1120, height=760):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Reload", callback=lambda *_args, i=item: self._load_item_editor(dpg, i))
                dpg.add_button(label="Save Changes + Readback", callback=lambda *_args, i=item: self._save_item_editor(dpg, i))
                if item.domain == "Players":
                    dpg.add_button(label="Reset Players", callback=lambda *_args, i=item: self._reset_item_editor(dpg, i))
            with dpg.child_window(height=-1, border=True):
                with dpg.tab_bar():
                    for section, groups in self.model.grouped_fields(item.domain).items():
                        with dpg.tab(label=section):
                            for group, entries in groups.items():
                                entries_list = list(entries)
                                options: list[str] = []
                                with dpg.collapsing_header(label=group, default_open=group in {"ID", "Vitals", "Basic Info"}):
                                    if item.domain == "Players" and section == "Stats" and group == "Season IDs":
                                        selector_options = self.model.player_season_stat_id_options(item.index)
                                        options = [option for option in selector_options if parse_id_prefixed_option(option) is not None]
                                        key = self._season_stat_selector_key(item)
                                        if options:
                                            selected = self.player_season_stat_id_selection.get(key)
                                            if selected not in options:
                                                selected = next((option for option in options if parse_id_prefixed_option(option) is not None), options[0])
                                                self.player_season_stat_id_selection[key] = selected
                                            with dpg.group(horizontal=True):
                                                dpg.add_text("Active Season Stat ID")
                                                dpg.add_combo(
                                                    options,
                                                    tag=self._season_stat_selector_tag(item),
                                                    default_value=selected,
                                                    width=280,
                                                    callback=lambda _s, app_data, _u=None, *args, i=item: self._set_player_season_stat_id(dpg, i, app_data),
                                                )
                                            dpg.add_spacer(height=6)
                                        else:
                                            self.player_season_stat_id_selection.pop(key, None)
                                            dpg.add_text("No player seasons with stats available")
                                            dpg.add_spacer(height=6)
                                    if item.domain == "Players" and section == "Stats" and group == "Season IDs":
                                        entries_list = [entry for entry in entries_list if not self.model.is_player_season_id_selector_entry(entry)]
                                        if not options:
                                            entries_list = [entry for entry in entries_list if not self.model.is_player_selected_stat_detail_entry(entry)]
                                    render_table(entries_list)
                    if item.domain == "Teams":
                        with dpg.tab(label="Team Records"):
                            render_team_records()
        self._load_item_editor(dpg, item)

    def _add_nav_button(self, dpg: Any, screen: str, label: str) -> None:
        tag = self._nav_tag(screen)
        self.nav_button_tags[screen] = tag
        dpg.add_button(label=label, tag=tag, width=-1, height=25, callback=lambda *_args, s=screen: self._show_screen(dpg, s))
        self._bind_item_theme(dpg, tag, self.item_themes.get("nav", ""))

    def _add_detail_row(self, dpg: Any, label: str, value_tag: str, *, accent: bool = False) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text(label, bullet=False)
            dpg.add_spacer(width=18)
            dpg.add_text("--", tag=value_tag)
            if accent:
                self._bind_item_theme(dpg, value_tag, self.item_themes.get("accent_text", ""))

    def _build_home_screen(self, dpg: Any, *, show: bool = True) -> None:
        with dpg.child_window(tag=self._app_screen_tag("Home"), show=show, width=-1, height=-1, border=True):
            dpg.add_text("Offline Player Editor")
            dpg.add_spacer(height=24)
            dpg.add_text("Hook target")
            dpg.add_radio_button(TARGET_CHOICES, default_value=target_display_label(self.model.target_executable), horizontal=True, callback=lambda _s, app_data, _u: self._set_target(dpg, app_data))
            dpg.add_spacer(height=12)
            dpg.add_text(self._game_status_text(), tag=self._home_target_status_tag())
            dpg.add_spacer(height=12)
            dpg.add_button(label="Refresh", width=140, callback=lambda *_args: self._attach(dpg))
            dpg.add_spacer(height=18)
            dpg.add_text("Using packaged offsets.", tag=self._home_status_tag())
            dpg.add_spacer(height=28)
            dpg.add_text("Extensions")
            dpg.add_spacer(height=8)
            ext = dpg.add_text("No additional Python modules detected in the editor directory.")
            self._bind_item_theme(dpg, ext, self.item_themes.get("muted_text", ""))

    def _build_player_generator_screen(self, dpg: Any, *, show: bool = False) -> None:
        state = self.player_generator_state
        with dpg.child_window(tag=self._screen_tag(PLAYER_GENERATOR_SCREEN), show=show, width=-1, height=-1, border=False):
            dpg.add_text("Player Generator")
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_text("Season")
                dpg.add_combo(list(state.seasons), tag=self._player_generator_tag("year"), default_value=state.selected_season, width=110)
                dpg.add_text("Source Team")
                dpg.add_combo(list(state.source_team_filters), tag=self._player_generator_tag("source_team"), default_value=state.selected_source_team, width=180)
                dpg.add_text("Player")
                dpg.add_combo(list(state.players), tag=self._player_generator_tag("selected_player"), default_value=state.selected_player, width=420)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Load Source", width=130, callback=lambda *_: self._load_player_generator_source(dpg))
                dpg.add_button(label="Add Current Roster to Pool SQL", width=230, callback=lambda *_: self._add_current_roster_to_player_pool(dpg))
                dpg.add_button(label="Sync Player Pool SQL", width=170, callback=lambda *_: self._sync_player_generator_pool(dpg))
                dpg.add_button(label="Display Preview", width=150, callback=lambda *_: self._display_generator_preview(dpg))
                dpg.add_button(label="Import Generated Players", width=190, callback=lambda *_: self._import_generator_to_game_display(dpg))
                dpg.add_button(label="Import Matched Names", width=180, callback=lambda *_: self._import_generator_to_game_display(dpg, match_existing_player_names=True))
            dpg.add_text(state.status, tag=self._player_generator_tag("status"))
            dpg.add_input_text(tag=self._generator_table_tag(), default_value=self._generator_display_text(state), multiline=True, readonly=True, width=-1, height=-1)

    def _load_player_generator_source(self, dpg: Any) -> None:
        display = self._generator_display_module()
        try:
            self.player_generator_state = display.load_generator_display_state()
        except Exception as exc:
            self.player_generator_state = display.empty_generator_display_state(f"Load failed: {exc}")
        self._sync_player_generator_status(dpg)

    def _refresh_player_generator_dropdowns(self, dpg: Any) -> None:
        if not getattr(self.player_generator_state, "source_loaded", False):
            return
        display = self._generator_display_module()
        if not hasattr(display, "update_generator_display_selection"):
            return
        season = str(dpg.get_value(self._player_generator_tag("year")) or getattr(self.player_generator_state, "selected_season", ""))
        source_team = str(dpg.get_value(self._player_generator_tag("source_team")) or getattr(self.player_generator_state, "selected_source_team", ""))
        selected_player = str(dpg.get_value(self._player_generator_tag("selected_player")) or "")
        if not season or not source_team:
            return
        state = display.update_generator_display_selection(self.player_generator_state, selected_season=season, selected_source_team=source_team)
        if selected_player in getattr(state, "players", ()):
            state = display.update_generator_display_selection(state, selected_player=selected_player)
        self.player_generator_state = state
        self._sync_player_generator_status(dpg)

    def _display_generator_preview(self, dpg: Any) -> None:
        display = self._generator_display_module()
        try:
            if not getattr(self.player_generator_state, "source_loaded", False):
                self.player_generator_state = display.load_generator_display_state()
                self._sync_player_generator_status(dpg)
            self._refresh_player_generator_dropdowns(dpg)
            self.player_generator_state = display.generate_generator_preview_display_state(self.player_generator_state)
        except Exception as exc:
            self.player_generator_state = display.empty_generator_display_state(f"Preview failed: {exc}")
        self._sync_player_generator_status(dpg)

    def _sync_player_generator_pool(self, dpg: Any) -> None:
        display = self._generator_display_module()
        self._reset_operation_cancel(dpg)
        self._show_operation_popup(dpg, "Syncing player pool SQL...", progress=0.0, overlay="0%")
        progress_callback = lambda current, total, message: self._update_operation_progress(dpg, current, total, message)
        try:
            if not getattr(self.player_generator_state, "source_loaded", False):
                self.player_generator_state = display.load_generator_display_state()
                self._sync_player_generator_status(dpg)
            self._refresh_player_generator_dropdowns(dpg)
            self.player_generator_state = display.sync_generator_pool_display_state(self.player_generator_state, progress_callback=progress_callback)
        except _OperationCancelled:
            message = "Pool SQL sync cancelled."
            self._safe_set(dpg, self._player_generator_tag("status"), message)
            self._show_operation_popup(dpg, message, progress=1.0, overlay="cancelled")
            return
        except Exception as exc:
            message = f"Pool SQL sync failed: {exc}"
            self._update_operation_progress(dpg, 0, 1, message)
            self.player_generator_state = display.empty_generator_display_state(message)
            self._sync_player_generator_status(dpg)
            return
        self._update_operation_progress(dpg, 1, 1, getattr(self.player_generator_state, "status", "Player pool SQL sync complete."))
        self._sync_player_generator_status(dpg)

    def _add_current_roster_to_player_pool(self, dpg: Any) -> None:
        display = self._generator_display_module()
        self._reset_operation_cancel(dpg)
        self._show_operation_popup(dpg, "Adding current roster to player pool SQL...", progress=0.0, overlay="0%")
        progress_callback = lambda current, total, message: self._update_operation_progress(dpg, current, total, message)
        try:
            if not getattr(self.player_generator_state, "source_loaded", False):
                self.player_generator_state = display.load_generator_display_state()
                self._sync_player_generator_status(dpg)
            self._refresh_player_generator_dropdowns(dpg)
            self.player_generator_state = display.add_current_roster_to_pool_display_state(self.model, self.player_generator_state, progress_callback=progress_callback)
        except _OperationCancelled:
            message = "Add to pool SQL cancelled."
            self._safe_set(dpg, self._player_generator_tag("status"), message)
            self._show_operation_popup(dpg, message, progress=1.0, overlay="cancelled")
            return
        except Exception as exc:
            message = f"Add to pool SQL failed: {exc}"
            self._update_operation_progress(dpg, 0, 1, message)
            self.player_generator_state = display.empty_generator_display_state(message)
            self._sync_player_generator_status(dpg)
            return
        self._update_operation_progress(dpg, 1, 1, getattr(self.player_generator_state, "status", "Added current roster to player pool SQL."))
        self._sync_player_generator_status(dpg)

    def _import_generator_to_game_display(self, dpg: Any, *, match_existing_player_names: bool = False) -> None:
        display = self._generator_display_module()
        self._reset_operation_cancel(dpg)
        self._show_operation_popup(dpg, "Importing generated players...", progress=0.0, overlay="0/0")
        progress_callback = lambda current, total, message: self._update_operation_progress(dpg, current, total, message)
        try:
            self.player_generator_state = display.import_generator_to_game_display_state(
                self.model,
                self.player_generator_state,
                match_existing_player_names=match_existing_player_names,
                progress_callback=progress_callback,
            )
        except _OperationCancelled:
            message = "Import cancelled."
            self._safe_set(dpg, self._player_generator_tag("status"), message)
            self._show_operation_popup(dpg, message, progress=1.0, overlay="cancelled")
            return
        except Exception as exc:
            message = f"Import failed: {exc}"
            self._update_operation_progress(dpg, 0, 1, message)
            if hasattr(dpg, "configure_item") and dpg.does_item_exist(self._operation_progress_tag()):
                dpg.configure_item(self._operation_progress_tag(), overlay="failed")
            self._safe_set(dpg, self._player_generator_tag("status"), message)
            return
        self._update_operation_progress(dpg, 1, 1, getattr(self.player_generator_state, "status", "Imported generated players."))
        self._sync_player_generator_status(dpg)

    def _generator_grid_text(self, columns: tuple[str, ...], rows: tuple[Any, ...]) -> str:
        headers = ("Player", "Team", "Player ID", *columns)
        table = [headers, *((str(row.player), str(row.source_team), str(row.player_id), *(str(value) for value in row.values)) for row in rows)]
        widths = [max(len(record[index]) for record in table) for index in range(len(headers))]

        def render(record: tuple[str, ...]) -> str:
            return " | ".join(value.ljust(widths[index]) for index, value in enumerate(record))

        return "\n".join((render(headers), "-+-".join("-" * width for width in widths), *(render(record) for record in table[1:])))

    def _generator_source_options_text(self, players: tuple[str, ...]) -> str:
        headers = ("Player", "Team", "Player ID")
        parsed_rows: list[tuple[str, str, str]] = []
        for label in players:
            parts = [part.strip() for part in str(label or "").split(" | ")]
            if len(parts) == 3:
                parsed_rows.append((parts[0], parts[1], parts[2]))
        table = [headers, *parsed_rows]
        widths = [max(len(record[index]) for record in table) for index in range(len(headers))]

        def render(record: tuple[str, ...]) -> str:
            return " | ".join(value.ljust(widths[index]) for index, value in enumerate(record))

        return "\n".join((render(headers), "-+-".join("-" * width for width in widths), *(render(record) for record in table[1:])))

    def _generator_display_text(self, state: Any) -> str:
        player_rows = tuple(getattr(state, "player_rows", ()))
        if player_rows:
            return self._generator_grid_text(tuple(getattr(state, "field_columns", ())), player_rows)
        return self._generator_source_options_text(tuple(getattr(state, "players", ())))

    def _sync_player_generator_status(self, dpg: Any) -> None:
        state = self.player_generator_state
        self._safe_configure(dpg, self._player_generator_tag("year"), items=list(getattr(state, "seasons", ())))
        self._safe_set(dpg, self._player_generator_tag("year"), getattr(state, "selected_season", ""))
        self._safe_configure(dpg, self._player_generator_tag("source_team"), items=list(getattr(state, "source_team_filters", ())))
        self._safe_set(dpg, self._player_generator_tag("source_team"), getattr(state, "selected_source_team", ""))
        self._safe_configure(dpg, self._player_generator_tag("selected_player"), items=list(getattr(state, "players", ())))
        self._safe_set(dpg, self._player_generator_tag("selected_player"), getattr(state, "selected_player", ""))
        self._safe_set(dpg, self._player_generator_tag("status"), getattr(state, "status", ""))
        self._safe_set(dpg, self._generator_table_tag(), self._generator_display_text(state))

    def _player_roster_snapshot_path(self, dpg: Any) -> Path:
        folder_raw = str(
            self._dpg_value_or_default(dpg, self._player_roster_export_folder_tag(), self.player_roster_export_folder)
            or self.player_roster_export_folder
        ).strip()
        filename_raw = str(
            self._dpg_value_or_default(dpg, self._player_roster_snapshot_filename_tag(), self.player_roster_snapshot_filename)
            or self.player_roster_snapshot_filename
        ).strip()
        if not folder_raw:
            folder_raw = str(PLAYER_ROSTER_EXPORTS_DIR)
        if not filename_raw:
            filename_raw = PLAYER_ROSTER_DEFAULT_EXPORT_FILE
        filename_path = Path(filename_raw).expanduser()
        if not filename_path.suffix:
            filename_path = filename_path.with_suffix(".json")
        if filename_path.is_absolute() or filename_path.parent != Path("."):
            path = filename_path
            self.player_roster_export_folder = str(path.parent)
            self.player_roster_snapshot_filename = path.name
        else:
            folder = Path(folder_raw).expanduser()
            path = folder / filename_path.name
            self.player_roster_export_folder = str(folder)
            self.player_roster_snapshot_filename = filename_path.name
        self.player_roster_snapshot_path = str(path)
        return path

    def _player_roster_export_mode(self, dpg: Any) -> str:
        mode = str(dpg.get_value(self._player_roster_export_mode_tag()) or self.player_roster_export_mode).strip()
        if mode not in PLAYER_ROSTER_EXPORT_MODES:
            mode = PLAYER_ROSTER_EXPORT_MODES[0]
        self.player_roster_export_mode = mode
        return mode

    def _player_roster_team_range(self, dpg: Any) -> tuple[int, int]:
        start_text = str(dpg.get_value(self._player_roster_team_start_tag()) or self.player_roster_team_start).strip()
        end_text = str(dpg.get_value(self._player_roster_team_end_tag()) or self.player_roster_team_end).strip()
        start = max(0, int(start_text))
        end = max(start, int(end_text))
        self.player_roster_team_start = str(start)
        self.player_roster_team_end = str(end)
        return start, end

    def _player_roster_export_items(
        self,
        mode: str,
        team_range: tuple[int, int] = (0, -1),
    ) -> tuple[str, list[RecordListItem], list[dict[str, Any] | None] | None]:
        loaded_players = self.model.loaded_items.get("Players", {})
        if mode == "Full Loaded Roster":
            return mode, list(loaded_players.values()), None
        if mode == "Draft Class":
            self.model._ensure_draft_class_items_loaded()
            return mode, list(self.model.loaded_items.get("Draft Class", {}).values()), None
        if mode == "Selected Players":
            ordered_labels = self.model.player_item_labels_for_team_filter(self.player_team_filter, self.player_search_text)
            selected_labels = self.selected_item_labels.get("Players", set())
            return mode, [loaded_players[label] for label in ordered_labels if label in selected_labels and label in loaded_players], None
        loaded_teams = list(self.model.loaded_items.get("Teams", {}).values())
        if mode == "Players From Team Range":
            start, end = team_range
            rows = self.model.player_roster_slot_items_for_team_items(loaded_teams[start : end + 1])
            return mode, [player for player, _placement in rows], [placement for _player, placement in rows]
        if mode == "Players From Single Team":
            selected = str(self.player_team_filter or "").strip()
            if not selected or selected == PLAYER_TEAM_FILTER_ALL:
                raise ValueError("select a team in the Team dropdown for single-team player export")
            team = self.model.loaded_items.get("Teams", {}).get(selected)
            if team is None:
                raise ValueError(f"selected team is not loaded: {selected}")
            rows = self.model.player_roster_slot_items_for_team_items((team,))
            return mode, [player for player, _placement in rows], [placement for _player, placement in rows]
        return mode, list(loaded_players.values()), None

    def _player_roster_apply_target_items(self, mode: str, snapshot: dict[str, Any]) -> list[RecordListItem] | None:
        if mode == "Draft Class":
            self.model._ensure_draft_class_items_loaded()
            return list(self.model.loaded_items.get("Draft Class", {}).values())
        return None

    def _export_player_roster_snapshot(self, dpg: Any) -> None:
        path = self._player_roster_snapshot_path(dpg)
        export_mode = self._player_roster_export_mode(dpg)
        team_range = self._player_roster_team_range(dpg) if export_mode == "Players From Team Range" else (0, -1)

        def worker() -> None:
            try:
                self.model.attach()
                mode, items, placements = self._player_roster_export_items(export_mode, team_range)
                snapshot = self.model.export_player_roster_snapshot_for_items(
                    items,
                    progress_callback=self._background_operation_progress,
                    mode=mode,
                    placements=placements,
                )
                self._raise_if_operation_cancelled()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            except _OperationCancelled:
                message = "Roster export cancelled."
                self._queue_operation_event("players_status", message)
                self._queue_operation_event("done", (message, "cancelled"))
                return
            except Exception as exc:
                message = f"Roster export failed: {exc}"
                self._queue_operation_event("players_status", message)
                self._queue_operation_event("done", (message, "failed"))
                return
            message = f"Exported {snapshot.get('record_count', 0)} players to {path}"
            self._queue_operation_event("players_status", message)
            self._queue_operation_event("done", (message, "complete"))

        self._start_operation_thread(dpg, "Exporting player roster...", worker)

    def _apply_player_roster_snapshot(self, dpg: Any) -> None:
        path = self._player_roster_snapshot_path(dpg)
        apply_mode = self._player_roster_export_mode(dpg)
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            message = f"Roster apply failed: {exc}"
            self._safe_set(dpg, self._status_tag("Players"), message)
            self._show_operation_popup(dpg, message, progress=1.0, overlay="failed")
            return

        def worker() -> None:
            try:
                self.model.attach()
                target_items = self._player_roster_apply_target_items(apply_mode, snapshot)
                result = self.model.apply_player_roster_snapshot(snapshot, progress_callback=self._background_operation_progress, target_items=target_items)
            except _OperationCancelled:
                message = "Roster apply cancelled."
                self._queue_operation_event("players_status", message)
                self._queue_operation_event("done", (message, "cancelled"))
                return
            except Exception as exc:
                message = f"Roster apply failed: {exc}"
                self._queue_operation_event("players_status", message)
                self._queue_operation_event("done", (message, "failed"))
                return
            message = (
                f"Applied roster snapshot: {result.get('succeeded', 0)} succeeded, "
                f"{result.get('failed', 0)} failed, {result.get('skipped', 0)} skipped"
            )
            self._queue_operation_event("players_status", message)
            self._queue_operation_event("done", (message, "complete"))

        self._start_operation_thread(dpg, "Applying player roster snapshot...", worker)

    def _franchise_tag(self, *parts: object) -> str:
        return _tag(FRANCHISE_MANAGER_SCREEN, *parts)

    def _import_manual_franchise_standings(self, dpg: Any) -> None:
        text = str(dpg.get_value(self._franchise_tag("manual_standings_text")) or "")
        self.franchise_manual_standings_text = text
        self._run_franchise_action(dpg, lambda facade: facade.import_manual_standings_text(text))

    def _franchise_lines_text(self, title: str, lines: object) -> str:
        if isinstance(lines, str):
            values = (lines,)
        elif lines:
            values = tuple(str(line) for line in lines)  # type: ignore[union-attr]
        else:
            values = ("--",)
        return "\n".join((title, "", *values))

    def _franchise_overview_text(self, dashboard: Any) -> str:
        overview = getattr(dashboard, "overview", None)
        return "\n".join(
            (
                "Franchise Overview",
                "",
                f"Current Season: {getattr(overview, 'current_season', '--')}",
                f"Current Phase: {getattr(overview, 'current_phase', '--')}",
                f"League Champion: {getattr(overview, 'league_champion', '--')}",
                f"Upcoming Draft: {getattr(overview, 'upcoming_draft', '--')}",
                f"Active User Team: {getattr(overview, 'active_user_team', '--')}",
                f"User Role: {getattr(overview, 'user_role', '--')}",
            )
        )

    def _franchise_next_stop_text(self, dashboard: Any) -> str:
        stop = getattr(dashboard, "next_sim_stop", None)
        return "\n".join(
            (
                "Next Simulation Stop",
                "",
                f"Date: {getattr(stop, 'date_label', '--')}",
                f"Reason: {getattr(stop, 'reason', '--')}",
                f"Priority: {getattr(stop, 'priority', '--')}",
                f"Teams Requesting Review: {getattr(stop, 'teams_requesting_review', '--')}",
            )
        )

    def _franchise_snapshot_text(self, dashboard: Any) -> str:
        snapshot = getattr(dashboard, "league_snapshot", None)
        return "\n\n".join(
            (
                self._franchise_lines_text("League Snapshot", getattr(snapshot, "standings_summary", ())),
                self._franchise_lines_text("Top Teams", getattr(snapshot, "top_teams", ())),
                self._franchise_lines_text("Worst Teams", getattr(snapshot, "worst_teams", ())),
                self._franchise_lines_text("Championship Favorites", getattr(snapshot, "championship_favorites", ())),
                self._franchise_lines_text("MVP Race", getattr(snapshot, "mvp_race", ())),
                self._franchise_lines_text("Rookie Race", getattr(snapshot, "rookie_race", ())),
            )
        )

    def _sync_franchise_dashboard(self, dpg: Any, dashboard: Any | None = None) -> None:
        if dashboard is not None:
            self.franchise_dashboard = dashboard
        dashboard = self.franchise_dashboard
        self._safe_set(dpg, self._franchise_tag("status"), getattr(dashboard, "status", ""))
        self._safe_set(dpg, self._franchise_tag("overview"), self._franchise_overview_text(dashboard))
        self._safe_set(dpg, self._franchise_tag("snapshot"), self._franchise_snapshot_text(dashboard))
        self._safe_set(dpg, self._franchise_tag("owner_alerts"), self._franchise_lines_text("Owner Alerts", getattr(dashboard, "owner_alerts", ())))
        self._safe_set(dpg, self._franchise_tag("gm_alerts"), self._franchise_lines_text("GM Alerts", getattr(dashboard, "gm_alerts", ())))
        self._safe_set(dpg, self._franchise_tag("next_stop"), self._franchise_next_stop_text(dashboard))
        self._safe_set(dpg, self._franchise_tag("activity"), self._franchise_lines_text("League Activity Feed", getattr(dashboard, "activity_feed", ())))
        self._safe_set(dpg, self._franchise_tag("development"), self._franchise_lines_text("Development Watch", getattr(dashboard, "development_watch", ())))

    def _run_franchise_action(self, dpg: Any, action: Any) -> None:
        try:
            dashboard = action(self.franchise_facade)
        except Exception as exc:
            self._safe_set(dpg, self._franchise_tag("status"), f"Franchise action failed: {exc}")
            return
        self._sync_franchise_dashboard(dpg, dashboard)

    def _show_franchise_report(self, dpg: Any, title: str, lines: object) -> None:
        self._safe_set(dpg, self._franchise_tag("activity"), self._franchise_lines_text(title, lines))

    def _build_franchise_manager_screen(self, dpg: Any, *, show: bool = False) -> None:
        with dpg.child_window(tag=self._screen_tag(FRANCHISE_MANAGER_SCREEN), show=show, width=-1, height=-1, border=False):
            dpg.add_text("Franchise Manager")
            dpg.add_spacer(height=8)
            dpg.add_text(getattr(self.franchise_dashboard, "status", ""), tag=self._franchise_tag("status"))
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create Franchise", width=130, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.create_franchise()))
                dpg.add_button(label="Load Franchise", width=120, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.load_franchise()))
                dpg.add_button(label="Save Franchise", width=120, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.save_franchise()))
                dpg.add_button(label="Import 2K Data", width=130, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.import_2k_data_from_offsets(self.model)))
                dpg.add_button(label="Run Evaluations", width=135, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.run_gm_evaluations()))
                dpg.add_button(label="Advance Phase", width=125, callback=lambda *_args: self._run_franchise_action(dpg, lambda facade: facade.advance_phase()))
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Open Draft Room", width=140, callback=lambda *_args: self._show_franchise_report(dpg, "Draft Room", self.franchise_facade.get_draft_report()))
                dpg.add_button(label="Open Team View", width=130, callback=lambda *_args: self._show_franchise_report(dpg, "Team View", (str(self.franchise_facade.get_team_dashboard().display_name), *self.franchise_facade.get_team_dashboard().recent_logs)))
                dpg.add_button(label="Open League History", width=155, callback=lambda *_args: self._show_franchise_report(dpg, "League History", self.franchise_facade.get_history_report()))
            dpg.add_spacer(height=8)
            with dpg.child_window(width=-1, height=120, border=True):
                dpg.add_text("Manual Team W-L Entry")
                dpg.add_text("Paste rows from a screenshot as: Team, Wins, Losses or Team 44-12")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag=self._franchise_tag("manual_standings_text"), default_value=self.franchise_manual_standings_text, multiline=True, width=-140, height=62)
                    dpg.add_button(label="Import W-L", width=110, height=30, callback=lambda *_args: self._import_manual_franchise_standings(dpg))
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=380, height=210, border=True):
                    dpg.add_text("Franchise Overview")
                    dpg.add_input_text(tag=self._franchise_tag("overview"), default_value=self._franchise_overview_text(self.franchise_dashboard), multiline=True, readonly=True, width=-1, height=-1)
                with dpg.child_window(width=-1, height=210, border=True):
                    dpg.add_text("League Snapshot")
                    dpg.add_input_text(tag=self._franchise_tag("snapshot"), default_value=self._franchise_snapshot_text(self.franchise_dashboard), multiline=True, readonly=True, width=-1, height=-1)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=380, height=150, border=True):
                    dpg.add_text("Owner Alerts")
                    dpg.add_input_text(tag=self._franchise_tag("owner_alerts"), default_value=self._franchise_lines_text("Owner Alerts", getattr(self.franchise_dashboard, "owner_alerts", ())), multiline=True, readonly=True, width=-1, height=-1)
                with dpg.child_window(width=380, height=150, border=True):
                    dpg.add_text("GM Alerts")
                    dpg.add_input_text(tag=self._franchise_tag("gm_alerts"), default_value=self._franchise_lines_text("GM Alerts", getattr(self.franchise_dashboard, "gm_alerts", ())), multiline=True, readonly=True, width=-1, height=-1)
                with dpg.child_window(width=-1, height=150, border=True):
                    dpg.add_text("Next Simulation Stop")
                    dpg.add_input_text(tag=self._franchise_tag("next_stop"), default_value=self._franchise_next_stop_text(self.franchise_dashboard), multiline=True, readonly=True, width=-1, height=-1)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=580, height=-1, border=True):
                    dpg.add_text("League Activity Feed")
                    dpg.add_input_text(tag=self._franchise_tag("activity"), default_value=self._franchise_lines_text("League Activity Feed", getattr(self.franchise_dashboard, "activity_feed", ())), multiline=True, readonly=True, width=-1, height=-1)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text("Development Watch")
                    dpg.add_input_text(tag=self._franchise_tag("development"), default_value=self._franchise_lines_text("Development Watch", getattr(self.franchise_dashboard, "development_watch", ())), multiline=True, readonly=True, width=-1, height=-1)

    def _build_players_screen(self, dpg: Any, *, show: bool = False) -> None:
        domain = "Players"
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=90, callback=lambda *_args: self._attach_and_scan(dpg, domain))
                dpg.add_spacer(width=18)
                dpg.add_text("Players: 0", tag=self._count_tag(domain))
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_text("Export folder")
                dpg.add_input_text(tag=self._player_roster_export_folder_tag(), default_value=self.player_roster_export_folder, width=320)
                dpg.add_text("File name")
                dpg.add_input_text(tag=self._player_roster_snapshot_filename_tag(), default_value=self.player_roster_snapshot_filename, width=260)
                dpg.add_button(label="Export Players", width=130, callback=lambda *_args: self._export_player_roster_snapshot(dpg))
                dpg.add_button(label="Apply Roster Snapshot", width=170, callback=lambda *_args: self._apply_player_roster_snapshot(dpg))
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_text("Export mode")
                dpg.add_combo(
                    list(PLAYER_ROSTER_EXPORT_MODES),
                    tag=self._player_roster_export_mode_tag(),
                    default_value=self.player_roster_export_mode,
                    width=210,
                )
                dpg.add_text("Team range")
                dpg.add_input_text(tag=self._player_roster_team_start_tag(), default_value=self.player_roster_team_start, width=45)
                dpg.add_text("to")
                dpg.add_input_text(tag=self._player_roster_team_end_tag(), default_value=self.player_roster_team_end, width=45)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_text("Team")
                dpg.add_combo(
                    list(self.model.player_team_filter_options()),
                    tag=self._player_team_filter_tag(),
                    default_value=PLAYER_TEAM_FILTER_ALL,
                    width=220,
                    callback=lambda _s, app_data, _u=None, *args: self._set_player_team_filter(dpg, app_data),
                )
                dpg.add_spacer(width=18)
                dpg.add_text("Search")
                dpg.add_input_text(
                    tag=self._player_search_tag(),
                    hint="Search players",
                    width=320,
                    callback=lambda _s, app_data, _u=None, *args: self._set_player_search_text(dpg, app_data),
                )
            dpg.add_spacer(height=14)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=420, height=-1, border=True):
                    dpg.add_group(tag=self._list_content_tag(domain))
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text("Select a player", tag=self._detail_tag(domain, "title"))
                    dpg.add_spacer(height=12)
                    for label in self.model.player_detail_labels():
                        self._add_detail_row(dpg, label, self._detail_tag(domain, label), accent=label == "OVR")
                        dpg.add_spacer(height=8)
                    dpg.add_spacer(height=10)
                    dpg.add_button(label="Edit Player", callback=lambda *_args: self._open_selected(dpg, domain))

    def _build_teams_screen(self, dpg: Any, *, show: bool = False) -> None:
        domain = "Teams"
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=90, callback=lambda *_args: self._attach_and_scan(dpg, domain))
                dpg.add_spacer(width=8)
                dpg.add_text("Teams: 0", tag=self._count_tag(domain))
            dpg.add_spacer(height=8)
            dpg.add_text(self._game_status_text(), tag=self._status_tag(domain))
            dpg.add_spacer(height=18)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=340, height=-1, border=True):
                    dpg.add_group(tag=self._list_content_tag(domain))
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text("Select a team", tag=self._detail_tag(domain, "title"))
                    dpg.add_spacer(height=8)
                    dpg.add_text(self._game_status_text(), tag=self._detail_tag(domain, "status"))
                    dpg.add_spacer(height=18)
                    for label in self.model.team_summary_labels():
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"{label}:")
                            dpg.add_input_text(tag=self._team_input_tag(label), width=-1)
                        dpg.add_spacer(height=4)
                    dpg.add_spacer(height=10)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Save Fields", width=120, callback=lambda *_args: self._save_team_summary(dpg))
                        dpg.add_button(label="Edit Team", width=120, callback=lambda *_args: self._open_selected(dpg, domain))
                        dpg.add_button(label="Zero All Team Record Data", width=190, callback=lambda *_args: self._zero_all_team_record_data_values(dpg))

    def _add_button_strip(self, dpg: Any, labels: tuple[str, ...], *, per_row: int, callback: Any | None = None) -> None:
        for start in range(0, len(labels), per_row):
            with dpg.group(horizontal=True):
                for label in labels[start : start + per_row]:
                    dpg.add_button(label=label, height=28, callback=(lambda *_args, selected=label: callback(selected)) if callback else None)
            dpg.add_spacer(height=6)

    def _build_history_screen(self, dpg: Any, *, show: bool = False) -> None:
        domain = "NBA History"
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=260, height=-1, border=False):
                    dpg.add_button(label="Refresh", width=-1, callback=lambda *_args: self._attach_and_scan(dpg, domain))
                    dpg.add_spacer(height=6)
                    dpg.add_button(label="Edit Selected History Row", width=-1, callback=lambda *_args: self._open_selected(dpg, domain))
                    dpg.add_spacer(height=18)
                    for label in HISTORY_SIDE_NAV:
                        dpg.add_button(label=label, width=-1, height=34, callback=lambda *_args, selected=label: self._set_history_section(dpg, selected))
                        dpg.add_spacer(height=6)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text(self.history_section, tag=self._heading_tag(domain))
                    dpg.add_spacer(height=14)
                    for section, tabs in HISTORY_SECTION_TABS.items():
                        with dpg.group(tag=self._history_tab_group_tag(section), show=section == self.history_section):
                            self._add_button_strip(dpg, tabs, per_row=5, callback=lambda selected: self._set_history_tab(dpg, selected))
                    dpg.add_spacer(height=8)
                    dpg.add_text(self._game_status_text(), tag=self._status_tag(domain))
                    dpg.add_text("NBA History: 0", tag=self._count_tag(domain))
                    dpg.add_spacer(height=10)
                    with dpg.child_window(width=-1, height=-1, border=True):
                        for section in HISTORY_TABLE_COLUMNS:
                            with dpg.group(tag=self._history_table_group_tag(section), show=section == self.history_section):
                                dpg.add_group(tag=self._history_table_content_tag(section))

    def _build_records_screen(self, dpg: Any, *, show: bool = False) -> None:
        domain = "NBA Records"
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=260, height=-1, border=False):
                    dpg.add_button(label="Refresh", width=-1, callback=lambda *_args: self._attach_and_scan(dpg, domain))
                    dpg.add_spacer(height=18)
                    for label in RECORD_SIDE_NAV:
                        dpg.add_button(label=label, width=-1, height=34, callback=lambda *_args, selected=label: self._set_record_section(dpg, selected))
                        dpg.add_spacer(height=6)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text(self.record_section, tag=self._heading_tag(domain))
                    dpg.add_spacer(height=14)
                    for section, tabs in RECORD_SECTION_STAT_TABS.items():
                        with dpg.group(tag=self._record_stat_group_tag(section), show=section == self.record_section):
                            self._add_button_strip(dpg, tabs, per_row=13, callback=lambda selected: self._set_record_stat(dpg, selected))
                    dpg.add_spacer(height=8)
                    dpg.add_text(self._game_status_text(), tag=self._status_tag(domain))
                    dpg.add_text("NBA Records: 0", tag=self._count_tag(domain))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Save Data Values", width=140, callback=lambda *_args: self._save_record_data_values(dpg))
                        dpg.add_button(label="Zero All Data Values", width=150, callback=lambda *_args: self._zero_record_data_values(dpg))
                    dpg.add_spacer(height=10)
                    with dpg.child_window(width=-1, height=-1, border=True):
                        with dpg.group(tag=self._record_cards_container_tag(), show=True):
                            labels = RECORD_CARD_LABELS
                            for row_index in range(RECORD_PREVIEW_CARDS):
                                with dpg.group(tag=self._record_card_tag(row_index), show=row_index < RECORD_SECTION_ROW_LAYOUT[self.record_section][1]):
                                    dpg.add_text(f"Record #{row_index + 1}", tag=self._record_card_title_tag(row_index))
                                    dpg.add_spacer(height=8)
                                    for start in range(0, len(labels), 3):
                                        with dpg.group(horizontal=True):
                                            for label in labels[start : start + 3]:
                                                with dpg.group():
                                                    dpg.add_text(f"{label}:")
                                                    dpg.add_input_text(tag=self._preview_tag(domain, row_index, label), readonly=label != "Data", width=280)
                                        dpg.add_spacer(height=8)
                                    dpg.add_spacer(height=18)
                        with dpg.group(tag=self._record_career_table_tag(), show=False):
                            with dpg.table(header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
                                for label in RECORD_CAREER_TABLE_LABELS:
                                    dpg.add_table_column(label=label)
                                for row_index in range(RECORD_PREVIEW_CARDS):
                                    with dpg.table_row():
                                        for label in RECORD_CAREER_TABLE_LABELS:
                                            if label == "Data":
                                                dpg.add_input_text(default_value="--", tag=self._record_career_cell_tag(row_index, label), width=120)
                                            else:
                                                dpg.add_text("--", tag=self._record_career_cell_tag(row_index, label))

    def _build_history_or_records_screen(self, dpg: Any, domain: str, *, show: bool = False) -> None:
        if domain == "NBA History":
            self._build_history_screen(dpg, show=show)
            return
        self._build_records_screen(dpg, show=show)

    def _build_domain_screen(self, dpg: Any, domain: str, *, show: bool = False) -> None:
        if domain == PLAYER_GENERATOR_SCREEN:
            self._build_player_generator_screen(dpg, show=show)
            return
        if domain == FRANCHISE_MANAGER_SCREEN:
            self._build_franchise_manager_screen(dpg, show=show)
            return
        if domain == "Players":
            self._build_players_screen(dpg, show=show)
            return
        if domain == "Teams":
            self._build_teams_screen(dpg, show=show)
            return
        if domain in {"NBA History", "NBA Records"}:
            self._build_history_or_records_screen(dpg, domain, show=show)
            return
        label = self._display_label(domain)
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=90, callback=lambda *_args, d=domain: self._attach_and_scan(dpg, d))
                dpg.add_spacer(width=8)
                dpg.add_text(f"{label}: 0", tag=self._count_tag(domain))
            dpg.add_spacer(height=8)
            dpg.add_text(self._game_status_text(), tag=self._status_tag(domain))
            dpg.add_spacer(height=18)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=420, height=-1, border=True):
                    dpg.add_group(tag=self._list_content_tag(domain))
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text(f"Select a {label.lower()}", tag=self._detail_tag(domain, "title"))
                    dpg.add_spacer(height=12)
                    dpg.add_text("Record address")
                    dpg.add_text("--", tag=self._detail_tag(domain, "address"))
                    dpg.add_spacer(height=18)
                    dpg.add_button(label=f"Edit {label}", callback=lambda *_args, d=domain: self._open_selected(dpg, d))

    def run(self, *, load_on_start: bool = True) -> None:
        import dearpygui.dearpygui as dpg
        from nba2k_editor.ui.theme import apply_base_theme, ensure_editor_themes

        dpg.create_context()
        apply_base_theme()
        self.item_themes = ensure_editor_themes()
        with dpg.window(
            label=APP_TITLE,
            tag="main_window",
            width=APP_VIEWPORT_WIDTH,
            height=APP_VIEWPORT_HEIGHT,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_collapse=True,
            no_scrollbar=True,
        ):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=210, height=-1, border=False):
                    self._add_nav_button(dpg, "Home", "Home")
                    for domain in NAV_ORDER:
                        if domain in APP_SCREENS:
                            self._add_nav_button(dpg, domain, self._display_label(domain))
                with dpg.child_window(width=-1, height=-1, border=False):
                    self._build_home_screen(dpg, show=True)
                    for domain in APP_SCREENS:
                        if domain != "Home":
                            self._build_domain_screen(dpg, domain, show=False)
        self._refresh_nav_state(dpg)

        dpg.create_viewport(title=APP_TITLE, width=APP_VIEWPORT_WIDTH, height=APP_VIEWPORT_HEIGHT)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)
        print("DPG_OPENED NBA2K Editor", flush=True)
        if load_on_start:
            self._attach_and_load_all(dpg)
        while dpg.is_dearpygui_running():
            self._poll_background_scan(dpg)
            self._poll_background_operation(dpg)
            dpg.render_dearpygui_frame()


__all__ = ["DpgEditorApp", "EDITOR_DOMAINS", "FieldEntry", "RecordListItem", "verify_edits"]




