from __future__ import annotations

import csv
import sqlite3
import statistics
import sys
from dataclasses import dataclass
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
OUT = ROOT / "outputs"
DB_PATH = GENERATOR_ROOT / "NBA Player Data" / "NBA_DATA_Master.sqlite"
CALIBRATION_BUCKET_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_attribute_total_summary_1947_within_001_complete.csv"
OUT_CSV = OUT / "irl_fg_pct_shooting_attribute_formula_calibration_targets_1947.csv"
OUT_MD = OUT / "irl_fg_pct_shooting_attribute_formula_calibration_targets_1947.md"

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


@dataclass(frozen=True)
class FgPctAttributeBucket:
    observed_fg_percent: float
    paired_count: int
    target_total_min: float
    target_total_max: float
    target_total_median: float
    target_total_range: float
    target_average_min: float
    target_average_max: float
    target_average_median: float
    target_average_range: float
    source_live_player: str


def num(value: Any) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text or text.lower().startswith("err:"):
            return None
        return float(text)
    except Exception:
        return None


def load_fg_pct_attribute_buckets(path: Path = CALIBRATION_BUCKET_CSV) -> list[FgPctAttributeBucket]:
    """Load the observed in-game FG% -> IRL attribute-total bucket map.

    Rows with no matched IRL FG% peers are skipped because they have no target
    min/max/median/range. The remaining rows say: an in-game FG% near X mapped
    to IRL players whose generated shooting-attribute totals had median Y.
    """

    buckets: list[FgPctAttributeBucket] = []
    for row in csv.DictReader(path.open(newline="", encoding="utf-8")):
        paired_count = int(float(row.get("paired_irl_count") or 0))
        median_total = num(row.get("paired_irl_attribute_total_median"))
        if paired_count <= 0 or median_total is None:
            continue
        buckets.append(
            FgPctAttributeBucket(
                observed_fg_percent=float(row["live_fg_percent"]),
                paired_count=paired_count,
                target_total_min=float(row["paired_irl_attribute_total_min"]),
                target_total_max=float(row["paired_irl_attribute_total_max"]),
                target_total_median=median_total,
                target_total_range=float(row["paired_irl_attribute_total_range"]),
                target_average_min=float(row["paired_irl_attribute_average_min"]),
                target_average_max=float(row["paired_irl_attribute_average_max"]),
                target_average_median=float(row["paired_irl_attribute_average_median"]),
                target_average_range=float(row["paired_irl_attribute_average_range"]),
                source_live_player=str(row["live_player"]),
            )
        )
    return sorted(buckets, key=lambda bucket: bucket.observed_fg_percent)


def weighted_median(values: list[tuple[float, float]]) -> float:
    """Return weighted median for [(value, weight), ...]."""

    if not values:
        raise ValueError("weighted_median requires at least one value")
    ordered = sorted(values, key=lambda item: item[0])
    total_weight = sum(weight for _value, weight in ordered)
    cutoff = total_weight / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= cutoff:
            return value
    return ordered[-1][0]


def estimate_target_from_irl_fg_percent(
    irl_fg_percent: float,
    buckets: list[FgPctAttributeBucket],
    *,
    window: float = 0.01,
    minimum_neighbors: int = 5,
) -> dict[str, Any]:
    """Estimate target shooting-attribute total from a player's IRL FG%.

    The calibration file is keyed by observed in-game FG%. This function treats
    that FG% axis as the lookup axis: for an IRL FG% target, find nearby observed
    FG%-bucket rows and return a robust target total/average.

    Weighting:
    - Closer FG% buckets get higher weight.
    - Buckets backed by more paired IRL players get higher weight.
    - If ±window has fewer than minimum_neighbors, nearest buckets are added.
    """

    if not buckets:
        raise ValueError("No calibration buckets available")

    selected = [bucket for bucket in buckets if abs(bucket.observed_fg_percent - irl_fg_percent) <= window]
    if len(selected) < minimum_neighbors:
        nearest = sorted(buckets, key=lambda bucket: abs(bucket.observed_fg_percent - irl_fg_percent))
        seen = {id(bucket) for bucket in selected}
        for bucket in nearest:
            if id(bucket) in seen:
                continue
            selected.append(bucket)
            seen.add(id(bucket))
            if len(selected) >= minimum_neighbors:
                break

    weighted_totals: list[tuple[float, float]] = []
    weighted_avgs: list[tuple[float, float]] = []
    for bucket in selected:
        distance = abs(bucket.observed_fg_percent - irl_fg_percent)
        closeness_weight = 1.0 / max(distance, 0.001)
        evidence_weight = max(1.0, float(bucket.paired_count)) ** 0.5
        weight = closeness_weight * evidence_weight
        weighted_totals.append((bucket.target_total_median, weight))
        weighted_avgs.append((bucket.target_average_median, weight))

    total_values = [bucket.target_total_median for bucket in selected]
    avg_values = [bucket.target_average_median for bucket in selected]
    distances = [abs(bucket.observed_fg_percent - irl_fg_percent) for bucket in selected]
    return {
        "lookup_irl_fg_percent": irl_fg_percent,
        "calibration_neighbors": len(selected),
        "calibration_fg_min": min(bucket.observed_fg_percent for bucket in selected),
        "calibration_fg_max": max(bucket.observed_fg_percent for bucket in selected),
        "calibration_closest_fg_diff": min(distances),
        "target_total_min": min(total_values),
        "target_total_max": max(total_values),
        "target_total_median": statistics.median(total_values),
        "target_total_weighted_median": weighted_median(weighted_totals),
        "target_total_range": max(total_values) - min(total_values),
        "target_average_min": min(avg_values),
        "target_average_max": max(avg_values),
        "target_average_median": statistics.median(avg_values),
        "target_average_weighted_median": weighted_median(weighted_avgs),
        "target_average_range": max(avg_values) - min(avg_values),
        "calibration_source_players": "; ".join(
            f"{bucket.source_live_player} ({bucket.observed_fg_percent:.3f}, target {bucket.target_total_median:.0f}, n {bucket.paired_count})"
            for bucket in sorted(selected, key=lambda bucket: abs(bucket.observed_fg_percent - irl_fg_percent))[:12]
        ),
    }


def load_irl_fg_percent_by_player() -> dict[str, dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    db_rows = con.execute("SELECT * FROM player_totals WHERE season = ?", (SEASON,)).fetchall()
    by_player: dict[str, list[dict[str, Any]]] = {}
    for row in db_rows:
        by_player.setdefault(str(row["player"]).strip(), []).append(dict(row))

    selected: dict[str, dict[str, Any]] = {}
    for player, rows in by_player.items():
        aggregate = [row for row in rows if str(row.get("team") or "").upper().endswith("TM")]
        if aggregate:
            row = aggregate[0]
        elif len(rows) == 1:
            row = rows[0]
        else:
            row = sorted(rows, key=lambda value: str(value.get("team") or ""))[0]
        fg_percent = num(row.get("fg_percent"))
        if fg_percent is None:
            continue
        selected[player] = {
            "irl_team": row.get("team"),
            "irl_games": num(row.get("g")),
            "irl_fgm": num(row.get("fg")),
            "irl_fga": num(row.get("fga")),
            "irl_fg_percent": fg_percent,
            "irl_source_row_count": len(rows),
        }
    return selected


def load_current_generated_shooting_attributes() -> dict[str, dict[str, Any]]:
    contract = GeneratorInputContract(
        season=SEASON,
        source_root=GeneratorSourceInventory.from_default().root,
        output_target=OutputTarget.PROPOSAL,
    ).validate()
    batch = generate_player_proposals_from_index(season_context_index(contract))
    out: dict[str, dict[str, Any]] = {}
    for proposal in batch.proposals:
        player = str(proposal.identity.get("player") or "").strip()
        by_field = proposal.by_field_key()
        values: dict[str, int] = {}
        for field in SHOOTING_ATTRIBUTE_FIELDS:
            candidate = by_field.get(field)
            if candidate is None:
                break
            values[FIELD_OUTPUT_NAMES[field]] = int(candidate.display_value)
        if len(values) != len(SHOOTING_ATTRIBUTE_FIELDS):
            continue
        total = sum(values.values())
        out[player] = {
            "current_total": total,
            "current_average": total / len(SHOOTING_ATTRIBUTE_FIELDS),
            **values,
        }
    return out


def build_formula_calibration_targets() -> list[dict[str, Any]]:
    buckets = load_fg_pct_attribute_buckets()
    irl_by_player = load_irl_fg_percent_by_player()
    generated_by_player = load_current_generated_shooting_attributes()
    rows: list[dict[str, Any]] = []
    for player, current in sorted(generated_by_player.items()):
        irl = irl_by_player.get(player)
        if not irl:
            continue
        irl_fg_percent = num(irl.get("irl_fg_percent"))
        if irl_fg_percent is None:
            continue
        target = estimate_target_from_irl_fg_percent(irl_fg_percent, buckets)
        delta_vs_weighted = current["current_total"] - target["target_total_weighted_median"]
        delta_vs_median = current["current_total"] - target["target_total_median"]
        rows.append(
            {
                "player": player,
                **irl,
                **current,
                **target,
                "delta_current_total_minus_target_weighted_median": delta_vs_weighted,
                "delta_current_total_minus_target_median": delta_vs_median,
                "recommended_direction": "lower" if delta_vs_weighted > 0 else "raise" if delta_vs_weighted < 0 else "hold",
            }
        )
    return rows


def write_outputs(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "player",
        "irl_team",
        "irl_games",
        "irl_fgm",
        "irl_fga",
        "irl_fg_percent",
        "current_total",
        "current_average",
        "target_total_weighted_median",
        "target_total_median",
        "target_total_min",
        "target_total_max",
        "target_total_range",
        "delta_current_total_minus_target_weighted_median",
        "delta_current_total_minus_target_median",
        "recommended_direction",
        "target_average_weighted_median",
        "target_average_median",
        "calibration_neighbors",
        "calibration_fg_min",
        "calibration_fg_max",
        "calibration_closest_fg_diff",
        "driving_layup",
        "standing_dunk",
        "driving_dunk",
        "close_shot",
        "midrange",
        "post_hook",
        "post_fade",
        "shot_iq",
        "offensive_consistency",
        "calibration_source_players",
        "irl_source_row_count",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    sorted_by_abs_delta = sorted(rows, key=lambda row: abs(float(row["delta_current_total_minus_target_weighted_median"])), reverse=True)
    lines = [
        "# IRL FG% -> shooting-attribute formula calibration targets",
        "",
        f"Input bucket file: `{CALIBRATION_BUCKET_CSV}`",
        f"Output CSV: `{OUT_CSV}`",
        "",
        "Method:",
        "1. Use each player's IRL FG% as the lookup value.",
        "2. Search the observed in-game FG%-bucket file for nearby FG% rows.",
        "3. Return the matched bucket's shooting-attribute target total/average.",
        "4. Compare the player's current generated shooting-attribute total to that target.",
        "",
        "This is a calibration helper only; it does not patch formulas.",
        "",
        f"Rows: {len(rows)}",
        "",
        "## Largest absolute current-total vs target-total deltas",
        "",
        "| Player | IRL FG% | Current total | Target weighted median | Delta | Direction | Sources |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in sorted_by_abs_delta[:25]:
        lines.append(
            f"| {row['player']} | {float(row['irl_fg_percent']):.3f} | {float(row['current_total']):.0f} | "
            f"{float(row['target_total_weighted_median']):.0f} | {float(row['delta_current_total_minus_target_weighted_median']):+.0f} | "
            f"{row['recommended_direction']} | {row['calibration_source_players']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows = build_formula_calibration_targets()
    write_outputs(rows)
    bob = next((row for row in rows if row["player"] == "Bob Feerick"), None)
    print(f"rows: {len(rows)}")
    print(f"csv: {OUT_CSV}")
    print(f"report: {OUT_MD}")
    if bob:
        print("Bob Feerick:")
        for key in [
            "irl_fg_percent",
            "current_total",
            "target_total_weighted_median",
            "target_total_median",
            "delta_current_total_minus_target_weighted_median",
            "recommended_direction",
            "calibration_source_players",
        ]:
            print(f"  {key}: {bob[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
