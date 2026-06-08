from __future__ import annotations

import re
from typing import Any

from nba2k_editor.models.data_model import (
    EDITOR_DOMAINS,
    EditorDataModel,
    FieldEntry,
    PLAYER_TEAM_FILTER_ALL,
    RecordListItem,
    target_display_label,
    verify_edits,
)

APP_TITLE = "Offline Player Data Editor"
APP_VIEWPORT_WIDTH = 1600
APP_VIEWPORT_HEIGHT = 900
RECORD_LIST_ROW_HEIGHT = 19
RECORD_LIST_VERTICAL_MARGIN = 140
MIN_RECORD_LIST_ROWS = 8
TARGET_CHOICES: tuple[str, ...] = ("NBA 2K22", "NBA 2K23", "NBA 2K24", "NBA 2K25", "NBA 2K26")
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
RECORD_STAT_TABS: tuple[str, ...] = RECORD_EXTENDED_STAT_TABS
RECORD_SECTION_STAT_TABS: dict[str, tuple[str, ...]] = {
    "Single Game (Regular)": RECORD_BASE_STAT_TABS,
    "Single Game (Playoffs)": RECORD_BASE_STAT_TABS,
    "Season": RECORD_EXTENDED_STAT_TABS,
    "Career": RECORD_EXTENDED_STAT_TABS,
}
RECORD_CARD_LABELS: tuple[str, ...] = ("First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data")
RECORD_CAREER_TABLE_LABELS: tuple[str, ...] = ("Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data")
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
        "Rebounds/Game": 2,
        "Assists/Game": 2,
        "Steals/Game": 2,
        "Blocks/Game": 2,
        "Minutes/Game": 2,
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
    "NBA History",
    "NBA Records",
    "Staff",
    "Stadiums",
    "Jerseys",
    "Shoes",
)
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
        self.nav_button_tags: dict[str, str] = {}
        self.item_themes: dict[str, str] = {}
        self._record_list_rows = 0
        self.history_section = "Season Awards"
        self.history_award = "Most Valuable Player"
        self.history_tabs: dict[str, str] = {section: tabs[0] for section, tabs in HISTORY_SECTION_TABS.items()}
        self.record_section = "Single Game (Regular)"
        self.record_stat = "Points"
        self.player_team_filter = PLAYER_TEAM_FILTER_ALL

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

    def _list_tag(self, domain: str) -> str:
        return _tag(domain, "list")

    def _player_team_filter_tag(self) -> str:
        return _tag("Players", "team_filter")

    def _record_list_rows_for_height(self, viewport_height: int) -> int:
        return max(MIN_RECORD_LIST_ROWS, (viewport_height - RECORD_LIST_VERTICAL_MARGIN) // RECORD_LIST_ROW_HEIGHT)

    def _resize_record_lists(self, dpg: Any) -> None:
        rows = self._record_list_rows_for_height(int(dpg.get_viewport_client_height()))
        if rows == self._record_list_rows:
            return
        self._record_list_rows = rows
        for domain in EDITOR_DOMAINS:
            self._safe_configure(dpg, self._list_tag(domain), num_items=rows)

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

    def _nav_tag(self, screen: str) -> str:
        return _tag("nav", screen)

    def _display_label(self, domain: str) -> str:
        return DOMAIN_LABELS.get(domain, domain)

    def _game_status_text(self) -> str:
        return self.model.runtime_status_text()

    def _safe_set(self, dpg: Any, tag: str, value: object) -> None:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, str(value))

    def _safe_configure(self, dpg: Any, tag: str, **kwargs: object) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, **kwargs)

    def _safe_delete_children(self, dpg: Any, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag, children_only=True)

    def _bind_item_theme(self, dpg: Any, item: str, theme: str) -> None:
        if theme and dpg.does_item_exist(item) and dpg.does_item_exist(theme):
            dpg.bind_item_theme(item, theme)

    def _refresh_nav_state(self, dpg: Any) -> None:
        for screen, tag in self.nav_button_tags.items():
            theme_key = "nav_selected" if screen == self.current_screen else "nav"
            self._bind_item_theme(dpg, tag, self.item_themes.get(theme_key, ""))

    def _show_screen(self, dpg: Any, domain: str) -> None:
        self.current_screen = domain
        for candidate in ("Home", *EDITOR_DOMAINS):
            tag = self._app_screen_tag(candidate)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=candidate == domain)
        self._refresh_nav_state(dpg)

    def _set_target(self, dpg: Any, selected: str) -> None:
        self.model.select_target_executable(_target_executable(str(selected)))
        self._refresh_status_labels(dpg)
        for domain in EDITOR_DOMAINS:
            self._sync_domain_list(dpg, domain)

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

    def _start_background_scan(self, dpg: Any, domains: tuple[str, ...]) -> None:
        if not self.model.start_background_refresh(domains):
            self._safe_set(dpg, self._home_target_status_tag(), "Scan already running...")
            return
        self._safe_set(dpg, self._home_target_status_tag(), "Loading record lists...")
        for domain in domains:
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
        if domain == "Players":
            self._sync_player_list(dpg)
            return
        labels = self.model.domain_item_labels(domain)
        self._safe_configure(dpg, self._list_tag(domain), items=labels)
        self._safe_set(dpg, self._count_tag(domain), f"{self._display_label(domain)}: {self.model.domain_item_count(domain)}")
        selected = self.model.selected_item(domain)
        if selected is not None and labels:
            self._safe_set(dpg, self._list_tag(domain), selected.display_label)
        self._safe_set(dpg, self._status_tag(domain), self.model.domain_status(domain))
        if domain in {"NBA History", "NBA Records"}:
            self._sync_record_preview(dpg, domain)
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
        labels = self.model.player_item_labels_for_team_filter(self.player_team_filter)
        self._safe_configure(dpg, self._list_tag(domain), items=labels)
        total_count = self.model.domain_item_count(domain)
        visible_count = len(labels)
        count_text = f"Players: {visible_count}" if self.player_team_filter == PLAYER_TEAM_FILTER_ALL else f"Players: {visible_count} / {total_count}"
        self._safe_set(dpg, self._count_tag(domain), count_text)
        selected = self.model.selected_item(domain)
        selected_label = selected.display_label if selected is not None else ""
        if labels and selected_label not in labels:
            selected = self.model.select_item_by_label(domain, labels[0])
        elif not labels:
            selected = self.model.select_item_by_label(domain, None)
        if selected is not None and labels:
            self._safe_set(dpg, self._list_tag(domain), selected.display_label)
        self._safe_set(dpg, self._status_tag(domain), self.model.domain_status(domain))
        self._update_detail_panel(dpg, domain)

    def _set_player_team_filter(self, dpg: Any, selected: str | None) -> None:
        self.player_team_filter = str(selected or PLAYER_TEAM_FILTER_ALL)
        self._sync_player_list(dpg)

    def _sync_record_preview(self, dpg: Any, domain: str) -> None:
        if domain == "NBA Records":
            record_row_start, record_row_count = self._active_record_row_group()
            rows = self.model.record_summary_rows(
                domain,
                limit=RECORD_PREVIEW_CARDS,
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
                    self._safe_set(dpg, self._preview_tag(domain, row_index, label), row_values.get(label, "--"))
            return

        for section in HISTORY_SIDE_NAV:
            self._safe_configure(dpg, self._history_tab_group_tag(section), show=section == self.history_section)
            self._safe_configure(dpg, self._history_table_group_tag(section), show=section == self.history_section)
        rows = self.model.record_summary_rows(
            domain,
            limit=None,
            history_type=self._active_history_type() if domain == "NBA History" else None,
        )
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

    def _active_history_type(self) -> int | None:
        if self.history_section == "Season Awards":
            return HISTORY_AWARD_TYPES.get(self.history_tabs.get("Season Awards", self.history_award))
        selected_tab = self.history_tabs.get(self.history_section)
        section_map = HISTORY_SECTION_TAB_TYPES.get(self.history_section, {})
        return section_map.get(selected_tab, HISTORY_SECTION_DEFAULT_TYPES.get(self.history_section))

    def _active_record_row_group(self) -> tuple[int, int]:
        section_start, row_count = RECORD_SECTION_ROW_LAYOUT.get(self.record_section, RECORD_SECTION_ROW_LAYOUT["Single Game (Regular)"])
        tabs = RECORD_SECTION_STAT_TABS.get(self.record_section, RECORD_BASE_STAT_TABS)
        stat_index = tabs.index(self.record_stat) if self.record_stat in tabs else 0
        return section_start + stat_index * row_count, row_count

    def _set_history_section(self, dpg: Any, label: str) -> None:
        self.history_section = label
        self._safe_set(dpg, self._heading_tag("NBA History"), label)
        self._sync_record_preview(dpg, "NBA History")

    def _set_history_tab(self, dpg: Any, label: str) -> None:
        self.history_tabs[self.history_section] = label
        if self.history_section == "Season Awards":
            self.history_award = label
        self._sync_record_preview(dpg, "NBA History")

    def _set_history_award(self, dpg: Any, label: str) -> None:
        self.history_section = "Season Awards"
        self._set_history_tab(dpg, label)

    def _set_record_section(self, dpg: Any, label: str) -> None:
        self.record_section = label
        tabs = RECORD_SECTION_STAT_TABS.get(self.record_section, RECORD_BASE_STAT_TABS)
        if self.record_stat not in tabs:
            self.record_stat = tabs[0]
        self._safe_set(dpg, self._heading_tag("NBA Records"), self.record_section)
        self._sync_record_preview(dpg, "NBA Records")

    def _set_record_stat(self, dpg: Any, label: str) -> None:
        self.record_stat = label
        self._safe_set(dpg, self._heading_tag("NBA Records"), self.record_section)
        self._sync_record_preview(dpg, "NBA Records")

    def _select_current(self, dpg: Any, domain: str, selected_label: str | None = None) -> None:
        selected = str(selected_label or dpg.get_value(self._list_tag(domain)) or "")
        self.model.select_item_by_label(domain, selected)
        self._update_detail_panel(dpg, domain)

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

    def _load_item_editor(self, dpg: Any, item: RecordListItem) -> None:
        loaded = 0
        failed = 0
        prefix = f"{item.domain}:{item.index}:"
        for row_key, entry in self.open_rows.items():
            if not row_key.startswith(prefix):
                continue
            try:
                value = self.model.read_entry_value(entry, index=item.index)
                text = str(value["display_value"])
                dpg.set_value(self._row_current_tag(item, entry), text)
                dpg.set_value(self._row_new_tag(item, entry), text)
                dpg.set_value(self._row_status_tag(item, entry), f"0x{value['address']:X}")
                loaded += 1
            except Exception as exc:
                dpg.set_value(self._row_current_tag(item, entry), "")
                dpg.set_value(self._row_new_tag(item, entry), "")
                dpg.set_value(self._row_status_tag(item, entry), str(exc)[:90])
                failed += 1
        self._safe_set(dpg, self._editor_status_tag(item), f"loaded {loaded} fields, {failed} unavailable")

    def _save_item_editor(self, dpg: Any, item: RecordListItem) -> None:
        saved = 0
        failed = 0
        prefix = f"{item.domain}:{item.index}:"
        for row_key, entry in self.open_rows.items():
            if not row_key.startswith(prefix):
                continue
            old_text = str(dpg.get_value(self._row_current_tag(item, entry)) or "")
            new_text = str(dpg.get_value(self._row_new_tag(item, entry)) or "")
            if new_text == old_text:
                continue
            try:
                readback = self.model.write_entry_value(entry, index=item.index, value=new_text)
                text = str(readback["display_value"])
                dpg.set_value(self._row_current_tag(item, entry), text)
                dpg.set_value(self._row_new_tag(item, entry), text)
                dpg.set_value(self._row_status_tag(item, entry), f"saved @ 0x{readback['address']:X}")
                saved += 1
            except Exception as exc:
                dpg.set_value(self._row_status_tag(item, entry), str(exc)[:90])
                failed += 1
        self._safe_set(dpg, self._editor_status_tag(item), f"saved {saved} changed fields, {failed} failed")

    def _open_editor_window(self, dpg: Any, item: RecordListItem) -> None:
        win_tag = _tag("editor", item.domain, item.index, "window")
        if dpg.does_item_exist(win_tag):
            dpg.focus_item(win_tag)
            return
        with dpg.window(label=f"{item.domain} [{item.index}] {item.label}", tag=win_tag, width=1120, height=760):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Reload", callback=lambda *_args, i=item: self._load_item_editor(dpg, i))
                dpg.add_button(label="Save Changes + Readback", callback=lambda *_args, i=item: self._save_item_editor(dpg, i))
            with dpg.child_window(height=-1, border=True):
                with dpg.tab_bar():
                    for section, groups in self.model.grouped_fields(item.domain).items():
                        with dpg.tab(label=section):
                            for group, entries in groups.items():
                                with dpg.collapsing_header(label=group, default_open=group in {"ID", "Vitals", "Basic Info"}):
                                    with dpg.table(header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
                                        dpg.add_table_column(label="Field")
                                        dpg.add_table_column(label="Current")
                                        dpg.add_table_column(label="New")
                                        dpg.add_table_column(label="Address / Status")
                                        target_match = re.search(r"nba2k(\d{2})", self.model.target_executable, flags=re.IGNORECASE)
                                        target_version = "2K" + target_match.group(1) if target_match else "2K26"
                                        for entry in entries:
                                            row_key = f"{item.domain}:{item.index}:{entry.ordinal}"
                                            self.open_rows[row_key] = entry
                                            with dpg.table_row():
                                                dpg.add_text(entry.display_name)
                                                dpg.add_input_text(tag=self._row_current_tag(item, entry), readonly=True, width=-1)
                                                versions = entry.field.get("versions")
                                                options: list[str] = []
                                                if isinstance(versions, dict):
                                                    for raw_key, payload in versions.items():
                                                        tokens = [chunk.strip().upper() for chunk in str(raw_key).split(",") if chunk.strip()]
                                                        if target_version.upper() not in tokens or not isinstance(payload, dict):
                                                            continue
                                                        raw_options = payload.get("dropdown") or payload.get("values")
                                                        if isinstance(raw_options, list):
                                                            options = [str(option) for option in raw_options]
                                                        break
                                                if options:
                                                    dpg.add_combo(options, tag=self._row_new_tag(item, entry), width=-1)
                                                else:
                                                    dpg.add_input_text(tag=self._row_new_tag(item, entry), width=-1)
                                                dpg.add_text("", tag=self._row_status_tag(item, entry))
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

    def _build_players_screen(self, dpg: Any, *, show: bool = False) -> None:
        domain = "Players"
        with dpg.child_window(tag=self._screen_tag(domain), show=show, width=-1, height=-1, border=False):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=90, callback=lambda *_args: self._attach_and_scan(dpg, domain))
                dpg.add_spacer(width=18)
                dpg.add_text("Players: 0", tag=self._count_tag(domain))
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
            dpg.add_spacer(height=14)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=420, height=-1, border=True, no_scrollbar=True):
                    dpg.add_listbox([], tag=self._list_tag(domain), width=-1, num_items=self._record_list_rows_for_height(APP_VIEWPORT_HEIGHT), callback=lambda _s, app_data, _u=None, *_, d=domain: self._select_current(dpg, d, app_data))
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
                with dpg.child_window(width=340, height=-1, border=True, no_scrollbar=True):
                    dpg.add_listbox([], tag=self._list_tag(domain), width=220, num_items=self._record_list_rows_for_height(APP_VIEWPORT_HEIGHT), callback=lambda _s, app_data, _u=None, *_, d=domain: self._select_current(dpg, d, app_data))
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

    def _record_screen_heading(self, domain: str) -> str:
        if domain == "NBA History":
            return "Season Awards"
        if domain == "NBA Records":
            return "Single Game (Regular)"
        return self._display_label(domain)

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
                with dpg.child_window(width=210, height=-1, border=False):
                    dpg.add_button(label="Refresh", width=-1, callback=lambda *_args: self._attach_and_scan(dpg, domain))
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
                    self._sync_record_preview(dpg, domain)

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
                                                    dpg.add_input_text(tag=self._preview_tag(domain, row_index, label), readonly=True, width=280)
                                        dpg.add_spacer(height=8)
                                    dpg.add_spacer(height=18)
                        with dpg.group(tag=self._record_career_table_tag(), show=False):
                            with dpg.table(header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp):
                                for label in RECORD_CAREER_TABLE_LABELS:
                                    dpg.add_table_column(label=label)
                                for row_index in range(RECORD_PREVIEW_CARDS):
                                    with dpg.table_row():
                                        for label in RECORD_CAREER_TABLE_LABELS:
                                            dpg.add_text("--", tag=self._record_career_cell_tag(row_index, label))

    def _build_history_or_records_screen(self, dpg: Any, domain: str, *, show: bool = False) -> None:
        if domain == "NBA History":
            self._build_history_screen(dpg, show=show)
            return
        self._build_records_screen(dpg, show=show)

    def _build_domain_screen(self, dpg: Any, domain: str, *, show: bool = False) -> None:
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
                with dpg.child_window(width=420, height=-1, border=True, no_scrollbar=True):
                    dpg.add_listbox([], tag=self._list_tag(domain), width=-1, num_items=self._record_list_rows_for_height(APP_VIEWPORT_HEIGHT), callback=lambda _s, app_data, _u=None, *_, d=domain: self._select_current(dpg, d, app_data))
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text(f"Select a {label.lower()}", tag=self._detail_tag(domain, "title"))
                    dpg.add_spacer(height=12)
                    dpg.add_text("Record address")
                    dpg.add_text("--", tag=self._detail_tag(domain, "address"))
                    dpg.add_spacer(height=18)
                    dpg.add_button(label=f"Edit {label}", callback=lambda *_args, d=domain: self._open_selected(dpg, d))

    def run(self, *, close_after_frames: int | None = None, load_on_start: bool = True) -> None:
        import dearpygui.dearpygui as dpg
        from nba2k_editor.ui.theme import apply_base_theme, ensure_editor_themes

        dpg.create_context()
        try:
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
                            if domain in EDITOR_DOMAINS:
                                self._add_nav_button(dpg, domain, self._display_label(domain))
                    with dpg.child_window(width=-1, height=-1, border=False):
                        self._build_home_screen(dpg, show=True)
                        for domain in EDITOR_DOMAINS:
                            self._build_domain_screen(dpg, domain, show=False)
            self._refresh_nav_state(dpg)

            dpg.create_viewport(title=APP_TITLE, width=APP_VIEWPORT_WIDTH, height=APP_VIEWPORT_HEIGHT)
            dpg.setup_dearpygui()
            dpg.show_viewport()
            dpg.set_primary_window("main_window", True)
            self._resize_record_lists(dpg)
            print("DPG_OPENED NBA2K Editor", flush=True)
            if load_on_start:
                self._attach_and_load_all(dpg)
            frame = 0
            while dpg.is_dearpygui_running():
                self._poll_background_scan(dpg)
                self._resize_record_lists(dpg)
                dpg.render_dearpygui_frame()
                frame += 1
                if close_after_frames is not None and frame >= close_after_frames:
                    break
        finally:
            dpg.destroy_context()


__all__ = ["DpgEditorApp", "EDITOR_DOMAINS", "FieldEntry", "RecordListItem", "verify_edits"]
