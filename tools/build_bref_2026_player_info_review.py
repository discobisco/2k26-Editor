#!/usr/bin/env python3
"""Build a separate review list for missing 2026 player_info rows from BRef profile pages.

Does not write to any SQLite database.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "outputs" / "2026_bref_review"
INPUT = REVIEW_DIR / "missing_player_info_candidates_distinct.csv"
OUTPUT = REVIEW_DIR / "missing_player_info_candidates_profile_enriched.csv"
CACHE = REVIEW_DIR / "profile_cache"
UA = "Mozilla/5.0 (compatible; nba2k-editor-generator/1.0)"
EXCEL_EPOCH = dt.date(1899, 12, 30)

def clean_html_text(fragment: str) -> str:
    fragment = fragment.replace("&nbsp;", " ").replace("&#9642;", " ").replace("&#x27;", "'")
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(fragment.split())

def excel_serial(date_text: str) -> int | str:
    if not date_text:
        return ""
    d = dt.date.fromisoformat(date_text)
    return (d - EXCEL_EPOCH).days

def parse_profile(html: str) -> dict[str, str | int]:
    out: dict[str, str | int] = {}
    m = re.search(r"<p><span>(\d+)-(\d+)</span>,&nbsp;<span>(\d+)lb</span>", html)
    if m:
        out["ht_in_in"] = int(m.group(1)) * 12 + int(m.group(2))
        out["wt"] = int(m.group(3))
    else:
        out["ht_in_in"] = ""
        out["wt"] = ""

    m = re.search(r'id="necro-birth"[^>]*data-birth="(\d{4}-\d{2}-\d{2})"', html)
    out["birth_date"] = excel_serial(m.group(1)) if m else ""

    college_match = re.search(r"<strong>\s*Colleges?\s*:\s*</strong>(.*?)</p>", html, re.S)
    if college_match:
        vals = [v.strip() for v in re.findall(r">([^<>]+)</a>", college_match.group(1)) if v.strip()]
        out["colleges"] = ", ".join(vals) if vals else clean_html_text(college_match.group(1))
    else:
        born_idx = html.find("Born:")
        born_fragment = html[born_idx : born_idx + 900] if born_idx >= 0 else ""
        birthplaces = re.findall(
            r"<a href='/friv/birthplaces\.fcgi\?country=[^'&]+(?:&state=[^']*)?'>([^<]+)</a>",
            born_fragment,
        )
        out["colleges"] = birthplaces[-1].strip() if birthplaces else ""

    debut_match = re.search(r'<strong>NBA Debut:\s*</strong><a href="[^"]+">([^<]+)</a>', html)
    if debut_match:
        try:
            debut = dt.datetime.strptime(debut_match.group(1).strip(), "%B %d, %Y").date()
            out["debut"] = debut.isoformat() + "T00:00:00Z"
        except ValueError:
            out["debut"] = debut_match.group(1).strip()
    else:
        out["debut"] = ""

    per_game_table = ""
    table_match = re.search(r'<table[^>]+id="per_game_stats".*?</table>', html, re.S)
    if table_match:
        per_game_table = table_match.group(0)
    seasons = [int(x) for x in re.findall(r'/leagues/NBA_(\d{4})\.html', per_game_table)]
    seasons = [s for s in seasons if 1947 <= s <= 2026]
    if seasons:
        out["from"] = min(seasons)
        out["to"] = max(seasons)
    else:
        out["from"] = ""
        out["to"] = ""

    # BRef active/non-HOF pages do not expose a player_info-style HOF value. Treat explicit HOF bling only as 1.
    # Footer/nav links to Hall of Fame are ignored.
    info_block = ""
    info_match = re.search(r'<div id="info".*?</div>', html, re.S)
    if info_match:
        info_block = info_match.group(0)
    out["hof"] = 1 if re.search(r'Hall of Fame|HOF', info_block, re.I) else 0

    unresolved = []
    for field in ["ht_in_in", "wt", "birth_date", "colleges", "from", "to", "debut"]:
        if out.get(field, "") == "":
            unresolved.append(field)
    out["source_status"] = "profile parsed" if not unresolved else "profile parsed with unresolved: " + ",".join(unresolved)
    return out

def fetch_or_cache(player_id: str) -> tuple[str | None, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{player_id}.html"
    if path.exists() and path.stat().st_size > 1000:
        return path.read_text(encoding="utf-8", errors="replace"), "cache"
    url = f"https://www.basketball-reference.com/players/{player_id[0]}/{player_id}.html"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", "replace")
        path.write_text(html, encoding="utf-8")
        return html, "fetched"
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, type(exc).__name__ + ": " + str(exc)

def main() -> None:
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8")))
    fields = [
        "candidate_no", "player", "player_id", "pos", "ht_in_in", "wt", "birth_date", "colleges", "from", "to", "debut", "hof",
        "source_status", "profile_fetch_status", "source_needed", "teams_2026", "age_from_season_info",
        "max_g_one_row", "max_mp_per_game", "max_pts_per_game",
    ]
    enriched = []
    for i, row in enumerate(rows, start=1):
        player_id = row["player_id"]
        html, fetch_status = fetch_or_cache(player_id)
        merged = {k: row.get(k, "") for k in fields}
        merged["profile_fetch_status"] = fetch_status
        if html:
            parsed = parse_profile(html)
            for key in ["ht_in_in", "wt", "birth_date", "colleges", "from", "to", "debut", "hof", "source_status"]:
                merged[key] = parsed.get(key, "")
            merged["source_needed"] = "none" if str(merged["source_status"]) == "profile parsed" else "review unresolved profile fields"
        else:
            merged["source_status"] = "profile fetch failed - not insertable"
            merged["source_needed"] = "retry/fallback source required"
        enriched.append(merged)
        print(f"{i:03d}/{len(rows)} {player_id} {row['player']} {fetch_status} {merged['source_status']}", flush=True)
        if fetch_status == "fetched":
            time.sleep(3.0)
        elif fetch_status.startswith("HTTP 429"):
            time.sleep(15.0)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(enriched)
    unresolved = [r for r in enriched if r["source_status"] != "profile parsed"]
    print(f"output={OUTPUT}")
    print(f"rows={len(enriched)} unresolved={len(unresolved)}")
    for r in unresolved[:30]:
        print(f"UNRESOLVED {r['candidate_no']} {r['player_id']} {r['player']} {r['source_status']} {r['profile_fetch_status']}")

if __name__ == "__main__":
    main()
