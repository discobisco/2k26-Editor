from __future__ import annotations

import csv
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
OUT = ROOT / "outputs" / "player_generator_tracking_loss"

TABLES = [
    "player_per_game",
    "player_totals",
    "player_per_36_min",
    "player_per_100_poss",
    "player_shooting",
    "advanced",
    "player_play_by_play",
]
IDENTITY_TABLE = "player_info"
SEASON_TABLE = "player_season_info"
TEAM_CONTEXT_TABLES = [
    "team_stats_per_game",
    "team_stats_per_100_pos",
    "team_summaries",
    "team_totals",
    "opponent_stats_per_game",
    "opponent_stats_per_100_poss",
    "opponent_totals",
]
PLAYER_REWARD_TABLES = [
    "all_star_selections",
    "all_teams",
    "player_award_shares",
    "all_team_voting",
    "draft_picks",
]

ALL_TRACKING_TABLES = [
    "team_abbrev",
    "team_stats_per_100_pos",
    "team_stats_per_game",
    "team_summaries",
    "team_totals",
    "opponent_stats_per_100_poss",
    "opponent_stats_per_game",
    "opponent_totals",
    "draft_picks",
    "player_season_info",
    "player_info",
    "player_per_game",
    "player_per_36_min",
    "player_per_100_poss",
    "player_totals",
    "player_shooting",
    "advanced",
    "player_play_by_play",
    "all_star_selections",
    "all_teams",
    "player_award_shares",
    "all_team_voting",
]

# Sparse-era-visible inputs: columns present for 1947-ish players that can proxy later-tracked stats.
CANDIDATE_KEYS = [
    "player_info.ht_in_in",
    "player_info.wt",
    "player_season_info.age",
    "player_per_game.g",
    "player_per_game.pts_per_game",
    "player_per_game.fg_per_game",
    "player_per_game.fga_per_game",
    "player_per_game.fg_percent",
    "player_per_game.ft_per_game",
    "player_per_game.fta_per_game",
    "player_per_game.ft_percent",
    "player_per_game.ast_per_game",
    "player_per_game.pf_per_game",
    "player_totals.pts",
    "player_totals.fg",
    "player_totals.fga",
    "player_totals.ft",
    "player_totals.fta",
    "player_totals.ast",
    "player_totals.pf",
    "advanced.ts_percent",
    "advanced.f_tr",
    "advanced.ows",
    "advanced.dws",
    "advanced.ws",
    # Team context available for sparse seasons.
    "team_summaries.w",
    "team_summaries.l",
    "team_summaries.mov",
    "team_summaries.srs",
    "team_summaries.o_rtg",
    "team_summaries.d_rtg",
    "team_summaries.pace",
    "team_summaries.ts_percent",
    "team_summaries.e_fg_percent",
    "team_summaries.tov_percent",
    "team_summaries.orb_percent",
    "team_summaries.drb_percent",
    "team_stats_per_game.pts_per_game",
    "team_stats_per_game.fga_per_game",
    "team_stats_per_game.fta_per_game",
    "team_stats_per_game.ast_per_game",
    "team_stats_per_game.pf_per_game",
    "team_totals.pts",
    "team_totals.fga",
    "team_totals.fta",
    "team_totals.ast",
    "team_totals.pf",
    # Opponent context.
    "opponent_stats_per_game.opp_pts_per_game",
    "opponent_stats_per_game.opp_fga_per_game",
    "opponent_stats_per_game.opp_fta_per_game",
    "opponent_stats_per_game.opp_ast_per_game",
    "opponent_stats_per_game.opp_pf_per_game",
    "opponent_stats_per_100_poss.opp_pts_per_100_poss",
    "opponent_stats_per_100_poss.opp_fga_per_100_poss",
    "opponent_stats_per_100_poss.opp_fta_per_100_poss",
    "opponent_totals.opp_pts",
    "opponent_totals.opp_fga",
    "opponent_totals.opp_fta",
    "opponent_totals.opp_ast",
    "opponent_totals.opp_pf",
    # Recognition/reward context.
    "all_star_selections.replaced",
    "all_teams.number_tm",
    "player_award_shares.first",
    "player_award_shares.pts_won",
    "player_award_shares.pts_max",
    "player_award_shares.share",
    "player_award_shares.winner",
    "all_team_voting.pts_won",
    "all_team_voting.pts_max",
    "all_team_voting.share",
    "all_team_voting.x1st_tm",
    "all_team_voting.x2nd_tm",
    "all_team_voting.x3rd_tm",
    "draft_picks.overall_pick",
    "draft_picks.round",
]

TARGET_KEYS = [
    "player_per_game.mp_per_game",
    "player_per_game.trb_per_game",
    "player_per_game.stl_per_game",
    "player_per_game.blk_per_game",
    "player_per_game.tov_per_game",
    "player_per_36_min.trb_per_36_min",
    "player_per_36_min.stl_per_36_min",
    "player_per_36_min.blk_per_36_min",
    "player_per_36_min.tov_per_36_min",
    "player_per_100_poss.trb_per_100_poss",
    "player_per_100_poss.stl_per_100_poss",
    "player_per_100_poss.blk_per_100_poss",
    "player_per_100_poss.tov_per_100_poss",
    "advanced.orb_percent",
    "advanced.drb_percent",
    "advanced.trb_percent",
    "advanced.ast_percent",
    "advanced.stl_percent",
    "advanced.blk_percent",
    "advanced.tov_percent",
    "advanced.usg_percent",
    "player_shooting.percent_fga_from_x0_3_range",
    "player_shooting.percent_fga_from_x3_10_range",
    "player_shooting.percent_fga_from_x10_16_range",
    "player_shooting.percent_fga_from_x16_3p_range",
    "player_shooting.percent_assisted_x2p_fg",
    "player_play_by_play.pg_percent",
    "player_play_by_play.sg_percent",
    "player_play_by_play.sf_percent",
    "player_play_by_play.pf_percent",
    "player_play_by_play.c_percent",
    "player_play_by_play.bad_pass_turnover",
    "player_play_by_play.lost_ball_turnover",
    "player_play_by_play.shooting_foul_committed",
    "player_play_by_play.offensive_foul_committed",
    "player_play_by_play.shooting_foul_drawn",
    "player_play_by_play.points_generated_by_assists",
]


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.upper() == "NA":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def corr(xs, ys):
    n = len(xs)
    if n < 20:
        return None
    mx, my = mean(xs), mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def table_columns(con, table):
    return [row[1] for row in con.execute(f'pragma table_info("{table}")')]


def tracking_rows(con):
    rows = []
    seasons = [r[0] for r in con.execute("select distinct season from player_per_game order by season") if r[0] is not None]
    for table in TABLES:
        cols = table_columns(con, table)
        numeric_cols = []
        for col in cols:
            if col in {"season", "lg", "player", "player_id", "team", "pos"}:
                continue
            # Treat as numeric if at least one numeric value exists.
            found = con.execute(f'select {col} from "{table}" where {col} is not null limit 200').fetchall()
            if any(number(v[0]) is not None for v in found):
                numeric_cols.append(col)
        for col in numeric_cols:
            available = []
            for season in seasons:
                total = con.execute(f'select count(*) from "{table}" where season=?', (season,)).fetchone()[0]
                nonnull = con.execute(f'select count(*) from "{table}" where season=? and {col} is not null', (season,)).fetchone()[0]
                ratio = nonnull / total if total else 0.0
                if total and ratio >= 0.50:
                    available.append(season)
            first = min(available) if available else None
            last = max(available) if available else None
            missing_1947 = 1947 not in set(available)
            rows.append({
                "table": table,
                "column": col,
                "key": f"{table}.{col}",
                "first_majority_tracked_season": first,
                "last_majority_tracked_season": last,
                "tracked_in_1947": not missing_1947,
                "majority_tracked_seasons": ";".join(str(s) for s in available),
            })
    return rows


def build_player_dataset(con):
    data = defaultdict(dict)
    identity = defaultdict(dict)
    team_context = defaultdict(dict)
    player_rewards = defaultdict(dict)
    player_career_rewards = defaultdict(dict)

    # Player identity is career-scoped and can be merged into each season/team row.
    cols = table_columns(con, IDENTITY_TABLE)
    for row in con.execute(f'select * from "{IDENTITY_TABLE}"'):
        d = dict(zip(cols, row))
        pid = str(d.get("player_id") or "").strip().upper()
        if pid:
            identity[pid].update({f"{IDENTITY_TABLE}.{c}": number(v) for c, v in d.items() if number(v) is not None})

    # Team and opponent rows are season/team scoped.
    for table in TEAM_CONTEXT_TABLES:
        cols = table_columns(con, table)
        for row in con.execute(f'select * from "{table}"'):
            d = dict(zip(cols, row))
            season = d.get("season")
            team = str(d.get("abbreviation") or d.get("team") or "").strip().upper()
            if season is None or not team:
                continue
            team_context[(int(season), team)].update({f"{table}.{c}": number(v) for c, v in d.items() if number(v) is not None})

    # Recognition/reward rows are player-season scoped when a season exists; draft is career-ish by player.
    for table in PLAYER_REWARD_TABLES:
        cols = table_columns(con, table)
        for row in con.execute(f'select * from "{table}"'):
            d = dict(zip(cols, row))
            pid = str(d.get("player_id") or "").strip().upper()
            if not pid:
                continue
            payload = {f"{table}.{c}": number(v) for c, v in d.items() if number(v) is not None}
            season = d.get("season")
            if season is None or table == "draft_picks":
                player_career_rewards[pid].update(payload)
            else:
                player_rewards[(int(season), pid)].update(payload)

    for table in [SEASON_TABLE] + TABLES:
        cols = table_columns(con, table)
        for row in con.execute(f'select * from "{table}"'):
            d = dict(zip(cols, row))
            season = d.get("season")
            pid = str(d.get("player_id") or "").strip().upper()
            team = str(d.get("team") or "").strip().upper()
            if season is None or not pid or not team:
                continue
            data[(int(season), pid, team)].update({f"{table}.{c}": number(v) for c, v in d.items() if number(v) is not None})

    for key in list(data):
        season, pid, team = key
        data[key].update(identity.get(pid, {}))
        data[key].update(team_context.get((season, team), {}))
        data[key].update(player_rewards.get((season, pid), {}))
        data[key].update(player_career_rewards.get(pid, {}))
    return data


def numeric_columns_for_tracking(con, table):
    cols = table_columns(con, table)
    numeric_cols = []
    for col in cols:
        if col in {"lg", "player", "player_id", "team", "tm", "abbreviation", "pos", "type", "award", "college", "arena", "birth_date", "debut", "colleges"}:
            continue
        values = con.execute(f'select "{col}" from "{table}" where "{col}" is not null limit 500').fetchall()
        if any(number(v[0]) is not None for v in values):
            numeric_cols.append(col)
    return numeric_cols


def column_tracking_by_season(con, table, column, seasons):
    cols = set(table_columns(con, table))
    if "season" not in cols:
        # Career-only table: mark tracked for all seasons if it has any numeric values.
        count = con.execute(f'select count(*) from "{table}" where "{column}" is not null').fetchone()[0]
        return {season: count > 0 for season in seasons}
    availability = {}
    for season in seasons:
        total = con.execute(f'select count(*) from "{table}" where season=?', (season,)).fetchone()[0]
        nonnull_rows = con.execute(f'select "{column}" from "{table}" where season=? and "{column}" is not null', (season,)).fetchall()
        numeric_nonnull = sum(1 for row in nonnull_rows if number(row[0]) is not None)
        ratio = numeric_nonnull / total if total else 0.0
        # Majority-tracked avoids treating one-off award/vote rows as a full-season column for normal stat tables,
        # but for sparse event/reward tables any row means the column exists for that season.
        if table in PLAYER_REWARD_TABLES:
            availability[season] = numeric_nonnull > 0
        else:
            availability[season] = bool(total and ratio >= 0.50)
    return availability


def yearly_tracking_loss_rows(con):
    seasons = [int(r[0]) for r in con.execute("select distinct season from player_per_game where season is not null order by season")]
    per_column = {}
    for table in ALL_TRACKING_TABLES:
        for column in numeric_columns_for_tracking(con, table):
            key = f"{table}.{column}"
            per_column[key] = {
                "table": table,
                "column": column,
                "availability": column_tracking_by_season(con, table, column, seasons),
            }

    year_rows = []
    event_rows = []
    for idx, season in enumerate(seasons):
        lost = []
        gained = []
        unavailable = []
        for key, meta in per_column.items():
            current = bool(meta["availability"].get(season))
            previous = bool(meta["availability"].get(seasons[idx - 1])) if idx > 0 else False
            if not current:
                unavailable.append(key)
            if idx > 0 and previous and not current:
                lost.append(key)
                event_rows.append({
                    "season": season,
                    "event": "lost",
                    "table": meta["table"],
                    "column": meta["column"],
                    "key": key,
                    "previous_season": seasons[idx - 1],
                })
            if current and (idx == 0 or not previous):
                gained.append(key)
                event_rows.append({
                    "season": season,
                    "event": "gained",
                    "table": meta["table"],
                    "column": meta["column"],
                    "key": key,
                    "previous_season": seasons[idx - 1] if idx > 0 else "",
                })
        year_rows.append({
            "season": season,
            "lost_count": len(lost),
            "gained_count": len(gained),
            "unavailable_numeric_column_count": len(unavailable),
            "lost_columns": ";".join(lost),
            "gained_columns": ";".join(gained),
        })
    return year_rows, event_rows


def backward_yearly_tracking_loss_rows(con):
    """Columns lost when walking backward: available in the next newer season, unavailable in this season."""
    seasons = [int(r[0]) for r in con.execute("select distinct season from player_per_game where season is not null order by season")]
    per_column = {}
    for table in ALL_TRACKING_TABLES:
        for column in numeric_columns_for_tracking(con, table):
            key = f"{table}.{column}"
            per_column[key] = {
                "table": table,
                "column": column,
                "availability": column_tracking_by_season(con, table, column, seasons),
            }

    year_rows = []
    event_rows = []
    for idx, season in enumerate(seasons):
        next_season = seasons[idx + 1] if idx + 1 < len(seasons) else None
        backward_lost = []
        backward_gained = []
        unavailable = []
        for key, meta in per_column.items():
            current = bool(meta["availability"].get(season))
            newer = bool(meta["availability"].get(next_season)) if next_season is not None else False
            if not current:
                unavailable.append(key)
            if next_season is not None and newer and not current:
                backward_lost.append(key)
                event_rows.append({
                    "season": season,
                    "newer_season": next_season,
                    "event": "lost_moving_backward",
                    "table": meta["table"],
                    "column": meta["column"],
                    "key": key,
                })
            if next_season is not None and current and not newer:
                backward_gained.append(key)
                event_rows.append({
                    "season": season,
                    "newer_season": next_season,
                    "event": "gained_moving_backward",
                    "table": meta["table"],
                    "column": meta["column"],
                    "key": key,
                })
        year_rows.append({
            "season": season,
            "newer_season": next_season if next_season is not None else "",
            "backward_lost_count": len(backward_lost),
            "backward_gained_count": len(backward_gained),
            "unavailable_numeric_column_count": len(unavailable),
            "backward_lost_columns": ";".join(backward_lost),
            "backward_gained_columns": ";".join(backward_gained),
        })
    return year_rows, event_rows


def correlation_rows(dataset):
    out = []
    for target in TARGET_KEYS:
        for candidate in CANDIDATE_KEYS:
            if candidate == target:
                continue
            xs, ys = [], []
            years = set()
            for (season, _pid, _team), vals in dataset.items():
                if season < 1974:  # use modern-ish tracked data to learn proxies, not sparse BAA/early NBA rows
                    continue
                x = vals.get(candidate)
                y = vals.get(target)
                if x is None or y is None:
                    continue
                xs.append(x); ys.append(y); years.add(season)
            c = corr(xs, ys)
            if c is None:
                continue
            out.append({
                "target": target,
                "candidate": candidate,
                "pearson_r": round(c, 4),
                "abs_r": round(abs(c), 4),
                "sample_size": len(xs),
                "first_sample_season": min(years),
                "last_sample_season": max(years),
            })
    out.sort(key=lambda r: (r["target"], -r["abs_r"], r["candidate"]))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    tr = tracking_rows(con)
    ds = build_player_dataset(con)
    cr = correlation_rows(ds)
    year_rows, event_rows = yearly_tracking_loss_rows(con)
    backward_year_rows, backward_event_rows = backward_yearly_tracking_loss_rows(con)

    with (OUT / "tracking_loss_moving_backward_by_year.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(backward_year_rows[0]))
        w.writeheader(); w.writerows(backward_year_rows)
    with (OUT / "tracking_loss_moving_backward_events.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(backward_event_rows[0]))
        w.writeheader(); w.writerows(backward_event_rows)

    with (OUT / "tracking_loss_by_year.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(year_rows[0]))
        w.writeheader(); w.writerows(year_rows)
    with (OUT / "tracking_loss_events_by_year.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(event_rows[0]))
        w.writeheader(); w.writerows(event_rows)

    with (OUT / "tracking_loss_by_column.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(tr[0]))
        w.writeheader(); w.writerows(tr)
    with (OUT / "best_modern_correlations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cr[0]))
        w.writeheader(); w.writerows(cr)

    missing_1947 = [r for r in tr if not r["tracked_in_1947"]]
    lines = [
        "# Player Generator tracking loss + modern correlation report",
        "",
        f"Database: `{DB}`",
        f"Columns with numeric data but not majority-tracked in 1947: {len(missing_1947)}",
        f"Seasons with newly lost numeric columns vs previous season: {sum(1 for row in year_rows if row['lost_count'])}",
        f"Seasons with lost columns when moving backward from newer season: {sum(1 for row in backward_year_rows if row['backward_lost_count'])}",
        "Candidate proxies include player box score/advanced, team context, opposing-team context, and player reward/voting/draft fields.",
        "",
        "## Key missing targets and best modern proxies",
        "",
    ]
    for target in TARGET_KEYS:
        best = [r for r in cr if r["target"] == target][:8]
        if not best:
            continue
        lines.append(f"### {target}")
        for r in best:
            lines.append(f"- {r['candidate']}: r={r['pearson_r']} n={r['sample_size']} seasons={r['first_sample_season']}-{r['last_sample_season']}")
        lines.append("")
    (OUT / "tracking_loss_and_correlation_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT / 'tracking_loss_moving_backward_by_year.csv'}")
    print(f"wrote {OUT / 'tracking_loss_moving_backward_events.csv'}")
    print(f"wrote {OUT / 'tracking_loss_by_year.csv'}")
    print(f"wrote {OUT / 'tracking_loss_events_by_year.csv'}")
    print(f"wrote {OUT / 'tracking_loss_by_column.csv'}")
    print(f"wrote {OUT / 'best_modern_correlations.csv'}")
    print(f"wrote {OUT / 'tracking_loss_and_correlation_summary.md'}")
    print(f"missing_1947_numeric_columns={len(missing_1947)} forward_loss_seasons={sum(1 for row in year_rows if row['lost_count'])} backward_loss_seasons={sum(1 for row in backward_year_rows if row['backward_lost_count'])} correlation_rows={len(cr)}")


if __name__ == "__main__":
    main()
