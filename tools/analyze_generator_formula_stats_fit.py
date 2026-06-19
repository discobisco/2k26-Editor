from __future__ import annotations

import csv
import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = REPO_ROOT / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget  # noqa: E402
from player_generator import generate_player_proposals_from_index, season_context_index  # noqa: E402
from source_data import GeneratorSourceInventory  # noqa: E402

OUT_DIR = REPO_ROOT / "outputs"
LIVE_STATS = OUT_DIR / "current_active_player_stats.csv"
COMPARISON = OUT_DIR / "live_vs_irl_1947_stats_comparison.csv"
DB_PATH = REPO_ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
OUT_CSV = OUT_DIR / "generator_formula_stats_fit_1947.csv"
OUT_JSON = OUT_DIR / "generator_formula_stats_fit_1947.json"
SEASON = 1947


def num(v: Any) -> float | None:
    try:
        text = str(v if v is not None else "").strip()
        if not text or text.lower().startswith("err:"):
            return None
        return float(text)
    except Exception:
        return None


def corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main() -> int:
    contract = GeneratorInputContract(
        season=SEASON,
        source_root=GeneratorSourceInventory.from_default().root,
        output_target=OutputTarget.PROPOSAL,
    ).validate()
    context = season_context_index(contract)
    batch = generate_player_proposals_from_index(context)
    proposals_by_name = {str(p.identity.get("player") or "").strip(): p for p in batch.proposals}

    live_rows = {r["player_label"]: r for r in csv.DictReader(LIVE_STATS.open(encoding="utf-8"))}
    # pivot comparison rows into IRL values by player/field
    comparisons: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(COMPARISON.open(encoding="utf-8")):
        player = r["player"]
        field = r["field"]
        comparisons.setdefault(player, {})[f"live_{field}"] = float(r["live_value"])
        comparisons.setdefault(player, {})[f"irl_{field}"] = float(r["irl_value"])
        comparisons.setdefault(player, {})[f"diff_{field}"] = float(r["diff_live_minus_irl"])

    rows: list[dict[str, Any]] = []
    fields = ["Tendencies/SHOT", "Tendencies/TOUCHES", "Attributes/OFFENSIVECONSISTENCY", "Attributes/MIDRANGE", "Attributes/CLOSESHOT", "Attributes/DRAWFOUL", "Attributes/FREETHROW", "Attributes/PASSACCURACY", "Tendencies/FOUL"]
    for name, live in sorted(live_rows.items()):
        proposal = proposals_by_name.get(name)
        if not proposal:
            continue
        by_field = proposal.by_field_key()
        row: dict[str, Any] = {"player": name, "team": live.get("team_label")}
        for field in fields:
            candidate = by_field.get(field)
            row[field] = candidate.display_value if candidate else ""
        for key, value in comparisons.get(name, {}).items():
            row[key] = value
        rows.append(row)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        keys = sorted({key for row in rows for key in row})
        head = ["player", "team", *fields]
        rest = [k for k in keys if k not in head]
        writer = csv.DictWriter(fh, fieldnames=[*head, *rest])
        writer.writeheader()
        writer.writerows(rows)

    metrics = {}
    for gen_field in fields:
        for target in ["irl_Field Goals Attempted", "live_Field Goals Attempted", "diff_Field Goals Attempted", "irl_Points", "live_Points", "diff_Points", "irl_Free Throws Attempted", "live_Free Throws Attempted", "diff_Free Throws Attempted"]:
            xs=[]; ys=[]
            for row in rows:
                x = num(row.get(gen_field)); y = num(row.get(target))
                if x is not None and y is not None:
                    xs.append(x); ys.append(y)
            metrics[f"{gen_field} vs {target}"] = {"n": len(xs), "r": corr(xs, ys)}
    OUT_JSON.write_text(json.dumps({"rows": len(rows), "metrics": metrics, "csv": str(OUT_CSV)}, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "csv": str(OUT_CSV), "json": str(OUT_JSON), "metrics": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
