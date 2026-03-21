"""Main application window (ported from the monolithic editor)."""
from __future__ import annotations

import queue
from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Any, Callable

import dearpygui.dearpygui as dpg

from .bound_vars import BoundBoolVar, BoundDoubleVar, BoundVar
from .shell_utils import UIHostMixin, open_file_dialog
from .app_launchers import (
    open_batch_edit as launcher_open_batch_edit,
    open_randomizer as launcher_open_randomizer,
    open_team_shuffle as launcher_open_team_shuffle,
)
from .app_shell import (
    build_ui as shell_build_ui,
    copy_to_clipboard as shell_copy_to_clipboard,
)

from ..core.config import MODULE_NAME
from ..core.offsets import TEAM_FIELD_DEFS
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from .home_screen import build_home_screen as _default_build_home_screen
from .players_screen import build_players_screen as _default_build_players_screen
from .teams_screen import build_teams_screen as _default_build_teams_screen
from .league_screen import (
    build_nba_history_screen as _default_build_nba_history_screen,
    build_nba_records_screen as _default_build_nba_records_screen,
)
from .staff_screen import build_staff_screen as _default_build_staff_screen
from .stadium_screen import build_stadium_screen as _default_build_stadium_screen
from .excel_screen import build_excel_screen as _default_build_excel_screen
from .trade_players import build_trade_players_screen as _default_build_trade_players_screen
from .controllers import league as league_controller
from .controllers import players as players_controller
from .controllers import stadium as stadium_controller
from .controllers import staff as staff_controller
from .controllers import teams as teams_controller
from .controllers import import_export as import_export_controller
from .controllers import trade as trade_controller
from .controllers.screen_registry import ScreenRegistration, ensure_screen_built
from .state.trade_state import TradeState


def _bind_passthrough_method(name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
    def _method(self: Any, *args: Any, **kwargs: Any) -> Any:
        return handler(self, *args, **kwargs)

    _method.__name__ = name
    return _method


def _bind_controller_method(handler: Callable[..., Any]) -> Callable[..., Any]:
    return _bind_passthrough_method(handler.__name__, handler)


def _bind_dpg_team_listbox_select(handler: Callable[..., Any]) -> Callable[..., Any]:
    def _method(
        self: Any,
        sender: Any = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> Any:
        return handler(self, sender, app_data)

    _method.__name__ = handler.__name__
    return _method


def _bind_dpg_player_selected(handler: Callable[..., Any]) -> Callable[..., Any]:
    def _method(
        self: Any,
        sender: Any = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> Any:
        return handler(self, sender, app_data, user_data)

    _method.__name__ = handler.__name__
    return _method


build_home_screen = _default_build_home_screen
build_players_screen = _default_build_players_screen
build_teams_screen = _default_build_teams_screen
build_nba_history_screen = _default_build_nba_history_screen
build_nba_records_screen = _default_build_nba_records_screen
build_staff_screen = _default_build_staff_screen
build_stadium_screen = _default_build_stadium_screen
build_excel_screen = _default_build_excel_screen
build_trade_players_screen = _default_build_trade_players_screen


@dataclass
class PlayerUIState:
    selected_team: str | None = None
    selected_player: Player | None = None
    selected_players: list[Player] = field(default_factory=list)
    current_players: list[Player] = field(default_factory=list)
    filtered_player_indices: list[int] = field(default_factory=list)
    player_list_items: list[str] = field(default_factory=list)
    player_search_var: BoundVar = field(default_factory=BoundVar)
    player_count_var: BoundVar = field(default_factory=lambda: BoundVar("Players: 0"))
    scan_status_var: BoundVar = field(default_factory=BoundVar)
    player_name_var: BoundVar = field(default_factory=lambda: BoundVar("Select a player"))
    player_ovr_var: BoundVar = field(default_factory=lambda: BoundVar("OVR --"))
    var_first: BoundVar = field(default_factory=BoundVar)
    var_last: BoundVar = field(default_factory=BoundVar)
    var_player_team: BoundVar = field(default_factory=BoundVar)
    player_detail_fields: dict[str, BoundVar] = field(default_factory=lambda: {
        "Position": BoundVar("--"),
        "Number": BoundVar("--"),
        "Height": BoundVar("--"),
        "Weight": BoundVar("--"),
        "Face ID": BoundVar("--"),
        "Unique ID": BoundVar("--"),
    })
    player_detail_widgets: dict[str, int | str] = field(default_factory=dict)
    player_list_container: int | str | None = None
    player_listbox_tag: int | str | None = None
    player_team_listbox: int | str | None = None
    team_combo_tag: int | str | None = None
    dataset_combo_tag: int | str | None = None
    btn_save: int | str | None = None
    btn_edit: int | str | None = None
    btn_copy: int | str | None = None
    btn_player_export: int | str | None = None
    btn_player_import: int | str | None = None
    copy_dialog_tag: int | str | None = None


@dataclass
class TeamUIState:
    team_var: BoundVar = field(default_factory=BoundVar)
    team_edit_var: BoundVar = field(default_factory=BoundVar)
    team_name_var: BoundVar = field(default_factory=BoundVar)
    team_field_vars: dict[str, BoundVar] = field(default_factory=dict)
    team_field_input_tags: dict[str, int | str] = field(default_factory=dict)
    team_count_var: BoundVar = field(default_factory=lambda: BoundVar("Teams: 0"))
    team_search_var: BoundVar = field(default_factory=BoundVar)
    team_scan_status_var: BoundVar = field(default_factory=BoundVar)
    team_list_container: int | str | None = None
    team_list_items: list[str] = field(default_factory=list)
    team_listbox_tag: int | str | None = None
    btn_team_save: int | str | None = None
    btn_team_full: int | str | None = None
    all_team_names: list[str] = field(default_factory=list)
    filtered_team_names: list[str] = field(default_factory=list)


@dataclass
class StaffUIState:
    staff_entries: list[tuple[int, str]] = field(default_factory=list)
    _filtered_staff_entries: list[tuple[int, str]] = field(default_factory=list)
    selected_staff_index: int | None = None
    staff_search_var: BoundVar = field(default_factory=BoundVar)
    staff_status_var: BoundVar = field(default_factory=BoundVar)
    staff_count_var: BoundVar = field(default_factory=lambda: BoundVar("Staff: 0"))
    staff_list_container: int | str | None = None
    staff_list_items: list[str] = field(default_factory=list)
    staff_listbox_tag: int | str | None = None
    btn_staff_full: int | str | None = None


@dataclass
class StadiumUIState:
    stadium_entries: list[tuple[int, str]] = field(default_factory=list)
    _filtered_stadium_entries: list[tuple[int, str]] = field(default_factory=list)
    selected_stadium_index: int | None = None
    stadium_search_var: BoundVar = field(default_factory=BoundVar)
    stadium_status_var: BoundVar = field(default_factory=BoundVar)
    stadium_count_var: BoundVar = field(default_factory=lambda: BoundVar("Stadiums: 0"))
    stadium_list_container: int | str | None = None
    stadium_list_items: list[str] = field(default_factory=list)
    stadium_listbox_tag: int | str | None = None
    btn_stadium_full: int | str | None = None


@dataclass
class LeagueUIState:
    league_page_super_types: dict[str, str] = field(default_factory=lambda: {
        "nba_history": "NBA History",
        "nba_records": "NBA Records",
    })
    league_states: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.league_states:
            return
        for page_key in self.league_page_super_types:
            self.league_states[page_key] = {
                "categories": [],
                "category_map": {},
                "selected_category": None,
                "records": [],
                "status_var": BoundVar(""),
                "count_var": BoundVar("Records: 0"),
                "category_combo_tag": None,
                "table_container": None,
                "table_tag": None,
                "status_text_tag": None,
                "count_text_tag": None,
            }


@dataclass
class TradeUIState:
    trade_team_options: list[str] = field(default_factory=list)
    trade_team_lookup: dict[str, int] = field(default_factory=dict)
    trade_participants: list[str] = field(default_factory=list)
    trade_active_team_var: BoundVar = field(default_factory=BoundVar)
    trade_roster_active: list[Player] = field(default_factory=list)
    trade_state: TradeState = field(default_factory=lambda: TradeState(slot_count=36))
    trade_selected_slot: int = 0
    trade_selected_player_obj: Player | None = None
    trade_contract_meta: dict[str, dict[str, object]] | None = None
    trade_status_var: BoundVar = field(default_factory=BoundVar)
    trade_active_team_combo_tag: int | str | None = None
    trade_add_team_combo_tag: int | str | None = None
    trade_participants_list_tag: int | str | None = None
    trade_roster_list_tag: int | str | None = None
    trade_outgoing_container: int | str | None = None
    trade_incoming_container: int | str | None = None
    trade_slot_combo_tag: int | str | None = None
    trade_status_text_tag: int | str | None = None


@dataclass
class ExcelUIState:
    excel_status_var: BoundVar = field(default_factory=BoundVar)
    excel_progress_var: BoundDoubleVar = field(default_factory=lambda: BoundDoubleVar(0))
    excel_progress_bar_tag: int | str | None = None
    excel_status_text_tag: int | str | None = None
    _excel_export_queue: queue.Queue | None = None
    _excel_export_thread: threading.Thread | None = None
    _excel_export_polling: bool = False
    _excel_export_entity_label: str = ""


def _state_bag_attr_map() -> dict[str, str]:
    mappings: dict[str, str] = {}
    for bag_attr, bag_type in (
        ("player_ui", PlayerUIState),
        ("team_ui", TeamUIState),
        ("staff_ui", StaffUIState),
        ("stadium_ui", StadiumUIState),
        ("league_ui", LeagueUIState),
        ("trade_ui", TradeUIState),
        ("excel_ui", ExcelUIState),
    ):
        for bag_field in dataclass_fields(bag_type):
            mappings[bag_field.name] = bag_attr
    return mappings


class PlayerEditorApp(UIHostMixin):
    """Dear PyGui implementation of the editor shell."""

    _STATE_BAG_ATTRS: dict[str, str] = _state_bag_attr_map()

    def __getattr__(self, name: str) -> Any:
        bag_name = self._STATE_BAG_ATTRS.get(name)
        if not bag_name:
            raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")
        return getattr(object.__getattribute__(self, bag_name), name)

    def __setattr__(self, name: str, value: Any) -> None:
        bag_name = type(self)._STATE_BAG_ATTRS.get(name)
        if bag_name and bag_name in self.__dict__:
            setattr(self.__dict__[bag_name], name, value)
            return
        object.__setattr__(self, name, value)

    def __init__(self, model: PlayerDataModel):
        self.model: PlayerDataModel = model
        # Navigation + layout
        self.screen_tags: dict[str, int | str] = {}
        self.content_root: int | str | None = None
        self.sidebar_tag: int | str | None = None
        # Status + offsets
        self.status_var = BoundVar("")
        self.status_text_tag: int | str | None = None
        self.offset_load_status = BoundVar("Using packaged offsets.")
        self.offset_status_text_tag: int | str | None = None
        self.hook_target_var = BoundVar(self.model.mem.module_name or MODULE_NAME)
        # Extension loader
        self.extension_vars: dict[str, BoundBoolVar] = {}
        self.loaded_extensions: set[str] = set()
        self.extension_status_var = BoundVar("")
        # Grouped screen-local state
        self.player_ui = PlayerUIState()
        team_field_defs = getattr(self.model, "team_field_defs", TEAM_FIELD_DEFS)
        self.team_ui = TeamUIState(
            team_field_vars={label: BoundVar("") for label in team_field_defs.keys()},
        )
        self.staff_ui = StaffUIState()
        self.stadium_ui = StadiumUIState()
        self.league_ui = LeagueUIState()
        self.trade_ui = TradeUIState()
        self.excel_ui = ExcelUIState()
        # Flags
        self.scanning = False
        self._pending_team_select: str | None = None
        # Misc
        self._screen_registry: dict[str, ScreenRegistration] = {
            "players": ScreenRegistration(
                key="players",
                builder=lambda app: build_players_screen(app),
                post_show="_post_show_players",
            ),
            "teams": ScreenRegistration(
                key="teams",
                builder=lambda app: build_teams_screen(app),
                post_show="_post_show_teams",
            ),
            "nba_history": ScreenRegistration(
                key="nba_history",
                builder=lambda app: build_nba_history_screen(app),
                post_show="_post_show_nba_history",
            ),
            "nba_records": ScreenRegistration(
                key="nba_records",
                builder=lambda app: build_nba_records_screen(app),
                post_show="_post_show_nba_records",
            ),
            "staff": ScreenRegistration(
                key="staff",
                builder=lambda app: build_staff_screen(app),
                post_show="_post_show_staff",
            ),
            "stadium": ScreenRegistration(
                key="stadium",
                builder=lambda app: build_stadium_screen(app),
                post_show="_post_show_stadium",
            ),
            "excel": ScreenRegistration(key="excel", builder=lambda app: build_excel_screen(app)),
            "trade": ScreenRegistration(
                key="trade",
                builder=lambda app: build_trade_players_screen(app),
                post_show="_post_show_trade_players",
            ),
        }

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------
    def destroy(self) -> None:
        try:
            dpg.destroy_context()
        except Exception:
            pass

    def _ensure_screen_built(self, key: str) -> None:
        registration = self._screen_registry.get(key)
        if registration is not None:
            ensure_screen_built(self, registration)

    def _post_show_players(self) -> None:
        self._ensure_roster_loaded(apply_pending_team_select=False)

    def _post_show_teams(self) -> None:
        self._ensure_roster_loaded(apply_pending_team_select=True)

    def _post_show_nba_history(self) -> None:
        self._refresh_league_records("nba_history")

    def _post_show_nba_records(self) -> None:
        self._refresh_league_records("nba_records")

    def _post_show_trade_players(self) -> None:
        self._refresh_trade_data()

    def _post_show_staff(self) -> None:
        self._refresh_staff_list()

    def _post_show_stadium(self) -> None:
        self._refresh_stadium_list()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _open_file_dialog(
        self,
        title: str,
        *,
        default_path: str | None = None,
        default_filename: str | None = None,
        file_types: list[tuple[str, str]] | None = None,
        callback: Callable[[str], None] | None = None,
        save: bool = False,
    ) -> None:
        open_file_dialog(
            title,
            default_path=default_path,
            default_filename=default_filename,
            file_types=file_types,
            callback=callback,
            save=save,
        )


_CONTROLLER_METHOD_BINDINGS: tuple[tuple[str, Callable[..., Any]], ...] = (
    ("_render_player_list", players_controller.render_player_list),
    ("_start_scan", players_controller.start_scan),
    ("_scan_thread", players_controller.scan_thread),
    ("_start_roster_scan", players_controller.start_roster_scan),
    ("_run_roster_scan", players_controller.run_roster_scan),
    ("_refresh_player_list", players_controller.refresh_player_list),
    ("_filter_player_list", players_controller.filter_player_list),
    ("_on_team_selected", players_controller.on_team_selected),
    ("_on_player_selected", players_controller.on_player_selected),
    ("_update_detail_fields", players_controller.update_detail_fields),
    ("_save_player", players_controller.save_player),
    ("_open_full_editor", players_controller.open_full_editor),
    ("_open_copy_dialog", players_controller.open_copy_dialog),
    ("_export_selected_player", players_controller.export_selected_player),
    ("_import_selected_player", players_controller.import_selected_player),
    ("get_player_list_items", players_controller.get_player_list_items),
    ("get_selected_player_indices", players_controller.get_selected_player_indices),
    ("set_selected_player_indices", players_controller.set_selected_player_indices),
    ("clear_player_selection", players_controller.clear_player_selection),
    ("_roster_needs_refresh", players_controller.roster_needs_refresh),
    ("_ensure_roster_loaded", players_controller.ensure_roster_loaded),
    ("_update_team_dropdown", players_controller.update_team_dropdown),
    ("_ensure_team_listbox", teams_controller.ensure_team_listbox),
    ("_start_team_scan", teams_controller.start_team_scan),
    ("_scan_teams_thread", teams_controller.scan_teams_thread),
    ("_filter_team_list", teams_controller.filter_team_list),
    ("_on_team_listbox_select", teams_controller.on_team_listbox_select),
    ("_on_team_edit_selected", teams_controller.on_team_edit_selected),
    ("_on_team_field_changed", teams_controller.on_team_field_changed),
    ("_save_team", teams_controller.save_team),
    ("_open_full_team_editor", teams_controller.open_full_team_editor),
    ("_league_state", league_controller.state_for),
    ("_filter_league_page_categories", league_controller.filter_page_categories),
    ("_register_league_widgets", league_controller.register_widgets),
    ("_on_league_category_selected", league_controller.on_category_selected),
    ("_ensure_league_categories", league_controller.ensure_categories),
    ("_update_league_status", league_controller.update_status),
    ("_clear_league_table", league_controller.clear_table),
    ("_render_league_table", league_controller.render_table),
    ("_refresh_league_records", league_controller.refresh_records),
    ("_current_staff_index", staff_controller.current_staff_index),
    ("_refresh_staff_list", staff_controller.refresh_staff_list),
    ("_filter_staff_list", staff_controller.filter_staff_list),
    ("_on_staff_selected", staff_controller.on_staff_selected),
    ("_open_full_staff_editor", staff_controller.open_full_staff_editor),
    ("get_staff_list_items", staff_controller.get_staff_list_items),
    ("get_selected_staff_indices", staff_controller.get_selected_staff_indices),
    ("set_staff_selection", staff_controller.set_staff_selection),
    ("_current_stadium_index", stadium_controller.current_stadium_index),
    ("_refresh_stadium_list", stadium_controller.refresh_stadium_list),
    ("_filter_stadium_list", stadium_controller.filter_stadium_list),
    ("_on_stadium_selected", stadium_controller.on_stadium_selected),
    ("_open_full_stadium_editor", stadium_controller.open_full_stadium_editor),
    ("get_stadium_list_items", stadium_controller.get_stadium_list_items),
    ("get_selected_stadium_indices", stadium_controller.get_selected_stadium_indices),
    ("set_stadium_selection", stadium_controller.set_stadium_selection),
    ("_set_excel_status", import_export_controller.set_excel_status),
    ("_reset_excel_progress", import_export_controller.reset_excel_progress),
    ("_apply_excel_progress", import_export_controller.apply_excel_progress),
    ("_excel_progress_callback", import_export_controller.excel_progress_callback),
    ("_queue_excel_export_progress", import_export_controller.queue_excel_export_progress),
    ("_poll_excel_export", import_export_controller.poll_excel_export),
    ("_finish_excel_export", import_export_controller.finish_excel_export),
    ("_import_excel", import_export_controller.import_excel),
    ("_export_excel", import_export_controller.export_excel),
    ("_refresh_trade_data", trade_controller.refresh_data),
    ("_trade_refresh_team_options", trade_controller.refresh_team_options),
    ("_trade_get_roster", trade_controller.get_roster),
    ("_trade_load_contracts", trade_controller.load_contracts),
    ("_trade_player_label", trade_controller.player_label),
    ("_trade_y1_salary", trade_controller.y1_salary),
    ("_trade_refresh_rosters", trade_controller.refresh_rosters),
    ("_trade_set_active_team", trade_controller.set_active_team),
    ("_trade_set_active_team_from_list", trade_controller.set_active_team_from_list),
    ("_trade_add_participant", trade_controller.add_participant),
    ("_trade_select_active_player", trade_controller.select_active_player),
    ("_trade_open_player_modal", trade_controller.open_player_modal),
    ("_trade_add_transaction", trade_controller.add_transaction),
    ("_trade_clear", trade_controller.clear),
    ("_trade_update_status", trade_controller.update_status),
    ("_trade_select_slot", trade_controller.select_slot),
    ("_trade_clear_slot", trade_controller.clear_slot),
    ("_trade_propose", trade_controller.propose),
    ("_trade_render_team_lists", trade_controller.render_team_lists),
)

for _method_name, _handler in _CONTROLLER_METHOD_BINDINGS:
    setattr(PlayerEditorApp, _method_name, _bind_controller_method(_handler))

PlayerEditorApp._on_team_listbox_select = _bind_dpg_team_listbox_select(teams_controller.on_team_listbox_select)
PlayerEditorApp._on_player_selected = _bind_dpg_player_selected(players_controller.on_player_selected)

for _method_name, _handler in (
    ("build_ui", shell_build_ui),
    ("copy_to_clipboard", staticmethod(shell_copy_to_clipboard)),
    ("_open_randomizer", launcher_open_randomizer),
    ("_open_team_shuffle", launcher_open_team_shuffle),
    ("_open_batch_edit", launcher_open_batch_edit),
):
    setattr(
        PlayerEditorApp,
        _method_name,
        _handler if isinstance(_handler, staticmethod) else _bind_passthrough_method(_method_name, _handler),
    )

PlayerEditorApp._is_nba_records_category = staticmethod(league_controller.is_nba_records_category)
__all__ = [
    "BoundBoolVar",
    "BoundDoubleVar",
    "BoundVar",
    "PlayerEditorApp",
    "build_home_screen",
    "build_players_screen",
    "build_teams_screen",
    "build_nba_history_screen",
    "build_nba_records_screen",
    "build_staff_screen",
    "build_stadium_screen",
    "build_excel_screen",
    "build_trade_players_screen",
]
