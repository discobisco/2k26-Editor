"""Team shuffle window (ported from the monolithic editor)."""
from __future__ import annotations

import random
import struct
import tkinter as tk

from ..core.conversions import to_int
from ..core.offsets import OFF_TEAM_PTR, PLAYER_STRIDE, TEAM_RECORD_SIZE
from ..models.data_model import FREE_AGENT_TEAM_ID, PlayerDataModel
from ..models.player import Player
from .widgets import bind_mousewheel


class TeamShuffleWindow(tk.Toplevel):
    """
    Shuffle players across selected teams while preserving roster sizes.

    When live memory pointers are available, writes go directly to the game
    process; otherwise, the cached player objects are updated.
    """

    MAX_ROSTER_SIZE = 15

    def __init__(self, parent: tk.Tk, model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Team Shuffle")
        self.model = model
        self.team_vars: dict[str, tk.BooleanVar] = {}
        self.configure(bg="#F5F5F5")
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        """Construct the UI for selecting teams and initiating the shuffle."""
        tk.Label(self, text="Select teams to shuffle players among them:", bg="#F5F5F5", font=("Segoe UI", 11)).pack(
            pady=(10, 5)
        )
        frame = tk.Frame(self, bg="#F5F5F5")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(frame, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        bind_mousewheel(scroll_frame, canvas)
        try:
            team_names = self.model.get_teams()
        except Exception:
            team_names = []
        if not team_names:
            team_names = [name for _, name in self.model.team_list]
        for idx, team_name in enumerate(team_names):
            var = tk.BooleanVar(value=False)
            self.team_vars[team_name] = var
            tk.Checkbutton(scroll_frame, text=team_name, variable=var, bg="#F5F5F5").grid(row=idx, column=0, sticky=tk.W, padx=10, pady=2)
        tk.Button(self, text="Shuffle Selected", command=self._shuffle_selected, bg="#52796F", fg="white", relief=tk.FLAT).pack(pady=(0, 10))
        tk.Button(self, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(pady=(0, 10))

    def _shuffle_selected(self) -> None:
        """Shuffle players across the selected teams."""
        import tkinter.messagebox as mb

        selected = [team for team, var in self.team_vars.items() if var.get()]
        if not selected:
            mb.showinfo("Shuffle Teams", "No teams selected.")
            return
        players_to_pool: list[Player] = []
        for team in selected:
            plist = self.model.get_players_by_team(team)
            if plist:
                players_to_pool.extend(plist)
        if not players_to_pool:
            mb.showinfo("Shuffle Teams", "No players to shuffle.")
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
                mb.showerror("Shuffle Teams", "Failed to resolve team or player table pointers.")
                return
            free_ptr = None
            for idx, name in self.model.team_list:
                if name and "free" in name.lower():
                    free_ptr = team_base + idx * TEAM_RECORD_SIZE
                    break
            if free_ptr is None:
                mb.showerror("Shuffle Teams", "Free Agents team could not be located.")
                return
            team_ptrs: dict[str, int] = {}
            for idx, name in self.model.team_list:
                if name in selected:
                    team_ptrs[name] = team_base + idx * TEAM_RECORD_SIZE
            for p in players_to_pool:
                try:
                    p_addr = player_base + p.index * PLAYER_STRIDE
                    self.model.mem.write_bytes(p_addr + OFF_TEAM_PTR, struct.pack("<Q", free_ptr))
                    p.team = "Free Agents"
                    p.team_id = free_agent_idx
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
                        self.model.mem.write_bytes(p_addr + OFF_TEAM_PTR, struct.pack("<Q", ptr))
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
                    p = players_to_pool[pos]
                    pos += 1
                    p.team = team
                    p.team_id = name_to_idx.get(team, p.team_id)
                    total_assigned += 1
            self.model._build_name_index_map()
        mb.showinfo("Shuffle Teams", f"Shuffle complete. {total_assigned} players reassigned. Remaining players are Free Agents.")


__all__ = ["TeamShuffleWindow"]
