from __future__ import annotations

import csv
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
OUT = ROOT / "outputs"
PAIR_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_pairs_1947_within_001.csv"
BASE_SUMMARY_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_summary_1947_within_001.csv"
DETAIL_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_pairs_1947_within_001_with_irl_attribute_totals.csv"
SUMMARY_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_attribute_total_summary_1947_within_001_complete.csv"

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


def load_attribute_totals() -> dict[str, dict[str, Any]]:
    contract = GeneratorInputContract(
        season=SEASON,
        source_root=GeneratorSourceInventory.from_default().root,
        output_target=OutputTarget.PROPOSAL,
    ).validate()
    batch = generate_player_proposals_from_index(season_context_index(contract))
    totals: dict[str, dict[str, Any]] = {}
    for proposal in batch.proposals:
        player = str(proposal.identity.get("player") or "").strip()
        by_field = proposal.by_field_key()
        values: dict[str, int] = {}
        missing: list[str] = []
        for field in SHOOTING_ATTRIBUTE_FIELDS:
            candidate = by_field.get(field)
            if candidate is None:
                missing.append(field)
            else:
                values[field] = int(candidate.display_value)
        if missing:
            continue
        total = sum(values.values())
        totals[player] = {
            "shooting_attribute_total": total,
            "shooting_attribute_average": total / len(SHOOTING_ATTRIBUTE_FIELDS),
            **{field.replace("Attributes/", "").lower(): value for field, value in values.items()},
        }
    return totals


def f(value: Any) -> float:
    return float(value)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    attr_by_player = load_attribute_totals()
    pair_rows = list(csv.DictReader(PAIR_CSV.open(newline="", encoding="utf-8")))

    detail_rows: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    missing_attr_players: set[str] = set()

    for row in pair_rows:
        irl_player = str(row["irl_player"])
        attrs = attr_by_player.get(irl_player)
        if attrs is None:
            missing_attr_players.add(irl_player)
            continue
        detail = {
            **row,
            "irl_shooting_attribute_total": attrs["shooting_attribute_total"],
            "irl_shooting_attribute_average": attrs["shooting_attribute_average"],
        }
        detail_rows.append(detail)
        grouped.setdefault(str(row["live_player"]), []).append(detail)

    summary_rows: list[dict[str, Any]] = []
    base_live_rows = list(csv.DictReader(BASE_SUMMARY_CSV.open(newline="", encoding="utf-8")))
    for base in base_live_rows:
        live_player = str(base["live_player"])
        matches = grouped.get(live_player, [])
        if not matches:
            summary_rows.append(
                {
                    "live_player": live_player,
                    "live_team": base["live_team"],
                    "live_player_index": base["live_player_index"],
                    "live_fg_percent": base["live_fg_percent"],
                    "paired_irl_count": 0,
                    "paired_irl_attribute_total_min": "",
                    "paired_irl_attribute_total_max": "",
                    "paired_irl_attribute_total_median": "",
                    "paired_irl_attribute_total_range": "",
                    "paired_irl_attribute_average_min": "",
                    "paired_irl_attribute_average_max": "",
                    "paired_irl_attribute_average_median": "",
                    "paired_irl_attribute_average_range": "",
                    "paired_irl_players_with_totals": "",
                }
            )
            continue
        totals = sorted(f(row["irl_shooting_attribute_total"]) for row in matches)
        avgs = sorted(f(row["irl_shooting_attribute_average"]) for row in matches)
        min_total = min(totals)
        max_total = max(totals)
        median_total = statistics.median(totals)
        min_avg = min(avgs)
        max_avg = max(avgs)
        median_avg = statistics.median(avgs)
        first = matches[0]
        sorted_matches = sorted(
            matches,
            key=lambda row: (f(row["abs_fg_percent_diff"]), str(row["irl_player"])),
        )
        summary_rows.append(
            {
                "live_player": live_player,
                "live_team": first["live_team"],
                "live_player_index": first["live_player_index"],
                "live_fg_percent": first["live_fg_percent"],
                "paired_irl_count": len(matches),
                "paired_irl_attribute_total_min": min_total,
                "paired_irl_attribute_total_max": max_total,
                "paired_irl_attribute_total_median": median_total,
                "paired_irl_attribute_total_range": max_total - min_total,
                "paired_irl_attribute_average_min": min_avg,
                "paired_irl_attribute_average_max": max_avg,
                "paired_irl_attribute_average_median": median_avg,
                "paired_irl_attribute_average_range": max_avg - min_avg,
                "paired_irl_players_with_totals": "; ".join(
                    f"{row['irl_player']} ({float(row['irl_fg_percent']):.3f}, total {int(float(row['irl_shooting_attribute_total']))}, diff {float(row['abs_fg_percent_diff']):.3f})"
                    for row in sorted_matches
                ),
            }
        )

    detail_rows.sort(key=lambda row: (str(row["live_player"]), f(row["abs_fg_percent_diff"]), str(row["irl_player"])))
    summary_rows.sort(key=lambda row: str(row["live_player"]))

    detail_fields = list(detail_rows[0].keys()) if detail_rows else []
    with DETAIL_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=detail_fields)
        writer.writeheader()
        writer.writerows(detail_rows)

    summary_fields = [
        "live_player",
        "live_team",
        "live_player_index",
        "live_fg_percent",
        "paired_irl_count",
        "paired_irl_attribute_total_min",
        "paired_irl_attribute_total_max",
        "paired_irl_attribute_total_median",
        "paired_irl_attribute_total_range",
        "paired_irl_attribute_average_min",
        "paired_irl_attribute_average_max",
        "paired_irl_attribute_average_median",
        "paired_irl_attribute_average_range",
        "paired_irl_players_with_totals",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    bob = next((row for row in summary_rows if row["live_player"] == "Bob Feerick"), None)
    print(f"input pair rows: {len(pair_rows)}")
    print(f"detail rows with IRL attribute totals: {len(detail_rows)}")
    print(f"summary rows: {len(summary_rows)}")
    print(f"missing IRL attribute players: {len(missing_attr_players)}")
    print(f"detail csv: {DETAIL_CSV}")
    print(f"summary csv: {SUMMARY_CSV}")
    if bob:
        print("Bob Feerick summary:")
        for key in [
            "live_fg_percent",
            "paired_irl_count",
            "paired_irl_attribute_total_min",
            "paired_irl_attribute_total_max",
            "paired_irl_attribute_total_median",
            "paired_irl_attribute_total_range",
            "paired_irl_players_with_totals",
        ]:
            print(f"  {key}: {bob[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
