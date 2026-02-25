"""Common dialogs for the Dear PyGui UI."""
from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg

from ..core.config import TEXT_PRIMARY, TEXT_SECONDARY


def _rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert #RRGGBB hex strings from config into RGBA tuples for DPG."""
    if not isinstance(hex_color, str) or not hex_color.startswith("#") or len(hex_color) < 7:
        return (255, 255, 255, alpha)
    hex_clean = hex_color.lstrip("#")
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return (r, g, b, alpha)


class ImportSummaryDialog:
    """Show import results and allow mapping missing players to roster names."""

    def __init__(
        self,
        app,
        title: str,
        summary_text: str,
        missing_players: list[str],
        roster_names: list[str],
        apply_callback: Callable[[dict[str, str]], None] | None = None,
        suggestions: dict[str, str] | None = None,
        suggestion_scores: dict[str, float] | None = None,
        require_confirmation: bool = False,
        missing_label: str | None = None,
    ) -> None:
        self.app = app
        self.title = title
        self.summary_text = summary_text
        self.missing_players = list(missing_players)
        self.roster_names = sorted(set(roster_names), key=lambda n: n.lower())
        self.apply_callback = apply_callback
        self.require_confirmation = require_confirmation
        self.suggestions = suggestions or {}
        self.suggestion_scores = suggestion_scores or {}
        self.missing_label = missing_label or "Players not found"
        self.window_tag = dpg.generate_uuid()
        self._choice_tags: dict[str, int | str] = {}
        self._confirm_tags: dict[str, int | str] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        with dpg.window(label=self.title, tag=self.window_tag, modal=True, no_collapse=True, width=760, height=520):
            dpg.add_text("Import summary:")
            dpg.add_input_text(default_value=self.summary_text, multiline=True, readonly=True, width=-1, height=140)
            if self.missing_players:
                dpg.add_spacer(height=6)
                dpg.add_text(self.missing_label, color=_rgba(TEXT_PRIMARY))
                with dpg.child_window(height=220, border=True):
                    for name in self.missing_players:
                        with dpg.group(horizontal=True):
                            dpg.add_text(name, color=_rgba(TEXT_PRIMARY))
                            default_choice = self._initial_suggestion(name)
                            combo = dpg.add_combo(items=self.roster_names, width=320, default_value=default_choice or "")
                            self._choice_tags[name] = combo
                            if self.require_confirmation:
                                chk = dpg.add_checkbox(label="Use", default_value=bool(default_choice))
                                self._confirm_tags[name] = chk
                            score_val = self.suggestion_scores.get(name) or self.suggestion_scores.get(name.lower())
                            if isinstance(score_val, (int, float)):
                                pct_text = f"{max(0.0, min(float(score_val), 1.0)) * 100:.0f}%"
                                dpg.add_text(pct_text, color=_rgba(TEXT_SECONDARY))
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                if self.missing_players and self.apply_callback:
                    label = "Apply Confirmed" if self.require_confirmation else "Apply Matches"
                    dpg.add_button(label=label, width=140, callback=lambda: self._apply())
                dpg.add_button(label="Close", width=90, callback=lambda: dpg.delete_item(self.window_tag))

    def _initial_suggestion(self, sheet_name: str) -> str | None:
        direct = self.suggestions.get(sheet_name) or self.suggestions.get(sheet_name.lower())
        if direct:
            return direct
        lower = sheet_name.lower()
        for cand in self.roster_names:
            if lower in cand.lower() or cand.lower() in lower:
                return cand
        return None

    def _apply(self) -> None:
        if not self.apply_callback:
            dpg.delete_item(self.window_tag)
            return
        mapping: dict[str, str] = {}
        for name in self.missing_players:
            tag = self._choice_tags.get(name)
            if tag is None or not dpg.does_item_exist(tag):
                continue
            value = str(dpg.get_value(tag) or "").strip()
            if not value:
                continue
            if self.require_confirmation:
                confirm_tag = self._confirm_tags.get(name)
                if confirm_tag is not None and not dpg.get_value(confirm_tag):
                    continue
            mapping[name] = value
        self.apply_callback(mapping)
        dpg.delete_item(self.window_tag)


class CategorySelectionDialog:
    """Modal checkbox list for selecting categories."""

    def __init__(
        self,
        app,
        categories: list[str],
        title: str | None = None,
        message: str | None = None,
        select_all: bool = True,
        include_raw_option: bool = False,
        callback: Callable[[list[str] | None, bool], None] | None = None,
    ) -> None:
        self.app = app
        self.categories = categories
        self.title = title or "Select categories"
        self.message = message or "Select categories to include"
        self.callback = callback
        self.include_raw = include_raw_option
        self.window_tag = dpg.generate_uuid()
        self.var_tags: dict[str, int | str] = {}
        self.raw_tag: int | str | None = None
        self._build_ui(select_all)

    def _build_ui(self, select_all: bool) -> None:
        with dpg.window(label=self.title, tag=self.window_tag, modal=True, no_collapse=True, width=520, height=420):
            dpg.add_text(self.message, wrap=460)
            with dpg.child_window(height=240, border=True):
                for cat in self.categories:
                    tag = dpg.add_checkbox(label=cat, default_value=select_all)
                    self.var_tags[cat] = tag
            if self.include_raw:
                self.raw_tag = dpg.add_checkbox(label="Also export full raw player records", default_value=False)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="OK", width=80, callback=lambda: self._finish(ok=True))
                dpg.add_button(label="Cancel", width=80, callback=lambda: dpg.delete_item(self.window_tag))

    def _finish(self, ok: bool) -> None:
        selected: list[str] | None
        if not ok:
            selected = None
            export_raw = False
        else:
            selected = [cat for cat, tag in self.var_tags.items() if dpg.get_value(tag)]
            export_raw = bool(self.raw_tag and dpg.get_value(self.raw_tag))
            if not selected and not export_raw:
                selected = None
        if self.callback:
            self.callback(selected, export_raw)
        dpg.delete_item(self.window_tag)


class TeamSelectionDialog:
    """Modal dialog allowing the user to select one or more teams."""

    def __init__(
        self,
        app,
        teams: list[tuple[int, str]] | list[str],
        title: str | None = None,
        message: str | None = None,
        select_all: bool = True,
        callback: Callable[[list[str] | None, bool], None] | None = None,
    ) -> None:
        self.app = app
        self.teams = teams
        self.title = title or "Select teams"
        self.message = message or "Select teams to include"
        self.callback = callback
        self.window_tag = dpg.generate_uuid()
        self.var_tags: dict[str, int | str] = {}
        self.all_tag: int | str | None = None
        self.range_tag: int | str | None = None
        self._range_team_names: set[str] = set()
        self._normalize_teams()
        self._build_ui(select_all)

    def _normalize_teams(self) -> None:
        normalized: list[tuple[int | None, str]] = []
        if self.teams and isinstance(self.teams[0], tuple):
            normalized = [(int(tid), str(name)) for tid, name in self.teams]  # type: ignore[list-item]
        else:
            normalized = [(None, str(name)) for name in self.teams]  # type: ignore[list-item]
        for tid, name in normalized:
            if tid is not None and 0 <= tid <= 29:
                self._range_team_names.add(name)
        self.teams = normalized

    def _build_ui(self, select_all: bool) -> None:
        with dpg.window(label=self.title, tag=self.window_tag, modal=True, no_collapse=True, width=520, height=480):
            dpg.add_text(self.message, wrap=460)
            self.all_tag = dpg.add_checkbox(label="All teams", default_value=select_all, callback=lambda: self._toggle_all())
            self.range_tag = dpg.add_checkbox(label="Teams 0-29", default_value=False, callback=lambda: self._toggle_range())
            with dpg.child_window(height=280, border=True):
                for _tid, name in self.teams:  # type: ignore[assignment]
                    tag = dpg.add_checkbox(label=name, default_value=select_all)
                    self.var_tags[name] = tag
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="OK", width=80, callback=lambda: self._finish(ok=True))
                dpg.add_button(label="Cancel", width=80, callback=lambda: dpg.delete_item(self.window_tag))
            self._toggle_all()

    def _toggle_all(self) -> None:
        if self.all_tag and dpg.get_value(self.all_tag):
            if self.range_tag:
                dpg.set_value(self.range_tag, False)
            for tag in self.var_tags.values():
                dpg.set_value(tag, False)
        self._sync_checkbox_states()

    def _toggle_range(self) -> None:
        if self.range_tag and dpg.get_value(self.range_tag):
            if self.all_tag:
                dpg.set_value(self.all_tag, False)
            for name, tag in self.var_tags.items():
                dpg.set_value(tag, name in self._range_team_names)
        self._sync_checkbox_states()

    def _sync_checkbox_states(self) -> None:
        enabled = not (self.all_tag and dpg.get_value(self.all_tag) or self.range_tag and dpg.get_value(self.range_tag))
        for tag in self.var_tags.values():
            dpg.configure_item(tag, enabled=enabled)

    def _finish(self, ok: bool) -> None:
        if not ok:
            selected = None
            all_teams = False
        else:
            if self.all_tag and dpg.get_value(self.all_tag):
                selected = []
                all_teams = True
            else:
                selected = [name for name, tag in self.var_tags.items() if dpg.get_value(tag)]
                all_teams = False
                if self.range_tag and dpg.get_value(self.range_tag):
                    if not selected:
                        selected = list(self._range_team_names)
        if self.callback:
            self.callback(selected, all_teams)
        dpg.delete_item(self.window_tag)


__all__ = ["ImportSummaryDialog", "CategorySelectionDialog", "TeamSelectionDialog"]
