from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

GENERATOR = Path(__file__).resolve().parent
REPO = GENERATOR.parents[1]
SOURCE_ROOT = GENERATOR / "NBA Player Data"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(GENERATOR))

from contracts import GeneratorInputContract, OutputTarget
from player_generator import generate_player_proposals_from_index, season_context_index

SEASON = 1947
BAA_GAMES_MINIMUM_EXCLUSIVE = 10
SHOOTING_ATTRIBUTE_KEYS = frozenset(
    {
        "Attributes/DRIVINGLAYUP",
        "Attributes/STANDINGDUNK",
        "Attributes/DRIVINGDUNK",
        "Attributes/CLOSESHOT",
        "Attributes/MIDRANGE",
        "Attributes/POSTHOOK",
        "Attributes/POSTFADE",
        "Attributes/IQSHOT",
        "Attributes/OFFENSIVECONSISTENCY",
    }
)
SHOT_TYPE_TENDENCY_KEYS: tuple[str, ...] = (
    "Tendencies/BASKETUNDERSHOT",
    "Tendencies/CLOSESHOT",
    "Tendencies/MIDSHOT",
    "Tendencies/DRIVINGLAYUP",
    "Tendencies/DRIVINGDUNK",
    "Tendencies/STANDINGDUNK",
    "Tendencies/POSTUP",
    "Tendencies/FROMPOSTSHOT",
)
FEERICK_PLAYER_ID = "feeribo01"
NBL_FLOOR_PLAYERS: tuple[tuple[str, str], ...] = (
    ("George Mikan", "mikange01"),
    ("Bobby McDermott", "mcderro01"),
    ("Bob Davies", "daviebo01"),
    ("Freddie Lewis", "lewisfr01"),
    ("Al Cervi", "cervial01"),
    ("Hal Tidrick", "tidriha01"),
    ("Arnie Risen", "risenar01"),
    ("Red Holzman", "holzmre01"),
    ("Bob Carpenter", "carpebo01"),
    ("Bob Calihan", "calihro01"),
)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric, got {value!r}")
    return float(value)


def _descending_average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (-values[index], index))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        tied_value = values[order[cursor]]
        while end < len(order) and values[order[end]] == tied_value:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for position in range(cursor, end):
            ranks[order[position]] = average_rank
        cursor = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_ranks = _descending_average_ranks(left)
    right_ranks = _descending_average_ranks(right)
    left_mean = sum(left_ranks) / len(left_ranks)
    right_mean = sum(right_ranks) / len(right_ranks)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_ranks, right_ranks))
    left_ss = sum((value - left_mean) ** 2 for value in left_ranks)
    right_ss = sum((value - right_mean) ** 2 for value in right_ranks)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator else None


def _attribute_totals(proposal: Any) -> dict[str, Any]:
    candidates = [candidate for candidate in proposal.field_candidates if candidate.section == "Attributes"]
    offense = [_number(candidate.display_value, candidate.field_key) for candidate in candidates if candidate.group == "Offense"]
    defense = [_number(candidate.display_value, candidate.field_key) for candidate in candidates if candidate.group == "Defense"]
    all_attributes = [_number(candidate.display_value, candidate.field_key) for candidate in candidates]
    by_field = proposal.by_field_key()
    shooting_values = {
        field_key: _number(by_field[field_key].display_value, field_key)
        for field_key in sorted(SHOOTING_ATTRIBUTE_KEYS)
    }
    shot_type_tendencies = {
        field_key: _number(by_field[field_key].display_value, field_key)
        for field_key in SHOT_TYPE_TENDENCY_KEYS
    }
    return {
        "offense_attribute_count": len(offense),
        "defense_attribute_count": len(defense),
        "attribute_count": len(all_attributes),
        "shooting_attribute_count": len(shooting_values),
        "shooting_attribute_total": int(sum(shooting_values.values())),
        "shooting_attribute_average": sum(shooting_values.values()) / len(shooting_values),
        "shooting_attributes": shooting_values,
        "three_point_attribute": _number(by_field["Attributes/3POINT"].display_value, "Attributes/3POINT"),
        "three_point_source_rule": by_field["Attributes/3POINT"].source_rule,
        "shot_type_tendencies": shot_type_tendencies,
        "offense_total": int(sum(offense)),
        "defense_total": int(sum(defense)),
        "attribute_total": int(sum(all_attributes)),
    }


def _record(context: Any, proposal: Any) -> dict[str, Any]:
    evidence = context.evidence_for(player_id=proposal.player_id, team=proposal.team)
    return {
        "player": str(proposal.identity.get("player") or proposal.player_id),
        "player_id": str(proposal.player_id),
        "team": str(proposal.team),
        "league": str(evidence.season_info.get("lg") or "").strip().upper(),
        "games": evidence.per_game.get("g"),
        "fg_percent": evidence.per_game.get("fg_percent"),
        "ows": evidence.advanced.get("ows"),
        "dws": evidence.advanced.get("dws"),
        "ws": evidence.advanced.get("ws"),
        **_attribute_totals(proposal),
    }


def _comparison(rows: list[dict[str, Any]], total_key: str, stat_key: str) -> dict[str, Any]:
    totals = [_number(row[total_key], f"{row['player_id']}.{total_key}") for row in rows]
    stats = [_number(row[stat_key], f"{row['player_id']}.{stat_key}") for row in rows]
    total_ranks = _descending_average_ranks(totals)
    stat_ranks = _descending_average_ranks(stats)
    players: list[dict[str, Any]] = []
    for row, total_rank, stat_rank in zip(rows, total_ranks, stat_ranks):
        player_row = {
            "player": row["player"],
            "player_id": row["player_id"],
            "team": row["team"],
            total_key: row[total_key],
            stat_key: row[stat_key],
            "attribute_rank": total_rank,
            "stat_rank": stat_rank,
            "rank_delta": total_rank - stat_rank,
            "exact_rank_match": total_rank == stat_rank,
        }
        if total_key == "shooting_attribute_total":
            player_row.update(
                {
                    "shooting_attribute_average": row["shooting_attribute_average"],
                    "shooting_attributes": row["shooting_attributes"],
                    "three_point_attribute": row["three_point_attribute"],
                    "three_point_source_rule": row["three_point_source_rule"],
                    "shot_type_tendencies": row["shot_type_tendencies"],
                }
            )
        players.append(player_row)
    players.sort(key=lambda row: (row["stat_rank"], row["attribute_rank"], row["player_id"]))
    exact_matches = sum(bool(row["exact_rank_match"]) for row in players)
    return {
        "eligible_players": len(players),
        "exact_rank_matches": exact_matches,
        "exact_ranking_pass": exact_matches == len(players),
        "spearman_rank_correlation": _spearman(totals, stats),
        "players": players,
    }


def build_benchmark() -> dict[str, Any]:
    contract = GeneratorInputContract(season=SEASON, source_root=SOURCE_ROOT, output_target=OutputTarget.PREVIEW)
    context = season_context_index(contract)
    batch = generate_player_proposals_from_index(context)
    records = [_record(context, proposal) for proposal in batch.proposals]

    baa_rows = [
        row
        for row in records
        if row["league"] == "BAA"
        and _number(row["games"], f"{row['player_id']}.games") > BAA_GAMES_MINIMUM_EXCLUSIVE
        and all(
            isinstance(row[key], (int, float)) and not isinstance(row[key], bool)
            for key in ("fg_percent", "ows", "dws", "ws")
        )
    ]
    baa_rows.sort(key=lambda row: (row["player_id"], row["team"]))

    by_league_player_id: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        key = (str(row["league"]), str(row["player_id"]))
        if key in by_league_player_id:
            raise RuntimeError(f"multiple canonical generated records for 1947 league/player_id={key}")
        by_league_player_id[key] = row

    feerick = by_league_player_id.get(("BAA", FEERICK_PLAYER_ID))
    if feerick is None:
        raise RuntimeError(f"missing exact 1947 BAA Bob Feerick record: {FEERICK_PLAYER_ID}")
    feerick_total = _number(feerick["attribute_total"], f"{FEERICK_PLAYER_ID}.attribute_total")

    nbl_floor: list[dict[str, Any]] = []
    for display_name, player_id in NBL_FLOOR_PLAYERS:
        row = by_league_player_id.get(("NBL", player_id))
        found_exact_nbl_record = row is not None
        player_total: float | None = None
        if row is not None and found_exact_nbl_record:
            player_total = _number(row["attribute_total"], f"{player_id}.attribute_total")
        nbl_floor.append(
            {
                "player": display_name,
                "player_id": player_id,
                "found_exact_nbl_record": found_exact_nbl_record,
                "team": row["team"] if row is not None else None,
                "attribute_total": player_total,
                "bob_feerick_attribute_total": feerick_total,
                "meets_floor": found_exact_nbl_record and player_total is not None and player_total >= feerick_total,
            }
        )

    comparisons = {
        "shooting_attribute_total_vs_fg_percent": _comparison(
            baa_rows, "shooting_attribute_total", "fg_percent"
        ),
        "offense_total_vs_ows": _comparison(baa_rows, "offense_total", "ows"),
        "defense_total_vs_dws": _comparison(baa_rows, "defense_total", "dws"),
        "attribute_total_vs_ws": _comparison(baa_rows, "attribute_total", "ws"),
    }
    return {
        "contract": {
            "season": SEASON,
            "baa_games_filter": f"> {BAA_GAMES_MINIMUM_EXCLUSIVE}",
            "identity": "exact player_id plus canonical generated team record",
            "shooting_total": "nine 1947 aggregate-FG shooting Attributes; per-player broad shot-type Tendencies are retained in each row",
            "offense_total": "sum of authored Attributes / Offense generated candidates",
            "defense_total": "sum of authored Attributes / Defense generated candidates",
            "attribute_total": "sum of every authored Attributes generated candidate",
            "rank_method": "descending average ranks for ties",
            "baa_eligible_players": len(baa_rows),
            "generated_records": len(records),
        },
        "field_counts": {
            "shooting": sorted({row["shooting_attribute_count"] for row in records}),
            "offense": sorted({row["offense_attribute_count"] for row in records}),
            "defense": sorted({row["defense_attribute_count"] for row in records}),
            "all_attributes": sorted({row["attribute_count"] for row in records}),
        },
        "baa_comparisons": comparisons,
        "baa_all_exact_ranking_pass": all(comparison["exact_ranking_pass"] for comparison in comparisons.values()),
        "bob_feerick": feerick,
        "nbl_bob_feerick_floor": nbl_floor,
        "nbl_all_named_players_meet_floor": all(row["meets_floor"] for row in nbl_floor),
    }


def _print_summary(result: dict[str, Any]) -> None:
    contract = result["contract"]
    print(f"1947 BAA eligible players (G > 10): {contract['baa_eligible_players']}")
    for label, comparison in result["baa_comparisons"].items():
        print(
            f"{label}: exact ranks {comparison['exact_rank_matches']}/{comparison['eligible_players']}; "
            f"Spearman {comparison['spearman_rank_correlation']:.6f}; pass={comparison['exact_ranking_pass']}"
        )
    feerick_total = result["bob_feerick"]["attribute_total"]
    print(f"Bob Feerick Total Attributes: {feerick_total}")
    for row in result["nbl_bob_feerick_floor"]:
        print(f"{row['player']} ({row['player_id']}): {row['attribute_total']}; meets floor={row['meets_floor']}")
    print(f"All named NBL players meet floor: {result['nbl_all_named_players_meet_floor']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 1947 BAA/NBL PlayerGen ranking benchmark.")
    parser.add_argument("--output", type=Path, help="Optional path for the complete JSON result.")
    args = parser.parse_args()
    result = build_benchmark()
    _print_summary(result)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote: {output}")


if __name__ == "__main__":
    main()
