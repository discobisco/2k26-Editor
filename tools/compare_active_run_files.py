from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OLD_ROOT = REPO / "outputs"
NEW_RUN = REPO / "outputs" / "current_active_attr_tendency_range_map" / "latest_valid_run_2026-06-20_1310" / "source_data"
OUT_DIR = REPO / "outputs" / "current_active_attr_tendency_range_map" / "latest_valid_run_2026-06-20_1310" / "comparison_vs_root_baseline"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def key(row: dict[str, str]) -> str:
    return " ".join(str(row.get("player_label", "")).split()).upper()


def numish(v: str) -> float | None:
    try:
        text = str(v).strip().replace(",", "")
        if text == "" or text.lower().startswith("err:"):
            return None
        return float(text)
    except Exception:
        return None


def index_unique(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    dupes: Counter[str] = Counter()
    for row in rows:
        k = key(row)
        if not k:
            continue
        if k in out:
            dupes[k] += 1
            continue
        out[k] = row
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def compare_table(old_path: Path, new_path: Path, table_name: str) -> dict[str, Any]:
    old_rows = read_rows(old_path)
    new_rows = read_rows(new_path)
    old = index_unique(old_rows)
    new = index_unique(new_rows)
    old_keys = set(old)
    new_keys = set(new)
    common = sorted(old_keys & new_keys)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    identity_cols = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
    if table_name == "stats":
        identity_cols.add("current_year_stat_id")
    value_cols = [c for c in (new_rows[0].keys() if new_rows else []) if c not in identity_cols]

    changed_rows: list[dict[str, Any]] = []
    numeric_deltas: list[dict[str, Any]] = []
    team_moves: list[dict[str, Any]] = []
    for k in common:
        o = old[k]
        n = new[k]
        if o.get("team_label") != n.get("team_label"):
            team_moves.append({
                "player_label": n.get("player_label") or o.get("player_label") or k,
                "old_team": o.get("team_label", ""),
                "new_team": n.get("team_label", ""),
                "old_player_index": o.get("player_index", ""),
                "new_player_index": n.get("player_index", ""),
            })
        changed_fields = []
        for col in value_cols:
            ov = o.get(col, "")
            nv = n.get(col, "")
            if ov == nv:
                continue
            changed_fields.append(col)
            on = numish(ov)
            nn = numish(nv)
            if on is not None and nn is not None:
                numeric_deltas.append({
                    "player_label": n.get("player_label") or o.get("player_label") or k,
                    "field": col,
                    "old": ov,
                    "new": nv,
                    "delta": nn - on,
                    "old_team": o.get("team_label", ""),
                    "new_team": n.get("team_label", ""),
                })
        if changed_fields:
            changed_rows.append({
                "player_label": n.get("player_label") or o.get("player_label") or k,
                "old_team": o.get("team_label", ""),
                "new_team": n.get("team_label", ""),
                "changed_field_count": len(changed_fields),
                "changed_fields_sample": "; ".join(changed_fields[:20]),
            })

    table_dir = OUT_DIR / table_name
    table_dir.mkdir(parents=True, exist_ok=True)
    write_csv(table_dir / "added_players.csv", [{"player_label": new[k].get("player_label", k), "team_label": new[k].get("team_label", ""), "player_index": new[k].get("player_index", "")} for k in added], ["player_label", "team_label", "player_index"])
    write_csv(table_dir / "removed_players.csv", [{"player_label": old[k].get("player_label", k), "team_label": old[k].get("team_label", ""), "player_index": old[k].get("player_index", "")} for k in removed], ["player_label", "team_label", "player_index"])
    write_csv(table_dir / "team_moves.csv", team_moves, ["player_label", "old_team", "new_team", "old_player_index", "new_player_index"])
    write_csv(table_dir / "changed_rows.csv", changed_rows, ["player_label", "old_team", "new_team", "changed_field_count", "changed_fields_sample"])
    top_deltas = sorted(numeric_deltas, key=lambda r: abs(float(r["delta"])), reverse=True)[:200]
    write_csv(table_dir / "top_numeric_deltas.csv", top_deltas, ["player_label", "field", "old", "new", "delta", "old_team", "new_team"])

    old_team_counts = Counter(r.get("team_label", "") for r in old_rows)
    new_team_counts = Counter(r.get("team_label", "") for r in new_rows)
    team_count_diffs = []
    for team in sorted(set(old_team_counts) | set(new_team_counts)):
        team_count_diffs.append({"team_label": team, "old_count": old_team_counts[team], "new_count": new_team_counts[team], "delta": new_team_counts[team] - old_team_counts[team]})
    write_csv(table_dir / "team_count_diffs.csv", team_count_diffs, ["team_label", "old_count", "new_count", "delta"])

    return {
        "table": table_name,
        "old_path": str(old_path),
        "new_path": str(new_path),
        "old_rows": len(old_rows),
        "new_rows": len(new_rows),
        "common_players": len(common),
        "added_players": len(added),
        "removed_players": len(removed),
        "team_moves": len(team_moves),
        "rows_with_value_changes": len(changed_rows),
        "numeric_value_changes": len(numeric_deltas),
        "top_added": [{"player_label": new[k].get("player_label", k), "team_label": new[k].get("team_label", "")} for k in added[:20]],
        "top_removed": [{"player_label": old[k].get("player_label", k), "team_label": old[k].get("team_label", "")} for k in removed[:20]],
        "team_moves_sample": team_moves[:20],
        "top_numeric_deltas_sample": top_deltas[:20],
        "team_count_diffs": team_count_diffs,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    reports.append(compare_table(OLD_ROOT / "current_active_player_stats.csv", NEW_RUN / "current_active_player_stats.csv", "stats"))
    reports.append(compare_table(OLD_ROOT / "current_active_player_attributes.csv", NEW_RUN / "current_active_player_attributes.csv", "attributes"))
    report = {"old_baseline": str(OLD_ROOT), "new_run": str(NEW_RUN), "tables": reports}
    (OUT_DIR / "comparison_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Active run comparison", "", f"Old baseline: `{OLD_ROOT}`", f"New run: `{NEW_RUN}`", ""]
    for r in reports:
        lines += [
            f"## {r['table']}",
            "",
            f"- Old rows: {r['old_rows']}",
            f"- New rows: {r['new_rows']}",
            f"- Common players: {r['common_players']}",
            f"- Added players: {r['added_players']}",
            f"- Removed players: {r['removed_players']}",
            f"- Team moves among common players: {r['team_moves']}",
            f"- Common rows with value changes: {r['rows_with_value_changes']}",
            "",
        ]
    (OUT_DIR / "comparison_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
