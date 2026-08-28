from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_DATABASE_NAME = "NBA_DATA_Master.sqlite"


_PHASE_ZERO_REQUIRED_SHEETS: tuple[str, ...] = (
    "Player Info",
    "Player Season Info",
    "Player Per Game",
    "Player Per 100 Poss",
    "Advanced",
    "Player Shooting",
    "Player Play by Play",
    "Team Stats Per Game",
    "Team Stats Per 100 Pos",
    "Team Summaries",
    "Opponent Stats Per Game",
    "Opponent Stats Per 100 Poss",
)


@dataclass(frozen=True)
class GeneratorSourceInventory:
    """Read-only inventory for generator source artifacts."""

    root: Path
    database_path: Path


    @classmethod
    def from_default(cls) -> "GeneratorSourceInventory":
        package_root = Path(__file__).resolve().parents[1]
        return cls.from_root(package_root / "Player Generator" / "NBA Player Data")

    @classmethod
    def from_root(cls, root: str | Path) -> "GeneratorSourceInventory":
        resolved_root = Path(root).expanduser().resolve()
        if not resolved_root.is_dir():
            raise FileNotFoundError(f"generator source root does not exist: {resolved_root}")
        inventory = cls(
            root=resolved_root,
            database_path=resolved_root / _DATABASE_NAME,
        )
        inventory._require_files()
        return inventory

    def _require_files(self) -> None:
        missing = [path for path in (self.database_path,) if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"missing generator source artifact(s): {joined}")

    def workbook_sheets(self) -> tuple[str, ...]:
        return sqlite_sheet_names(self.database_path)

    def required_phase_zero_sheets(self) -> tuple[str, ...]:
        return _PHASE_ZERO_REQUIRED_SHEETS

    def missing_required_sheets(self) -> list[str]:
        present = set(self.workbook_sheets())
        return [sheet for sheet in self.required_phase_zero_sheets() if sheet not in present]


def sqlite_sheet_names(database_path: str | Path) -> tuple[str, ...]:
    db_file = Path(database_path).expanduser().resolve()
    if not db_file.is_file():
        raise FileNotFoundError(f"generator SQLite database does not exist: {db_file}")
    with sqlite3.connect(db_file) as connection:
        rows = connection.execute("SELECT sheet_name FROM workbook_tables ORDER BY ordinal").fetchall()
    return tuple(str(row[0]) for row in rows)


__all__ = ["GeneratorSourceInventory", "sqlite_sheet_names"]
