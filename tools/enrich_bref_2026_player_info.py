#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
SEASON = 2026
UA = "Mozilla/5.0 (compatible; nba2k-editor-generator/1.0)"
EXCEL_EPOCH = dt.date(1899, 12, 30)


def fetch_player(player_id: str) -> str:
    url = f"https://www.basketball-reference.com/players/{player_id[0]}/{player_id}.html"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def html_text(fragment: str) -> str:
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = fragment.replace("&nbsp;", " ").replace("&#9642;", " ")
    return " ".join(fragment.split())


def parse_height_inches(html: str) -> int | None:
    m = re.search(r"<p><span>(\d+)-(\d+)</span>,&nbsp;<span>(\d+)lb</span>", html)
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2))


def parse_weight(html: str) -> int | None:
    m = re.search(r"<p><span>(\d+)-(\d+)</span>,&nbsp;<span>(\d+)lb</span>", html)
    return int(m.group(3)) if m else None


def parse_birth_serial(html: str) -> int | None:
    m = re.search(r'id="necro-birth"[^>]*data-birth="(\d{4}-\d{2}-\d{2})"', html)
    if not m:
        return None
    born = dt.date.fromisoformat(m.group(1))
    return (born - EXCEL_EPOCH).days


def parse_colleges(html: str) -> str | None:
    m = re.search(r"<strong>\s*(?:College|High School):\s*</strong>(.*?)</p>", html, re.S)
    if not m:
        return None
    vals = re.findall(r">([^<>]+)</a>", m.group(1))
    if vals:
        return ", ".join(v.strip() for v in vals if v.strip()) or None
    txt = html_text(m.group(1))
    return txt or None


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    missing = con.execute(
        """
        select s.player_id, s.player, s.pos, s.age
        from (select distinct player_id, player, pos, age from player_season_info where season=?) s
        left join player_info i on i.player_id=s.player_id
        where i.player_id is null
        order by s.player
        """,
        (SEASON,),
    ).fetchall()
    print(f"missing player_info rows={len(missing)}")
    inserted = 0
    with con:
        for row in missing:
            pid = row["player_id"]
            try:
                html = fetch_player(pid)
                ht = parse_height_inches(html)
                wt = parse_weight(html)
                birth = parse_birth_serial(html)
                colleges = parse_colleges(html)
                pos = row["pos"]
            except Exception as exc:
                print(f"fetch failed {pid} {row['player']}: {exc}")
                ht = wt = birth = colleges = None
                pos = row["pos"]
            con.execute(
                """
                insert into player_info (player, player_id, pos, ht_in_in, wt, birth_date, colleges, "from", "to", debut, hof)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["player"], pid, pos, ht, wt, birth, colleges, SEASON, SEASON, None, 0),
            )
            inserted += 1
            if inserted % 25 == 0:
                print(f"inserted {inserted}")
            time.sleep(0.25)
    print(f"inserted player_info rows={inserted}")


if __name__ == "__main__":
    main()
