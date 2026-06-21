from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
import unicodedata

from player_rules_core import PlayerProfileResult, _number, _profile_value

_EXCEL_EPOCH = date(1899, 12, 30)


def derive_player_profile_values(evidence: Any) -> PlayerProfileResult:
    values: dict[str, Any] = {}
    for key, result in _profile_results(evidence).items():
        values[key] = _profile_value(result)
    return PlayerProfileResult(values=values)


def _profile_results(evidence: Any) -> dict[str, dict[str, Any]]:
    player_name = str(getattr(evidence, "identity", {}).get("player") or getattr(evidence, "season_info", {}).get("player") or "").strip()
    first_name, last_name = _split_player_name(player_name)
    birthday = _birth_date(evidence)
    position, secondary = _positions(evidence)
    play_types = _play_types(evidence)
    return {
        "Vitals/FIRSTNAME": {"value": first_name, "source_rule": "profile_name_split_v1", "evidence_keys": ("identity.player",)},
        "Vitals/LASTNAME": {"value": last_name, "source_rule": "profile_name_split_v1", "evidence_keys": ("identity.player",)},
        "Vitals/BIRTHDAY": {"value": birthday.day, "source_rule": "profile_birth_day_from_source_v1", "evidence_keys": ("identity.birth_date",)},
        "Vitals/BIRTHMONTH": {"value": birthday.month, "source_rule": "profile_birth_month_from_source_v1", "evidence_keys": ("identity.birth_date",)},
        "Vitals/BIRTHYEAR": {"value": _birth_year_slot(evidence, birthday), "source_rule": "profile_birth_year_current_age_value_v1", "evidence_keys": ("identity.birth_date", "season_info.age")},
        "Vitals/WINGSPANCM": {"value": _wingspan_cm(evidence), "source_rule": "profile_wingspan_metric_height_minus_two_v1", "evidence_keys": ("identity.ht_in_in",)},
        "Vitals/POSITION": {"value": position, "source_rule": "profile_position_play_by_play_v1", "evidence_keys": ("play_by_play.pg_percent", "play_by_play.sg_percent", "play_by_play.sf_percent", "play_by_play.pf_percent", "play_by_play.c_percent")},
        "Vitals/SECONDARYPOSITION": {"value": secondary, "source_rule": "profile_secondary_position_play_by_play_v1", "evidence_keys": ("play_by_play.pg_percent", "play_by_play.sg_percent", "play_by_play.sf_percent", "play_by_play.pf_percent", "play_by_play.c_percent")},
        "Vitals/PLAYTYPE1": {"value": play_types[0], "source_rule": "profile_player_play_types_v1", "evidence_keys": _play_type_evidence()},
        "Vitals/PLAYTYPE2": {"value": play_types[1], "source_rule": "profile_player_play_types_v1", "evidence_keys": _play_type_evidence()},
        "Vitals/PLAYTYPE3": {"value": play_types[2], "source_rule": "profile_player_play_types_v1", "evidence_keys": _play_type_evidence()},
        "Vitals/PLAYTYPE4": {"value": play_types[3], "source_rule": "profile_player_play_types_v1", "evidence_keys": _play_type_evidence()},
    }


def _split_player_name(player_name: str) -> tuple[str, str]:
    clean = _ascii_name(player_name).replace(".", "").strip()
    parts = [part for part in clean.split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    if parts[-1].lower() in suffixes and len(parts) >= 3:
        return " ".join(parts[:-2]), f"{parts[-2]} {parts[-1]}"
    return " ".join(parts[:-1]), parts[-1]


def _ascii_name(text: str) -> str:
    replacements = {
        "Ä‡": "c",
        "Ä": "c",
        "Ä": "c",
        "Ä�": "d",
        "Ä‘": "d",
        "Å¡": "s",
        "Å½": "Z",
        "Å¾": "z",
        "Ä±": "i",
        "Ä°": "I",
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ã¶": "o",
        "Ã¼": "u",
        "Ã±": "n",
        "ё": "e",
        "Ё": "E",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if ord(ch) < 128)


def _birth_date(evidence: Any) -> date:
    value = getattr(evidence, "identity", {}).get("birth_date")
    number = _number({"birth_date": value}, "birth_date")
    if number is not None:
        return _EXCEL_EPOCH + timedelta(days=int(number))
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    age = int(_number(getattr(evidence, "season_info", {}), "age") or 25)
    return date(int(getattr(evidence, "season", 2026)) - age, 1, 1)


def _birth_year_slot(evidence: Any, birthday: date) -> int:
    season = int(getattr(evidence, "season", 2026))
    reference = date(season - 1, 10, 1)
    age = reference.year - birthday.year - ((reference.month, reference.day) < (birthday.month, birthday.day))
    if age < 0:
        age = int(_number(getattr(evidence, "season_info", {}), "age") or 0)
    return 1900 + age


def _wingspan_cm(evidence: Any) -> int:
    height = _number(getattr(evidence, "identity", {}), "ht_in_in") or 78.0
    return int(round((height - 2.0) * 2.54))


def _positions(evidence: Any) -> tuple[str, str]:
    play = getattr(evidence, "play_by_play", {})
    shares = (
        ("PG", _number(play, "pg_percent") or 0.0),
        ("SG", _number(play, "sg_percent") or 0.0),
        ("SF", _number(play, "sf_percent") or 0.0),
        ("PF", _number(play, "pf_percent") or 0.0),
        ("C", _number(play, "c_percent") or 0.0),
    )
    ordered = sorted(shares, key=lambda item: item[1], reverse=True)
    if ordered[0][1] > 0:
        first = ordered[0][0]
        second = ordered[1][0] if ordered[1][1] > 0 else first
        return first, second
    raw = str(getattr(evidence, "season_info", {}).get("pos") or getattr(evidence, "identity", {}).get("pos") or "SF")
    first = raw.split("-")[0].strip().upper() or "SF"
    return first, first


def _play_type_evidence() -> tuple[str, ...]:
    return (
        "per_game.ast_per_game",
        "per_game.x3pa_per_game",
        "advanced.ast_percent",
        "advanced.usg_percent",
        "shooting.percent_fga_from_x3p_range",
        "shooting.percent_dunks_of_fga",
        "shooting.percent_fga_from_x0_3_range",
        "shooting.percent_fga_from_x3_10_range",
        "play_by_play.points_generated_by_assists",
        "play_by_play.pg_percent",
        "play_by_play.sg_percent",
        "play_by_play.sf_percent",
        "play_by_play.pf_percent",
        "play_by_play.c_percent",
    )


def _play_types(evidence: Any) -> tuple[str, str, str, str]:
    pg = _number(getattr(evidence, "play_by_play", {}), "pg_percent") or 0.0
    sg = _number(getattr(evidence, "play_by_play", {}), "sg_percent") or 0.0
    sf = _number(getattr(evidence, "play_by_play", {}), "sf_percent") or 0.0
    pf = _number(getattr(evidence, "play_by_play", {}), "pf_percent") or 0.0
    c = _number(getattr(evidence, "play_by_play", {}), "c_percent") or 0.0
    ast = _number(getattr(evidence, "per_game", {}), "ast_per_game") or 0.0
    ast_pct = _number(getattr(evidence, "advanced", {}), "ast_percent") or 0.0
    x3pa = _number(getattr(evidence, "per_game", {}), "x3pa_per_game") or 0.0
    x3_share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x3p_range") or 0.0
    dunk_share = _number(getattr(evidence, "shooting", {}), "percent_dunks_of_fga") or 0.0
    rim_share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x0_3_range") or 0.0
    short_share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x3_10_range") or 0.0
    points_assist = _number(getattr(evidence, "play_by_play", {}), "points_generated_by_assists") or 0.0

    scores = {
        "P&R Ball Handler": (ast / 8.0) * 0.55 + (ast_pct / 40.0) * 0.30 + ((pg + sg) / 100.0) * 0.15,
        "P&R Wing": (ast / 6.0) * 0.45 + (ast_pct / 30.0) * 0.35 + ((sf + pf) / 100.0) * 0.20,
        "3 PT": (x3pa / 8.0) * 0.55 + x3_share * 0.45,
        "Handoff Receiver": (x3pa / 7.0) * 0.60 + x3_share * 0.40 - (ast / 12.0),
        "Handoff Passer": (points_assist / 1200.0) * 0.50 + (ast_pct / 35.0) * 0.35 + ((pf + c) / 100.0) * 0.15,
        "P&R Roll Man": dunk_share * 0.45 + rim_share * 0.25 + short_share * 0.15 + (c / 100.0) * 0.15,
        "Cutter": rim_share * 0.35 + dunk_share * 0.30 + ((sf + pf + c) / 100.0) * 0.35,
        "Post Up High": short_share * 0.45 + (ast / 8.0) * 0.25 + (c / 100.0) * 0.30,
        "Post Up Low": (rim_share + short_share) * 0.45 + dunk_share * 0.25 + (c / 100.0) * 0.30,
    }
    allowed = {
        "P&R Ball Handler": ((pg + sg) >= 20.0 or (c < 70.0 and ast >= 5.0 and ast_pct >= 20.0)) and scores["P&R Ball Handler"] >= 0.42,
        "P&R Wing": (sf + pf) >= 20.0 and ast >= 4.0 and scores["P&R Wing"] >= 0.55,
        "3 PT": x3pa >= 3.0 and scores["3 PT"] >= (0.40 if c >= 70.0 else 0.50),
        "Handoff Receiver": (sg + sf) >= 20.0 and x3pa >= 4.0 and ast < 3.0 and scores["Handoff Receiver"] >= 0.50,
        "Handoff Passer": (pf + c) >= 30.0 and ast >= 4.0 and points_assist >= 700.0 and scores["Handoff Passer"] >= 0.55,
        "P&R Roll Man": c >= 40.0 and (dunk_share >= 0.10 or rim_share >= 0.40 or short_share >= 0.35) and scores["P&R Roll Man"] >= 0.25,
        "Cutter": (sf + pf + c) >= 40.0 and ((x3pa < 3.0) or dunk_share >= 0.10 or rim_share >= 0.30) and scores["Cutter"] >= 0.35,
        "Post Up High": c >= 70.0 and ast >= 4.0 and short_share >= 0.30 and scores["Post Up High"] >= 0.55,
        "Post Up Low": c >= 70.0 and ast < 4.0 and (rim_share + short_share + dunk_share) >= 0.60 and scores["Post Up Low"] >= 0.55,
    }
    def sort_key(item: tuple[str, float]) -> tuple[float, float]:
        name, score = item
        if c >= 70.0 and ast >= 4.0:
            priority = {"3 PT": 4.0, "Handoff Passer": 3.0, "Post Up High": 2.0, "P&R Roll Man": 1.0}.get(name, 0.0)
        elif c >= 70.0:
            priority = {"P&R Roll Man": 4.0, "Cutter": 3.0, "Post Up Low": 2.0}.get(name, 0.0)
        else:
            priority = 1.0 if name == "P&R Ball Handler" and pg >= 70.0 and ast >= 5.0 else 0.0
        return (priority, score)

    ordered = [name for name, score in sorted(scores.items(), key=sort_key, reverse=True) if allowed[name]]
    if not ordered:
        ordered = [max(scores.items(), key=lambda item: item[1])[0]]
    while len(ordered) < 4:
        ordered.append("None")
    return (ordered[0], ordered[1], ordered[2], ordered[3])
