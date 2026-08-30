from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from source_data import GeneratorSourceInventory

@dataclass(frozen=True)
class WorkbookSqliteTable:
    sheet_name: str
    table_name: str
    row_count: int
    column_count: int


def ensure_workbook_sqlite_database(source_root: str | Path | None = None) -> Path:
    """Return the required generator SQLite DB path.

    The generator runtime is SQLite-only. It does not import or rebuild from
    the Excel workbook. If the DB is missing or invalid, fail loudly so the
    checked-in SQLite artifact can be restored/rebuilt out-of-band.
    """

    inventory = GeneratorSourceInventory.from_root(source_root) if source_root is not None else GeneratorSourceInventory.from_default()
    database_path = _require_database(inventory.database_path)
    if not workbook_sqlite_tables(database_path):
        raise ValueError(f"generator SQLite database has no workbook table metadata: {database_path}")
    return database_path


def workbook_sqlite_tables(database_path: str | Path) -> tuple[WorkbookSqliteTable, ...]:
    database_file = _require_database(database_path)
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            """
            SELECT sheet_name, table_name, row_count, column_count
            FROM workbook_tables
            ORDER BY ordinal
            """
        ).fetchall()
    return tuple(
        WorkbookSqliteTable(
            sheet_name=str(row[0]),
            table_name=str(row[1]),
            row_count=int(row[2]),
            column_count=int(row[3]),
        )
        for row in rows
    )


def workbook_sqlite_sheet_names(database_path: str | Path) -> tuple[str, ...]:
    return tuple(table.sheet_name for table in workbook_sqlite_tables(database_path))


def iter_workbook_sqlite_sheet_rows(database_path: str | Path, sheet_name: str) -> tuple[dict[str, Any], ...]:
    database_file = _require_database(database_path)
    table_name = _table_name_for_sheet(database_file, sheet_name)
    with sqlite3.connect(database_file) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f'SELECT * FROM "{table_name}"').fetchall()
    return tuple(dict(row) for row in rows)


def query_rows_for_season(
    database_path: str | Path,
    table_name: str,
    season: int,
    *,
    limit: int | None = None,
) -> tuple[dict[str, Any], ...]:
    _validate_identifier(table_name)
    database_file = _require_database(database_path)
    sql = f'SELECT * FROM "{table_name}" WHERE "season" = ?'
    params: list[Any] = [int(season)]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(database_file) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(sql, params).fetchall()
    return tuple(dict(row) for row in rows)


def _table_name_for_sheet(database_path: Path, sheet_name: str) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT table_name FROM workbook_tables WHERE sheet_name = ?",
            (sheet_name,),
        ).fetchone()
    if row is None:
        raise KeyError(f"workbook sheet not found in SQLite database: {sheet_name}")
    return str(row[0])


def _require_database(path: str | Path) -> Path:
    database_file = Path(path).expanduser().resolve()
    if not database_file.is_file():
        raise FileNotFoundError(f"generator SQLite database does not exist: {database_file}")
    return database_file


def _validate_identifier(identifier: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"unsafe SQL identifier: {identifier!r}")


__all__ = [
    "WorkbookSqliteTable",
    "ensure_workbook_sqlite_database",
    "iter_workbook_sqlite_sheet_rows",
    "query_rows_for_season",
    "workbook_sqlite_sheet_names",
    "workbook_sqlite_tables",
]
