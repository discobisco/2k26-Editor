"""Helpers for loading NBA reference data from the bundled Excel workbook.

This module keeps a small, cached view of the NBA Player Data workbook so AI
prompts can include real-world context (latest season stats, bio). Data is
loaded lazily and reused across requests.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..core.config import BASE_DIR
from ..core.conversions import format_height_inches

LOG = logging.getLogger("nba2k26.ai.nba_data")

NBA_DATA_PATH = BASE_DIR / "NBA Player Data" / "NBA DATA Master.xlsx"

_LOCK = threading.Lock()
_BIO_CACHE: dict[str, dict[str, Any]] | None = None
_PER_GAME_CACHE: dict[str, dict[str, Any]] | None = None
_LAST_ERROR: str | None = None
_LOADING: bool = False


def _normalize_name(name: str) -> str:
    """Lowercase and strip non-alphanumeric characters for matching."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text.lower() == "nan" else text


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        numeric = float(value)
        if math.isnan(numeric):
            return None
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        numeric = float(value)
        if math.isnan(numeric):
            return None
        return numeric
    except Exception:
        return None


def warm_cache_async() -> None:
    """Start loading the NBA workbook in the background."""
    global _LOADING
    with _LOCK:
        if _BIO_CACHE is not None or _LOADING:
            return
        _LOADING = True
    thread = threading.Thread(target=_load_data, name="NBADataLoader", daemon=True)
    thread.start()


def ensure_loaded(wait: bool = True) -> bool:
    """Load the Excel workbook if needed. Optionally block until ready."""
    global _LOADING
    with _LOCK:
        if _BIO_CACHE is not None and _PER_GAME_CACHE is not None:
            return True
        loading = _LOADING
        if not loading:
            _LOADING = True
    if not loading:
        _load_data()
    elif wait:
        while True:
            with _LOCK:
                if not _LOADING:
                    break
            time.sleep(0.05)
    with _LOCK:
        return _BIO_CACHE is not None and _PER_GAME_CACHE is not None


def _load_data() -> None:
    """Parse the Excel workbook into lightweight lookup maps."""
    global _BIO_CACHE, _PER_GAME_CACHE, _LAST_ERROR, _LOADING
    try:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError("Pandas is required for NBA data lookup (pip install pandas openpyxl).") from exc
        if not NBA_DATA_PATH.exists():
            raise FileNotFoundError(f"NBA data workbook not found at {NBA_DATA_PATH}")
        info_df = pd.read_excel(
            NBA_DATA_PATH,
            sheet_name="Player Info",
            usecols=["player", "pos", "ht_in_in", "wt", "colleges", "from", "to"],
        )
        per_game_df = pd.read_excel(
            NBA_DATA_PATH,
            sheet_name="Player Per Game",
            usecols=[
                "season",
                "player",
                "team",
                "pos",
                "g",
                "mp_per_game",
                "pts_per_game",
                "trb_per_game",
                "ast_per_game",
                "stl_per_game",
                "blk_per_game",
                "fg_percent",
                "x3p_percent",
                "ft_percent",
            ],
        )
        info_df["norm"] = info_df["player"].astype(str).map(_normalize_name)
        per_game_df["norm"] = per_game_df["player"].astype(str).map(_normalize_name)

        bio_cache: dict[str, dict[str, Any]] = {}
        for _, row in info_df.iterrows():
            norm = row.get("norm")
            if not norm:
                continue
            bio_cache[norm] = {
                "player": _clean_text(row.get("player")),
                "pos": _clean_text(row.get("pos")),
                "height": _to_int(row.get("ht_in_in")),
                "weight": _to_int(row.get("wt")),
                "college": _clean_text(row.get("colleges")),
                "from": _to_int(row.get("from")),
                "to": _to_int(row.get("to")),
            }

        per_game_cache: dict[str, dict[str, Any]] = {}
        for raw_norm, group in per_game_df.groupby("norm"):
            norm = _clean_text(raw_norm)
            if not norm:
                continue
            try:
                latest_season = int(group["season"].max())
            except Exception:
                continue
            latest = group[group["season"] == latest_season]
            combined = latest[latest["team"].astype(str).str.contains("TM")]
            target = combined if not combined.empty else latest
            target = target.sort_values(["g", "mp_per_game"], ascending=False)
            row = target.iloc[0]
            per_game_cache[norm] = {
                "player": _clean_text(row.get("player")),
                "season": latest_season,
                "team": _clean_text(row.get("team")),
                "pos": _clean_text(row.get("pos")),
                "g": _to_int(row.get("g")),
                "mpg": _to_float(row.get("mp_per_game")),
                "ppg": _to_float(row.get("pts_per_game")),
                "rpg": _to_float(row.get("trb_per_game")),
                "apg": _to_float(row.get("ast_per_game")),
                "spg": _to_float(row.get("stl_per_game")),
                "bpg": _to_float(row.get("blk_per_game")),
                "fg_pct": _to_float(row.get("fg_percent")),
                "fg3_pct": _to_float(row.get("x3p_percent")),
                "ft_pct": _to_float(row.get("ft_percent")),
            }

        with _LOCK:
            _BIO_CACHE = bio_cache
            _PER_GAME_CACHE = per_game_cache
            _LAST_ERROR = None
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Failed to load NBA player data workbook")
        with _LOCK:
            _LAST_ERROR = str(exc)
    finally:
        with _LOCK:
            _LOADING = False


def get_player_summary(names: Sequence[str]) -> str | None:
    """Return a concise NBA data summary for the first matching player."""
    if not ensure_loaded(wait=True):
        return None
    with _LOCK:
        per_game = _PER_GAME_CACHE or {}
        bio = _BIO_CACHE or {}
    for raw_name in names:
        if not raw_name:
            continue
        norm = _normalize_name(str(raw_name))
        if not norm:
            continue
        stats = per_game.get(norm)
        if stats is None:
            continue
        profile = bio.get(norm, {})
        return _format_summary(stats, profile)
    return None


def _fmt_num(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _format_summary(stats: dict[str, Any], profile: dict[str, Any]) -> str:
    bits: list[str] = []
    season = stats.get("season")
    team = stats.get("team") or "N/A"
    pos = stats.get("pos") or profile.get("pos") or "N/A"
    season_label = f"{season}" if season is not None else "recent season"
    bits.append(
        f"Latest NBA season {season_label} ({team}, {pos}): "
        f"{_fmt_num(stats.get('mpg'))} MPG — "
        f"{_fmt_num(stats.get('ppg'))} PTS, {_fmt_num(stats.get('rpg'))} REB, {_fmt_num(stats.get('apg'))} AST, "
        f"{_fmt_num(stats.get('spg'))} STL, {_fmt_num(stats.get('bpg'))} BLK; "
        f"shooting {_fmt_pct(stats.get('fg_pct'))} FG / {_fmt_pct(stats.get('fg3_pct'))} 3P / {_fmt_pct(stats.get('ft_pct'))} FT."
    )
    bio_pieces: list[str] = []
    height = _to_int(profile.get("height"))
    if height:
        bio_pieces.append(format_height_inches(height))
    weight = _to_int(profile.get("weight"))
    if weight:
        bio_pieces.append(f"{weight} lbs")
    college = profile.get("college")
    if college:
        bio_pieces.append(f"college: {college}")
    start = _to_int(profile.get("from"))
    end = _to_int(profile.get("to"))
    if start or end:
        span = f"{start or '?'}–{end or '?'}"
        bio_pieces.append(f"career span: {span}")
    if bio_pieces:
        bits.append("Bio: " + ", ".join(bio_pieces) + ".")
    return " ".join(bits)


def last_error() -> str | None:
    """Return the last load error, if any (for status messaging)."""
    with _LOCK:
        return _LAST_ERROR


__all__ = ["warm_cache_async", "ensure_loaded", "get_player_summary", "last_error"]
