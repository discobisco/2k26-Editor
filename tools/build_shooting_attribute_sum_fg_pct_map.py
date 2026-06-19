from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = ROOT / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget  # noqa: E402
from player_generator import generate_player_proposals_from_index, season_context_index  # noqa: E402
from source_data import GeneratorSourceInventory  # noqa: E402

SEASON = 1947
OUT_DIR = ROOT / "outputs"
LIVE_STATS_CSV = OUT_DIR / "current_active_player_stats.csv"
OUT_CSV = OUT_DIR / "shooting_attribute_sum_vs_live_fg_pct_1947.csv"
OUT_NO_HAWKS_CSV = OUT_DIR / "shooting_attribute_sum_vs_live_fg_pct_1947_no_hawks.csv"
REPORT_JSON = OUT_DIR / "shooting_attribute_sum_vs_live_fg_pct_1947_summary.json"
EXCLUDED_TEAM_LABELS = {"Atlanta Hawks"}

SHOOTING_ATTRIBUTE_FIELDS = (
    "Attributes/DRIVINGLAYUP",
    "Attributes/STANDINGDUNK",
    "Attributes/DRIVINGDUNK",
    "Attributes/CLOSESHOT",
    "Attributes/MIDRANGE",
    "Attributes/POSTHOOK",
    "Attributes/POSTFADE",
    "Attributes/IQSHOT",
    "Attributes/OFFENSIVECONSISTENCY",
)

FIELD_OUTPUT_NAMES = {
    "Attributes/DRIVINGLAYUP": "driving_layup",
    "Attributes/STANDINGDUNK": "standing_dunk",
    "Attributes/DRIVINGDUNK": "driving_dunk",
    "Attributes/CLOSESHOT": "close_shot",
    "Attributes/MIDRANGE": "midrange",
    "Attributes/POSTHOOK": "post_hook",
    "Attributes/POSTFADE": "post_fade",
    "Attributes/IQSHOT": "shot_iq",
    "Attributes/OFFENSIVECONSISTENCY": "offensive_consistency",
}


def num(value: Any) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text or text.lower().startswith("err:"):
            return None
        return float(text)
    except Exception:
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    sx = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    sy = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (sx * sy)


def build_rows() -> list[dict[str, Any]]:
    contract = GeneratorInputContract(
        season=SEASON,
        source_root=GeneratorSourceInventory.from_default().root,
        output_target=OutputTarget.PROPOSAL,
    ).validate()
    batch = generate_player_proposals_from_index(season_context_index(contract))
    proposals_by_player = {
        str(proposal.identity.get("player") or "").strip(): proposal
        for proposal in batch.proposals
    }

    rows: list[dict[str, Any]] = []
    for live in csv.DictReader(LIVE_STATS_CSV.open(newline="", encoding="utf-8")):
        player = str(live.get("player_label") or "").strip()
        proposal = proposals_by_player.get(player)
        if proposal is None:
            continue
        fgm = num(live.get("Field Goals Made"))
        fga = num(live.get("Field Goals Attempted"))
        gp = num(live.get("Games Played"))
        if fgm is None or fga is None or fga <= 0:
            continue
        by_field = proposal.by_field_key()
        attr_values: dict[str, int] = {}
        missing: list[str] = []
        for field in SHOOTING_ATTRIBUTE_FIELDS:
            candidate = by_field.get(field)
            if candidate is None:
                missing.append(field)
                continue
            attr_values[FIELD_OUTPUT_NAMES[field]] = int(candidate.display_value)
        if missing:
            continue
        total = sum(attr_values.values())
        row: dict[str, Any] = {
            "player": player,
            "live_team_label": live.get("team_label"),
            "player_index": live.get("player_index"),
            "games_played": gp,
            "field_goals_made": fgm,
            "field_goals_attempted": fga,
            "live_fg_percent": fgm / fga,
            "live_fga_per_game": None if gp is None or gp <= 0 else fga / gp,
            "shooting_attribute_sum": total,
            "shooting_attribute_average": total / len(SHOOTING_ATTRIBUTE_FIELDS),
        }
        row.update(attr_values)
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "player",
        "live_team_label",
        "player_index",
        "games_played",
        "field_goals_made",
        "field_goals_attempted",
        "live_fg_percent",
        "live_fga_per_game",
        "shooting_attribute_sum",
        "shooting_attribute_average",
        "driving_layup",
        "standing_dunk",
        "driving_dunk",
        "close_shot",
        "midrange",
        "post_hook",
        "post_fade",
        "shot_iq",
        "offensive_consistency",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    xs = [float(row["shooting_attribute_sum"]) for row in rows]
    ys = [float(row["live_fg_percent"]) for row in rows]
    bob = next((row for row in rows if row["player"] == "Bob Feerick"), None)
    return {
        "rows": len(rows),
        "attribute_fields": list(SHOOTING_ATTRIBUTE_FIELDS),
        "sum_vs_live_fg_percent_pearson_r": pearson(xs, ys),
        "attribute_sum_min": min(xs) if xs else None,
        "attribute_sum_max": max(xs) if xs else None,
        "attribute_sum_mean": statistics.mean(xs) if xs else None,
        "live_fg_percent_min": min(ys) if ys else None,
        "live_fg_percent_max": max(ys) if ys else None,
        "live_fg_percent_mean": statistics.mean(ys) if ys else None,
        "bob_feerick": bob,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    rows.sort(key=lambda row: (str(row["player"])))
    no_hawks = [row for row in rows if row.get("live_team_label") not in EXCLUDED_TEAM_LABELS]
    write_csv(OUT_CSV, rows)
    write_csv(OUT_NO_HAWKS_CSV, no_hawks)
    summary = {
        "all_players": summarize(rows),
        "no_hawks": summarize(no_hawks),
        "outputs": {
            "all_players_csv": str(OUT_CSV),
            "no_hawks_csv": str(OUT_NO_HAWKS_CSV),
        },
    }
    REPORT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
