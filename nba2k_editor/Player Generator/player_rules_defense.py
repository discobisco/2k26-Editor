from __future__ import annotations

from typing import Any


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        return float(text) if text and text.upper() not in {"NA", "N/A", "NONE", "NULL"} else 0.0
    except Exception:
        return 0.0


def _source(evidence: Any, namespace: str) -> dict[str, Any]:
    return {
        "identity": getattr(evidence, "identity", {}),
        "season_info": getattr(evidence, "season_info", {}),
        "per_game": getattr(evidence, "per_game", {}),
        "totals": getattr(evidence, "totals", {}),
        "per_36": getattr(evidence, "per_36", {}),
        "per_100": getattr(evidence, "per_100", {}),
        "advanced": getattr(evidence, "advanced", {}),
        "shooting": getattr(evidence, "shooting", {}),
        "play_by_play": getattr(evidence, "play_by_play", {}),
        "team_stats_per_game": getattr(evidence, "team_stats_per_game", {}),
        "team_summary": getattr(evidence, "team_summary", {}),
        "opponent_stats_per_game": getattr(evidence, "opponent_stats_per_game", {}),
    }.get(namespace, {})


def _read(evidence: Any, path: str) -> float:
    namespace, _, key = path.partition(".")
    return _number(_source(evidence, namespace).get(key))


def _row_value(row: dict[str, Any], path: str) -> float:
    namespace, _, key = path.partition(".")
    for candidate in (path, key, f"player_{namespace}.{key}"):
        if candidate in row:
            return _number(row.get(candidate))
    return 0.0


_RANK_POPULATION_CACHE: dict[tuple[int, int, str], tuple[float, ...]] = {}


def _rank(value: float, rows: Any, path: str) -> float:
    import bisect

    row_tuple = tuple(rows or ())
    cache_key = (id(row_tuple), len(row_tuple), path)
    population = _RANK_POPULATION_CACHE.get(cache_key)
    if population is None:
        population = tuple(sorted(item for row in row_tuple if (item := _row_value(row, path)) != 0.0))
        _RANK_POPULATION_CACHE[cache_key] = population
    if not population:
        return 0.0
    return bisect.bisect_right(population, value) / len(population)


def _score(evidence: Any, rows: Any, parts: tuple[tuple[str, float], ...]) -> tuple[float, tuple[str, ...]]:
    total = 0.0
    weight_total = 0.0
    keys: list[str] = []
    for path, weight in parts:
        invert = path.startswith("!")
        clean = path[1:] if invert else path
        ranked = _rank(_read(evidence, clean), rows, clean)
        total += (1.0 - ranked if invert else ranked) * weight
        weight_total += weight
        keys.append(clean)
    return (total / weight_total if weight_total else 0.0), tuple(dict.fromkeys(keys))


def _attribute(rule_name: str, evidence: Any, rows: Any, parts: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    score, keys = _score(evidence, rows, parts)
    return {"value": round(25 + score * 74), "score": score, "source_rule": rule_name, "evidence_keys": keys}


def _tendency(rule_name: str, evidence: Any, rows: Any, parts: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    score, keys = _score(evidence, rows, parts)
    return {"value": round(score * 100), "score": score, "source_rule": rule_name, "evidence_keys": keys}


def _fixed(rule_name: str, value: int, keys: tuple[str, ...]) -> dict[str, Any]:
    return {"value": value, "source_rule": rule_name, "evidence_keys": keys}

def derive_attribute_block(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_block', evidence, league_player_rows, (('per_game.blk_per_game', 0.6), ('advanced.blk_percent', 0.4)))

def derive_attribute_defenseconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_defenseconsistency', evidence, league_player_rows, (('advanced.dws', 0.45), ('advanced.dbpm', 0.3), ('team_summary.d_rtg', 0.25)))

def derive_attribute_helpdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_helpdefense', evidence, league_player_rows, (('advanced.dws', 0.4), ('per_game.blk_per_game', 0.25), ('per_game.stl_per_game', 0.2), ('team_summary.d_rtg', 0.15)))

def derive_attribute_interiordefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_interiordefense', evidence, league_player_rows, (('per_game.blk_per_game', 0.35), ('advanced.blk_percent', 0.25), ('per_game.drb_per_game', 0.2), ('identity.ht_in_in', 0.2)))

def derive_attribute_passperception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passperception', evidence, league_player_rows, (('per_game.stl_per_game', 0.45), ('advanced.stl_percent', 0.35), ('advanced.dbpm', 0.2)))

def derive_attribute_perimeterdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_perimeterdefense', evidence, league_player_rows, (('per_game.stl_per_game', 0.4), ('advanced.stl_percent', 0.35), ('advanced.dbpm', 0.25)))

def derive_attribute_steal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_steal', evidence, league_player_rows, (('advanced.stl_percent', 0.6), ('per_game.stl_per_game', 0.4)))

def derive_attribute_lateralquickness(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_lateralquickness', evidence, league_player_rows, (('per_game.stl_per_game', 0.35), ('advanced.stl_percent', 0.35), ('!identity.wt', 0.3)))

def derive_attribute_pickandrolldefenseiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_pickandrolldefenseiq', evidence, league_player_rows, (('advanced.dbpm', 0.4), ('advanced.dws', 0.35), ('per_game.stl_per_game', 0.25)))

def derive_attribute_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_contestshot', evidence, league_player_rows, (('advanced.dbpm', 0.35), ('per_game.blk_per_game', 0.3), ('advanced.dws', 0.2), ('identity.ht_in_in', 0.15)))

def derive_tendency_blockshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_blockshot', evidence, league_player_rows, (('per_game.blk_per_game', 0.65), ('advanced.blk_percent', 0.35)))

def derive_tendency_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_contestshot', evidence, league_player_rows, (('advanced.dbpm', 0.35), ('per_game.blk_per_game', 0.25), ('advanced.dws', 0.25), ('per_game.pf_per_game', 0.15)))

def derive_tendency_foul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_foul', evidence, league_player_rows, (('per_game.pf_per_game', 0.75), ('advanced.f_tr', 0.25)))

def derive_tendency_hardfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_hardfoul', evidence, league_player_rows, (('per_game.pf_per_game', 0.65), ('identity.wt', 0.2), ('per_game.blk_per_game', 0.15)))

def derive_tendency_onballsteal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_onballsteal', evidence, league_player_rows, (('advanced.stl_percent', 0.55), ('per_game.stl_per_game', 0.45)))

def derive_tendency_passinterception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_passinterception', evidence, league_player_rows, (('advanced.stl_percent', 0.6), ('per_game.stl_per_game', 0.4)))

def derive_tendency_takecharge(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_takecharge', evidence, league_player_rows, (('per_game.pf_per_game', 0.4), ('advanced.dws', 0.35), ('identity.wt', 0.25)))

__all__ = ['derive_attribute_block', 'derive_attribute_defenseconsistency', 'derive_attribute_helpdefense', 'derive_attribute_interiordefense', 'derive_attribute_passperception', 'derive_attribute_perimeterdefense', 'derive_attribute_steal', 'derive_attribute_lateralquickness', 'derive_attribute_pickandrolldefenseiq', 'derive_attribute_contestshot', 'derive_tendency_blockshot', 'derive_tendency_contestshot', 'derive_tendency_foul', 'derive_tendency_hardfoul', 'derive_tendency_onballsteal', 'derive_tendency_passinterception', 'derive_tendency_takecharge']