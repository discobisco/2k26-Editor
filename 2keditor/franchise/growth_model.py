from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable

_DEFAULT_NBA_DATA_ROOT = Path(__file__).resolve().parents[1] / "Player Generator" / "NBA Player Data"
_GROWTH_MODEL_RELATIVE_PATH = Path("statistical_growth_model") / "player_growth_model.sqlite"
_POOL_RELATIVE_PATH = Path("player_generation_pool") / "player_generation_pool.sqlite"
_BREF_ID_RE = re.compile(r"^[a-z]+[a-z0-9]*\d{2}$", re.IGNORECASE)


def default_nba_data_root() -> Path:
    return _DEFAULT_NBA_DATA_ROOT


def _growth_model_path(data_root: str | Path | None = None) -> Path:
    root = Path(data_root).expanduser().resolve() if data_root is not None else default_nba_data_root()
    return root / _GROWTH_MODEL_RELATIVE_PATH


def _pool_path(data_root: str | Path | None = None) -> Path:
    root = Path(data_root).expanduser().resolve() if data_root is not None else default_nba_data_root()
    return root / _POOL_RELATIVE_PATH


def _valid_master_player_id(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or not _BREF_ID_RE.match(text):
        return ""
    return text


def master_player_for_live_index(
    player_index: int,
    *,
    data_root: str | Path | None = None,
    run_id: str | None = None,
) -> tuple[str, str, str]:
    """Return no Master mapping; Pool packages intentionally contain no identity link."""

    path = _pool_path(data_root)
    if not path.is_file():
        return "", "", ""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        selected_run_id = run_id
        if selected_run_id is None:
            row = connection.execute("SELECT run_id FROM pool_runs ORDER BY run_id DESC LIMIT 1").fetchone()
            selected_run_id = str(row[0]) if row is not None else ""
    _ = player_index
    return "", "", selected_run_id or ""


def growth_facts_for_master_player(
    player_id: str,
    *,
    season: int,
    data_root: str | Path | None = None,
    source_limit: int = 6,
) -> tuple[tuple[str, str], ...]:
    """Return source-native growth facts for one master player-season."""

    selected_player_id = _valid_master_player_id(player_id)
    if not selected_player_id:
        return ()
    path = _growth_model_path(data_root)
    if not path.is_file():
        return ()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        profile = connection.execute(
            """
            SELECT player_id, player, season, next_season, total_metric_count,
                   improved_count, declined_count, unchanged_count,
                   strongest_source_table, weakest_source_table, coverage_confidence
              FROM player_growth_profile
             WHERE lower(player_id) = lower(?) AND season = ?
             LIMIT 1
            """,
            (selected_player_id, int(season)),
        ).fetchone()
        if profile is None:
            return (("growth_model_status", f"no_player_growth_profile_for_{int(season)}"),)
        sources = connection.execute(
            """
            SELECT source_table, metric_count
              FROM player_growth_source_profile
             WHERE lower(player_id) = lower(?) AND season = ?
             ORDER BY metric_count DESC, source_table
             LIMIT ?
            """,
            (selected_player_id, int(season), int(source_limit)),
        ).fetchall()
    source_text = "; ".join(f"{row['source_table']}:{int(row['metric_count'] or 0)}" for row in sources)
    facts: list[tuple[str, str]] = [
        ("growth_model_player_id", str(profile["player_id"] or selected_player_id)),
        ("growth_model_player", str(profile["player"] or "")),
        ("growth_model_season", str(int(profile["season"]))),
        ("growth_model_next_season", str(int(profile["next_season"]))),
        ("growth_model_metric_count", str(int(profile["total_metric_count"] or 0))),
        ("growth_model_positive_delta_count", str(int(profile["improved_count"] or 0))),
        ("growth_model_negative_delta_count", str(int(profile["declined_count"] or 0))),
        ("growth_model_unchanged_count", str(int(profile["unchanged_count"] or 0))),
        ("growth_model_strongest_source_table", str(profile["strongest_source_table"] or "")),
        ("growth_model_weakest_source_table", str(profile["weakest_source_table"] or "")),
        ("growth_model_coverage_confidence", str(profile["coverage_confidence"] or "")),
    ]
    if source_text:
        facts.append(("growth_model_sources", source_text))
    return tuple(facts)


def franchise_growth_facts_for_player(
    player_index: int,
    *,
    season: int,
    data_root: str | Path | None = None,
) -> tuple[tuple[str, str], ...]:
    """Growth-model facts for a live franchise player index.

    Pool player names and Master IDs are intentionally not mapping evidence, so
    no facts are returned until a separate exact identity source exists.
    """

    master_player_id, master_player, run_id = master_player_for_live_index(player_index, data_root=data_root)
    if not master_player_id:
        return ()
    facts: list[tuple[str, str]] = [
        ("growth_model_mapping_source", f"player_generation_pool:{run_id}:player_index"),
        ("growth_model_master_player_id", master_player_id),
    ]
    if master_player:
        facts.append(("growth_model_master_player", master_player))
    facts.extend(growth_facts_for_master_player(master_player_id, season=int(season), data_root=data_root))
    return tuple((key, value) for key, value in facts if value not in (None, ""))


def growth_facts_dict(facts: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {str(key): str(value) for key, value in facts}


__all__ = [
    "default_nba_data_root",
    "franchise_growth_facts_for_player",
    "growth_facts_dict",
    "growth_facts_for_master_player",
    "master_player_for_live_index",
]
