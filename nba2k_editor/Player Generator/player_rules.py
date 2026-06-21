from __future__ import annotations

from typing import Any, Callable

from player_rules_core import PlayerRuleResult, PlayerProfileResult, ProfileValue, RuleSpec, RuleValue, _number, _profile_value, _rule_value
from player_rules_profile import derive_player_profile_values, _split_player_name
from player_rules_offense import (
    derive_attribute_ballcontrol,
    derive_attribute_closeshot,
    derive_attribute_drawfoul,
    derive_attribute_drivingdunk,
    derive_attribute_drivinglayup,
    derive_attribute_field_3point,
    derive_attribute_freethrow,
    derive_attribute_iqshot,
    derive_attribute_midrange,
    derive_attribute_offensiveconsistency,
    derive_attribute_passaccuracy,
    derive_attribute_passiq,
    derive_attribute_passvision,
    derive_attribute_postcontrol,
    derive_attribute_postfade,
    derive_attribute_postfadeaway,
    derive_attribute_posthook,
    derive_attribute_standingdunk,
    derive_tendency_3pointshot,
    derive_tendency_3pointspotupshot,
    derive_tendency_alleyoop,
    derive_tendency_closeshot,
    derive_tendency_drivepullup3point,
    derive_tendency_drivingdunk,
    derive_tendency_drivinglayup,
    derive_tendency_eurosteplayup,
    derive_tendency_flashydunk,
    derive_tendency_hopsteplayup,
    derive_tendency_midshot,
    derive_tendency_postfadeleft,
    derive_tendency_postfaderight,
    derive_tendency_posthookleft,
    derive_tendency_posthookright,
    derive_tendency_postup,
    derive_tendency_shot,
    derive_tendency_spinlayup,
    derive_tendency_standingdunk,
    derive_tendency_stepbackjumper3point,
)
from player_rules_defense import (
    derive_attribute_block,
    derive_attribute_contestshot,
    derive_attribute_defenseconsistency,
    derive_attribute_helpdefense,
    derive_attribute_interiordefense,
    derive_attribute_passperception,
    derive_attribute_perimeterdefense,
    derive_attribute_pickandrolldefenseiq,
    derive_attribute_steal,
    derive_tendency_blockshot,
    derive_tendency_contestshot,
    derive_tendency_foul,
    derive_tendency_hardfoul,
    derive_tendency_onballsteal,
    derive_tendency_passinterception,
)
from player_rules_athleticism import (
    derive_attribute_agility,
    derive_attribute_speed,
    derive_attribute_speedwithball,
    derive_attribute_stamina,
    derive_attribute_strength,
    derive_attribute_vertical,
)
from player_rules_rebounding import (
    derive_attribute_defensiverebound,
    derive_attribute_offensiverebound,
    derive_tendency_crash,
    derive_tendency_putback,
    derive_tendency_putbackdunk,
)
from player_rules_mental import (
    derive_attribute_hands,
    derive_attribute_hustle,
    derive_attribute_intangibles,
    derive_attribute_potential,
    derive_tendency_playdiscipline,
    derive_tendency_touches,
)

RuleFunction = Callable[..., dict[str, Any]]

_RULE_FUNCTIONS: dict[str, RuleFunction] = {
    name: value
    for name, value in globals().items()
    if name.startswith("derive_attribute_") or name.startswith("derive_tendency_")
}

PLAYER_RULE_SCHEME: dict[str, RuleSpec] = {
    "Attributes/3POINT": RuleSpec("Attributes/3POINT", "offense", "derive_attribute_field_3point"),
    "Attributes/CLOSESHOT": RuleSpec("Attributes/CLOSESHOT", "offense", "derive_attribute_closeshot"),
    "Attributes/MIDRANGE": RuleSpec("Attributes/MIDRANGE", "offense", "derive_attribute_midrange"),
    "Attributes/FREETHROW": RuleSpec("Attributes/FREETHROW", "offense", "derive_attribute_freethrow"),
    "Attributes/DRAWFOUL": RuleSpec("Attributes/DRAWFOUL", "offense", "derive_attribute_drawfoul"),
    "Attributes/DRIVINGLAYUP": RuleSpec("Attributes/DRIVINGLAYUP", "offense", "derive_attribute_drivinglayup"),
    "Attributes/DRIVINGDUNK": RuleSpec("Attributes/DRIVINGDUNK", "offense", "derive_attribute_drivingdunk"),
    "Attributes/STANDINGDUNK": RuleSpec("Attributes/STANDINGDUNK", "offense", "derive_attribute_standingdunk"),
    "Attributes/PASSACCURACY": RuleSpec("Attributes/PASSACCURACY", "offense", "derive_attribute_passaccuracy"),
    "Attributes/PASSVISION": RuleSpec("Attributes/PASSVISION", "offense", "derive_attribute_passvision"),
    "Attributes/PASSIQ": RuleSpec("Attributes/PASSIQ", "offense", "derive_attribute_passiq"),
    "Attributes/BALLCONTROL": RuleSpec("Attributes/BALLCONTROL", "offense", "derive_attribute_ballcontrol"),
    "Attributes/POSTFADEAWAY": RuleSpec("Attributes/POSTFADEAWAY", "offense", "derive_attribute_postfadeaway"),
    "Attributes/POSTFADE": RuleSpec("Attributes/POSTFADE", "offense", "derive_attribute_postfade"),
    "Attributes/POSTHOOK": RuleSpec("Attributes/POSTHOOK", "offense", "derive_attribute_posthook"),
    "Attributes/POSTCONTROL": RuleSpec("Attributes/POSTCONTROL", "offense", "derive_attribute_postcontrol"),
    "Attributes/OFFENSIVECONSISTENCY": RuleSpec("Attributes/OFFENSIVECONSISTENCY", "offense", "derive_attribute_offensiveconsistency"),
    "Attributes/IQSHOT": RuleSpec("Attributes/IQSHOT", "offense", "derive_attribute_iqshot"),
    "Attributes/BLOCK": RuleSpec("Attributes/BLOCK", "defense", "derive_attribute_block"),
    "Attributes/STEAL": RuleSpec("Attributes/STEAL", "defense", "derive_attribute_steal"),
    "Attributes/PASSPERCEPTION": RuleSpec("Attributes/PASSPERCEPTION", "defense", "derive_attribute_passperception"),
    "Attributes/PERIMETERDEFENSE": RuleSpec("Attributes/PERIMETERDEFENSE", "defense", "derive_attribute_perimeterdefense"),
    "Attributes/INTERIORDEFENSE": RuleSpec("Attributes/INTERIORDEFENSE", "defense", "derive_attribute_interiordefense"),
    "Attributes/HELPDEFENSE": RuleSpec("Attributes/HELPDEFENSE", "defense", "derive_attribute_helpdefense"),
    "Attributes/DEFENSECONSISTENCY": RuleSpec("Attributes/DEFENSECONSISTENCY", "defense", "derive_attribute_defenseconsistency"),
    "Attributes/PICKANDROLLDEFENSEIQ": RuleSpec("Attributes/PICKANDROLLDEFENSEIQ", "defense", "derive_attribute_pickandrolldefenseiq"),
    "Attributes/CONTESTSHOT": RuleSpec("Attributes/CONTESTSHOT", "defense", "derive_attribute_contestshot"),
    "Attributes/SPEED": RuleSpec("Attributes/SPEED", "athleticism", "derive_attribute_speed"),
    "Attributes/SPEEDWITHBALL": RuleSpec("Attributes/SPEEDWITHBALL", "athleticism", "derive_attribute_speedwithball"),
    "Attributes/AGILITY": RuleSpec("Attributes/AGILITY", "athleticism", "derive_attribute_agility"),
    "Attributes/STAMINA": RuleSpec("Attributes/STAMINA", "athleticism", "derive_attribute_stamina"),
    "Attributes/STRENGTH": RuleSpec("Attributes/STRENGTH", "athleticism", "derive_attribute_strength"),
    "Attributes/VERTICAL": RuleSpec("Attributes/VERTICAL", "athleticism", "derive_attribute_vertical"),
    "Attributes/OFFENSIVEREBOUND": RuleSpec("Attributes/OFFENSIVEREBOUND", "rebounding", "derive_attribute_offensiverebound"),
    "Attributes/DEFENSEREBOUND": RuleSpec("Attributes/DEFENSEREBOUND", "rebounding", "derive_attribute_defensiverebound"),
    "Attributes/HANDS": RuleSpec("Attributes/HANDS", "mental", "derive_attribute_hands"),
    "Attributes/HUSTLE": RuleSpec("Attributes/HUSTLE", "mental", "derive_attribute_hustle"),
    "Attributes/INTANGIBLES": RuleSpec("Attributes/INTANGIBLES", "mental", "derive_attribute_intangibles"),
    "Attributes/POTENTIAL": RuleSpec("Attributes/POTENTIAL", "mental", "derive_attribute_potential"),
    "Tendencies/SHOT": RuleSpec("Tendencies/SHOT", "offense", "derive_tendency_shot"),
    "Tendencies/3POINTSHOT": RuleSpec("Tendencies/3POINTSHOT", "offense", "derive_tendency_3pointshot"),
    "Tendencies/3POINTSPOTUPSHOT": RuleSpec("Tendencies/3POINTSPOTUPSHOT", "offense", "derive_tendency_3pointspotupshot"),
    "Tendencies/DRIVEPULLUP3POINT": RuleSpec("Tendencies/DRIVEPULLUP3POINT", "offense", "derive_tendency_drivepullup3point"),
    "Tendencies/STEPBACKJUMPER3POINT": RuleSpec("Tendencies/STEPBACKJUMPER3POINT", "offense", "derive_tendency_stepbackjumper3point"),
    "Tendencies/MIDSHOT": RuleSpec("Tendencies/MIDSHOT", "offense", "derive_tendency_midshot"),
    "Tendencies/CLOSESHOT": RuleSpec("Tendencies/CLOSESHOT", "offense", "derive_tendency_closeshot"),
    "Tendencies/DRIVINGLAYUP": RuleSpec("Tendencies/DRIVINGLAYUP", "offense", "derive_tendency_drivinglayup"),
    "Tendencies/EUROSTEPLAYUP": RuleSpec("Tendencies/EUROSTEPLAYUP", "offense", "derive_tendency_eurosteplayup"),
    "Tendencies/HOPSTEPLAYUP": RuleSpec("Tendencies/HOPSTEPLAYUP", "offense", "derive_tendency_hopsteplayup"),
    "Tendencies/SPINLAYUP": RuleSpec("Tendencies/SPINLAYUP", "offense", "derive_tendency_spinlayup"),
    "Tendencies/DRIVINGDUNK": RuleSpec("Tendencies/DRIVINGDUNK", "offense", "derive_tendency_drivingdunk"),
    "Tendencies/STANDINGDUNK": RuleSpec("Tendencies/STANDINGDUNK", "offense", "derive_tendency_standingdunk"),
    "Tendencies/FLASHYDUNK": RuleSpec("Tendencies/FLASHYDUNK", "offense", "derive_tendency_flashydunk"),
    "Tendencies/ALLEYOOP": RuleSpec("Tendencies/ALLEYOOP", "offense", "derive_tendency_alleyoop"),
    "Tendencies/POSTUP": RuleSpec("Tendencies/POSTUP", "offense", "derive_tendency_postup"),
    "Tendencies/POSTFADELEFT": RuleSpec("Tendencies/POSTFADELEFT", "offense", "derive_tendency_postfadeleft"),
    "Tendencies/POSTFADERIGHT": RuleSpec("Tendencies/POSTFADERIGHT", "offense", "derive_tendency_postfaderight"),
    "Tendencies/POSTHOOKLEFT": RuleSpec("Tendencies/POSTHOOKLEFT", "offense", "derive_tendency_posthookleft"),
    "Tendencies/POSTHOOKRIGHT": RuleSpec("Tendencies/POSTHOOKRIGHT", "offense", "derive_tendency_posthookright"),
    "Tendencies/FOUL": RuleSpec("Tendencies/FOUL", "defense", "derive_tendency_foul"),
    "Tendencies/HARDFOUL": RuleSpec("Tendencies/HARDFOUL", "defense", "derive_tendency_hardfoul"),
    "Tendencies/BLOCKSHOT": RuleSpec("Tendencies/BLOCKSHOT", "defense", "derive_tendency_blockshot"),
    "Tendencies/ONBALLSTEAL": RuleSpec("Tendencies/ONBALLSTEAL", "defense", "derive_tendency_onballsteal"),
    "Tendencies/PASSINTERCEPTION": RuleSpec("Tendencies/PASSINTERCEPTION", "defense", "derive_tendency_passinterception"),
    "Tendencies/CONTESTSHOT": RuleSpec("Tendencies/CONTESTSHOT", "defense", "derive_tendency_contestshot"),
    "Tendencies/CRASH": RuleSpec("Tendencies/CRASH", "rebounding", "derive_tendency_crash"),
    "Tendencies/PUTBACK": RuleSpec("Tendencies/PUTBACK", "rebounding", "derive_tendency_putback"),
    "Tendencies/PUTBACKDUNK": RuleSpec("Tendencies/PUTBACKDUNK", "rebounding", "derive_tendency_putbackdunk"),
    "Tendencies/PLAYDISCIPLINE": RuleSpec("Tendencies/PLAYDISCIPLINE", "mental", "derive_tendency_playdiscipline"),
    "Tendencies/TOUCHES": RuleSpec("Tendencies/TOUCHES", "mental", "derive_tendency_touches"),
}

_HOT_ZONE_KEYS = (
    "Tendencies/UNDERBASKET",
    "Tendencies/CLOSELEFT",
    "Tendencies/CLOSEMIDDLE",
    "Tendencies/CLOSERIGHT",
    "Tendencies/MIDRANGECENTER",
    "Tendencies/MIDRANGELEFT",
    "Tendencies/MIDRANGELEFTCENTER",
    "Tendencies/MIDRANGERIGHT",
    "Tendencies/MIDRANGERIGHTCENTER",
    "Tendencies/3CENTER",
    "Tendencies/3LEFT",
    "Tendencies/3LEFTCENTER",
    "Tendencies/3RIGHT",
    "Tendencies/3RIGHTCENTER",
)

_SCHEME_ONLY_FIELDS = {
    "Attributes/PICKANDROLLDEFENSEIQ",
    "Attributes/POSTFADEAWAY",
    "Attributes/CONTESTSHOT",
}


def rule_spec_for(field_key: str) -> RuleSpec:
    return PLAYER_RULE_SCHEME[field_key]


def derive_player_rule_values(evidence: Any, *, league_player_rows: Any = ()) -> PlayerRuleResult:
    values: dict[str, RuleValue] = {}
    for field_key, spec in PLAYER_RULE_SCHEME.items():
        if field_key in _SCHEME_ONLY_FIELDS:
            continue
        function = _RULE_FUNCTIONS[spec.function]
        values[field_key] = _rule_value(function(evidence, league_player_rows=league_player_rows))
    for field_key in _HOT_ZONE_KEYS:
        values[field_key] = _rule_value(_derive_hot_zone(field_key, evidence))
    for field_key in _EXTRA_TENDENCY_KEYS:
        if field_key not in values:
            values[field_key] = _rule_value(_derive_extra_tendency(field_key, evidence))
    for field_key in _DURABILITY_KEYS:
        values[field_key] = _rule_value({"value": 90, "source_rule": "durability_default_90_pending_injury_database", "evidence_keys": ("durability_default_90_pending_injury_database",)})
    return PlayerRuleResult(values=values)


_DURABILITY_KEYS = (
    "Attributes/BACKDURABILITY", "Attributes/HEADDURABILITY", "Attributes/LEFTANKLEDURABILITY", "Attributes/LEFTELBOWDURABILITY",
    "Attributes/LEFTFOOTDURABILITY", "Attributes/LEFTHIPDURABILITY", "Attributes/LEFTKNEEDURABILITY", "Attributes/LEFTSHOULDERDURABILITY",
    "Attributes/MISCDURABILITY", "Attributes/NECKDURABILITY", "Attributes/RIGHTANKLEDURABILITY", "Attributes/RIGHTELBOWDURABILITY",
    "Attributes/RIGHTFOOTDURABILITY", "Attributes/RIGHTHIPDURABILITY", "Attributes/RIGHTKNEEDURABILITY", "Attributes/RIGHTSHOULDERDURABILITY",
)


_EXTRA_TENDENCY_KEYS = (
    "Tendencies/CONTESTEDJUMPER3POINT", "Tendencies/CONTESTEDJUMPERMID", "Tendencies/CONTESTEDJUMPERMIDRANGE",
    "Tendencies/DRIVEPULLUPMIDRANGE", "Tendencies/3POINTOFFSCREENSHOT", "Tendencies/MIDOFFSCREENSHOT",
    "Tendencies/3POINTCENTERSHOT", "Tendencies/3POINTLEFTSHOT", "Tendencies/3POINTCENTERLEFTSHOT", "Tendencies/3POINTRIGHTSHOT", "Tendencies/3POINTCENTERRIGHTSHOT",
    "Tendencies/CLOSELEFTSHOT", "Tendencies/CLOSEMIDDLESHOT", "Tendencies/CLOSERIGHTSHOT", "Tendencies/CENTERMIDSHOT", "Tendencies/LEFTMIDSHOT", "Tendencies/CENTERLEFTMIDSHOT", "Tendencies/MIDRIGHTSHOT", "Tendencies/CENTERMIDRIGHTSHOT",
    "Tendencies/BASKETUNDERSHOT", "Tendencies/SPINJUMPER", "Tendencies/MIDSPOTUPSHOT", "Tendencies/STEPTHROUGH", "Tendencies/STEPBACKJUMPERMIDRANGE", "Tendencies/TRANSITIONPULLUP3POINT", "Tendencies/USEGLASS",
    "Tendencies/FLOATER", "Tendencies/NOSETUPDRIBBLE", "Tendencies/SETUPWITHHESITATION", "Tendencies/SETUPWITHSIZEUP", "Tendencies/STEPBACKJUMPERMID", "Tendencies/TRIPLETHREATIDLE", "Tendencies/TRIPLETHREATJABSTEP", "Tendencies/TRIPLETHREATPUMPFAKE", "Tendencies/THREATTRIPLESHOT",
    "Tendencies/ATTACKSTRONGONDRIVE", "Tendencies/DRIVE", "Tendencies/DRIVEPULLUPMID", "Tendencies/DRIVERIGHT", "Tendencies/DRIVINGBEHINDTHEBACK", "Tendencies/DRIBBLECROSSOVER", "Tendencies/DRIVINGDOUBLECROSSOVER", "Tendencies/DRIVINGDRIBBLEHESITATION", "Tendencies/DRIVINGHALFSPIN", "Tendencies/DRIVINGINANDOUT", "Tendencies/DRIBBLESPIN", "Tendencies/DRIVINGSTEPBACK", "Tendencies/NODRIVINGDRIBBLEMOVE", "Tendencies/OFFSCREENDRIVE", "Tendencies/SPOTUPDRIVE",
    "Tendencies/ALLEYOOPPASS", "Tendencies/DISHTOOPENMAN", "Tendencies/FLASHYPASS",
    "Tendencies/POSTAGGRESSIVEBACKDOWN", "Tendencies/POSTBACKDOWN", "Tendencies/POSTDRIVE", "Tendencies/POSTDROPSTEP", "Tendencies/POSTFACEUP", "Tendencies/HOPPOSTSHOT", "Tendencies/POSTSHIMMYSHOT", "Tendencies/POSTSPIN", "Tendencies/POSTSTEPBACKSHOT", "Tendencies/POSTUPANDUNDER", "Tendencies/FROMPOSTSHOT",
    "Tendencies/ISOVSAVERAGEDEFENDER", "Tendencies/ISOVSELITEDEFENDER", "Tendencies/ISOVSGOODDEFENDER", "Tendencies/ISOVSPOORDEFENDER", "Tendencies/ROLLVSPOP", "Tendencies/TRANSITIONSPOTUP", "Tendencies/TAKECHARGE",
)


def _derive_extra_tendency(field_key: str, evidence: Any) -> dict[str, Any]:
    key = field_key.rsplit("/", 1)[1]
    if "3POINT" in key or key.startswith("3") or key.endswith("3POINT"):
        value = _scaled_tendency(evidence, "per_game", "x3pa_per_game", 12.0)
        evidence_keys = ("per_game.x3pa_per_game",)
    elif "MID" in key or "JUMPER" in key or "SPINJUMPER" in key:
        value = _scaled_tendency(evidence, "shooting", "percent_fga_from_x16_3p_range", 0.35)
        evidence_keys = ("shooting.percent_fga_from_x16_3p_range",)
    elif "CLOSE" in key or "BASKET" in key or "FLOATER" in key or "USEGLASS" in key:
        value = _scaled_tendency(evidence, "shooting", "percent_fga_from_x0_3_range", 0.45)
        evidence_keys = ("shooting.percent_fga_from_x0_3_range",)
    elif "POST" in key or key == "FROMPOSTSHOT":
        value = _scaled_tendency(evidence, "shooting", "percent_fga_from_x3_10_range", 0.45)
        evidence_keys = ("shooting.percent_fga_from_x3_10_range",)
    elif "PASS" in key or key == "DISHTOOPENMAN":
        value = _scaled_tendency(evidence, "per_game", "ast_per_game", 11.0)
        evidence_keys = ("per_game.ast_per_game",)
    elif "DRIVE" in key or "DRIBBLE" in key or "TRIPLE" in key or "SETUP" in key or key.startswith("ISO"):
        value = _scaled_tendency(evidence, "advanced", "usg_percent", 35.0)
        evidence_keys = ("advanced.usg_percent",)
    elif key == "TAKECHARGE":
        value = _scaled_tendency(evidence, "play_by_play", "offensive_foul_drawn", 35.0)
        evidence_keys = ("play_by_play.offensive_foul_drawn",)
    else:
        value = _scaled_tendency(evidence, "per_game", "fga_per_game", 22.0)
        evidence_keys = ("per_game.fga_per_game",)
    return {"value": value, "source_rule": f"tendency_{key.lower()}_direct_2026_v1", "evidence_keys": evidence_keys}


def _scaled_tendency(evidence: Any, source_name: str, column: str, max_value: float) -> int:
    value = _number(getattr(evidence, source_name, {}), column) or 0.0
    score = value / max_value if max_value > 0 else 0.0
    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0
    return int(round(score * 100))


def _derive_hot_zone(field_key: str, evidence: Any) -> dict[str, Any]:
    if "3" in field_key:
        pct = _number(getattr(evidence, "shooting", {}), "fg_percent_from_x3p_range")
        share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x3p_range") or 0.0
        hot_cutoff = 0.38
        cold_cutoff = 0.32
        evidence_keys = ("shooting.fg_percent_from_x3p_range", "shooting.percent_fga_from_x3p_range")
    elif "MIDRANGE" in field_key:
        pct = _number(getattr(evidence, "shooting", {}), "fg_percent_from_x16_3p_range")
        share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x16_3p_range") or 0.0
        hot_cutoff = 0.45
        cold_cutoff = 0.36
        evidence_keys = ("shooting.fg_percent_from_x16_3p_range", "shooting.percent_fga_from_x16_3p_range")
    else:
        pct = _number(getattr(evidence, "shooting", {}), "fg_percent_from_x0_3_range")
        share = _number(getattr(evidence, "shooting", {}), "percent_fga_from_x0_3_range") or 0.0
        hot_cutoff = 0.68
        cold_cutoff = 0.55
        evidence_keys = ("shooting.fg_percent_from_x0_3_range", "shooting.percent_fga_from_x0_3_range")
    if pct is None or share <= 0.01:
        value = "Neutral"
    elif pct >= hot_cutoff:
        value = "Hot"
    elif pct < cold_cutoff:
        value = "Cold"
    else:
        value = "Neutral"
    return {"value": value, "source_rule": "tendency_hot_zone_direct_2026_v1", "evidence_keys": evidence_keys}


__all__ = [
    "PLAYER_RULE_SCHEME",
    "PlayerProfileResult",
    "PlayerRuleResult",
    "ProfileValue",
    "RuleValue",
    "derive_player_profile_values",
    "derive_player_rule_values",
    "rule_spec_for",
    "_split_player_name",
]
