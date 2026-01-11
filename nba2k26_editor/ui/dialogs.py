"""Common dialogs and reusable widgets (ported from the monolithic editor)."""
from __future__ import annotations

import difflib
import tkinter as tk
from tkinter import ttk
from typing import Callable, Any

from ..core.config import (
    PANEL_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT_BG,
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    INPUT_TEXT_FG,
)
from .widgets import bind_mousewheel


class ImportSummaryDialog(tk.Toplevel):
    """Dialog displaying import results and providing quick player lookup."""

    MAX_SUGGESTIONS = 200

    def __init__(
        self,
        parent: tk.Misc,
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
        super().__init__(parent)
        self.title(title)
        if isinstance(parent, (tk.Tk, tk.Toplevel)):
            self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.configure(bg=PANEL_BG)
        self.apply_callback = apply_callback
        self.missing_players = list(missing_players)
        self.mapping: dict[str, str] = {}
        self.require_confirmation = require_confirmation
        self._raw_score_lookup = suggestion_scores or {}
        self._confirm_vars: dict[str, tk.BooleanVar] = {}
        self._row_entries: dict[str, "SearchEntry"] = {}
        summary_frame = tk.Frame(self, bg=PANEL_BG)
        summary_frame.pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(
            summary_frame,
            text="Import summary:",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        summary_lines_count = summary_text.count("\n") + 1
        summary_box = tk.Text(
            summary_frame,
            height=max(3, min(12, summary_lines_count)),
            wrap="word",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            relief=tk.FLAT,
            state="normal",
            padx=0,
            pady=0,
            highlightthickness=0,
        )
        summary_box.insert("1.0", summary_text)
        summary_box.config(state="disabled")
        summary_box.pack(fill=tk.X, pady=(4, 0))
        if missing_players:
            missing_frame = tk.LabelFrame(
                self,
                text=missing_label or "Players not found - type to search the current roster",
                bg=PANEL_BG,
                fg=TEXT_PRIMARY,
                labelanchor="n",
                padx=8,
                pady=8,
            )
            missing_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
            canvas = tk.Canvas(missing_frame, highlightthickness=0, bg=PANEL_BG)
            scrollbar = tk.Scrollbar(missing_frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            rows_frame = tk.Frame(canvas, bg=PANEL_BG)
            canvas.create_window((0, 0), window=rows_frame, anchor="nw")
            bind_mousewheel(rows_frame, canvas)

            def _on_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))

            rows_frame.bind("<Configure>", _on_configure)
            header_fg = TEXT_PRIMARY
            tk.Label(rows_frame, text="Sheet Name", bg=PANEL_BG, fg=header_fg, font=("Segoe UI", 10, "bold")).grid(
                row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 4)
            )
            tk.Label(rows_frame, text="Search roster", bg=PANEL_BG, fg=header_fg, font=("Segoe UI", 10, "bold")).grid(
                row=0, column=1, sticky="w", pady=(0, 4)
            )
            show_scores = bool(self._raw_score_lookup)
            score_col = 2
            use_col = 2
            if show_scores:
                tk.Label(rows_frame, text="Match %", bg=PANEL_BG, fg=header_fg, font=("Segoe UI", 10, "bold")).grid(
                    row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 4)
                )
                use_col = 3
            if self.require_confirmation:
                tk.Label(rows_frame, text="Use", bg=PANEL_BG, fg=header_fg, font=("Segoe UI", 10, "bold")).grid(
                    row=0, column=use_col, sticky="w", padx=(6, 0), pady=(0, 4)
                )
            roster_sorted = sorted(set(roster_names), key=lambda n: n.lower())
            self._roster_lookup = {name.lower(): name for name in roster_sorted}
            self._suggestions: dict[str, str] = {}
            if suggestions:
                for raw_name, candidate in suggestions.items():
                    if not candidate:
                        continue
                    key = str(raw_name or "").strip()
                    if not key:
                        continue
                    cand = str(candidate).strip()
                    if not cand:
                        continue
                    self._suggestions.setdefault(key, cand)
                    self._suggestions.setdefault(key.lower(), cand)
            for idx, name in enumerate(missing_players, start=1):
                tk.Label(rows_frame, text=name, bg=PANEL_BG, fg=TEXT_PRIMARY).grid(
                    row=idx, column=0, sticky="w", padx=(0, 10), pady=2
                )
                combo = SearchEntry(rows_frame, roster_sorted, width=32)
                combo.grid(row=idx, column=1, sticky="ew", pady=2)
                self._row_entries[name] = combo
                suggestion = self._get_initial_suggestion(name, roster_sorted)
                use_var: tk.BooleanVar | None = None
                if self.require_confirmation:
                    use_var = tk.BooleanVar(value=bool(suggestion))
                    self._confirm_vars[name] = use_var
                if suggestion:
                    combo.insert(0, suggestion)
                    combo.icursor(tk.END)
                    if not self.require_confirmation or (use_var and use_var.get()):
                        self._set_mapping(name, suggestion)

                def _on_entry_change(value: str, source=name, dialog=self, confirm_var=use_var) -> None:
                    cleaned = value.strip()
                    if dialog.require_confirmation and confirm_var is not None:
                        if cleaned and not confirm_var.get():
                            confirm_var.set(True)
                        elif not cleaned and confirm_var.get():
                            dialog.after_idle(lambda: confirm_var.set(False))
                    dialog._set_mapping(source, cleaned)

                combo.set_match_callback(_on_entry_change)
                score_value = self._raw_score_lookup.get(name) or self._raw_score_lookup.get(name.lower())
                if show_scores:
                    if isinstance(score_value, (int, float)):
                        normalized = max(0.0, min(float(score_value), 1.0))
                        display_score = f"{normalized * 100:.0f}%"
                    else:
                        display_score = "-"
                    tk.Label(rows_frame, text=display_score, bg=PANEL_BG, fg=TEXT_SECONDARY).grid(
                        row=idx, column=score_col, sticky="w", padx=(8, 0), pady=2
                    )
                if self.require_confirmation and use_var is not None:

                    def _on_toggle(*_args, source=name, entry=combo, var=use_var, dialog=self) -> None:
                        if var.get():
                            current = entry.get().strip()
                            if not current:
                                dialog.after_idle(lambda: var.set(False))
                                return
                            dialog._set_mapping(source, current)
                        else:
                            dialog._set_mapping(source, "")

                    use_var.trace_add("write", _on_toggle)
                    tk.Checkbutton(
                        rows_frame,
                        text="",
                        variable=use_var,
                        bg=PANEL_BG,
                        fg=TEXT_PRIMARY,
                        activebackground=PANEL_BG,
                        selectcolor=PANEL_BG,
                    ).grid(row=idx, column=use_col, sticky="w", padx=(6, 0), pady=2)
            rows_frame.columnconfigure(1, weight=1)
        btn_frame = tk.Frame(self, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))
        if missing_players and apply_callback:
            btn_label = "Apply Confirmed" if self.require_confirmation else "Apply Matches"
            tk.Button(
                btn_frame,
                text=btn_label,
                command=self._on_apply,
                width=14,
                bg=ACCENT_BG,
                activebackground=BUTTON_ACTIVE_BG,
                fg=TEXT_PRIMARY,
            ).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            width=12,
            bg=BUTTON_BG,
            activebackground=BUTTON_ACTIVE_BG,
            fg=BUTTON_TEXT,
        ).pack(side=tk.RIGHT)

    def _get_initial_suggestion(self, sheet_name: str, roster_sorted: list[str]) -> str | None:
        key = str(sheet_name or "").strip()
        if not key:
            return None
        direct = self._suggestions.get(key) or self._suggestions.get(key.lower())
        if direct:
            return direct
        return self._closest_roster_match(key, roster_sorted)

    def _closest_roster_match(self, sheet_name: str, roster_sorted: list[str]) -> str | None:
        if not sheet_name:
            return None
        lower = sheet_name.lower()
        match = self._roster_lookup.get(lower)
        if match:
            return match
        for candidate in roster_sorted:
            cand_lower = candidate.lower()
            if lower in cand_lower or cand_lower in lower:
                return candidate
        matches = difflib.get_close_matches(sheet_name, roster_sorted, n=1, cutoff=0.65)
        if matches:
            return matches[0]
        matches_lower = difflib.get_close_matches(lower, list(self._roster_lookup.keys()), n=1, cutoff=0.65)
        if matches_lower:
            return self._roster_lookup.get(matches_lower[0])
        return None

    def _set_mapping(self, sheet_name: str, roster_value: str) -> None:
        value = (roster_value or "").strip()
        if self.require_confirmation:
            confirm_var = self._confirm_vars.get(sheet_name)
            if confirm_var is not None and not confirm_var.get():
                if sheet_name in self.mapping:
                    self.mapping.pop(sheet_name, None)
                return
        if value:
            self.mapping[sheet_name] = value
        elif sheet_name in self.mapping:
            self.mapping.pop(sheet_name, None)

    def _on_apply(self) -> None:
        if self.require_confirmation:
            final_mapping: dict[str, str] = {}
            for raw_name, entry in self._row_entries.items():
                confirm_var = self._confirm_vars.get(raw_name)
                if confirm_var and confirm_var.get():
                    value = entry.get().strip()
                    if value:
                        final_mapping[raw_name] = value
            if self.apply_callback:
                self.apply_callback(final_mapping)
        elif self.apply_callback:
            self.apply_callback(dict(self.mapping))
        self.destroy()


class SearchEntry(ttk.Entry):
    """Entry with dropdown suggestion list that stays open while typing."""

    def __init__(self, parent: tk.Misc, values: list[str], width: int = 30):
        self._all_values = values
        self._popup = None
        self._listbox = None
        super().__init__(parent, width=width)
        style = ttk.Style(self)
        style_name = "SearchEntry.TEntry"
        try:
            style.configure(style_name, foreground=INPUT_TEXT_FG, fieldbackground="white")
            self.configure(style=style_name)
        except tk.TclError:
            try:
                self.configure(foreground=INPUT_TEXT_FG)
            except tk.TclError:
                pass
        self._match_callback: Callable[[str], None] | None = None
        self.bind("<KeyRelease>", self._on_keyrelease, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Down>", self._move_focus_to_list, add="+")
        self.bind("<Return>", self._commit_current, add="+")

    def set_match_callback(self, callback: Callable[[str], None]) -> None:
        self._match_callback = callback

    def _move_focus_to_list(self, event=None) -> None:
        if self._listbox:
            self._listbox.focus_set()
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(0)
            self._listbox.activate(0)

    def _commit_current(self, event=None) -> None:
        value = self.get().strip()
        if self._listbox and self._listbox.curselection():
            value = self._listbox.get(self._listbox.curselection()[0])
            self.delete(0, tk.END)
            self.insert(0, value)
        if self._match_callback:
            self._match_callback(value)
        self._hide_popup()

    def _on_keyrelease(self, event) -> None:
        if event.keysym in ("Return", "Escape", "Tab"):
            return
        term = self.get().strip().lower()
        if not term:
            filtered = self._all_values[: ImportSummaryDialog.MAX_SUGGESTIONS]
        else:
            filtered = [v for v in self._all_values if term in v.lower()]
            filtered = filtered[: ImportSummaryDialog.MAX_SUGGESTIONS]
        if not filtered:
            self._hide_popup()
            return
        self._show_popup(filtered)

    def _on_focus_out(self, event) -> None:
        widget = event.widget
        if self._popup and widget not in (self, self._listbox):
            self.after(100, self._hide_popup)

    def _show_popup(self, values: list[str]) -> None:
        if self._popup and not self._popup.winfo_exists():
            self._popup = None
        if not self._popup:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup.configure(bg="#2C3E50")
            self._listbox = tk.Listbox(
                self._popup,
                selectmode=tk.SINGLE,
                activestyle="dotbox",
                bg="#2C3E50",
                fg="#ECF0F1",
                highlightthickness=0,
                relief=tk.FLAT,
            )
            self._listbox.pack(fill=tk.BOTH, expand=True)
            self._listbox.bind("<ButtonRelease-1>", self._on_list_click, add="+")
            self._listbox.bind("<Return>", self._commit_current, add="+")
            self._listbox.bind("<Escape>", lambda _e: self._hide_popup(), add="+")
        assert self._popup and self._listbox
        self._listbox.delete(0, tk.END)
        for item in values:
            self._listbox.insert(tk.END, item)
        self._popup.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        width = max(self.winfo_width(), 240)
        height = min(200, self._popup.winfo_reqheight())
        self._popup.geometry(f"{width}x{height}+{x}+{y}")
        self._popup.deiconify()

    def _on_list_click(self, _event) -> None:
        if self._listbox and self._listbox.curselection():
            value = self._listbox.get(self._listbox.curselection()[0])
            self.delete(0, tk.END)
            self.insert(0, value)
            if self._match_callback:
                self._match_callback(value)
        self._hide_popup()

    def _hide_popup(self) -> None:
        if self._popup:
            self._popup.destroy()
            self._popup = None
            self._listbox = None


class CategorySelectionDialog(tk.Toplevel):
    """
    Modal dialog allowing the user to select one or more categories.
    """

    def __init__(
        self,
        parent: tk.Misc,
        categories: list[str],
        title: str | None = None,
        message: str | None = None,
        select_all: bool = True,
    ) -> None:
        super().__init__(parent)
        self.title(title or "Select categories")
        self.resizable(False, False)
        if isinstance(parent, (tk.Tk, tk.Toplevel)):
            self.transient(parent)
        self.grab_set()
        self.selected: list[str] | None = []
        self.export_full_records: bool = False
        self.export_full_records_var = tk.BooleanVar(value=False)
        tk.Label(self, text=message or "Select the following categories:").pack(padx=10, pady=(10, 5))
        frame = tk.Frame(self)
        frame.pack(padx=10, pady=5)
        self.var_map: dict[str, tk.BooleanVar] = {}
        for cat in categories:
            var = tk.BooleanVar(value=select_all)
            chk = tk.Checkbutton(frame, text=cat, variable=var)
            chk.pack(anchor=tk.W)
            self.var_map[cat] = var
        raw_frame = tk.Frame(self)
        raw_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        tk.Checkbutton(
            raw_frame,
            text="Also export full raw player records",
            variable=self.export_full_records_var,
            anchor="w",
            padx=0,
        ).pack(anchor=tk.W)
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(5, 10))
        tk.Button(btn_frame, text="OK", width=10, command=self._on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", width=10, command=self._on_cancel).pack(side=tk.LEFT, padx=5)

    def _on_ok(self) -> None:
        selected: list[str] = []
        for cat, var in self.var_map.items():
            try:
                if var.get():
                    selected.append(cat)
            except Exception:
                pass
        export_raw = bool(self.export_full_records_var.get())
        if not selected and not export_raw:
            self.selected = None
        else:
            self.selected = selected
        self.export_full_records = export_raw
        self.destroy()

    def _on_cancel(self) -> None:
        self.selected = None
        self.export_full_records = False
        self.destroy()


__all__ = ["ImportSummaryDialog", "CategorySelectionDialog", "SearchEntry"]
