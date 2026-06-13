from __future__ import annotations

import json
from typing import Any

from nba2k_editor.memory.game_memory import GameMemory
from nba2k_editor.models.data_model import EditorDataModel
from nba2k_editor.models.team_record_routing import team_record_row_group, _team_record_start_index


def summarize_row(model: EditorDataModel, record_base: int, record_stride: int, index: int) -> dict[str, Any]:
    addr = int(record_base) + int(index) * int(record_stride)
    row = model._record_summary_values_for_address("NBA Records", addr, 1)
    try:
        head32 = model.memory.read_uint32(addr)
    except Exception:
        head32 = None
    try:
        head64 = model.memory.read_u64(addr)
    except Exception:
        head64 = None
    return {
        "index": index,
        "addr": hex(addr),
        "head32": None if head32 is None else hex(head32),
        "head64": None if head64 is None else hex(head64),
        "first": row.get("First Name"),
        "last": row.get("Last Name"),
        "data": row.get("Data"),
        "year": row.get("Year"),
        "team_logo": row.get("Team Logo"),
    }


def main() -> int:
    mem = GameMemory("NBA2K26.exe")
    if not mem.open_process():
        print(json.dumps({"error": "attach failed"}))
        return 2
    try:
        model = EditorDataModel(memory=mem, target_executable="NBA2K26.exe")
        teams = model.refresh_domain_items("Teams", limit=5)
        if not teams:
            print(json.dumps({"error": "no teams", "status": model.domain_status("Teams")}))
            return 1
        record_base = model.domain_base("NBA Records")
        record_stride = model.domain_stride("NBA Records")
        output: list[dict[str, Any]] = []
        for item in teams[:3]:
            start = _team_record_start_index(model, item)
            team = {
                "team_index": item.index,
                "label": item.display_label,
                "team_addr": hex(int(item.address)),
                "team_addr_low32": hex(int(item.address) & 0xFFFFFFFF),
                "current_start": start,
                "around_start": [],
                "category_first_rows": {},
                "hits_before_after": [],
            }
            if start is not None:
                for idx in range(max(0, start - 12), start + 16):
                    team["around_start"].append(summarize_row(model, record_base, record_stride, idx))
                low = int(item.address) & 0xFFFFFFFF
                for idx in range(max(0, start - 600), start + 520):
                    addr = int(record_base) + idx * int(record_stride)
                    try:
                        if int(mem.read_uint32(addr)) == low:
                            team["hits_before_after"].append(idx)
                    except Exception:
                        pass
                for section, stat in [
                    ("Single Game (Regular)", "Points"),
                    ("Single Game (Regular)", "FG Made"),
                    ("Single Game (Playoffs)", "Points"),
                    ("Season", "Points"),
                    ("Career", "Points"),
                ]:
                    row_start, count = team_record_row_group(section, stat)
                    idx = int(start) + int(row_start)
                    team["category_first_rows"][f"{section} / {stat}"] = {
                        "row_start": row_start,
                        "count": count,
                        **summarize_row(model, record_base, record_stride, idx),
                    }
            output.append(team)
        print(json.dumps(output, indent=2))
        return 0
    finally:
        mem.close()


if __name__ == "__main__":
    raise SystemExit(main())
