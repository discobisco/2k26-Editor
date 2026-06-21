from __future__ import annotations

import ctypes
import json
import struct
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from nba2k_editor.models.data_model import EditorDataModel  # noqa: E402
from nba2k_editor.memory.game_memory import GameMemory  # noqa: E402
from nba2k_editor.memory.win32 import (  # noqa: E402
    TH32CS_SNAPMODULE,
    TH32CS_SNAPMODULE32,
    CreateToolhelp32Snapshot,
    Module32FirstW,
    Module32NextW,
    MODULEENTRY32W,
    CloseHandle,
)

OUT = REPO_ROOT / "outputs" / "current_team_staff_stadium_base_rebuild.json"
TARGET = "NBA2K26.exe"
TEAM_STRIDE = 5672
STADIUM_STRIDE = 4792
STAFF_STRIDE = 432


def _module_info(pid: int, module_name: str) -> tuple[int, int]:
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if not snap:
        raise RuntimeError("CreateToolhelp32Snapshot failed")
    me32 = MODULEENTRY32W()
    me32.dwSize = ctypes.sizeof(MODULEENTRY32W)
    try:
        if not Module32FirstW(snap, ctypes.byref(me32)):
            raise RuntimeError("Module32FirstW failed")
        while True:
            if me32.szModule == module_name:
                base = ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                return int(base), int(me32.modBaseSize)
            if not Module32NextW(snap, ctypes.byref(me32)):
                break
    finally:
        CloseHandle(snap)
    raise RuntimeError(f"module not found: {module_name}")


def _safe_wstring(memory: GameMemory, addr: int, chars: int) -> str:
    try:
        return " ".join(memory.read_wstring(addr, chars).replace("\uffff", "").split())
    except Exception:
        return ""


def _looks_label(text: str) -> bool:
    clean = "".join(ch for ch in text if ch.isprintable()).strip()
    if len(clean) < 2:
        return False
    return any(ch.isalpha() for ch in clean)


def _team_rows(memory: GameMemory, base: int) -> list[str]:
    rows = []
    for i in range(5):
        # Team name offset from learned Team row evidence.
        label = _safe_wstring(memory, base + i * TEAM_STRIDE + 738, 24)
        rows.append(label)
    return rows


def _stadium_rows(memory: GameMemory, base: int) -> list[str]:
    rows = []
    for i in range(5):
        rows.append(_safe_wstring(memory, base + i * STADIUM_STRIDE + 0, 64))
    return rows


def _staff_rows(memory: GameMemory, base: int) -> list[str]:
    rows = []
    for i in range(8):
        addr = base + i * STAFF_STRIDE
        first = _safe_wstring(memory, addr + 0x50, 24)
        last = _safe_wstring(memory, addr + 0x78, 24)
        rows.append(" ".join(part for part in (first, last) if part))
    return rows


def _score(rows: list[str]) -> int:
    return sum(1 for row in rows if _looks_label(row))


def _qword(memory: GameMemory, addr: int) -> int | None:
    try:
        return memory.read_u64(addr)
    except Exception:
        return None


def main() -> int:
    model = EditorDataModel(target_executable=TARGET)
    if not model.attach():
        raise SystemExit(f"attach failed: {model.last_status}")
    memory = model.memory
    if memory.pid is None or memory.base_addr is None:
        raise SystemExit("missing process/module base")

    player_base = model.domain_base("Players")
    module_base, module_size = _module_info(memory.pid, TARGET)
    blob = memory.read_bytes(module_base, module_size)
    needle = struct.pack("<Q", int(player_base))

    hits: list[int] = []
    pos = blob.find(needle)
    while pos != -1:
        hits.append(pos)
        pos = blob.find(needle, pos + 1)

    candidates: list[dict[str, Any]] = []
    for rva in hits:
        slots = {
            "player": rva,
            "stadium": rva + 0x18,
            "team": rva + 0x20,
            "staff": rva + 0x60,
        }
        table_ptrs = {name: _qword(memory, module_base + slot_rva) for name, slot_rva in slots.items()}
        team = _team_rows(memory, table_ptrs["team"] or 0) if table_ptrs["team"] else []
        stadium = _stadium_rows(memory, table_ptrs["stadium"] or 0) if table_ptrs["stadium"] else []
        staff = _staff_rows(memory, table_ptrs["staff"] or 0) if table_ptrs["staff"] else []
        candidates.append({
            "slot_rvas": slots,
            "table_ptrs": {k: (hex(v) if v else None) for k, v in table_ptrs.items()},
            "team_rows": team,
            "stadium_rows": stadium,
            "staff_rows": staff,
            "scores": {"team": _score(team), "stadium": _score(stadium), "staff": _score(staff)},
        })

    candidates.sort(key=lambda c: (c["scores"]["team"], c["scores"]["stadium"], c["scores"]["staff"]), reverse=True)
    best = candidates[0] if candidates else None
    result = {
        "target": TARGET,
        "attach_status": model.last_status,
        "module_base": hex(module_base),
        "module_size": module_size,
        "player_base": hex(player_base),
        "player_qword_hit_count": len(hits),
        "best_candidate": best,
        "candidates": candidates[:10],
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
