"""Randomizer modal for the Dear PyGui UI."""
from __future__ import annotations

import random
from typing import Dict, Tuple

import dearpygui.dearpygui as dpg

from ..core.conversions import to_int
from ..models.data_model import PlayerDataModel

CategoryFieldKey = Tuple[str, str]


class RandomizerWindow:
    """Randomize player attributes/tendencies/durability across selected teams."""

    def __init__(self, app, model: PlayerDataModel) -> None:
        self.app = app
        self.model = model
        self.window_tag: int | str = dpg.generate_uuid()
        self.min_tags: Dict[CategoryFieldKey, int | str] = {}
        self.max_tags: Dict[CategoryFieldKey, int | str] = {}
        self.team_check_tags: Dict[str, int | str] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        with dpg.window(
            label="Randomizer",
            tag=self.window_tag,
            modal=True,
            no_collapse=True,
            width=820,
            height=620,
        ):
            dpg.add_text(
                "Pick per-field min/max values, choose teams, and randomize players in-place.",
                wrap=760,
            )
            dpg.add_spacer(height=6)
            with dpg.tab_bar():
                for cat in ("Attributes", "Tendencies", "Durability"):
                    fields = self.model.categories.get(cat, [])
                    if not fields:
                        continue
                    with dpg.tab(label=cat):
                        self._build_category_tab(cat, fields)
            dpg.add_spacer(height=10)
            dpg.add_text("Teams")
            with dpg.child_window(height=160, border=True):
                for team in self._team_names():
                    tag = dpg.add_checkbox(label=team, default_value=False)
                    self.team_check_tags[team] = tag
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Randomize Selected", width=180, callback=lambda: self._randomize_selected())
                dpg.add_button(label="Close", width=90, callback=lambda: dpg.delete_item(self.window_tag))

    def _build_category_tab(self, category: str, fields: list[dict]) -> None:
        with dpg.child_window(height=320, border=True):
            with dpg.table(
                header_row=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                borders_innerH=True,
                borders_innerV=True,
                borders_outerH=True,
                borders_outerV=True,
            ):
                dpg.add_table_column(label="Field", width_fixed=False)
                dpg.add_table_column(label="Min", width_fixed=True, init_width_or_weight=80)
                dpg.add_table_column(label="Max", width_fixed=True, init_width_or_weight=80)
                for field in fields:
                    name = field.get("name") or "Field"
                    dpg.add_table_row()
                    dpg.add_text(str(name))
                    min_default, max_default, min_limit, max_limit = self._default_bounds(category, field)
                    min_tag = dpg.add_input_int(default_value=min_default, min_value=min_limit, max_value=max_limit, step=1, width=90)
                    max_tag = dpg.add_input_int(default_value=max_default, min_value=min_limit, max_value=max_limit, step=1, width=90)
                    self.min_tags[(category, str(name))] = min_tag
                    self.max_tags[(category, str(name))] = max_tag

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _randomize_selected(self) -> None:
        selected = [team for team, tag in self.team_check_tags.items() if dpg.does_item_exist(tag) and dpg.get_value(tag)]
        if not selected:
            self.app.show_warning("Randomizer", "Select at least one team first.")
            return
        categories = ("Attributes", "Tendencies", "Durability")
        updated_players = 0
        for team_name in selected:
            try:
                players = self.model.get_players_by_team(team_name)
            except Exception:
                players = []
            if not players:
                continue
            for player in players:
                player_updated = False
                for cat in categories:
                    for field in self.model.categories.get(cat, []):
                        fname = field.get("name")
                        if not isinstance(fname, str) or not fname:
                            continue
                        key = (cat, fname)
                        min_tag = self.min_tags.get(key)
                        max_tag = self.max_tags.get(key)
                        if min_tag is None or max_tag is None:
                            continue
                        offset_raw = field.get("offset")
                        if offset_raw in (None, ""):
                            continue
                        try:
                            min_val = int(dpg.get_value(min_tag))
                            max_val = int(dpg.get_value(max_tag))
                        except Exception:
                            continue
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
        self.app.show_message("Randomizer", f"Randomization complete. {updated_players} players updated.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _default_bounds(self, category: str, field: dict) -> tuple[int, int, int, int]:
        if category in ("Attributes", "Durability"):
            return 25, 99, 0, 120
        if category == "Tendencies":
            return 0, 100, 0, 120
        length = to_int(field.get("length", 8)) or 8
        max_val = (1 << length) - 1 if length else 255
        return 0, max_val, 0, max_val

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


def open_randomizer(app) -> RandomizerWindow:
    """Convenience helper to open the randomizer modal."""
    return RandomizerWindow(app, app.model)


__all__ = ["RandomizerWindow", "open_randomizer"]
