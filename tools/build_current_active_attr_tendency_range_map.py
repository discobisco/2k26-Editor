from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path
from statistics import mean, median
from typing import Any

from active_export_runs import active_export_paths, latest_run_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN_DIR = latest_run_dir(REPO_ROOT)
SOURCE_PATHS = active_export_paths(SOURCE_RUN_DIR)
MAP_ROOT = SOURCE_RUN_DIR / "current_active_attr_tendency_range_map"
SOURCE_DIR = MAP_ROOT / "source_data"
DERIVED_DIR = MAP_ROOT / "derived_outputs"
SUPPORT_DIR = MAP_ROOT / "supporting_analysis"

IDENTITY = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
STAT_FILES = {
    "stats": SOURCE_PATHS["stats_csv"],
    "attributes": SOURCE_PATHS["attributes_csv"],
    "tendencies": SOURCE_PATHS["tendencies_csv"],
}

COUNTING_STATS = {
    "Points": "PTS",
    "Assists": "AST",
    "Blocks": "BLK",
    "Fouls": "PF",
    "Steals": "STL",
    "Turnovers": "TOV",
    "Defensive Rebounds": "DREB",
    "Offensive Rebounds": "ORB",
    "Field Goals Attempted": "FGA",
    "Field Goals Made": "FGM",
    "Free Throws Attempted": "FTA",
    "Free Throws Made": "FTM",
    "Three Pointers Attempted": "3PA",
    "Three Pointers Made": "3PM",
    "Total +/-": "+/-",
}

ATTRIBUTE_BINS = [(25, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 99.000001)]
TENDENCY_BINS = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 100.000001)]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text or text.lower().startswith("err:"):
        return None
    try:
        return float(text)
    except Exception:
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sx = math.sqrt(sum(x * x for x in dx))
    sy = math.sqrt(sum(y * y for y in dy))
    if sx <= 0 or sy <= 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


def fmt(v: float | None) -> str:
    if v is None:
        return ""
    if abs(v) >= 100:
        return f"{v:.1f}"
    if abs(v) >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"


def stat_features(row: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    gp = num(row.get("Games Played")) or 0.0
    gs = num(row.get("Games Started")) or 0.0
    minutes = num(row.get("Minutes")) or 0.0
    if gp > 0:
        out["GP"] = gp
        out["GS"] = gs
        out["GS%"] = gs / gp * 100.0
        out["MP/g"] = minutes / gp
    if minutes > 0:
        out["Minutes"] = minutes
    raw: dict[str, float] = {}
    for col, short in COUNTING_STATS.items():
        v = num(row.get(col))
        if v is None:
            continue
        raw[short] = v
        if gp > 0:
            out[f"{short}/g"] = v / gp
        if minutes > 0:
            out[f"{short}/36"] = v / minutes * 36.0
    fgm, fga = raw.get("FGM"), raw.get("FGA")
    tpm, tpa = raw.get("3PM"), raw.get("3PA")
    ftm, fta = raw.get("FTM"), raw.get("FTA")
    pts = raw.get("PTS")
    if fgm is not None and fga and fga > 0:
        out["FG%"] = fgm / fga * 100.0
    if tpm is not None and tpa and tpa > 0:
        out["3P%"] = tpm / tpa * 100.0
    if ftm is not None and fta and fta > 0:
        out["FT%"] = ftm / fta * 100.0
    if tpa is not None and fga and fga > 0:
        out["3PAr"] = tpa / fga * 100.0
    if fta is not None and fga and fga > 0:
        out["FTr"] = fta / fga * 100.0
    if pts is not None and fga and fga > 0:
        out["PTS/FGA"] = pts / fga
    if fgm is not None and tpm is not None and fga and fga > 0:
        out["eFG%"] = (fgm + 0.5 * tpm) / fga * 100.0
    if pts is not None and fga is not None and fta is not None and (2 * (fga + 0.44 * fta)) > 0:
        out["TS%"] = pts / (2 * (fga + 0.44 * fta)) * 100.0
    dreb, oreb = raw.get("DREB"), raw.get("ORB")
    if dreb is not None and oreb is not None:
        reb = dreb + oreb
        if gp > 0:
            out["REB/g"] = reb / gp
        if minutes > 0:
            out["REB/36"] = reb / minutes * 36.0
    return out


def qualified_indices(stats_rows: list[dict[str, str]]) -> set[str]:
    ok: set[str] = set()
    for row in stats_rows:
        gs = num(row.get("Games Started")) or 0.0
        minutes = num(row.get("Minutes")) or 0.0
        if gs >= 25 and minutes > 0:
            ok.add(str(row.get("player_index", "")))
    return ok


def best_for_field(field: str, field_rows: list[dict[str, str]], feature_by_player: dict[str, dict[str, float]], q: set[str]) -> dict[str, Any] | None:
    values_by_player: dict[str, float] = {}
    for row in field_rows:
        pid = str(row.get("player_index", ""))
        if pid not in q:
            continue
        v = num(row.get(field))
        if v is None:
            continue
        values_by_player[pid] = v
    best: dict[str, Any] | None = None
    stat_names = sorted({k for pid in values_by_player for k in feature_by_player.get(pid, {})})
    for stat in stat_names:
        xs: list[float] = []
        ys: list[float] = []
        for pid, field_value in values_by_player.items():
            stat_value = feature_by_player.get(pid, {}).get(stat)
            if stat_value is None:
                continue
            xs.append(field_value)
            ys.append(stat_value)
        r = pearson(xs, ys)
        if r is None:
            continue
        row = {"field": field, "best_stat": stat, "r": r, "abs_r": abs(r), "n": len(xs)}
        if best is None or (row["abs_r"], row["n"]) > (best["abs_r"], best["n"]):
            best = row
    return best


def bin_rows(field: str, kind: str, best: dict[str, Any], field_rows: list[dict[str, str]], feature_by_player: dict[str, dict[str, float]], q: set[str]) -> list[dict[str, Any]]:
    stat = str(best["best_stat"])
    bins = ATTRIBUTE_BINS if kind == "attribute" else TENDENCY_BINS
    values: list[tuple[float, float]] = []
    for row in field_rows:
        pid = str(row.get("player_index", ""))
        if pid not in q:
            continue
        fv = num(row.get(field))
        sv = feature_by_player.get(pid, {}).get(stat)
        if fv is None or sv is None:
            continue
        values.append((fv, sv))
    out: list[dict[str, Any]] = []
    for lo, hi in bins:
        vals = [sv for fv, sv in values if lo <= fv < hi]
        label_hi = int(hi) if hi < 100.000001 else (99 if kind == "attribute" else 100)
        out.append({
            "kind": kind,
            "field": field,
            "best_stat": stat,
            "r": best["r"],
            "n": best["n"],
            "value_range": f"{int(lo)}-{label_hi}",
            "players": len(vals),
            "stat_mean": mean(vals) if vals else None,
            "stat_median": median(vals) if vals else None,
            "stat_min": min(vals) if vals else None,
            "stat_max": max(vals) if vals else None,
        })
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    for path in STAT_FILES.values():
        shutil.copy2(path, SOURCE_DIR / path.name)
    stats = read_csv(STAT_FILES["stats"])
    attrs = read_csv(STAT_FILES["attributes"])
    tends = read_csv(STAT_FILES["tendencies"])
    q = qualified_indices(stats)
    feature_by_player = {str(row.get("player_index", "")): stat_features(row) for row in stats}

    attr_fields = [f for f in attrs[0] if f not in IDENTITY]
    tend_fields = [f for f in tends[0] if f not in IDENTITY]
    best_rows: list[dict[str, Any]] = []
    bin_out: list[dict[str, Any]] = []
    for kind, rows, fields in (("attribute", attrs, attr_fields), ("tendency", tends, tend_fields)):
        for field in fields:
            best = best_for_field(field, rows, feature_by_player, q)
            if not best:
                continue
            best = {"kind": kind, **best}
            best_rows.append(best)
            bin_out.extend(bin_rows(field, kind, best, rows, feature_by_player, q))

    best_rows.sort(key=lambda r: (r["kind"], str(r["field"])))
    public_best_rows = [
        {"kind": r["kind"], "field": r["field"], "selected_stat": r["best_stat"], "players": r["n"]}
        for r in best_rows
    ]
    public_bin_rows = [
        {
            "kind": r["kind"],
            "field": r["field"],
            "selected_stat": r["best_stat"],
            "value_range": r["value_range"],
            "players": r["players"],
            "stat_mean": r["stat_mean"],
            "stat_median": r["stat_median"],
            "stat_min": r["stat_min"],
            "stat_max": r["stat_max"],
        }
        for r in bin_out
    ]
    write_csv(DERIVED_DIR / "current_active_attr_tendency_best_stat_ranges_min25_starts.csv", public_best_rows, ["kind", "field", "selected_stat", "players"])
    write_csv(DERIVED_DIR / "current_active_attr_tendency_best_stat_range_bins_min25_starts.csv", public_bin_rows, ["kind", "field", "selected_stat", "value_range", "players", "stat_mean", "stat_median", "stat_min", "stat_max"])
    (DERIVED_DIR / "current_active_attr_tendency_best_stat_ranges_min25_starts.json").write_text(json.dumps({"qualified_players": len(q), "selected_stats": public_best_rows, "stat_value_bins": public_bin_rows}, indent=2), encoding="utf-8")

    md = [
        "# Current active attribute/tendency stat-value ranges",
        "",
        f"Filter: {len(q)} qualified players, 25+ starts, minutes > 0.",
        f"Source rows: stats={len(stats)}, attributes={len(attrs)}, tendencies={len(tends)}.",
        "Each field shows the selected stat's actual values beside each game-value range.",
        "",
    ]
    for kind in ("attribute", "tendency"):
        md.append(f"## {kind.title()}s")
        md.append("")
        for best in [r for r in best_rows if r["kind"] == kind]:
            md.append(f"### {best['field']}")
            md.append("")
            md.append(f"Selected stat: `{best['best_stat']}`  |  players={best['n']}")
            md.append("")
            md.append("| Value range | Players | Stat mean | Stat median | Stat min | Stat max |")
            md.append("|---|---:|---:|---:|---:|---:|")
            for b in [x for x in bin_out if x["kind"] == kind and x["field"] == best["field"]]:
                md.append(f"| {b['value_range']} | {b['players']} | {fmt(b['stat_mean'])} | {fmt(b['stat_median'])} | {fmt(b['stat_min'])} | {fmt(b['stat_max'])} |")
            md.append("")
    md_path = DERIVED_DIR / "current_active_attr_tendency_best_stat_ranges_WITH_STATS_min25_starts.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    # Compatibility copies matching prior artifact split names, with stat values as the visible data.
    write_csv(DERIVED_DIR / "current_active_attribute_best_stat_ranges_min25_starts.csv", [r for r in public_best_rows if r["kind"] == "attribute"], ["kind", "field", "selected_stat", "players"])
    write_csv(DERIVED_DIR / "current_active_tendency_best_stat_ranges_min25_starts.csv", [r for r in public_best_rows if r["kind"] == "tendency"], ["kind", "field", "selected_stat", "players"])
    write_csv(DERIVED_DIR / "current_active_attribute_best_stat_range_bins_min25_starts.csv", [r for r in public_bin_rows if r["kind"] == "attribute"], ["kind", "field", "selected_stat", "value_range", "players", "stat_mean", "stat_median", "stat_min", "stat_max"])
    write_csv(DERIVED_DIR / "current_active_tendency_best_stat_range_bins_min25_starts.csv", [r for r in public_bin_rows if r["kind"] == "tendency"], ["kind", "field", "selected_stat", "value_range", "players", "stat_mean", "stat_median", "stat_min", "stat_max"])

    print(json.dumps({
        "source_run_dir": str(SOURCE_RUN_DIR),
        "output_dir": str(MAP_ROOT),
        "qualified_players": len(q),
        "stats_rows": len(stats),
        "attribute_rows": len(attrs),
        "tendency_rows": len(tends),
        "attribute_fields": len(attr_fields),
        "tendency_fields": len(tend_fields),
        "best_rows": len(best_rows),
        "md": str(md_path),
        "csv": str(DERIVED_DIR / "current_active_attr_tendency_best_stat_ranges_min25_starts.csv"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
