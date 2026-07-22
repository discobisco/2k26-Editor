from __future__ import annotations

import bisect
from typing import Any


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        return float(text) if text and text.upper() not in {"NA", "N/A", "NONE", "NULL"} else 0.0
    except Exception:
        return 0.0


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _row_optional_number(row: dict[str, Any], path: str) -> float | None:
    namespace, _, key = path.partition(".")
    for candidate in (path, f"player_{namespace}.{key}", key):
        if candidate in row:
            return _optional_number(row.get(candidate))
    return None


def _shot_attempt_share(evidence: Any) -> float | None:
    player_attempts = _optional_number(_source(evidence, "totals").get("fga"))
    team_row = _source(evidence, "team_stats_per_game")
    team_attempts_per_game = _optional_number(team_row.get("fga_per_game"))
    team_games = _optional_number(team_row.get("g"))
    if player_attempts is None or team_attempts_per_game is None or team_games is None:
        return None
    team_attempts = team_attempts_per_game * team_games
    if player_attempts < 0.0 or team_attempts <= 0.0:
        return None
    return player_attempts / team_attempts


def _row_shot_attempt_share(row: dict[str, Any]) -> float | None:
    player_attempts = _row_optional_number(row, "totals.fga")
    team_attempts_per_game = _row_optional_number(row, "team_stats_per_game.fga_per_game")
    team_games = _row_optional_number(row, "team_stats_per_game.g")
    if player_attempts is None or team_attempts_per_game is None or team_games is None:
        return None
    team_attempts = team_attempts_per_game * team_games
    if player_attempts < 0.0 or team_attempts <= 0.0:
        return None
    return player_attempts / team_attempts


_RANK_POPULATION_CACHE: dict[tuple[int, int, str], tuple[float, ...]] = {}
_SHOT_ATTEMPT_SHARE_POPULATION_CACHE: dict[tuple[int, int], tuple[float, ...]] = {}


def _shot_attempt_share_percentile(shot_share: float, rows: Any) -> float | None:
    row_tuple = tuple(rows or ())
    cache_key = (id(row_tuple), len(row_tuple))
    population = _SHOT_ATTEMPT_SHARE_POPULATION_CACHE.get(cache_key)
    if population is None:
        population = tuple(sorted(
            share
            for row in row_tuple
            if (share := _row_shot_attempt_share(row)) is not None
        ))
        _SHOT_ATTEMPT_SHARE_POPULATION_CACHE[cache_key] = population
    if not population:
        return None
    return bisect.bisect_right(population, shot_share) / len(population)


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



def derive_attribute_ballcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_ballcontrol', evidence, league_player_rows, (('per_game.ast_per_game', 0.65), ('advanced.ast_percent', 0.25), ('!advanced.tov_percent', 0.1)))

def derive_attribute_drawfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_drawfoul', evidence, league_player_rows, (('per_game.fta_per_game', 0.7), ('advanced.f_tr', 0.3)))

def derive_attribute_offensiveconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_offensiveconsistency', evidence, league_player_rows, (('per_game.pts_per_game', 0.4), ('advanced.ts_percent', 0.3), ('advanced.ows', 0.3)))

def derive_attribute_passaccuracy(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passaccuracy', evidence, league_player_rows, (('per_game.ast_per_game', 0.7), ('advanced.ast_percent', 0.3)))

def derive_attribute_passiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passiq', evidence, league_player_rows, (('per_game.ast_per_game', 0.45), ('advanced.ast_percent', 0.35), ('!advanced.tov_percent', 0.2)))

def derive_attribute_passvision(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_passvision', evidence, league_player_rows, (('advanced.ast_percent', 0.6), ('per_game.ast_per_game', 0.4)))

def derive_attribute_iqshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute('derive_attribute_iqshot', evidence, league_player_rows, (('advanced.ts_percent', 0.55), ('per_game.fg_percent', 0.3), ('per_game.ft_percent', 0.15)))

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

def derive_tendency_postfaceup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postfaceup', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_posthopstep(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_posthopstep', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postspin', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_postup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency('derive_tendency_postup', evidence, league_player_rows, (('identity.ht_in_in', 0.3), ('identity.wt', 0.25), ('per_game.x2pa_per_game', 0.25), ('per_game.orb_per_game', 0.2)))

def derive_tendency_shot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    shot_share = _shot_attempt_share(evidence)
    if shot_share is None:
        return None
    score = _shot_attempt_share_percentile(shot_share, league_player_rows)
    if score is None:
        return None
    return {
        "value": round(score * 100),
        "score": score,
        "source_rule": "derive_tendency_shot_team_attempt_share",
        "evidence_keys": (
            "totals.fga",
            "team_stats_per_game.fga_per_game",
            "team_stats_per_game.g",
            f"shot_attempt_share={shot_share:.8f}",
            "scale=league_player_shot_attempt_share_percentile",
        ),
    }

__all__ = ['derive_attribute_ballcontrol', 'derive_attribute_drawfoul', 'derive_attribute_offensiveconsistency', 'derive_attribute_passaccuracy', 'derive_attribute_passiq', 'derive_attribute_passvision', 'derive_attribute_iqshot', 'derive_tendency_drive', 'derive_tendency_attackstrongondrive', 'derive_tendency_driveright', 'derive_tendency_drivingbehindtheback', 'derive_tendency_dribblecrossover', 'derive_tendency_drivingdoublecrossover', 'derive_tendency_drivingdribblehesitation', 'derive_tendency_drivinghalfspin', 'derive_tendency_drivinginandout', 'derive_tendency_dribblespin', 'derive_tendency_drivingstepback', 'derive_tendency_offscreendrive', 'derive_tendency_spotupdrive', 'derive_tendency_nodrivingdribblemove', 'derive_tendency_nosetupdribble', 'derive_tendency_setupwithhesitation', 'derive_tendency_setupwithsizeup', 'derive_tendency_triplethreatidle', 'derive_tendency_triplethreatjabstep', 'derive_tendency_triplethreatpumpfake', 'derive_tendency_threattripleshot', 'derive_tendency_alleyooppass', 'derive_tendency_dishtoopenman', 'derive_tendency_flashypass', 'derive_tendency_postaggressivebackdown', 'derive_tendency_postbackdown', 'derive_tendency_postdrive', 'derive_tendency_postfaceup', 'derive_tendency_posthopstep', 'derive_tendency_postspin', 'derive_tendency_postup', 'derive_tendency_shot']