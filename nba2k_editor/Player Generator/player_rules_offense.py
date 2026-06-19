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

def derive_attribute_field_3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_field_3point', evidence, league_player_rows, (('per_game.x3p_percent', 0.7), ('per_game.x3pa_per_game', 0.3)))

def derive_attribute_ballcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_ballcontrol', evidence, league_player_rows, (('per_game.ast_per_game', 0.65), ('advanced.ast_percent', 0.25), ('!advanced.tov_percent', 0.1)))

def derive_attribute_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_closeshot', evidence, league_player_rows, (('per_game.x2p_percent', 0.55), ('per_game.fg_percent', 0.3), ('per_game.fga_per_game', 0.15)))

def derive_attribute_drawfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_drawfoul', evidence, league_player_rows, (('per_game.fta_per_game', 0.7), ('advanced.f_tr', 0.3)))

def derive_attribute_drivingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_drivingdunk', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.45), ('shooting.num_of_dunks', 0.35), ('identity.ht_in_in', 0.2)))

def derive_attribute_drivinglayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_drivinglayup', evidence, league_player_rows, (('per_game.x2p_percent', 0.45), ('per_game.fg_percent', 0.3), ('per_game.fta_per_game', 0.25)))

def derive_attribute_freethrow(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_freethrow', evidence, league_player_rows, (('per_game.ft_percent', 1.0),))

def derive_attribute_midrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_midrange', evidence, league_player_rows, (('per_game.x2p_percent', 0.45), ('per_game.fg_percent', 0.35), ('per_game.ft_percent', 0.2)))

def derive_attribute_offensiveconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_offensiveconsistency', evidence, league_player_rows, (('per_game.pts_per_game', 0.4), ('advanced.ts_percent', 0.3), ('advanced.ows', 0.3)))

def derive_attribute_passaccuracy(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passaccuracy', evidence, league_player_rows, (('per_game.ast_per_game', 0.7), ('advanced.ast_percent', 0.3)))

def derive_attribute_passiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passiq', evidence, league_player_rows, (('per_game.ast_per_game', 0.45), ('advanced.ast_percent', 0.35), ('!advanced.tov_percent', 0.2)))

def derive_attribute_passvision(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passvision', evidence, league_player_rows, (('advanced.ast_percent', 0.6), ('per_game.ast_per_game', 0.4)))

def derive_attribute_postfade(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_postfade', evidence, league_player_rows, (('identity.ht_in_in', 0.25), ('identity.wt', 0.25), ('per_game.x2p_percent', 0.3), ('per_game.pts_per_game', 0.2)))

def derive_attribute_posthook(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_posthook', evidence, league_player_rows, (('identity.ht_in_in', 0.35), ('identity.wt', 0.25), ('per_game.x2p_percent', 0.25), ('per_game.fta_per_game', 0.15)))

def derive_attribute_postcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_postcontrol', evidence, league_player_rows, (('identity.wt', 0.35), ('identity.ht_in_in', 0.3), ('per_game.trb_per_game', 0.2), ('per_game.x2p_percent', 0.15)))

def derive_attribute_iqshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_iqshot', evidence, league_player_rows, (('advanced.ts_percent', 0.55), ('per_game.fg_percent', 0.3), ('per_game.ft_percent', 0.15)))

def derive_attribute_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_standingdunk', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.35), ('identity.ht_in_in', 0.35), ('identity.wt', 0.2), ('per_game.orb_per_game', 0.1)))

def derive_tendency_field_3pointshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointcentershot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointcentershot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointleftshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointleftshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointcenterleftshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointcenterleftshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointrightshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointrightshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointcenterrightshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointcenterrightshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointoffscreenshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointoffscreenshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3pointspotupshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3pointspotupshot', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_drivepullup3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivepullup3point', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_stepbackjumper3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_stepbackjumper3point', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_transitionpullup3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_transitionpullup3point', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_center3(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_center3', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_left3(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_left3', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_right3(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_right3', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3center(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3center', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3left(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3left', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3leftcenter(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3leftcenter', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3right(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3right', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_field_3rightcenter(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_field_3rightcenter', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_contestedjumper3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_contestedjumper3point', evidence, league_player_rows, (('per_game.x3pa_per_game', 0.65), ('advanced.x3p_ar', 0.2), ('per_game.x3p_percent', 0.15)))

def derive_tendency_midshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_centermidshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_centermidshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_leftmidshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_leftmidshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_centerleftmidshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_centerleftmidshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrightshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrightshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_centermidrightshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_centermidrightshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midoffscreenshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midoffscreenshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midspotupshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midspotupshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_contestedjumpermid(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_contestedjumpermid', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_contestedjumpermidrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_contestedjumpermidrange', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_drivepullupmidrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivepullupmidrange', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_drivepullupmid(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivepullupmid', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_stepbackjumpermid(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_stepbackjumpermid', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_stepbackjumpermidrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_stepbackjumpermidrange', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_spinjumper(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_spinjumper', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrangecenter(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrangecenter', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrangeleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrangeleft', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrangeleftcenter(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrangeleftcenter', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrangeright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrangeright', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_midrangerightcenter(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_midrangerightcenter', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.45), ('per_game.fga_per_game', 0.35), ('per_game.ft_percent', 0.2)))

def derive_tendency_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closeshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closeleftshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closeleftshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closemiddleshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closemiddleshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closerightshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closerightshot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_basketundershot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_basketundershot', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_underbasket(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_underbasket', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_floater(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_floater', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closeleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closeleft', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closemiddle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closemiddle', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_closeright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_closeright', evidence, league_player_rows, (('per_game.x2pa_per_game', 0.5), ('per_game.fta_per_game', 0.25), ('per_game.orb_per_game', 0.25)))

def derive_tendency_drivinglayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivinglayup', evidence, league_player_rows, (('per_game.fta_per_game', 0.45), ('per_game.x2pa_per_game', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_eurosteplayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_eurosteplayup', evidence, league_player_rows, (('per_game.fta_per_game', 0.45), ('per_game.x2pa_per_game', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_hopsteplayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_hopsteplayup', evidence, league_player_rows, (('per_game.fta_per_game', 0.45), ('per_game.x2pa_per_game', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_spinlayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_spinlayup', evidence, league_player_rows, (('per_game.fta_per_game', 0.45), ('per_game.x2pa_per_game', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_drivingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivingdunk', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.35), ('shooting.num_of_dunks', 0.3), ('identity.ht_in_in', 0.25), ('per_game.orb_per_game', 0.1)))

def derive_tendency_flashydunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_flashydunk', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.35), ('shooting.num_of_dunks', 0.3), ('identity.ht_in_in', 0.25), ('per_game.orb_per_game', 0.1)))

def derive_tendency_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_standingdunk', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.35), ('shooting.num_of_dunks', 0.3), ('identity.ht_in_in', 0.25), ('per_game.orb_per_game', 0.1)))

def derive_tendency_alleyoop(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_alleyoop', evidence, league_player_rows, (('shooting.percent_dunks_of_fga', 0.35), ('shooting.num_of_dunks', 0.3), ('identity.ht_in_in', 0.25), ('per_game.orb_per_game', 0.1)))

def derive_tendency_drive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drive', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_attackstrongondrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_attackstrongondrive', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_driveright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_driveright', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivingbehindtheback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivingbehindtheback', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_dribblecrossover(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_dribblecrossover', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivingdoublecrossover(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivingdoublecrossover', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivingdribblehesitation(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivingdribblehesitation', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivinghalfspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivinghalfspin', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivinginandout(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivinginandout', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_dribblespin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_dribblespin', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_drivingstepback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_drivingstepback', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_offscreendrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_offscreendrive', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_spotupdrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_spotupdrive', evidence, league_player_rows, (('per_game.fta_per_game', 0.4), ('per_game.ast_per_game', 0.3), ('per_game.fga_per_game', 0.3)))

def derive_tendency_nodrivingdribblemove(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_nodrivingdribblemove', evidence, league_player_rows, (('!per_game.fta_per_game', 0.5), ('!per_game.ast_per_game', 0.3), ('!advanced.usg_percent', 0.2)))

def derive_tendency_nosetupdribble(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_nosetupdribble', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_setupwithhesitation(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_setupwithhesitation', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_setupwithsizeup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_setupwithsizeup', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_triplethreatidle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_triplethreatidle', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_triplethreatjabstep(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_triplethreatjabstep', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_triplethreatpumpfake(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_triplethreatpumpfake', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_threattripleshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_threattripleshot', evidence, league_player_rows, (('per_game.fga_per_game', 0.45), ('advanced.usg_percent', 0.35), ('per_game.ast_per_game', 0.2)))

def derive_tendency_alleyooppass(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_alleyooppass', evidence, league_player_rows, (('per_game.ast_per_game', 0.7), ('advanced.ast_percent', 0.3)))

def derive_tendency_dishtoopenman(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_dishtoopenman', evidence, league_player_rows, (('per_game.ast_per_game', 0.7), ('advanced.ast_percent', 0.3)))

def derive_tendency_flashypass(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_flashypass', evidence, league_player_rows, (('per_game.ast_per_game', 0.7), ('advanced.ast_percent', 0.3)))

def derive_tendency_postaggressivebackdown(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postaggressivebackdown', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postbackdown(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postbackdown', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postdrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postdrive', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postdropstep(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postdropstep', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postfaceup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postfaceup', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postfadeleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postfadeleft', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postfaderight(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postfaderight', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_posthookleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_posthookleft', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_posthookright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_posthookright', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_hoppostshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_hoppostshot', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_posthopstep(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_posthopstep', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postshimmyshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postshimmyshot', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postspin', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_poststepbackshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_poststepbackshot', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postup', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postupandunder(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postupandunder', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_frompostshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_frompostshot', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_stepthrough(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_stepthrough', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_useglass(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_useglass', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_shot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_shot', evidence, league_player_rows, (('per_game.fga_per_game', 0.65), ('advanced.usg_percent', 0.35)))

__all__ = ['derive_attribute_field_3point', 'derive_attribute_ballcontrol', 'derive_attribute_closeshot', 'derive_attribute_drawfoul', 'derive_attribute_drivingdunk', 'derive_attribute_drivinglayup', 'derive_attribute_freethrow', 'derive_attribute_midrange', 'derive_attribute_offensiveconsistency', 'derive_attribute_passaccuracy', 'derive_attribute_passiq', 'derive_attribute_passvision', 'derive_attribute_postfade', 'derive_attribute_posthook', 'derive_attribute_postcontrol', 'derive_attribute_iqshot', 'derive_attribute_standingdunk', 'derive_tendency_field_3pointshot', 'derive_tendency_field_3pointcentershot', 'derive_tendency_field_3pointleftshot', 'derive_tendency_field_3pointcenterleftshot', 'derive_tendency_field_3pointrightshot', 'derive_tendency_field_3pointcenterrightshot', 'derive_tendency_field_3pointoffscreenshot', 'derive_tendency_field_3pointspotupshot', 'derive_tendency_drivepullup3point', 'derive_tendency_stepbackjumper3point', 'derive_tendency_transitionpullup3point', 'derive_tendency_center3', 'derive_tendency_left3', 'derive_tendency_right3', 'derive_tendency_field_3center', 'derive_tendency_field_3left', 'derive_tendency_field_3leftcenter', 'derive_tendency_field_3right', 'derive_tendency_field_3rightcenter', 'derive_tendency_contestedjumper3point', 'derive_tendency_midshot', 'derive_tendency_centermidshot', 'derive_tendency_leftmidshot', 'derive_tendency_centerleftmidshot', 'derive_tendency_midrightshot', 'derive_tendency_centermidrightshot', 'derive_tendency_midoffscreenshot', 'derive_tendency_midspotupshot', 'derive_tendency_contestedjumpermid', 'derive_tendency_contestedjumpermidrange', 'derive_tendency_drivepullupmidrange', 'derive_tendency_drivepullupmid', 'derive_tendency_stepbackjumpermid', 'derive_tendency_stepbackjumpermidrange', 'derive_tendency_spinjumper', 'derive_tendency_midrangecenter', 'derive_tendency_midrangeleft', 'derive_tendency_midrangeleftcenter', 'derive_tendency_midrangeright', 'derive_tendency_midrangerightcenter', 'derive_tendency_closeshot', 'derive_tendency_closeleftshot', 'derive_tendency_closemiddleshot', 'derive_tendency_closerightshot', 'derive_tendency_basketundershot', 'derive_tendency_underbasket', 'derive_tendency_floater', 'derive_tendency_closeleft', 'derive_tendency_closemiddle', 'derive_tendency_closeright', 'derive_tendency_drivinglayup', 'derive_tendency_eurosteplayup', 'derive_tendency_hopsteplayup', 'derive_tendency_spinlayup', 'derive_tendency_drivingdunk', 'derive_tendency_flashydunk', 'derive_tendency_standingdunk', 'derive_tendency_alleyoop', 'derive_tendency_drive', 'derive_tendency_attackstrongondrive', 'derive_tendency_driveright', 'derive_tendency_drivingbehindtheback', 'derive_tendency_dribblecrossover', 'derive_tendency_drivingdoublecrossover', 'derive_tendency_drivingdribblehesitation', 'derive_tendency_drivinghalfspin', 'derive_tendency_drivinginandout', 'derive_tendency_dribblespin', 'derive_tendency_drivingstepback', 'derive_tendency_offscreendrive', 'derive_tendency_spotupdrive', 'derive_tendency_nodrivingdribblemove', 'derive_tendency_nosetupdribble', 'derive_tendency_setupwithhesitation', 'derive_tendency_setupwithsizeup', 'derive_tendency_triplethreatidle', 'derive_tendency_triplethreatjabstep', 'derive_tendency_triplethreatpumpfake', 'derive_tendency_threattripleshot', 'derive_tendency_alleyooppass', 'derive_tendency_dishtoopenman', 'derive_tendency_flashypass', 'derive_tendency_postaggressivebackdown', 'derive_tendency_postbackdown', 'derive_tendency_postdrive', 'derive_tendency_postdropstep', 'derive_tendency_postfaceup', 'derive_tendency_postfadeleft', 'derive_tendency_postfaderight', 'derive_tendency_posthookleft', 'derive_tendency_posthookright', 'derive_tendency_hoppostshot', 'derive_tendency_posthopstep', 'derive_tendency_postshimmyshot', 'derive_tendency_postspin', 'derive_tendency_poststepbackshot', 'derive_tendency_postup', 'derive_tendency_postupandunder', 'derive_tendency_frompostshot', 'derive_tendency_stepthrough', 'derive_tendency_useglass', 'derive_tendency_shot']
