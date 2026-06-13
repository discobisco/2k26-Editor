from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

_WORKBOOK_NAME = "NBA DATA Master.xlsx"
_PORTRAITS_NAME = "Player Portraits.txt"
_LOGOS_NAME = "Team Logos.txt"

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
    """Read-only inventory for the checked-in Phase 0 source data."""

    root: Path
    workbook_path: Path
    portraits_path: Path
    logos_path: Path

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
            workbook_path=resolved_root / _WORKBOOK_NAME,
            portraits_path=resolved_root / _PORTRAITS_NAME,
            logos_path=resolved_root / _LOGOS_NAME,
        )
        inventory._require_files()
        return inventory

    def _require_files(self) -> None:
        missing = [path for path in (self.workbook_path, self.portraits_path, self.logos_path) if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"missing generator source artifact(s): {joined}")

    def workbook_sheets(self) -> tuple[str, ...]:
        return read_workbook_sheets(self.workbook_path)

    def sidecar_counts(self) -> dict[str, int]:
        return {
            "portraits": _json_object_count(self.portraits_path),
            "logos": _json_object_count(self.logos_path),
        }

    def required_phase_zero_sheets(self) -> tuple[str, ...]:
        return _PHASE_ZERO_REQUIRED_SHEETS

    def missing_required_sheets(self) -> list[str]:
        present = set(self.workbook_sheets())
        return [sheet for sheet in self.required_phase_zero_sheets() if sheet not in present]


def read_workbook_sheets(path: str | Path) -> tuple[str, ...]:
    workbook_path = Path(path).expanduser().resolve()
    if not workbook_path.is_file():
        raise FileNotFoundError(f"workbook does not exist: {workbook_path}")
    with zipfile.ZipFile(workbook_path) as workbook:
        with workbook.open("xl/workbook.xml") as handle:
            tree = ElementTree.parse(handle)
    namespace = {"xlsx": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = [str(element.attrib.get("name", "")).strip() for element in tree.findall(".//xlsx:sheet", namespace)]
    return tuple(sheet for sheet in sheets if sheet)


def _json_object_count(path: Path) -> int:
    payload = _read_json_object(path)
    return len(payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"source sidecar is not a JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"source sidecar is not a JSON object: {path}")
    return payload


__all__ = ["GeneratorSourceInventory", "read_workbook_sheets"]
