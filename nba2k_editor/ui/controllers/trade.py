"""Trade controller helpers."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

from ...models.player import Player
from .entity_edit import coerce_int


def format_trade_summary(slot_number: int, transaction_count: int) -> str:
    return f"Trade staged (Slot {slot_number}): {transaction_count} moves (write hooks not yet implemented)."


def refresh_data(app) -> None:
    """Refresh team options, rosters, and staged packages for the trade screen."""
    refresh_team_options(app)
    refresh_rosters(app)
    render_team_lists(app)
    update_status(app, "")
    if app.trade_slot_combo_tag and dpg.does_item_exist(app.trade_slot_combo_tag):
        dpg.configure_item(app.trade_slot_combo_tag, items=[f"Slot {i + 1}" for i in range(36)])
        dpg.set_value(app.trade_slot_combo_tag, f"Slot {app.trade_selected_slot + 1}")
    if app.trade_participants_list_tag and dpg.does_item_exist(app.trade_participants_list_tag):
        dpg.configure_item(app.trade_participants_list_tag, items=app.trade_participants)
    if app.trade_active_team_combo_tag and dpg.does_item_exist(app.trade_active_team_combo_tag):
        dpg.configure_item(app.trade_active_team_combo_tag, items=app.trade_participants)
        if app.trade_active_team_var.get():
            dpg.set_value(app.trade_active_team_combo_tag, app.trade_active_team_var.get())


def refresh_team_options(app) -> None:
    """Populate global team list and ensure participants list is initialized."""
    try:
        if _roster_needs_refresh(app):
            app.model.refresh_players()
    except Exception:
        pass
    sorted_teams = sorted(
        app.model.team_list,
        key=lambda pair: pair[0] if isinstance(pair, tuple) and pair and pair[0] is not None else 10**9,
    )
    app.trade_team_options = [name for tid, name in sorted_teams]
    app.trade_team_lookup = {name: tid for tid, name in sorted_teams}
    if not app.trade_participants and app.trade_team_options:
        app.trade_participants.append(app.trade_team_options[0])
        if len(app.trade_team_options) > 1:
            app.trade_participants.append(app.trade_team_options[1])
        app.trade_active_team_var.set(app.trade_participants[0])
    app.trade_state.select_slot(app.trade_selected_slot)
    _sync_dropdowns(app)
    render_team_lists(app)


def get_roster(app, team_name: str | None) -> list[Player]:
    if not team_name:
        return []
    players = getattr(app.model, "players", []) or []
    if _roster_needs_refresh(app):
        try:
            app.model.refresh_players()
            players = getattr(app.model, "players", [])
        except Exception:
            return []
    team_id = app.trade_team_lookup.get(team_name)
    roster: list[Player] = []
    for player in players:
        if team_id is not None and player.team_id == team_id:
            roster.append(player)
        elif team_id is None and player.team == team_name:
            roster.append(player)
    load_contracts(app, roster)
    return roster


def load_contracts(app, players: list[Player]) -> None:
    """Attach contract info to players if contract offsets are available."""
    if app.trade_contract_meta is None:
        contract_fields = app.model.categories.get("Contract", []) or []
        meta_map: dict[str, dict[str, object]] = {}
        for field in contract_fields:
            name = field.get("name") or field.get("display_name") or field.get("normalized_name")
            if not name:
                continue
            meta_map[str(name)] = field
        app.trade_contract_meta = meta_map
    meta_map = app.trade_contract_meta or {}
    salary_fields = [f"Year {i}" for i in range(1, 7)]
    extra_fields = [
        "Years Left",
        "Original Contract Length",
        "Extension Length",
        "Option",
        "Extension Option",
        "Free Agency Type",
        "Type",
        "Two-Way NBA Days Left",
    ]
    for player in players:
        contract: dict[str, object] = {}
        record_ptr = getattr(player, "record_ptr", None)
        salaries: list[object] = []
        for label in salary_fields:
            meta = meta_map.get(label)
            if not meta:
                continue
            try:
                value = app.model.decode_field_value(
                    entity_type="player",
                    entity_index=player.index,
                    category="Contract",
                    field_name=label,
                    meta=meta,
                    record_ptr=record_ptr,
                )
            except Exception:
                value = None
            if value is not None:
                salaries.append(value)
        if salaries:
            contract["salaries"] = salaries
        for label in extra_fields:
            meta = meta_map.get(label)
            if not meta:
                continue
            try:
                value = app.model.decode_field_value(
                    entity_type="player",
                    entity_index=player.index,
                    category="Contract",
                    field_name=label,
                    meta=meta,
                    record_ptr=record_ptr,
                )
            except Exception:
                value = None
            if value is not None:
                contract[label] = value
        setattr(player, "contract_info", contract)


def player_label(app, player: Player) -> str:
    contract = getattr(player, "contract_info", {}) or {}
    salaries = contract.get("salaries") or []
    salary_str = ""
    if isinstance(salaries, (list, tuple)) and salaries:
        salary_str = f" | Y1 {salaries[0]}"
    return f"{player.index}: {player.full_name}{salary_str}"


def y1_salary(player: Player) -> int:
    contract = getattr(player, "contract_info", {}) or {}
    salaries = contract.get("salaries") or []
    if isinstance(salaries, (list, tuple)) and salaries:
        try:
            return int(salaries[0])
        except Exception:
            return 0
    return 0


def refresh_rosters(app) -> None:
    """Load roster for the active team and update list widget."""
    app.trade_roster_active = get_roster(app, app.trade_active_team_var.get())
    if app.trade_roster_list_tag and dpg.does_item_exist(app.trade_roster_list_tag):
        dpg.configure_item(
            app.trade_roster_list_tag,
            items=[player_label(app, player) for player in app.trade_roster_active],
        )


def set_active_team(app, _sender, value) -> None:
    app.trade_active_team_var.set(value or "")
    app.trade_selected_player_obj = None
    refresh_rosters(app)


def set_active_team_from_list(app, _sender, value) -> None:
    set_active_team(app, _sender, value)
    if app.trade_active_team_combo_tag and dpg.does_item_exist(app.trade_active_team_combo_tag):
        try:
            dpg.set_value(app.trade_active_team_combo_tag, value)
        except Exception:
            pass


def add_participant(app, team_name: str | None) -> None:
    if not team_name:
        return
    if team_name not in app.trade_participants and len(app.trade_participants) < 36:
        app.trade_participants.append(team_name)
        app.trade_state.select_slot(app.trade_selected_slot)
        _sync_dropdowns(app)
        if not app.trade_active_team_var.get():
            app.trade_active_team_var.set(team_name)
        refresh_rosters(app)
        render_team_lists(app)
    _sync_add_team_dropdown(app)


def select_active_player(app, _sender, value) -> None:
    app.trade_selected_player_obj = None
    if not value:
        return
    label = str(value)
    try:
        idx = int(label.split(":", 1)[0].strip())
    except Exception:
        return
    for player in app.trade_roster_active:
        if player.index == idx:
            app.trade_selected_player_obj = player
            break


def open_player_modal(app) -> None:
    """Open modal to select players and direction for the active team."""
    team = app.trade_active_team_var.get()
    if not team:
        update_status(app, "Select a team first.")
        return
    roster = app.trade_roster_active or []
    if not roster:
        update_status(app, "No roster loaded for selected team.")
        return
    modal = dpg.generate_uuid()
    player_list = dpg.generate_uuid()
    direction_radio = dpg.generate_uuid()
    dest_combo = dpg.generate_uuid()
    roster_labels = [player_label(app, player) for player in roster]

    def _confirm(_s, _a):
        selection = dpg.get_value(player_list)
        direction = dpg.get_value(direction_radio)
        dest = dpg.get_value(dest_combo)
        idx = None
        if isinstance(selection, int):
            idx = selection
        elif isinstance(selection, str):
            try:
                idx = roster_labels.index(selection)
            except ValueError:
                idx = None
        if idx is None or idx < 0 or idx >= len(roster):
            update_status(app, "Select a player.")
            return
        if not dest:
            update_status(app, "Select a destination team.")
            return
        player = roster[idx]
        if direction == "send":
            add_transaction(app, player, team, dest, outgoing=True)
        else:
            add_transaction(app, player, dest, team, outgoing=False)
        dpg.delete_item(modal)

    with dpg.window(modal=True, popup=True, tag=modal, width=360, height=360, label=f"Trade Players - {team}"):
        dpg.add_text(f"Players on {team}")
        dpg.add_listbox(tag=player_list, items=roster_labels, num_items=10)
        dpg.add_text("Direction")
        dpg.add_radio_button(items=["send", "receive"], default_value="send", tag=direction_radio, horizontal=True)
        dpg.add_text("Other team")
        choices = [name for name in app.trade_participants if name != team]
        dpg.add_combo(items=choices, default_value=choices[0] if choices else "", tag=dest_combo)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Confirm", width=100, callback=_confirm)
            dpg.add_button(label="Cancel", width=100, callback=lambda *_: dpg.delete_item(modal))


def add_transaction(app, player: Player, from_team: str | None, to_team: str | None, outgoing: bool) -> None:
    if not from_team or not to_team or from_team == to_team:
        update_status(app, "Pick distinct source and destination teams.")
        return
    source = from_team if outgoing else to_team
    dest = to_team if outgoing else from_team
    if not app.trade_state.add_transaction(player, source, dest):
        update_status(app, "Transaction already exists in this slot.")
        return
    render_team_lists(app)
    update_status(app, f"Staged {player.full_name} ({from_team} ↔ {to_team}) in Slot {app.trade_selected_slot + 1}")


def clear(app) -> None:
    app.trade_state.clear_slot(app.trade_selected_slot)
    render_team_lists(app)
    update_status(app, "")


def update_status(app, text: str) -> None:
    app.trade_status_var.set(text)
    if app.trade_status_text_tag and dpg.does_item_exist(app.trade_status_text_tag):
        dpg.set_value(app.trade_status_text_tag, text)


def select_slot(app, value) -> None:
    """Switch the active trade package slot (1-36)."""
    idx = coerce_int(str(value).replace("Slot", "").strip(), 1) - 1
    idx = max(0, min(35, idx))
    app.trade_selected_slot = idx
    app.trade_state.select_slot(idx)
    render_team_lists(app)
    update_status(app, f"Switched to Slot {idx + 1}")


def clear_slot(app) -> None:
    """Clear only the current slot packages."""
    app.trade_state.clear_slot(app.trade_selected_slot)
    render_team_lists(app)
    update_status(app, f"Cleared Slot {app.trade_selected_slot + 1}")


def propose(app) -> None:
    slot = app.trade_state.current_slot()
    if not slot.transactions:
        update_status(app, "Add players to the package before proposing a trade.")
        return
    summary = format_trade_summary(app.trade_selected_slot + 1, len(slot.transactions))
    update_status(app, summary)


def render_team_lists(app) -> None:
    """Render outgoing/incoming lists per team for the current slot."""
    if hasattr(app, "render_calls"):
        try:
            app.render_calls += 1
        except Exception:
            pass
    trade_state = getattr(app, "trade_state", None)
    if trade_state is None:
        return
    slot = trade_state.current_slot()
    packages = slot.packages(app.trade_participants)
    if not (app.trade_outgoing_container and app.trade_incoming_container):
        return
    for container in (app.trade_outgoing_container, app.trade_incoming_container):
        try:
            for child in list(dpg.get_item_children(container, 1) or []):
                dpg.delete_item(child)
        except Exception:
            pass
    for team in app.trade_participants:
        pkg = packages.get(team)
        outgoing = list(pkg.outgoing) if pkg else []
        incoming = list(pkg.incoming) if pkg else []
        out_salary = sum(y1_salary(player) for player in outgoing)
        in_salary = sum(y1_salary(player) for player in incoming)
        with dpg.group(parent=app.trade_outgoing_container):
            dpg.add_text(f"{team} (outgoing) — Y1 total: {out_salary:,}")
            dpg.add_listbox(items=[player_label(app, player) for player in outgoing] or ["(none)"], num_items=4, width=320)
            dpg.add_spacer(height=4)
        with dpg.group(parent=app.trade_incoming_container):
            dpg.add_text(f"{team} (incoming) — Y1 total: {in_salary:,}")
            dpg.add_listbox(items=[player_label(app, player) for player in incoming] or ["(none)"], num_items=4, width=320)
            dpg.add_spacer(height=4)


def _sync_dropdowns(app) -> None:
    _sync_add_team_dropdown(app)
    if app.trade_participants_list_tag and dpg.does_item_exist(app.trade_participants_list_tag):
        dpg.configure_item(app.trade_participants_list_tag, items=app.trade_participants)
    if app.trade_active_team_combo_tag and dpg.does_item_exist(app.trade_active_team_combo_tag):
        dpg.configure_item(app.trade_active_team_combo_tag, items=app.trade_participants)
        if app.trade_active_team_var.get():
            dpg.set_value(app.trade_active_team_combo_tag, app.trade_active_team_var.get())


def _roster_needs_refresh(app) -> bool:
    checker = getattr(app, "_roster_needs_refresh", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return not getattr(app.model, "team_list", None) or not getattr(app.model, "players", None)


def _sync_add_team_dropdown(app) -> None:
    if app.trade_add_team_combo_tag and dpg.does_item_exist(app.trade_add_team_combo_tag):
        remaining = [name for name in app.trade_team_options if name not in app.trade_participants]
        dpg.configure_item(app.trade_add_team_combo_tag, items=remaining)
