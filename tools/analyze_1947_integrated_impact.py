from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GEN_DIR = REPO_ROOT / "nba2k_editor" / "Player Generator"
for path in (REPO_ROOT, GEN_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contracts import GeneratorInputContract, OutputTarget  # noqa: E402
from player_generator import generate_player_proposals_from_index, season_context_index  # noqa: E402
from source_data import GeneratorSourceInventory  # noqa: E402

SEASON = 1947
OUT_DIR = REPO_ROOT / "outputs"
ANALYSIS_DIR = OUT_DIR / "1947_integrated_analysis"
FIELD_ROWS_CSV = OUT_DIR / "current_live_vs_irl_1947_field_comparison_rows.csv"
PLAYOFF_ROWS_CSV = OUT_DIR / "sim_1947_playoff_leader_screenshot_rows.csv"
POSTSEASON_JSON = OUT_DIR / "sim_1947_postseason_result.json"
DB_PATH = GEN_DIR / "NBA Player Data" / "NBA_DATA_Master.sqlite"

POSITIONS = ("PG", "SG", "SF", "PF", "C")
REGULAR_STAT_FIELDS_FOR_MAE = (
    "Points",
    "Field Goals Attempted",
    "Field Goals Made",
    "Free Throws Attempted",
    "Free Throws Made",
    "Assists",
    "Fouls",
    "Three Pointers Attempted",
    "Three Pointers Made",
)


def norm(text: object) -> str:
    base = "".join(
        ch for ch in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(ch)
    ).lower()
    base = base.replace(".", "").replace("'", "")
    base = re.sub(r"\bjr\b|\bsr\b|\bii\b|\biii\b|\biv\b", "", base)
    return re.sub(r"[^a-z0-9]+", "", base)


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if text == "" or text.lower() in {"none", "null", "dnq"} or text.lower().startswith("err:"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def mean(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    return sum(clean) / len(clean) if clean else None


def pct_rank(values: list[float | None], value: float | None, *, reverse: bool = False) -> float | None:
    clean = sorted(float(v) for v in values if v is not None and not math.isnan(float(v)))
    if not clean or value is None:
        return None
    value = float(value)
    below = sum(1 for v in clean if v < value)
    equal = sum(1 for v in clean if v == value)
    pct = (below + 0.5 * equal) / len(clean) * 100.0
    return 100.0 - pct if reverse else pct


def weighted(parts: list[tuple[float | None, float]]) -> float:
    return sum((0.0 if value is None else float(value)) * weight for value, weight in parts)


def safe_div(a: float | None, b: float | None) -> float | None:
    return None if a is None or b in (None, 0) else a / b


def load_positions() -> dict[str, dict[str, Any]]:
    contract = GeneratorInputContract(
        SEASON, GeneratorSourceInventory.from_default().root, OutputTarget.PROPOSAL
    ).validate()
    batch = generate_player_proposals_from_index(season_context_index(contract))
    by_name: dict[str, dict[str, Any]] = {}
    for proposal in batch.proposals:
        fields = proposal.by_field_key()
        player = str(proposal.identity.get("player") or proposal.player_id)
        pos = str(fields.get("Vitals/POSITION").display_value if fields.get("Vitals/POSITION") else "").strip().upper()
        sec = str(
            fields.get("Vitals/SECONDARYPOSITION").display_value
            if fields.get("Vitals/SECONDARYPOSITION")
            else ""
        ).strip().upper()
        by_name[norm(player)] = {
            "player": player,
            "primary_pos": pos,
            "secondary_pos": sec,
            "source_player_id": proposal.player_id,
            "generated_team": proposal.team,
        }
    return by_name


def load_regular_rows() -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    with FIELD_ROWS_CSV.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_player: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        for key in ("live_total", "irl_total", "live_pg", "irl_pg", "diff_pg"):
            row[key] = num(row.get(key))
        by_player[str(row["player"])] [str(row["field"])] = row
    return rows, by_player


def build_abbrev_mapping(full_names: list[str], playoff_rows: list[dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    by_last_initial: dict[tuple[str, str], list[str]] = defaultdict(list)
    for full in full_names:
        parts = str(full).split()
        if not parts:
            continue
        by_last_initial[(parts[0][0].upper(), norm(" ".join(parts[1:]) if len(parts) > 1 else parts[-1]))].append(full)
        by_last_initial[(parts[0][0].upper(), norm(parts[-1]))].append(full)

    mapping: dict[str, str] = {}
    issues: list[dict[str, Any]] = []
    for row in playoff_rows:
        short = str(row["name"]).strip()
        if short in mapping:
            continue
        match = re.match(r"^([A-Z])\.\s+(.+)$", short)
        if not match:
            issues.append({"abbrev": short, "issue": "unsupported abbreviated form", "candidates": []})
            continue
        key = (match.group(1).upper(), norm(match.group(2)))
        candidates = sorted(set(by_last_initial.get(key, [])))
        if len(candidates) == 1:
            mapping[short] = candidates[0]
        else:
            issues.append({"abbrev": short, "issue": "unmatched" if not candidates else "ambiguous", "candidates": candidates})
    return mapping, issues


def load_playoff_rows(full_names: list[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    with PLAYOFF_ROWS_CSV.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for key in ("rank", "gs", "gp"):
            value = num(row.get(key))
            row[key] = None if value is None else int(value)
        for key in ("min", "pts", "reb", "ast", "stl", "blk", "to", "fls", "fg_pct"):
            row[key] = num(row.get(key))
        row["fg_pct_qualified"] = str(row.get("fg_pct_qualified", "")).lower() == "true"
    mapping, issues = build_abbrev_mapping(full_names, rows)
    by_player: dict[str, dict[str, Any]] = {}
    visible_rankings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        full = mapping.get(str(row["name"]).strip())
        if not full:
            continue
        visible_rankings[full].append({
            "sort_category": row["sort_category"],
            "rank": row["rank"],
            "source_image": row["source_image"],
        })
        record = by_player.setdefault(full, {"player": full})
        # Duplicate rows for the same player should agree. Fill missing fields and prefer qualified FG%.
        for key in ("pos", "gs", "gp", "min", "pts", "reb", "ast", "stl", "blk", "to", "fls"):
            if record.get(key) is None and row.get(key) is not None:
                record[key] = row[key]
            elif key not in record:
                record[key] = row.get(key)
        if row.get("fg_pct") is not None and (record.get("fg_pct") is None or row.get("fg_pct_qualified")):
            record["fg_pct"] = row.get("fg_pct")
            record["fg_pct_qualified"] = row.get("fg_pct_qualified")
    for player, rankings in visible_rankings.items():
        by_player[player]["visible_rankings"] = rankings
        by_player[player]["leaderboard_hits"] = len(rankings)
        by_player[player]["top3_hits"] = sum(1 for hit in rankings if hit["rank"] is not None and hit["rank"] <= 3)
    return rows, by_player, mapping, issues


def load_db_context() -> tuple[dict[str, dict[str, Any]], dict[str, float], dict[str, dict[str, Any]]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    advanced: dict[str, dict[str, Any]] = {}
    for row in con.execute("SELECT player, player_id, team, ows, dws, ws FROM advanced WHERE season = ?", (SEASON,)):
        advanced[norm(row["player"])] = dict(row)
    all_baa: dict[str, float] = {}
    for row in con.execute("SELECT player, number_tm FROM all_teams WHERE season = ? AND type = 'All-BAA'", (SEASON,)):
        all_baa[norm(row["player"])] = 1.0 if row["number_tm"] == "1st" else 0.6 if row["number_tm"] == "2nd" else 0.0
    teams: dict[str, dict[str, Any]] = {}
    for row in con.execute("SELECT abbreviation, playoffs, w, l, srs FROM team_summaries WHERE season = ?", (SEASON,)):
        teams[str(row["abbreviation"])] = dict(row)
    return advanced, all_baa, teams


def build_scores() -> dict[str, Any]:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    position_by_name = load_positions()
    _, regular_by_player = load_regular_rows()
    full_names = sorted(regular_by_player.keys())
    playoff_rows, playoff_by_player, abbrev_mapping, mapping_issues = load_playoff_rows(full_names)
    advanced, all_baa, teams = load_db_context()
    postseason = json.loads(POSTSEASON_JSON.read_text(encoding="utf-8"))
    champion_team = str(postseason.get("champion_irl_team") or "")
    finals_mvp = str(postseason.get("finals", {}).get("finals_mvp") or "")

    records: list[dict[str, Any]] = []
    for player, fields in regular_by_player.items():
        pos_info = position_by_name.get(norm(player), {})
        primary_pos = pos_info.get("primary_pos", "")
        if primary_pos not in POSITIONS:
            continue
        live_fgm = fields.get("Field Goals Made", {}).get("live_pg")
        live_fga = fields.get("Field Goals Attempted", {}).get("live_pg")
        irl_fgm = fields.get("Field Goals Made", {}).get("irl_pg")
        irl_fga = fields.get("Field Goals Attempted", {}).get("irl_pg")
        irl_team = str(next(iter(fields.values())).get("irl_team") if fields else "")
        adv = advanced.get(norm(player), {})
        team = teams.get(irl_team, {})
        playoffs_flag = float(team.get("playoffs") or 0)
        srs = num(team.get("srs"))
        wins = num(team.get("w"))
        losses = num(team.get("l"))
        rec: dict[str, Any] = {
            "player": player,
            "primary_pos": primary_pos,
            "secondary_pos": pos_info.get("secondary_pos", ""),
            "source_player_id": pos_info.get("source_player_id", ""),
            "irl_team": irl_team,
            "sim_ppg": fields.get("Points", {}).get("live_pg"),
            "irl_ppg": fields.get("Points", {}).get("irl_pg"),
            "sim_fga_pg": live_fga,
            "irl_fga_pg": irl_fga,
            "sim_fta_pg": fields.get("Free Throws Attempted", {}).get("live_pg"),
            "irl_fta_pg": fields.get("Free Throws Attempted", {}).get("irl_pg"),
            "sim_ast_pg": fields.get("Assists", {}).get("live_pg"),
            "irl_ast_pg": fields.get("Assists", {}).get("irl_pg"),
            "sim_fg_pct": safe_div(live_fgm, live_fga),
            "irl_fg_pct": safe_div(irl_fgm, irl_fga),
            "sim_games": fields.get("Games Played", {}).get("live_total"),
            "irl_games": fields.get("Games Played", {}).get("irl_total"),
            "ows": num(adv.get("ows")),
            "dws": num(adv.get("dws")),
            "ws": num(adv.get("ws")),
            "all_baa_score": all_baa.get(norm(player), 0.0),
            "team_playoffs": playoffs_flag,
            "team_wins": wins,
            "team_losses": losses,
            "team_srs": srs,
            "champion": 1.0 if irl_team == champion_team else 0.0,
            "finals_mvp": 1.0 if norm(player) == norm(finals_mvp) else 0.0,
        }
        diffs = [abs(fields[field]["diff_pg"]) for field in REGULAR_STAT_FIELDS_FOR_MAE if field in fields and fields[field].get("diff_pg") is not None]
        rec["stat_mae_pg"] = mean(diffs)
        playoff = playoff_by_player.get(player)
        if playoff:
            for key in ("gs", "gp", "min", "pts", "reb", "ast", "stl", "blk", "to", "fls", "fg_pct", "leaderboard_hits", "top3_hits"):
                rec[f"po_{key}"] = playoff.get(key)
            rec["po_visible_rankings"] = "; ".join(
                f"{hit['sort_category']}#{hit['rank']}" for hit in sorted(playoff.get("visible_rankings", []), key=lambda h: (h["sort_category"], h["rank"]))
            )
        else:
            for key in ("gs", "gp", "min", "pts", "reb", "ast", "stl", "blk", "to", "fls", "fg_pct", "leaderboard_hits", "top3_hits"):
                rec[f"po_{key}"] = None
            rec["po_visible_rankings"] = ""
        records.append(rec)

    # Percentile components.
    percentile_keys = [
        "sim_ppg", "sim_fga_pg", "sim_fta_pg", "sim_fg_pct", "sim_ast_pg", "sim_games",
        "irl_ppg", "irl_fga_pg", "irl_fta_pg", "irl_fg_pct", "irl_ast_pg", "irl_games",
        "ows", "dws", "ws", "team_wins", "team_srs",
        "po_pts", "po_min", "po_reb", "po_ast", "po_stl", "po_blk", "po_fg_pct", "po_gp", "po_to", "po_fls", "po_leaderboard_hits", "po_top3_hits",
    ]
    for key in percentile_keys:
        values = [rec.get(key) for rec in records]
        reverse = key in {"po_to", "po_fls"}
        for rec in records:
            rec[f"{key}_pct"] = pct_rank(values, rec.get(key), reverse=reverse)

    for rec in records:
        rec["sim_regular_production_score"] = weighted([
            (rec.get("sim_ppg_pct"), 0.40),
            (rec.get("sim_fga_pg_pct"), 0.25),
            (rec.get("sim_fta_pg_pct"), 0.15),
            (rec.get("sim_fg_pct_pct"), 0.10),
            (rec.get("sim_games_pct"), 0.05),
            (rec.get("sim_ast_pg_pct"), 0.05),
        ])
        rec["irl_regular_production_score"] = weighted([
            (rec.get("irl_ppg_pct"), 0.40),
            (rec.get("irl_fga_pg_pct"), 0.25),
            (rec.get("irl_fta_pg_pct"), 0.15),
            (rec.get("irl_fg_pct_pct"), 0.10),
            (rec.get("irl_games_pct"), 0.05),
            (rec.get("irl_ast_pg_pct"), 0.05),
        ])
        rec["irl_value_score"] = weighted([
            (rec.get("ws_pct"), 0.50),
            (rec.get("ows_pct"), 0.30),
            (rec.get("dws_pct"), 0.20),
        ])
        rec["award_score"] = rec["all_baa_score"] * 70.0 + rec["finals_mvp"] * 30.0
        rec["team_success_score"] = weighted([
            (70.0 if rec["champion"] else 0.0, 0.55),
            (70.0 if rec["team_playoffs"] else 0.0, 0.20),
            (rec.get("team_wins_pct"), 0.15),
            (rec.get("team_srs_pct"), 0.10),
        ])
        rec["sim_playoff_visible_score"] = weighted([
            (rec.get("po_pts_pct"), 0.30),
            (rec.get("po_min_pct"), 0.15),
            (rec.get("po_reb_pct"), 0.15),
            (rec.get("po_stl_pct"), 0.10),
            (rec.get("po_blk_pct"), 0.10),
            (rec.get("po_fg_pct_pct"), 0.08),
            (rec.get("po_gp_pct"), 0.07),
            (rec.get("po_top3_hits_pct"), 0.05),
        ])
        # Historical IRL side includes awards, team success, OWS/DWS/WS, and regular production.
        rec["historical_irl_score"] = weighted([
            (rec["irl_regular_production_score"], 0.35),
            (rec["irl_value_score"], 0.25),
            (rec["award_score"], 0.20),
            (rec["team_success_score"], 0.20),
        ])
        # Sim side includes regular sim production and the visible playoff/postseason evidence.
        rec["sim_integrated_score"] = weighted([
            (rec["sim_regular_production_score"], 0.50),
            (rec["sim_playoff_visible_score"], 0.25),
            (100.0 if rec["finals_mvp"] else 0.0, 0.10),
            (100.0 if rec["champion"] else 0.0, 0.15),
        ])
        rec["sim_minus_historical_score"] = rec["sim_integrated_score"] - rec["historical_irl_score"]

    score_cols = [
        "player", "primary_pos", "secondary_pos", "source_player_id", "irl_team",
        "historical_irl_score", "sim_integrated_score", "sim_minus_historical_score", "stat_mae_pg",
        "sim_regular_production_score", "irl_regular_production_score", "irl_value_score", "award_score", "team_success_score", "sim_playoff_visible_score",
        "sim_ppg", "irl_ppg", "sim_fga_pg", "irl_fga_pg", "sim_fta_pg", "irl_fta_pg", "sim_fg_pct", "irl_fg_pct", "sim_ast_pg", "irl_ast_pg", "sim_games", "irl_games",
        "ows", "dws", "ws", "all_baa_score", "champion", "finals_mvp", "team_playoffs", "team_wins", "team_srs",
        "po_gp", "po_gs", "po_min", "po_pts", "po_reb", "po_ast", "po_stl", "po_blk", "po_to", "po_fls", "po_fg_pct", "po_leaderboard_hits", "po_top3_hits", "po_visible_rankings",
    ]
    with (ANALYSIS_DIR / "integrated_player_scores.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=score_cols)
        writer.writeheader()
        for rec in sorted(records, key=lambda item: item["historical_irl_score"], reverse=True):
            writer.writerow({col: rec.get(col, "") for col in score_cols})

    mapping_cols = ["abbrev", "full_player"]
    with (ANALYSIS_DIR / "playoff_name_mapping.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=mapping_cols)
        writer.writeheader()
        for abbrev, full in sorted(abbrev_mapping.items()):
            writer.writerow({"abbrev": abbrev, "full_player": full})
    (ANALYSIS_DIR / "playoff_name_mapping_issues.json").write_text(json.dumps(mapping_issues, indent=2), encoding="utf-8")

    top_rows: list[dict[str, Any]] = []
    for pos in POSITIONS:
        scoped = [rec for rec in records if rec["primary_pos"] == pos]
        for rank, rec in enumerate(sorted(scoped, key=lambda item: item["historical_irl_score"], reverse=True)[:5], start=1):
            row = {"position": pos, "rank_by_historical_irl": rank, **{col: rec.get(col, "") for col in score_cols}}
            top_rows.append(row)
    top_cols = ["position", "rank_by_historical_irl", *score_cols]
    with (ANALYSIS_DIR / "top5_by_position_integrated.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=top_cols)
        writer.writeheader()
        writer.writerows(top_rows)

    # Human report.
    lines: list[str] = [
        "# 1947 integrated sim-vs-IRL impact analysis",
        "",
        f"Regular-season rows: {len(records)} players",
        f"Playoff screenshot rows: {len(playoff_rows)} rows",
        f"Mapped playoff players: {len(playoff_by_player)}",
        f"Mapping issues: {len(mapping_issues)}",
        "",
        "## Formula",
        "- Historical IRL score = 35% IRL regular production + 25% OWS/DWS/WS + 20% awards/FMVP + 20% team/postseason success.",
        "- Sim integrated score = 50% sim regular production + 25% visible playoff production + 10% Finals MVP + 15% championship.",
        "- Playoff production is screenshot-visible only, not a complete playoff table dump.",
        "",
        "## Top 5 by position, historical IRL score",
        "| Pos | Rank | Player | Hist IRL | Sim int | Gap | Stat MAE/G | IRL prod | OWS/DWS/WS | Awards | Team/Post | PO score | PO line | PO ranks |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in top_rows:
        ws_text = f"{row.get('ows') or ''}/{row.get('dws') or ''}/{row.get('ws') or ''}"
        po_line = ""
        if row.get("po_pts") is not None:
            po_line = f"{row.get('po_pts')}p {row.get('po_reb')}r {row.get('po_ast')}a {row.get('po_min')}m"
        lines.append(
            f"| {row['position']} | {row['rank_by_historical_irl']} | {row['player']} | "
            f"{row['historical_irl_score']:.1f} | {row['sim_integrated_score']:.1f} | {row['sim_minus_historical_score']:.1f} | "
            f"{row['stat_mae_pg']:.2f} | {row['irl_regular_production_score']:.1f} | {ws_text} | "
            f"{row['award_score']:.1f} | {row['team_success_score']:.1f} | {row['sim_playoff_visible_score']:.1f} | {po_line} | {row.get('po_visible_rankings') or ''} |"
        )
    lines.extend([
        "",
        "## Highest historical IRL scores overall",
        "| Rank | Player | Pos | Hist IRL | Sim int | Gap | IRL PPG | OWS | DWS | WS | Awards | Team/Post | Playoff visible |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for rank, rec in enumerate(sorted(records, key=lambda item: item["historical_irl_score"], reverse=True)[:20], start=1):
        lines.append(
            f"| {rank} | {rec['player']} | {rec['primary_pos']} | {rec['historical_irl_score']:.1f} | {rec['sim_integrated_score']:.1f} | "
            f"{rec['sim_minus_historical_score']:.1f} | {rec['irl_ppg']:.1f} | {rec.get('ows') or ''} | {rec.get('dws') or ''} | {rec.get('ws') or ''} | "
            f"{rec['award_score']:.1f} | {rec['team_success_score']:.1f} | {rec.get('po_visible_rankings') or ''} |"
        )
    (ANALYSIS_DIR / "integrated_impact_report.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "players": len(records),
        "playoff_rows": len(playoff_rows),
        "mapped_playoff_players": len(playoff_by_player),
        "mapping_issues": len(mapping_issues),
        "files": {
            "scores": str(ANALYSIS_DIR / "integrated_player_scores.csv"),
            "top5": str(ANALYSIS_DIR / "top5_by_position_integrated.csv"),
            "report": str(ANALYSIS_DIR / "integrated_impact_report.md"),
            "mapping": str(ANALYSIS_DIR / "playoff_name_mapping.csv"),
            "mapping_issues": str(ANALYSIS_DIR / "playoff_name_mapping_issues.json"),
        },
        "top_pf": next((row for row in top_rows if row["position"] == "PF" and row["rank_by_historical_irl"] == 1), None),
    }
    (ANALYSIS_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> int:
    summary = build_scores()
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
