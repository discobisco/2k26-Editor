from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from source_data import GeneratorSourceInventory

_ARCHIVE_SQL_RELATIVE_PATH = Path("NBA_Database.sql")
_ARCHIVE_SQLITE_RELATIVE_PATH = Path("nba.sqlite")
_SQL_SERVER_CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+\[dbo\]\.\[([^\]]+)\]", re.IGNORECASE)
_SQL_SERVER_COLUMN_RE = re.compile(r"^\s*\[([^\]]+)\]\s+\[?([A-Za-z0-9_]+)\]?")


@dataclass(frozen=True)
class SqlSourceInventory:
    """Read-only SQL base sources selected for generator enrichment.

    `NBA_Database.sql` is an optional SQL Server dump. Treat it as canonical
    source evidence, not as directly sqlite-queryable text.

    `nba.sqlite` is the queryable NBA SQL source shipped beside the workbook
    database.
    """

    source_root: Path
    archive_sql_dump_path: Path
    archive_sqlite_path: Path

    @classmethod
    def from_default(cls) -> "SqlSourceInventory":
        inventory = GeneratorSourceInventory.from_default()
        return cls.from_source_root(inventory.root)

    @classmethod
    def from_source_root(cls, source_root: str | Path) -> "SqlSourceInventory":
        resolved_root = Path(source_root).expanduser().resolve()
        inventory = cls(
            source_root=resolved_root,
            archive_sql_dump_path=resolved_root / _ARCHIVE_SQL_RELATIVE_PATH,
            archive_sqlite_path=resolved_root / _ARCHIVE_SQLITE_RELATIVE_PATH,
        )
        inventory._require_files()
        return inventory

    def _require_files(self) -> None:
        return None

    def sql_dump_tables(self) -> tuple[str, ...]:
        return sql_dump_table_names(self.archive_sql_dump_path)

    def sql_dump_columns(self, table_name: str) -> tuple[SqlDumpColumn, ...]:
        return sql_dump_table_columns(self.archive_sql_dump_path, table_name)

    def sqlite_tables(self) -> tuple[str, ...]:
        return sqlite_table_names(self.archive_sqlite_path)

    def sqlite_columns(self, table_name: str) -> tuple[str, ...]:
        return sqlite_table_columns(self.archive_sqlite_path, table_name)

    def sqlite_row_count(self, table_name: str) -> int:
        return sqlite_row_count(self.archive_sqlite_path, table_name)


@dataclass(frozen=True)
class SqlDumpColumn:
    name: str
    sql_type: str


@dataclass(frozen=True)
class SqlBaseTableRole:
    source: str
    table: str
    role: str


_SQL_BASE_TABLE_ROLES: tuple[SqlBaseTableRole, ...] = (
    SqlBaseTableRole("archive_sqlite", "common_player_info", "queryable player bio/common information"),
    SqlBaseTableRole("archive_sqlite", "draft_history", "queryable draft identity and pick metadata"),
    SqlBaseTableRole("archive_sqlite", "draft_combine_stats", "queryable combine measurements"),
    SqlBaseTableRole("archive_sqlite", "player", "queryable player identity list"),
    SqlBaseTableRole("archive_sqlite", "team", "queryable team identity list"),
    SqlBaseTableRole("archive_sqlite", "team_history", "queryable team history"),
    SqlBaseTableRole("archive_sqlite", "game", "queryable game result/stat table"),
    SqlBaseTableRole("archive_sqlite", "play_by_play", "queryable event-level possession log"),
)


def selected_sql_base_table_roles() -> tuple[SqlBaseTableRole, ...]:
    return _SQL_BASE_TABLE_ROLES


@lru_cache(maxsize=None)
def sql_dump_table_names(sql_dump_path: str | Path) -> tuple[str, ...]:
    path = _require_file(sql_dump_path)
    tables: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            match = _SQL_SERVER_CREATE_TABLE_RE.search(line)
            if match:
                tables.append(match.group(1))
                continue
            if tables and line.startswith("SET IDENTITY_INSERT"):
                break
    return tuple(tables)


@lru_cache(maxsize=None)
def sql_dump_table_columns(sql_dump_path: str | Path, table_name: str) -> tuple[SqlDumpColumn, ...]:
    path = _require_file(sql_dump_path)
    columns: list[SqlDumpColumn] = []
    in_target_table = False
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            create_match = _SQL_SERVER_CREATE_TABLE_RE.search(line)
            if create_match:
                if in_target_table:
                    break
                in_target_table = create_match.group(1).lower() == table_name.lower()
                continue
            if not in_target_table:
                continue
            if line.lstrip().startswith(")"):
                break
            column_match = _SQL_SERVER_COLUMN_RE.match(line)
            if column_match:
                columns.append(SqlDumpColumn(name=column_match.group(1), sql_type=column_match.group(2)))
    if not columns:
        raise KeyError(f"SQL dump table not found or has no parsed columns: {table_name}")
    return tuple(columns)


def sqlite_table_names(sqlite_path: str | Path) -> tuple[str, ...]:
    path = _require_file(sqlite_path)
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return tuple(str(row[0]) for row in rows)


def sqlite_table_columns(sqlite_path: str | Path, table_name: str) -> tuple[str, ...]:
    _validate_identifier(table_name)
    path = _require_file(sqlite_path)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    if not rows:
        raise KeyError(f"SQLite table not found or has no columns: {table_name}")
    return tuple(str(row[1]) for row in rows)


def sqlite_row_count(sqlite_path: str | Path, table_name: str) -> int:
    _validate_identifier(table_name)
    path = _require_file(sqlite_path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    if row is None:
        raise KeyError(f"SQLite table not found: {table_name}")
    return int(row[0])


def _require_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQL source file does not exist: {resolved}")
    return resolved


def _validate_identifier(identifier: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"unsafe SQL identifier: {identifier!r}")


__all__ = [
    "SqlBaseTableRole",
    "SqlDumpColumn",
    "SqlSourceInventory",
    "selected_sql_base_table_roles",
    "sql_dump_table_columns",
    "sql_dump_table_names",
    "sqlite_row_count",
    "sqlite_table_columns",
    "sqlite_table_names",
]
