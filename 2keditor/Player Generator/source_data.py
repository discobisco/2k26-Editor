from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_DATABASE_NAME = "NBA_DATA_Master.sqlite"


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


__all__ = ["GeneratorSourceInventory"]
