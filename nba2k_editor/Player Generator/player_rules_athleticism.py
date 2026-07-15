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

def derive_attribute_acceleration(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_acceleration', evidence, league_player_rows, (('!identity.wt', 0.35), ('per_game.stl_per_game', 0.25), ('per_game.ast_per_game', 0.2), ('team_summary.pace', 0.2)))

def derive_attribute_agility(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_agility', evidence, league_player_rows, (('!identity.wt', 0.35), ('per_game.stl_per_game', 0.25), ('per_game.ast_per_game', 0.2), ('team_summary.pace', 0.2)))

def derive_attribute_speed(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_speed', evidence, league_player_rows, (('!identity.wt', 0.3), ('per_game.stl_per_game', 0.25), ('per_game.ast_per_game', 0.2), ('team_summary.pace', 0.25)))

def derive_attribute_speedwithball(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_speedwithball', evidence, league_player_rows, (('per_game.ast_per_game', 0.45), ('advanced.ast_percent', 0.25), ('!identity.wt', 0.2), ('team_summary.pace', 0.1)))

def derive_attribute_stamina(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_stamina', evidence, league_player_rows, (('per_game.mp_per_game', 0.55), ('per_game.g', 0.25), ('per_game.gs', 0.2)))

def derive_attribute_strength(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_strength', evidence, league_player_rows, (('identity.wt', 0.55), ('identity.ht_in_in', 0.25), ('per_game.trb_per_game', 0.2)))

def derive_attribute_vertical(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_vertical', evidence, league_player_rows, (('per_game.blk_per_game', 0.35), ('per_game.orb_per_game', 0.3), ('identity.ht_in_in', 0.2), ('per_game.stl_per_game', 0.15)))

def derive_attribute_backdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_backdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_headdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_headdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_leftankledurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_leftankledurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_leftelbowdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_leftelbowdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_leftfootdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_leftfootdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_lefthanddurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_lefthanddurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_lefthipdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_lefthipdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_leftkneedurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_leftkneedurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_leftshoulderdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_leftshoulderdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_miscdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_miscdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_neckdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_neckdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_rightankledurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_rightankledurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_rightelbowdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_rightelbowdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_rightfootdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_rightfootdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_righthanddurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_righthanddurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_righthipdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_righthipdurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_rightkneedurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_rightkneedurability', 90, ('durability.default_90_pending_injury_database',))

def derive_attribute_rightshoulderdurability(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _fixed('derive_attribute_rightshoulderdurability', 90, ('durability.default_90_pending_injury_database',))

__all__ = ['derive_attribute_acceleration', 'derive_attribute_agility', 'derive_attribute_speed', 'derive_attribute_speedwithball', 'derive_attribute_stamina', 'derive_attribute_strength', 'derive_attribute_vertical', 'derive_attribute_backdurability', 'derive_attribute_headdurability', 'derive_attribute_leftankledurability', 'derive_attribute_leftelbowdurability', 'derive_attribute_leftfootdurability', 'derive_attribute_lefthanddurability', 'derive_attribute_lefthipdurability', 'derive_attribute_leftkneedurability', 'derive_attribute_leftshoulderdurability', 'derive_attribute_miscdurability', 'derive_attribute_neckdurability', 'derive_attribute_rightankledurability', 'derive_attribute_rightelbowdurability', 'derive_attribute_rightfootdurability', 'derive_attribute_righthanddurability', 'derive_attribute_righthipdurability', 'derive_attribute_rightkneedurability', 'derive_attribute_rightshoulderdurability']