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


def _rank(value: float, rows: Any, path: str) -> float:
    population = [_row_value(row, path) for row in tuple(rows or ())]
    population = [item for item in population if item != 0.0]
    if not population:
        return 0.0
    return sum(1 for item in population if item <= value) / len(population)


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
    return {"value": round(25 + score * 74), "source_rule": rule_name, "evidence_keys": keys}


def _tendency(rule_name: str, evidence: Any, rows: Any, parts: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    score, keys = _score(evidence, rows, parts)
    return {"value": round(score * 100), "source_rule": rule_name, "evidence_keys": keys}


def _fixed(rule_name: str, value: int, keys: tuple[str, ...]) -> dict[str, Any]:
    return {"value": value, "source_rule": rule_name, "evidence_keys": keys}

def derive_attribute_defenserebound(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_defenserebound', evidence, league_player_rows, (('advanced.drb_percent', 0.55), ('per_game.drb_per_game', 0.3), ('per_game.trb_per_game', 0.15)))

def derive_attribute_offensiverebound(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_offensiverebound', evidence, league_player_rows, (('advanced.orb_percent', 0.55), ('per_game.orb_per_game', 0.3), ('per_game.trb_per_game', 0.15)))

def derive_tendency_crash(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_crash', evidence, league_player_rows, (('advanced.orb_percent', 0.45), ('per_game.orb_per_game', 0.35), ('per_game.trb_per_game', 0.2)))

def derive_tendency_putback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_putback', evidence, league_player_rows, (('advanced.orb_percent', 0.45), ('per_game.orb_per_game', 0.35), ('per_game.fg_percent', 0.2)))

def derive_tendency_putbackdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_putbackdunk', evidence, league_player_rows, (('advanced.orb_percent', 0.35), ('per_game.orb_per_game', 0.25), ('identity.ht_in_in', 0.25), ('identity.wt', 0.15)))

__all__ = ['derive_attribute_defenserebound', 'derive_attribute_offensiverebound', 'derive_tendency_crash', 'derive_tendency_putback', 'derive_tendency_putbackdunk']
