"""Team shuffle modal for Dear PyGui."""
from __future__ import annotations

import random

import dearpygui.dearpygui as dpg

from ..core.offsets import OFF_TEAM_PTR, PLAYER_STRIDE, TEAM_RECORD_SIZE
from ..models.data_model import FREE_AGENT_TEAM_ID, PlayerDataModel


class TeamShuffleWindow:
    """Shuffle players across selected teams while preserving roster sizes."""

    MAX_ROSTER_SIZE = 15

    def __init__(self, app, model: PlayerDataModel) -> None:
        self.app = app
        self.model = model
        self.window_tag: int | str = dpg.generate_uuid()
        self.team_tags: dict[str, int | str] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        with dpg.window(
            label="Team Shuffle",
            tag=self.window_tag,
            modal=True,
            no_collapse=True,
            width=700,
            height=520,
        ):
            dpg.add_text("Select teams to shuffle players among them.")
            dpg.add_spacer(height=6)
            with dpg.child_window(height=320, border=True):
                for team in self._team_names():
                    tag = dpg.add_checkbox(label=team, default_value=False)
                    self.team_tags[team] = tag
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Shuffle Selected", width=170, callback=lambda: self._shuffle_selected())
                dpg.add_button(label="Close", width=90, callback=lambda: dpg.delete_item(self.window_tag))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _shuffle_selected(self) -> None:
        selected = [team for team, tag in self.team_tags.items() if dpg.does_item_exist(tag) and dpg.get_value(tag)]
        if not selected:
            self.app.show_warning("Shuffle Teams", "Select one or more teams first.")
            return
        players_to_pool = []
        for team in selected:
            try:
                players = self.model.get_players_by_team(team)
            except Exception:
                players = []
            if players:
                players_to_pool.extend(players)
        if not players_to_pool:
            self.app.show_warning("Shuffle Teams", "No players found for the selected teams.")
            return
        name_to_idx = {name: idx for idx, name in self.model.team_list}
        free_agent_idx = name_to_idx.get("Free Agents", FREE_AGENT_TEAM_ID)
        live_mode = (
            not self.model.external_loaded
            and self.model.mem.hproc is not None
            and self.model.mem.base_addr is not None
        )
        total_assigned = 0
        if live_mode:
            team_base = self.model._resolve_team_base_ptr()
            player_base = self.model._resolve_player_table_base()
            if team_base is None or player_base is None:
                self.app.show_error("Shuffle Teams", "Failed to resolve team or player table pointers.")
                return
            free_ptr = None
            for idx, name in self.model.team_list:
                if name and "free" in name.lower():
                    free_ptr = team_base + idx * TEAM_RECORD_SIZE
                    break
            if free_ptr is None:
                self.app.show_error("Shuffle Teams", "Free Agents team could not be located.")
                return
            team_ptrs: dict[str, int] = {}
            for idx, name in self.model.team_list:
                if name in selected:
                    team_ptrs[name] = team_base + idx * TEAM_RECORD_SIZE
            for player in players_to_pool:
                try:
                    p_addr = player_base + player.index * PLAYER_STRIDE
                    self.model.mem.write_pointer(p_addr + OFF_TEAM_PTR, free_ptr)
                    player.team = "Free Agents"
                    player.team_id = free_agent_idx
                except Exception:
                    pass
            random.shuffle(players_to_pool)
            pos = 0
            for team in selected:
                ptr = team_ptrs.get(team)
                if ptr is None:
                    continue
                for _ in range(self.MAX_ROSTER_SIZE):
                    if pos >= len(players_to_pool):
                        break
                    player = players_to_pool[pos]
                    pos += 1
                    try:
                        p_addr = player_base + player.index * PLAYER_STRIDE
                        self.model.mem.write_pointer(p_addr + OFF_TEAM_PTR, ptr)
                        player.team = team
                        player.team_id = name_to_idx.get(team, player.team_id)
                        total_assigned += 1
                    except Exception:
                        pass
            try:
                self.model.refresh_players()
            except Exception:
                pass
        else:
            for p in players_to_pool:
                p.team = "Free Agents"
                p.team_id = free_agent_idx
            random.shuffle(players_to_pool)
            pos = 0
            for team in selected:
                for _ in range(self.MAX_ROSTER_SIZE):
                    if pos >= len(players_to_pool):
                        break
                    player = players_to_pool[pos]
                    pos += 1
                    player.team = team
                    player.team_id = name_to_idx.get(team, player.team_id)
                    total_assigned += 1
            self.model._build_name_index_map()
        self.app.show_message("Shuffle Teams", f"Shuffle complete. {total_assigned} players reassigned. Remaining players are Free Agents.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _team_names(self) -> list[str]:
        try:
            names = self.model.get_teams()
        except Exception:
            names = []
        if names:
            return list(names)
        try:
            return [name for _, name in self.model.team_list]
        except Exception:
            return []


def open_team_shuffle(app) -> TeamShuffleWindow:
    """Convenience helper to open the team shuffle modal."""
    return TeamShuffleWindow(app, app.model)


__all__ = ["TeamShuffleWindow", "open_team_shuffle"]
