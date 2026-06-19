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

def derive_attribute_hands(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_hands', evidence, league_player_rows, (('per_game.ast_per_game', 0.35), ('!advanced.tov_percent', 0.25), ('per_game.trb_per_game', 0.2), ('identity.ht_in_in', 0.2)))

def derive_attribute_hustle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_hustle', evidence, league_player_rows, (('per_game.trb_per_game', 0.35), ('per_game.stl_per_game', 0.25), ('advanced.ws', 0.25), ('per_game.g', 0.15)))

def derive_attribute_intangibles(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_intangibles', evidence, league_player_rows, (('advanced.ws', 0.35), ('advanced.per', 0.25), ('advanced.bpm', 0.2), ('team_summary.srs', 0.2)))

def derive_attribute_cachcedovr(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_cachcedovr', evidence, league_player_rows, (('advanced.per', 0.35), ('advanced.ws', 0.35), ('per_game.pts_per_game', 0.3)))

def derive_attribute_maxovr(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_maxovr', evidence, league_player_rows, (('advanced.per', 0.35), ('advanced.ws', 0.35), ('per_game.pts_per_game', 0.3)))

def derive_attribute_minovr(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_minovr', evidence, league_player_rows, (('advanced.per', 0.35), ('advanced.ws', 0.35), ('per_game.pts_per_game', 0.3)))

def derive_attribute_postfadeaway(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_postfadeaway', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2p_percent', 0.25), ('per_game.ft_percent', 0.2)))

def derive_attribute_potential(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_potential', evidence, league_player_rows, (('!season_info.age', 0.4), ('advanced.ws', 0.25), ('advanced.per', 0.2), ('per_game.g', 0.15)))

def derive_tendency_isovsaveragedefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_isovsaveragedefender', evidence, league_player_rows, (('advanced.usg_percent', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_isovselitedefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_isovselitedefender', evidence, league_player_rows, (('advanced.usg_percent', 0.45), ('per_game.fga_per_game', 0.35), ('advanced.ts_percent', 0.2)))

def derive_tendency_isovsgooddefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_isovsgooddefender', evidence, league_player_rows, (('advanced.usg_percent', 0.45), ('per_game.fga_per_game', 0.35), ('advanced.ts_percent', 0.2)))

def derive_tendency_isovspoordefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_isovspoordefender', evidence, league_player_rows, (('advanced.usg_percent', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.pts_per_game', 0.2)))

def derive_tendency_playdiscipline(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_playdiscipline', evidence, league_player_rows, (('!advanced.tov_percent', 0.35), ('advanced.ts_percent', 0.3), ('advanced.ws', 0.2), ('per_game.g', 0.15)))

def derive_tendency_rollvspop(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_rollvspop', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.4), ('per_game.x2pa_per_game', 0.3), ('identity.ht_in_in', 0.3)))

def derive_tendency_touches(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_touches', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('per_game.ast_per_game', 0.3), ('advanced.usg_percent', 0.25)))

def derive_tendency_transitionspotup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_transitionspotup', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.45), ('team_summary.pace', 0.3), ('per_game.fga_per_game', 0.25)))

__all__ = ['derive_attribute_hands', 'derive_attribute_hustle', 'derive_attribute_intangibles', 'derive_attribute_cachcedovr', 'derive_attribute_maxovr', 'derive_attribute_minovr', 'derive_attribute_postfadeaway', 'derive_attribute_potential', 'derive_tendency_isovsaveragedefender', 'derive_tendency_isovselitedefender', 'derive_tendency_isovsgooddefender', 'derive_tendency_isovspoordefender', 'derive_tendency_playdiscipline', 'derive_tendency_rollvspop', 'derive_tendency_touches', 'derive_tendency_transitionspotup']
