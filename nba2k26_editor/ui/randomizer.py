"""Randomizer window (ported from the monolithic editor)."""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk

from ..core.conversions import to_int
from ..models.data_model import PlayerDataModel
from .widgets import bind_mousewheel


class RandomizerWindow(tk.Toplevel):
    """
    Randomize player attributes/tendencies/durability for selected teams.

    Provides per-field min/max controls and applies randomized values to all
    players on the checked teams using live memory writes where possible.
    """

    def __init__(self, parent: tk.Tk, model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Randomizer")
        self.model = model
        self.min_vars: dict[tuple[str, str], tk.IntVar] = {}
        self.max_vars: dict[tuple[str, str], tk.IntVar] = {}
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
        """Construct the notebook with category tabs and team selection."""
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for cat in ("Attributes", "Tendencies", "Durability"):
            frame = tk.Frame(notebook, bg="#F5F5F5")
            notebook.add(frame, text=cat)
            self._build_category_page(frame, cat)
        team_frame = tk.Frame(notebook, bg="#F5F5F5")
        notebook.add(team_frame, text="Teams")
        self._build_team_page(team_frame)
        tk.Button(self, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(pady=(0, 10))

    def _build_category_page(self, parent: tk.Frame, category: str) -> None:
        """Add min/max controls for each field in a category."""
        canvas = tk.Canvas(parent, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        bind_mousewheel(scroll_frame, canvas)
        tk.Label(scroll_frame, text="Field", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=(10, 5), pady=2
        )
        tk.Label(scroll_frame, text="Min", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(scroll_frame, text="Max", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=5, pady=2)
        fields = self.model.categories.get(category, [])
        for idx, field in enumerate(fields, start=1):
            name = field.get("name", f"Field {idx}")
            tk.Label(scroll_frame, text=name, bg="#F5F5F5").grid(row=idx, column=0, sticky=tk.W, padx=(10, 5), pady=2)
            if category in ("Attributes", "Durability"):
                default_min, default_max = 25, 99
                spin_from, spin_to = 25, 99
            elif category == "Tendencies":
                default_min, default_max = 0, 100
                spin_from, spin_to = 0, 100
            else:
                default_min = 0
                length = to_int(field.get("length", 8))
                default_max = (1 << length) - 1 if length else 255
                spin_from, spin_to = 0, default_max
            min_var = tk.IntVar(value=default_min)
            max_var = tk.IntVar(value=default_max)
            self.min_vars[(category, name)] = min_var
            self.max_vars[(category, name)] = max_var
            tk.Spinbox(scroll_frame, from_=spin_from, to=spin_to, textvariable=min_var, width=5).grid(row=idx, column=1, padx=2, pady=2)
            tk.Spinbox(scroll_frame, from_=spin_from, to=spin_to, textvariable=max_var, width=5).grid(row=idx, column=2, padx=2, pady=2)

    def _build_team_page(self, parent: tk.Frame) -> None:
        """Add team checkboxes and randomize action."""
        tk.Button(parent, text="Randomize Selected", command=self._randomize_selected, bg="#52796F", fg="white", relief=tk.FLAT).pack(
            pady=(5, 10)
        )
        canvas = tk.Canvas(parent, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        bind_mousewheel(scroll_frame, canvas)
        team_names = []
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

    def _randomize_selected(self) -> None:
        """Apply randomized values within per-field bounds to selected teams."""
        import tkinter.messagebox as mb

        selected = [team for team, var in self.team_vars.items() if var.get()]
        if not selected:
            mb.showinfo("Randomizer", "No teams selected for randomization.")
            return
        categories = ["Attributes", "Tendencies", "Durability"]
        updated_players = 0
        for team_name in selected:
            players = self.model.get_players_by_team(team_name)
            if not players:
                continue
            for player in players:
                player_updated = False
                for cat in categories:
                    fields = self.model.categories.get(cat, [])
                    for field in fields:
                        fname = field.get("name")
                        if not isinstance(fname, str) or not fname:
                            continue
                        key = (cat, fname)
                        if key not in self.min_vars or key not in self.max_vars:
                            continue
                        offset_raw = field.get("offset")
                        if offset_raw in (None, ""):
                            continue
                        min_val = self.min_vars[key].get()
                        max_val = self.max_vars[key].get()
                        if min_val > max_val:
                            min_val, max_val = max_val, min_val
                        rating = random.randint(min_val, max_val)
                        ok = self.model.encode_field_value(
                            entity_type="player",
                            entity_index=player.index,
                            category=cat,
                            field_name=fname,
                            meta=field,
                            display_value=rating,
                            record_ptr=getattr(player, "record_ptr", None),
                        )
                        if ok:
                            player_updated = True
                if player_updated:
                    updated_players += 1
        try:
            self.model.refresh_players()
        except Exception:
            pass
        mb.showinfo("Randomizer", f"Randomization complete. {updated_players} players updated.")


__all__ = ["RandomizerWindow"]
