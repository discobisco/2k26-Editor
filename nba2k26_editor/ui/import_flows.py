"""Import workflows extracted from PlayerEditorApp for reuse and readability."""
from __future__ import annotations

import csv as _csv
import io
import os
import tempfile
import urllib.parse
import urllib.request
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox

from ..core.config import COY_SHEET_ID, COY_SHEET_TABS, COY_TENDENCY_AVERAGE_TAB
from ..importing import excel_import
from .dialogs import CategorySelectionDialog


def open_import_dialog(app: Any) -> None:
    """Delegate for PlayerEditorApp._open_import_dialog."""
    paths = filedialog.askopenfilenames(
        parent=app,
        title="Select Import Files",
        filetypes=[("Data files", "*.txt *.csv *.tsv *.xlsx *.xls"), ("All files", "*.*")],
    )
    if not paths:
        return
    excel_paths = [p for p in paths if os.path.splitext(p)[1].lower() in (".xlsx", ".xls")]
    delimited_paths = [p for p in paths if p not in excel_paths]
    if excel_paths:
        match_response = messagebox.askyesnocancel(
            "Excel Import",
            "Match players by name?\n\nYes = match each row to a roster player by name.\n"
            "No = overwrite players in current roster order.\nCancel = abort import.",
        )
        if match_response is None:
            return
        match_by_name = bool(match_response)
        excel_results: dict[str, int] = {}
        missing_names: set[str] = set()
        for path in excel_paths:
            try:
                res = excel_import.import_excel_workbook(app.model, path, match_by_name=match_by_name)
                excel_results[path] = sum(res.values()) if isinstance(res, dict) else 0
                missing_bucket = getattr(app.model, "import_partial_matches", {}).get("excel_missing", {})
                if isinstance(missing_bucket, dict):
                    missing_names.update(missing_bucket.keys())
            except Exception as exc:
                messagebox.showerror("Import Data", f"Failed to import {os.path.basename(path)}:\n{exc}")
        try:
            app.model.refresh_players()
        except Exception:
            pass
        app._start_scan()
        if excel_results:
            lines = [f"Imported {count} updates from {os.path.basename(path)}" for path, count in excel_results.items()]
            if missing_names:
                lines.append(f"Players not found: {len(missing_names)}")
            messagebox.showinfo("Import Data", "\n".join(lines))
        if not delimited_paths:
            return
    # Precompute normalized header names for each known category
    from ..core.offsets import ATTR_IMPORT_ORDER, TEND_IMPORT_ORDER, DUR_IMPORT_ORDER

    attr_norms = [app.model._normalize_header_name(h) for h in ATTR_IMPORT_ORDER]
    tend_norms = [app.model._normalize_header_name(h) for h in TEND_IMPORT_ORDER]
    dur_norms = [app.model._normalize_header_name(h) for h in DUR_IMPORT_ORDER]
    file_map: dict[str, str] = {}
    for path in delimited_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
        except Exception:
            continue
        delim = "\t" if "\t" in first_line else "," if "," in first_line else ";"
        header = [h.strip() for h in first_line.strip().split(delim)]
        headers_norm = [app.model._normalize_header_name(h) for h in header[1:]] if len(header) > 1 else []
        score_attr = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in attr_norms))
        score_tend = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in tend_norms))
        score_dur = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in dur_norms))
        if score_attr >= score_tend and score_attr >= score_dur and score_attr > 0:
            cat = "Attributes"
        elif score_tend >= score_attr and score_tend >= score_dur and score_tend > 0:
            cat = "Tendencies"
        elif score_dur >= score_attr and score_dur >= score_tend and score_dur > 0:
            cat = "Durability"
        else:
            continue
        if cat not in file_map:
            file_map[cat] = path
    if not file_map:
        messagebox.showerror("Import Data", "The selected file(s) do not match any known data category.")
        return
    results = app.model.import_all(file_map)
    messages = []
    for cat in ["Attributes", "Tendencies", "Durability"]:
        if cat in file_map:
            count = results.get(cat)
            basename = os.path.basename(file_map[cat])
            messages.append(f"Imported {count} players for {cat} from {basename}.")
    msg = "\n".join(messages) if messages else "No data was imported."
    messagebox.showinfo("Import Data", msg)
    app._start_scan()


def open_2kcoy(app: Any) -> None:
    """Delegate for PlayerEditorApp._open_2kcoy."""
    try:
        app.model.refresh_players()
    except Exception:
        pass
    if not app.model.mem.hproc:
        messagebox.showinfo(
            "2K COY Import",
            "NBA 2K26 does not appear to be running. Please launch the game and load a roster before importing.",
        )
        return
    categories_to_ask = ["Attributes", "Tendencies", "Durability", "Potential"]
    try:
        dlg = CategorySelectionDialog(
            app,
            categories_to_ask,
            title="Select categories to import",
            message="Import the following categories:",
        )
        app.wait_window(dlg)
        selected_categories = dlg.selected
    except Exception:
        selected_categories = None
    if not selected_categories:
        return
    loading_win = tk.Toplevel(app)
    loading_win.title("Loading")
    loading_win.geometry("350x120")
    loading_win.resizable(False, False)
    tk.Label(
        loading_win,
        text="Loading data... Please wait and do not click the updater.",
        wraplength=320,
        justify="left",
    ).pack(padx=20, pady=20)
    loading_win.update_idletasks()
    auto_download = bool(COY_SHEET_ID)
    file_map: dict[str, str] = {}
    not_found: set[str] = set()
    category_tables: dict[str, dict[str, object]] = {}
    results: dict[str, int] = {}
    tend_defaults_path: str | None = None
    if auto_download:
        for cat, sheet_name in COY_SHEET_TABS.items():
            if cat not in selected_categories:
                continue
            try:
                url = (
                    f"https://docs.google.com/spreadsheets/d/{COY_SHEET_ID}/"
                    f"gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
                )
                with urllib.request.urlopen(url, timeout=30) as resp:
                    csv_text = resp.read().decode("utf-8")
            except Exception:
                csv_text = ""
            if not csv_text:
                continue
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
            tmp.write(csv_text)
            tmp.close()
            file_map[cat] = tmp.name
            try:
                rows = list(_csv.reader(io.StringIO(csv_text)))
                category_tables[cat] = {"rows": rows, "delimiter": ","}
                info = app.model.prepare_import_rows(cat, rows, context="coy") if rows else None
                if info:
                    for row in info["data_rows"]:
                        name = app.model.compose_import_row_name(info, row)
                        if name and not app.model._match_player_indices(name):
                            not_found.add(name)
            except Exception:
                pass
        if "Tendencies" in selected_categories:
            try:
                url = (
                    f"https://docs.google.com/spreadsheets/d/{COY_SHEET_ID}/"
                    f"gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(COY_TENDENCY_AVERAGE_TAB)}"
                )
                with urllib.request.urlopen(url, timeout=30) as resp:
                    csv_text = resp.read().decode("utf-8")
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
                tmp.write(csv_text)
                tmp.close()
                tend_defaults_path = tmp.name
            except Exception:
                tend_defaults_path = None
    if not file_map:
        def prompt_file(cat_name: str) -> str:
            return filedialog.askopenfilename(
                title=f"Select {cat_name} Import File",
                filetypes=[("Delimited files", "*.csv *.tsv *.txt"), ("All files", "*.*")],
            )
        for cat in categories_to_ask:
            if cat not in selected_categories:
                continue
            path = prompt_file(cat)
            if not path:
                file_map.clear()
                return
            file_map[cat] = path

        def collect_missing_names(cat_name: str, path: str) -> None:
            if not path or not os.path.isfile(path):
                return
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    sample = f.readline()
                    delim = "\t" if "\t" in sample else "," if "," in sample else ";"
                    f.seek(0)
                    rows = list(_csv.reader(f, delimiter=delim))
                category_tables[cat_name] = {"rows": rows, "delimiter": delim}
                info = app.model.prepare_import_rows(cat_name, rows, context="coy") if rows else None
                if info:
                    for row in info["data_rows"]:
                        name = app.model.compose_import_row_name(info, row)
                        if name and not app.model._match_player_indices(name):
                            not_found.add(name)
            except Exception:
                pass

        for cat_name, path in file_map.items():
            collect_missing_names(cat_name, path)
    attr_pool_size = 0
    attr_names_set: set[str] = set()
    if "Attributes" in file_map:
        try:
            path = file_map["Attributes"]
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.readline()
                delim = "\t" if "\t" in sample else "," if "," in sample else ";"
                f.seek(0)
                reader = _csv.reader(f, delimiter=delim)
                rows = list(reader)
            info = app.model.prepare_import_rows("Attributes", rows, context="coy") if rows else None
            if info:
                name_col = info["name_col"]
                for row in info["data_rows"]:
                    if not row or len(row) <= name_col:
                        continue
                    cell = str(row[name_col]).strip()
                    if cell:
                        attr_names_set.add(cell)
                attr_pool_size = len(attr_names_set)
        except Exception:
            attr_pool_size = 0
    aux_files = {"tendencies_defaults": tend_defaults_path} if tend_defaults_path else None
    results = app.model.import_coy_tables(file_map, aux_files=aux_files)
    try:
        app.model.refresh_players()
    except Exception:
        pass
    if auto_download:
        for p in file_map.values():
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass
        if tend_defaults_path:
            try:
                if os.path.isfile(tend_defaults_path):
                    os.remove(tend_defaults_path)
            except Exception:
                pass
    msg_lines = ["2K COY import completed."]
    if not file_map:
        msg_lines.append("\nNo recognizable columns were found in the workbook.")
    if results:
        msg_lines.append("\nPlayers updated:")
        for cat, cnt in results.items():
            if file_map.get(cat):
                msg_lines.append(f"  {cat}: {cnt}")
    partial_info = getattr(app.model, "import_partial_matches", {}) or {}
    had_partial = False
    for cat, mapping in partial_info.items():
        if not mapping:
            continue
        if not had_partial:
            msg_lines.append("\nPlayers requiring confirmation (skipped):")
            had_partial = True
        msg_lines.append(f"  {cat}: {len(mapping)}")
    if not_found:
        msg_lines.append("\nPlayers not found in the current roster:")
        sample = list(sorted(not_found))[:30]
        for name in sample:
            msg_lines.append(f"  - {name}")
        remaining = len(not_found) - len(sample)
        if remaining > 0:
            msg_lines.append(f"  ...and {remaining} more.")
    msg_lines.append(f"\nPlayers in Attributes sheet: {attr_pool_size}")
    summary_text = "\n".join(msg_lines)
    try:
        dlg = tk.Toplevel(app)
        dlg.title("Import Summary")
        dlg.geometry("450x500")
        dlg.resizable(True, True)
        txt = tk.Text(dlg, wrap="word", height=20, width=60)
        txt.insert("1.0", summary_text)
        txt.config(state="disabled")
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        tk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=(0, 10))
    except Exception:
        messagebox.showinfo("Import Summary", summary_text)
    try:
        loading_win.destroy()
    except Exception:
        pass


__all__ = ["open_import_dialog", "open_2kcoy"]
