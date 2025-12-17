"""Excel import helpers lifted from the monolithic editor."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, cast

import pandas as pd  # type: ignore

from . import csv_import
from ..core.config import COY_SHEET_TABS
from ..models.schema import PreparedImportRows


def categorize_columns(model, df: Any) -> tuple[str | None, list[str], dict[str, list[str]]]:
    """Return (name_column, name_columns, categorized_column_map) for a DataFrame."""
    if df is None or getattr(df, "empty", False):
        return (None, [], {})
    try:
        columns = [str(col).strip() for col in df.columns]
    except Exception:
        return (None, [], {})
    if not columns:
        return (None, [], {})
    name_column = columns[0]
    first_name_markers = {"FIRSTNAME", "FIRST", "FNAME", "PLAYERFIRST", "PLAYERFIRSTNAME", "GIVENNAME"}
    last_name_markers = {"LASTNAME", "LAST", "LNAME", "PLAYERLAST", "PLAYERLASTNAME", "SURNAME", "FAMILYNAME"}

    def _collect_name_columns(cols: Iterable[str]) -> list[str]:
        name_cols: list[str] = []
        for idx, column_name in enumerate(cols):
            normalized = model._normalize_header_name(column_name)
            if idx == 0:
                if column_name not in name_cols:
                    name_cols.append(column_name)
                continue
            if not normalized:
                continue
            if normalized in first_name_markers and column_name not in name_cols:
                name_cols.append(column_name)
                continue
            if normalized in last_name_markers and column_name not in name_cols:
                name_cols.append(column_name)
        return name_cols

    name_columns = _collect_name_columns(df.columns)
    field_lookup: dict[str, list[tuple[str, str]]] = {}
    for cat_name, fields in (model.categories or {}).items():
        for field in fields:
            if not isinstance(field, dict):
                continue
            fname = str(field.get("name", "")).strip()
            if not fname:
                continue
            normalized = model._normalize_field_name(fname)
            if not normalized:
                continue
            entries = field_lookup.setdefault(normalized, [])
            if not any(existing_cat == cat_name and existing_name == fname for existing_cat, existing_name in entries):
                entries.append((cat_name, fname))
    categorized: dict[str, list[str]] = {}
    for idx, column_name in enumerate(columns):
        if idx == 0:
            continue
        normalized = model._normalize_header_name(column_name)
        if not normalized:
            continue
        cat_entries = field_lookup.get(normalized)
        if not cat_entries:
            continue
        first_entry = cat_entries[0]
        if not isinstance(first_entry, (tuple, list)) or len(first_entry) < 2:
            continue
        category = first_entry[0]
        categorized.setdefault(category, []).append(df.columns[idx])
    return (name_column, name_columns, categorized)


def collect_missing_names(model, cat_name: str, rows: list[list[str]], not_found: set[str]) -> None:
    """Collect missing names for manual mapping."""
    if not rows:
        return
    info = csv_import.prepare_import_rows(model, cat_name, rows, context="excel")
    if not info:
        return
    for row in info["data_rows"]:
        name = csv_import.compose_import_row_name(info, row)
        if not name:
            continue
        if not model._match_player_indices(name):
            not_found.add(name)


def dataframe_to_temp_csv(df: Any) -> str | None:
    """Persist a DataFrame to a temporary CSV path and return the filename."""
    if df is None or getattr(df, "empty", False):
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
        df.to_csv(tmp.name, index=False)
    except Exception:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        return None
    tmp.close()
    return tmp.name


def import_excel_workbook(model, workbook_path: str, *, match_by_name: bool = True) -> dict[str, int]:
    """
    Process an Excel/CSV workbook and import recognized categories into the model.
    Returns a mapping of category -> players updated count.
    """
    try:
        import pandas as _pd  # type: ignore
    except Exception:
        raise RuntimeError("Pandas is required for Excel import. Install with: pip install pandas openpyxl") from None
    file_map: dict[str, str] = {}
    not_found: set[str] = set()
    category_tables: dict[str, dict[str, object]] = {}
    category_frames: dict[str, Any] = {}
    dataframes: list[tuple[str, Any]] = []
    file_ext = os.path.splitext(workbook_path)[1].lower()
    if file_ext in (".csv", ".tsv", ".txt"):
        try:
            df = cast(Any, _pd.read_csv(workbook_path, sep=None, engine="python"))
        except Exception as exc:
            raise RuntimeError(f"Failed to read {os.path.basename(workbook_path)}") from exc
        dataframes.append((os.path.basename(workbook_path), df))
    else:
        try:
            xls = _pd.ExcelFile(workbook_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read {os.path.basename(workbook_path)}") from exc
        for sheet_name in xls.sheet_names:
            sheet_label = str(sheet_name)
            df: Any = None
            try:
                df = cast(Any, xls.parse(sheet_label))
            except Exception:
                try:
                    df = cast(Any, _pd.read_excel(workbook_path, sheet_name=sheet_label))
                except Exception:
                    df = None
            if df is None:
                continue
            dataframes.append((sheet_label, df))
    for sheet_name, df in dataframes:
        name_column, name_columns, categorized = categorize_columns(model, df)
        if not name_column or not categorized:
            continue
        if not name_columns:
            name_columns = [name_column]
        for cat_name, column_names in categorized.items():
            usable_columns: list[str] = []
            for column_name in column_names:
                try:
                    series = df[column_name]
                except Exception:
                    continue
                drop = False
                try:
                    if series.isna().all():
                        drop = True
                except Exception:
                    pass
                if not drop:
                    try:
                        if series.astype(str).str.strip().eq("").all():
                            drop = True
                    except Exception:
                        pass
                if drop:
                    continue
                usable_columns.append(column_name)
            if not usable_columns:
                continue
            subset_columns = list(name_columns)
            for column_name in usable_columns:
                if column_name not in subset_columns:
                    subset_columns.append(column_name)
            try:
                subset_df = df[subset_columns].copy()
            except Exception:
                continue
            if cat_name in category_frames:
                existing_df = category_frames[cat_name]
                name_existing = existing_df.columns[0]
                name_new = subset_df.columns[0]
                if name_new != name_existing:
                    try:
                        subset_df = subset_df.rename(columns={name_new: name_existing})
                    except Exception:
                        pass
                try:
                    existing_df = existing_df.loc[:, ~existing_df.columns.duplicated()]
                except Exception:
                    pass
                try:
                    subset_df = subset_df.loc[:, ~subset_df.columns.duplicated()]
                except Exception:
                    pass
                try:
                    merged = existing_df.merge(subset_df, on=existing_df.columns[0], how="outer")
                except Exception:
                    merged = existing_df
                category_frames[cat_name] = merged
            else:
                category_frames[cat_name] = subset_df
            if match_by_name:
                rows = [list(category_frames[cat_name].columns)]
                rows.extend([list(row) for row in category_frames[cat_name].fillna("").astype(str).values.tolist()])
                category_tables[cat_name] = {"rows": rows, "delimiter": ","}
                collect_missing_names(model, cat_name, rows, not_found)
    def prune_columns(df: Any) -> Any:
        if df is None or getattr(df, "empty", False):
            return df
        try:
            columns = list(df.columns)
        except Exception:
            return df
        if not columns:
            return df
        usable = [columns[0]]
        for column_name in columns[1:]:
            try:
                series = df[column_name]
            except Exception:
                continue
            drop = False
            try:
                if series.isna().all():
                    drop = True
            except Exception:
                pass
            if not drop:
                try:
                    if series.astype(str).str.strip().eq("").all():
                        drop = True
                except Exception:
                    pass
            if not drop:
                usable.append(column_name)
        return df[usable]
    for cat_name, cat_df in category_frames.items():
        if cat_name in file_map:
            continue
        cat_df = prune_columns(cat_df)
        if cat_df is None or getattr(cat_df, "empty", False):
            continue
        try:
            cat_df = cat_df.loc[:, ~cat_df.columns.duplicated()]
        except Exception:
            pass
        if len(cat_df.columns) <= 1:
            continue
        tmp_path = dataframe_to_temp_csv(cat_df)
        if tmp_path:
            file_map[cat_name] = tmp_path
    results: dict[str, int] = {}
    try:
        if file_map:
            results = model.import_excel_tables(file_map, match_by_name=match_by_name)  # type: ignore[attr-defined]
        else:
            results = {}
    finally:
        for p in file_map.values():
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass
    if match_by_name and not_found:
        model.import_partial_matches["excel_missing"] = {name: [] for name in sorted(not_found)}
    return results


def build_coy_file_map(base_dir: Path, workbook_dir: Path, *, download: Any) -> dict[str, str]:
    """
    Download COY sheets into CSVs and return a file map for import.
    The ``download`` callable should accept (sheet_id, sheet_name, target_path).
    """
    file_map: dict[str, str] = {}
    for cat_name, sheet_name in COY_SHEET_TABS.items():
        target = workbook_dir / f"{sheet_name}.csv"
        try:
            download(sheet_name, target)
        except Exception:
            continue
        if target.is_file():
            file_map[cat_name] = str(target)
    return file_map


__all__ = ["import_excel_workbook", "categorize_columns", "collect_missing_names", "dataframe_to_temp_csv", "build_coy_file_map"]
