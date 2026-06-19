from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
import unicodedata

import player_rules_athleticism as athleticism
import player_rules_defense as defense
import player_rules_mental as mental
import player_rules_offense as offense
import player_rules_rebounding as rebounding
from positional_identities import classify_positional_identities


@dataclass(frozen=True)
class ProfileValue:
    field: str
    domain: str
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class RuleValue:
    field: str
    domain: str
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerProfileResult:
    values: dict[str, ProfileValue]


@dataclass(frozen=True)
class PlayerRuleResult:
    values: dict[str, RuleValue]


@dataclass(frozen=True)
class PlayerRuleSpec:
    field_key: str
    section: str
    group: str
    normalized_name: str
    module: str
    function: str


_ATTRIBUTE_RULE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ('3POINT', 'Offense', 'offense', 'derive_attribute_field_3point'),
    ('BALLCONTROL', 'Offense', 'offense', 'derive_attribute_ballcontrol'),
    ('CLOSESHOT', 'Offense', 'offense', 'derive_attribute_closeshot'),
    ('DRAWFOUL', 'Offense', 'offense', 'derive_attribute_drawfoul'),
    ('DRIVINGDUNK', 'Offense', 'offense', 'derive_attribute_drivingdunk'),
    ('DRIVINGLAYUP', 'Offense', 'offense', 'derive_attribute_drivinglayup'),
    ('FREETHROW', 'Offense', 'offense', 'derive_attribute_freethrow'),
    ('MIDRANGE', 'Offense', 'offense', 'derive_attribute_midrange'),
    ('OFFENSIVECONSISTENCY', 'Offense', 'offense', 'derive_attribute_offensiveconsistency'),
    ('PASSACCURACY', 'Offense', 'offense', 'derive_attribute_passaccuracy'),
    ('PASSIQ', 'Offense', 'offense', 'derive_attribute_passiq'),
    ('PASSVISION', 'Offense', 'offense', 'derive_attribute_passvision'),
    ('POSTFADE', 'Offense', 'offense', 'derive_attribute_postfade'),
    ('POSTHOOK', 'Offense', 'offense', 'derive_attribute_posthook'),
    ('POSTCONTROL', 'Offense', 'offense', 'derive_attribute_postcontrol'),
    ('IQSHOT', 'Offense', 'offense', 'derive_attribute_iqshot'),
    ('STANDINGDUNK', 'Offense', 'offense', 'derive_attribute_standingdunk'),
    ('BLOCK', 'Defense', 'defense', 'derive_attribute_block'),
    ('DEFENSECONSISTENCY', 'Defense', 'defense', 'derive_attribute_defenseconsistency'),
    ('HELPDEFENSE', 'Defense', 'defense', 'derive_attribute_helpdefense'),
    ('INTERIORDEFENSE', 'Defense', 'defense', 'derive_attribute_interiordefense'),
    ('PASSPERCEPTION', 'Defense', 'defense', 'derive_attribute_passperception'),
    ('PERIMETERDEFENSE', 'Defense', 'defense', 'derive_attribute_perimeterdefense'),
    ('STEAL', 'Defense', 'defense', 'derive_attribute_steal'),
    ('ACCELERATION', 'Athleticism', 'athleticism', 'derive_attribute_acceleration'),
    ('AGILITY', 'Athleticism', 'athleticism', 'derive_attribute_agility'),
    ('SPEED', 'Athleticism', 'athleticism', 'derive_attribute_speed'),
    ('SPEEDWITHBALL', 'Athleticism', 'athleticism', 'derive_attribute_speedwithball'),
    ('STAMINA', 'Athleticism', 'athleticism', 'derive_attribute_stamina'),
    ('STRENGTH', 'Athleticism', 'athleticism', 'derive_attribute_strength'),
    ('VERTICAL', 'Athleticism', 'athleticism', 'derive_attribute_vertical'),
    ('BACKDURABILITY', 'Durability', 'athleticism', 'derive_attribute_backdurability'),
    ('HEADDURABILITY', 'Durability', 'athleticism', 'derive_attribute_headdurability'),
    ('LEFTANKLEDURABILITY', 'Durability', 'athleticism', 'derive_attribute_leftankledurability'),
    ('LEFTELBOWDURABILITY', 'Durability', 'athleticism', 'derive_attribute_leftelbowdurability'),
    ('LEFTFOOTDURABILITY', 'Durability', 'athleticism', 'derive_attribute_leftfootdurability'),
    ('LEFTHANDDURABILITY', 'Durability', 'athleticism', 'derive_attribute_lefthanddurability'),
    ('LEFTHIPDURABILITY', 'Durability', 'athleticism', 'derive_attribute_lefthipdurability'),
    ('LEFTKNEEDURABILITY', 'Durability', 'athleticism', 'derive_attribute_leftkneedurability'),
    ('LEFTSHOULDERDURABILITY', 'Durability', 'athleticism', 'derive_attribute_leftshoulderdurability'),
    ('MISCDURABILITY', 'Durability', 'athleticism', 'derive_attribute_miscdurability'),
    ('NECKDURABILITY', 'Durability', 'athleticism', 'derive_attribute_neckdurability'),
    ('RIGHTANKLEDURABILITY', 'Durability', 'athleticism', 'derive_attribute_rightankledurability'),
    ('RIGHTELBOWDURABILITY', 'Durability', 'athleticism', 'derive_attribute_rightelbowdurability'),
    ('RIGHTFOOTDURABILITY', 'Durability', 'athleticism', 'derive_attribute_rightfootdurability'),
    ('RIGHTHANDDURABILITY', 'Durability', 'athleticism', 'derive_attribute_righthanddurability'),
    ('RIGHTHIPDURABILITY', 'Durability', 'athleticism', 'derive_attribute_righthipdurability'),
    ('RIGHTKNEEDURABILITY', 'Durability', 'athleticism', 'derive_attribute_rightkneedurability'),
    ('RIGHTSHOULDERDURABILITY', 'Durability', 'athleticism', 'derive_attribute_rightshoulderdurability'),
    ('HANDS', 'Mental', 'mental', 'derive_attribute_hands'),
    ('HUSTLE', 'Mental', 'mental', 'derive_attribute_hustle'),
    ('INTANGIBLES', 'Mental', 'mental', 'derive_attribute_intangibles'),
    ('CACHCEDOVR', 'Misc', 'mental', 'derive_attribute_cachcedovr'),
    ('LATERALQUICKNESS', 'Misc', 'defense', 'derive_attribute_lateralquickness'),
    ('MAXOVR', 'Misc', 'mental', 'derive_attribute_maxovr'),
    ('MINOVR', 'Misc', 'mental', 'derive_attribute_minovr'),
    ('PICKANDROLLDEFENSEIQ', 'Misc', 'defense', 'derive_attribute_pickandrolldefenseiq'),
    ('POSTFADEAWAY', 'Misc', 'mental', 'derive_attribute_postfadeaway'),
    ('POTENTIAL', 'Misc', 'mental', 'derive_attribute_potential'),
    ('CONTESTSHOT', 'Misc', 'defense', 'derive_attribute_contestshot'),
    ('DEFENSEREBOUND', 'Rebounding', 'rebounding', 'derive_attribute_defenserebound'),
    ('OFFENSIVEREBOUND', 'Rebounding', 'rebounding', 'derive_attribute_offensiverebound'),
)

_TENDENCY_RULE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ('CONTESTEDJUMPER3POINT', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumper3point'),
    ('CONTESTEDJUMPERMID', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermid'),
    ('CONTESTEDJUMPERMIDRANGE', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermidrange'),
    ('DRIVEPULLUP3POINT', 'Jump Shooting', 'offense', 'derive_tendency_drivepullup3point'),
    ('DRIVEPULLUPMIDRANGE', 'Jump Shooting', 'offense', 'derive_tendency_drivepullupmidrange'),
    ('3POINTOFFSCREENSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointoffscreenshot'),
    ('MIDOFFSCREENSHOT', 'Jump Shooting', 'offense', 'derive_tendency_midoffscreenshot'),
    ('3POINTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointshot'),
    ('3POINTCENTERSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcentershot'),
    ('3POINTLEFTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointleftshot'),
    ('3POINTCENTERLEFTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcenterleftshot'),
    ('3POINTRIGHTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointrightshot'),
    ('3POINTCENTERRIGHTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcenterrightshot'),
    ('CLOSESHOT', 'Jump Shooting', 'offense', 'derive_tendency_closeshot'),
    ('CLOSELEFTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_closeleftshot'),
    ('CLOSEMIDDLESHOT', 'Jump Shooting', 'offense', 'derive_tendency_closemiddleshot'),
    ('CLOSERIGHTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_closerightshot'),
    ('MIDSHOT', 'Jump Shooting', 'offense', 'derive_tendency_midshot'),
    ('CENTERMIDSHOT', 'Jump Shooting', 'offense', 'derive_tendency_centermidshot'),
    ('LEFTMIDSHOT', 'Jump Shooting', 'offense', 'derive_tendency_leftmidshot'),
    ('CENTERLEFTMIDSHOT', 'Jump Shooting', 'offense', 'derive_tendency_centerleftmidshot'),
    ('MIDRIGHTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_midrightshot'),
    ('CENTERMIDRIGHTSHOT', 'Jump Shooting', 'offense', 'derive_tendency_centermidrightshot'),
    ('BASKETUNDERSHOT', 'Jump Shooting', 'offense', 'derive_tendency_basketundershot'),
    ('SPINJUMPER', 'Jump Shooting', 'offense', 'derive_tendency_spinjumper'),
    ('3POINTSPOTUPSHOT', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointspotupshot'),
    ('MIDSPOTUPSHOT', 'Jump Shooting', 'offense', 'derive_tendency_midspotupshot'),
    ('STEPTHROUGH', 'Jump Shooting', 'offense', 'derive_tendency_stepthrough'),
    ('STEPBACKJUMPER3POINT', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumper3point'),
    ('STEPBACKJUMPERMIDRANGE', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumpermidrange'),
    ('TRANSITIONPULLUP3POINT', 'Jump Shooting', 'offense', 'derive_tendency_transitionpullup3point'),
    ('USEGLASS', 'Jump Shooting', 'offense', 'derive_tendency_useglass'),
    ('ALLEYOOP', 'Layups And Dunks', 'offense', 'derive_tendency_alleyoop'),
    ('CRASH', 'Layups And Dunks', 'rebounding', 'derive_tendency_crash'),
    ('DRIVINGDUNK', 'Layups And Dunks', 'offense', 'derive_tendency_drivingdunk'),
    ('DRIVINGLAYUP', 'Layups And Dunks', 'offense', 'derive_tendency_drivinglayup'),
    ('EUROSTEPLAYUP', 'Layups And Dunks', 'offense', 'derive_tendency_eurosteplayup'),
    ('FLASHYDUNK', 'Layups And Dunks', 'offense', 'derive_tendency_flashydunk'),
    ('FLOATER', 'Layups And Dunks', 'offense', 'derive_tendency_floater'),
    ('HOPSTEPLAYUP', 'Layups And Dunks', 'offense', 'derive_tendency_hopsteplayup'),
    ('PUTBACK', 'Layups And Dunks', 'rebounding', 'derive_tendency_putback'),
    ('PUTBACKDUNK', 'Layups And Dunks', 'rebounding', 'derive_tendency_putbackdunk'),
    ('SPINLAYUP', 'Layups And Dunks', 'offense', 'derive_tendency_spinlayup'),
    ('STANDINGDUNK', 'Layups And Dunks', 'offense', 'derive_tendency_standingdunk'),
    ('NOSETUPDRIBBLE', 'Drive Setup', 'offense', 'derive_tendency_nosetupdribble'),
    ('SETUPWITHHESITATION', 'Drive Setup', 'offense', 'derive_tendency_setupwithhesitation'),
    ('SETUPWITHSIZEUP', 'Drive Setup', 'offense', 'derive_tendency_setupwithsizeup'),
    ('STEPBACKJUMPERMID', 'Drive Setup', 'offense', 'derive_tendency_stepbackjumpermid'),
    ('TRIPLETHREATIDLE', 'Drive Setup', 'offense', 'derive_tendency_triplethreatidle'),
    ('TRIPLETHREATJABSTEP', 'Drive Setup', 'offense', 'derive_tendency_triplethreatjabstep'),
    ('TRIPLETHREATPUMPFAKE', 'Drive Setup', 'offense', 'derive_tendency_triplethreatpumpfake'),
    ('THREATTRIPLESHOT', 'Drive Setup', 'offense', 'derive_tendency_threattripleshot'),
    ('ATTACKSTRONGONDRIVE', 'Driving', 'offense', 'derive_tendency_attackstrongondrive'),
    ('DRIVE', 'Driving', 'offense', 'derive_tendency_drive'),
    ('DRIVEPULLUPMID', 'Driving', 'offense', 'derive_tendency_drivepullupmid'),
    ('DRIVERIGHT', 'Driving', 'offense', 'derive_tendency_driveright'),
    ('DRIVINGBEHINDTHEBACK', 'Driving', 'offense', 'derive_tendency_drivingbehindtheback'),
    ('DRIBBLECROSSOVER', 'Driving', 'offense', 'derive_tendency_dribblecrossover'),
    ('DRIVINGDOUBLECROSSOVER', 'Driving', 'offense', 'derive_tendency_drivingdoublecrossover'),
    ('DRIVINGDRIBBLEHESITATION', 'Driving', 'offense', 'derive_tendency_drivingdribblehesitation'),
    ('DRIVINGHALFSPIN', 'Driving', 'offense', 'derive_tendency_drivinghalfspin'),
    ('DRIVINGINANDOUT', 'Driving', 'offense', 'derive_tendency_drivinginandout'),
    ('DRIBBLESPIN', 'Driving', 'offense', 'derive_tendency_dribblespin'),
    ('DRIVINGSTEPBACK', 'Driving', 'offense', 'derive_tendency_drivingstepback'),
    ('NODRIVINGDRIBBLEMOVE', 'Driving', 'offense', 'derive_tendency_nodrivingdribblemove'),
    ('OFFSCREENDRIVE', 'Driving', 'offense', 'derive_tendency_offscreendrive'),
    ('SPOTUPDRIVE', 'Driving', 'offense', 'derive_tendency_spotupdrive'),
    ('ALLEYOOPPASS', 'Passing', 'offense', 'derive_tendency_alleyooppass'),
    ('DISHTOOPENMAN', 'Passing', 'offense', 'derive_tendency_dishtoopenman'),
    ('FLASHYPASS', 'Passing', 'offense', 'derive_tendency_flashypass'),
    ('POSTAGGRESSIVEBACKDOWN', 'Post Game', 'offense', 'derive_tendency_postaggressivebackdown'),
    ('POSTBACKDOWN', 'Post Game', 'offense', 'derive_tendency_postbackdown'),
    ('POSTDRIVE', 'Post Game', 'offense', 'derive_tendency_postdrive'),
    ('POSTDROPSTEP', 'Post Game', 'offense', 'derive_tendency_postdropstep'),
    ('POSTFACEUP', 'Post Game', 'offense', 'derive_tendency_postfaceup'),
    ('POSTFADELEFT', 'Post Game', 'offense', 'derive_tendency_postfadeleft'),
    ('POSTFADERIGHT', 'Post Game', 'offense', 'derive_tendency_postfaderight'),
    ('POSTHOOKLEFT', 'Post Game', 'offense', 'derive_tendency_posthookleft'),
    ('POSTHOOKRIGHT', 'Post Game', 'offense', 'derive_tendency_posthookright'),
    ('HOPPOSTSHOT', 'Post Game', 'offense', 'derive_tendency_hoppostshot'),
    ('POSTHOPSTEP', 'Post Game', 'offense', 'derive_tendency_posthopstep'),
    ('POSTSHIMMYSHOT', 'Post Game', 'offense', 'derive_tendency_postshimmyshot'),
    ('POSTSPIN', 'Post Game', 'offense', 'derive_tendency_postspin'),
    ('POSTSTEPBACKSHOT', 'Post Game', 'offense', 'derive_tendency_poststepbackshot'),
    ('POSTUP', 'Post Game', 'offense', 'derive_tendency_postup'),
    ('POSTUPANDUNDER', 'Post Game', 'offense', 'derive_tendency_postupandunder'),
    ('FROMPOSTSHOT', 'Post Game', 'offense', 'derive_tendency_frompostshot'),
    ('ISOVSAVERAGEDEFENDER', 'Freelance', 'mental', 'derive_tendency_isovsaveragedefender'),
    ('ISOVSELITEDEFENDER', 'Freelance', 'mental', 'derive_tendency_isovselitedefender'),
    ('ISOVSGOODDEFENDER', 'Freelance', 'mental', 'derive_tendency_isovsgooddefender'),
    ('ISOVSPOORDEFENDER', 'Freelance', 'mental', 'derive_tendency_isovspoordefender'),
    ('PLAYDISCIPLINE', 'Freelance', 'mental', 'derive_tendency_playdiscipline'),
    ('ROLLVSPOP', 'Freelance', 'mental', 'derive_tendency_rollvspop'),
    ('TOUCHES', 'Freelance', 'mental', 'derive_tendency_touches'),
    ('TRANSITIONSPOTUP', 'Freelance', 'mental', 'derive_tendency_transitionspotup'),
    ('BLOCKSHOT', 'Defense', 'defense', 'derive_tendency_blockshot'),
    ('CONTESTSHOT', 'Defense', 'defense', 'derive_tendency_contestshot'),
    ('FOUL', 'Defense', 'defense', 'derive_tendency_foul'),
    ('HARDFOUL', 'Defense', 'defense', 'derive_tendency_hardfoul'),
    ('ONBALLSTEAL', 'Defense', 'defense', 'derive_tendency_onballsteal'),
    ('PASSINTERCEPTION', 'Defense', 'defense', 'derive_tendency_passinterception'),
    ('TAKECHARGE', 'Defense', 'defense', 'derive_tendency_takecharge'),
    ('CENTER3', 'Hot Zones', 'offense', 'derive_tendency_center3'),
    ('CLOSELEFT', 'Hot Zones', 'offense', 'derive_tendency_closeleft'),
    ('CLOSEMIDDLE', 'Hot Zones', 'offense', 'derive_tendency_closemiddle'),
    ('CLOSERIGHT', 'Hot Zones', 'offense', 'derive_tendency_closeright'),
    ('LEFT3', 'Hot Zones', 'offense', 'derive_tendency_left3'),
    ('MIDRANGECENTER', 'Hot Zones', 'offense', 'derive_tendency_midrangecenter'),
    ('MIDRANGELEFT', 'Hot Zones', 'offense', 'derive_tendency_midrangeleft'),
    ('MIDRANGELEFTCENTER', 'Hot Zones', 'offense', 'derive_tendency_midrangeleftcenter'),
    ('MIDRANGERIGHT', 'Hot Zones', 'offense', 'derive_tendency_midrangeright'),
    ('MIDRANGERIGHTCENTER', 'Hot Zones', 'offense', 'derive_tendency_midrangerightcenter'),
    ('RIGHT3', 'Hot Zones', 'offense', 'derive_tendency_right3'),
    ('3CENTER', 'Hot Zones', 'offense', 'derive_tendency_field_3center'),
    ('3LEFT', 'Hot Zones', 'offense', 'derive_tendency_field_3left'),
    ('3LEFTCENTER', 'Hot Zones', 'offense', 'derive_tendency_field_3leftcenter'),
    ('3RIGHT', 'Hot Zones', 'offense', 'derive_tendency_field_3right'),
    ('3RIGHTCENTER', 'Hot Zones', 'offense', 'derive_tendency_field_3rightcenter'),
    ('UNDERBASKET', 'Hot Zones', 'offense', 'derive_tendency_underbasket'),
    ('SHOT', 'Tendencies', 'offense', 'derive_tendency_shot'),
)

_RULE_MODULES: dict[str, Any] = {
    "offense": offense,
    "defense": defense,
    "rebounding": rebounding,
    "athleticism": athleticism,
    "mental": mental,
}


def _make_specs(section: str, rows: tuple[tuple[str, str, str, str], ...]) -> dict[str, PlayerRuleSpec]:
    return {
        f"{section}/{name}": PlayerRuleSpec(
            field_key=f"{section}/{name}",
            section=section,
            group=group,
            normalized_name=name,
            module=module,
            function=function,
        )
        for name, group, module, function in rows
    }


ATTRIBUTE_RULE_SCHEME: dict[str, PlayerRuleSpec] = _make_specs("Attributes", _ATTRIBUTE_RULE_ROWS)
TENDENCY_RULE_SCHEME: dict[str, PlayerRuleSpec] = _make_specs("Tendencies", _TENDENCY_RULE_ROWS)
PLAYER_RULE_SCHEME: dict[str, PlayerRuleSpec] = {**ATTRIBUTE_RULE_SCHEME, **TENDENCY_RULE_SCHEME}


def derive_player_profile_values(evidence: Any) -> PlayerProfileResult:
    values: dict[str, ProfileValue] = {}
    first_name, last_name = _split_player_name(_ascii_name_text(evidence.identity.get("player")))
    height_in = _int_number(evidence.identity, "ht_in_in")
    weight_lb = _int_number(evidence.identity, "wt")
    birth = _birth_date(evidence.identity.get("birth_date"))
    position, secondary_position = _position_values(evidence)
    play_types = _play_type_values(evidence)

    _add_profile(values, "FIRSTNAME", first_name, "profile_name_v1", ("identity.player",))
    _add_profile(values, "LASTNAME", last_name, "profile_name_v1", ("identity.player",))
    _add_profile(values, "HEIGHT", height_in, "profile_height_v1", ("identity.ht_in_in",))
    _add_profile(values, "HEIGHTCM", _round_half_up(height_in * 2.54), "profile_height_metric_v1", ("identity.ht_in_in",))
    _add_profile(values, "WINGSPANCM", _round_half_up((height_in - 2) * 2.54), "profile_wingspan_metric_height_minus_two_v1", ("identity.ht_in_in",))
    _add_profile(values, "WEIGHT", weight_lb, "profile_weight_v1", ("identity.wt",))
    _add_profile(values, "WEIGHTKG", round(weight_lb * 0.45359237), "profile_weight_metric_v1", ("identity.wt",))
    _add_profile(values, "POSITION", position, "profile_position_v1", ("season_info.pos", "identity.pos"))
    _add_profile(values, "SECONDARYPOSITION", secondary_position, "profile_secondary_position_v1", ("season_info.pos", "identity.pos"))
    _add_profile(values, "BIRTHDAY", birth.day, "profile_birth_day_v1", ("identity.birth_date",))
    _add_profile(values, "BIRTHMONTH", birth.month, "profile_birth_month_v1", ("identity.birth_date",))
    _add_profile(values, "BIRTHYEAR", _birth_year_age_slot(evidence.season, birth), "profile_birth_year_current_age_value_v1", ("identity.birth_date", "season_info.season"))
    for index, play_type in enumerate(play_types, start=1):
        _add_profile(values, f"PLAYTYPE{index}", play_type, "profile_player_play_types_v1", ("positional_identities.role_key",))
    _add_profile(values, "COLLEGEFROM", _clean_text(evidence.identity.get("colleges")), "profile_college_from_v1", ("identity.colleges",))
    years_pro = _int_number(evidence.season_info, "experience")
    if years_pro == 0:
        start_year = _int_number(evidence.identity, "from")
        years_pro = max(0, int(evidence.season) - start_year) if start_year else 0
    _add_profile(values, "YEARSPRO", years_pro, "profile_years_pro_v1", ("season_info.experience", "identity.from"))
    return PlayerProfileResult(values=values)


def derive_player_rule_values(evidence: Any, *, league_player_rows: Any = ()) -> PlayerRuleResult:
    values: dict[str, RuleValue] = {}
    for field_key, spec in PLAYER_RULE_SCHEME.items():
        module = _RULE_MODULES[spec.module]
        rule = getattr(module, spec.function)
        resolved = _call_rule(rule, evidence, league_player_rows=league_player_rows)
        values[field_key] = _coerce_rule_value(spec, resolved)
    return PlayerRuleResult(values=values)


def rule_spec_for(field_key: str) -> PlayerRuleSpec:
    return PLAYER_RULE_SCHEME[field_key]


def _call_rule(rule: Callable[..., Any], evidence: Any, *, league_player_rows: Any) -> Any:
    try:
        return rule(evidence, league_player_rows=league_player_rows)
    except TypeError:
        return rule(evidence)


def _add_profile(values: dict[str, ProfileValue], field: str, value: int | str, source_rule: str, evidence_keys: tuple[str, ...]) -> None:
    values[f"Vitals/{field}"] = ProfileValue(field=field, domain="Vitals", value=value, source_rule=source_rule, evidence_keys=evidence_keys)


def _split_player_name(name: str) -> tuple[str, str]:
    parts = str(name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _ascii_name_text(value: object) -> str:
    text = str(value or "")
    fixes = {"Ä‡": "c", "Ä": "c", "Ä": "c", "Ä": "C", "Å«": "u", "ё": "e", "Ё": "E"}
    for bad, good in fixes.items():
        text = text.replace(bad, good)
    try:
        text = text.encode("cp1252").decode("utf-8")
    except Exception:
        pass
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").strip()


def _clean_text(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"NA", "N/A", "NONE", "NULL"} else text


def _int_number(row: dict[str, Any], key: str) -> int:
    try:
        return round(float(row.get(key) or 0))
    except Exception:
        return 0


def _birth_date(raw: object) -> date:
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()
    try:
        return date(1899, 12, 30) + timedelta(days=int(float(text)))
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return date(1900, 1, 1)


def _birth_year_age_slot(season: int, born: date) -> int:
    anchor = date(int(season) - 1, 10, 1)
    age = anchor.year - born.year - ((anchor.month, anchor.day) < (born.month, born.day))
    return 1900 + max(0, age)


def _position_values(evidence: Any) -> tuple[str, str]:
    raw = _clean_text(evidence.season_info.get("pos")) or _clean_text(evidence.identity.get("pos"))
    parts = [part.strip().upper() for part in raw.replace("–", "-").replace("—", "-").replace("/", "-").split("-") if part.strip()]
    if not parts:
        return "PG", "None"
    return parts[0], parts[1] if len(parts) > 1 else "None"


def _play_type_values(evidence: Any) -> tuple[str, str, str, str]:
    role_keys = tuple(match.role_key for match in classify_positional_identities(evidence))
    position, _secondary = _position_values(evidence)
    joined = " ".join(role_keys).lower()
    plays: list[str] = []

    def add(*items: str) -> None:
        for item in items:
            if item not in plays:
                plays.append(item)

    if "pnr" in joined or position == "PG":
        add("P&R Ball Handler")
    if any(token in joined for token in ("pull-up three", "above-the-break", "movement shooter", "stretch", "pick-and-pop")):
        add("3 PT")
    if "point forward" in joined:
        add("P&R Wing", "Handoff Passer")
    if "point center" in joined or "high-post" in joined:
        add("Handoff Passer", "Post Up High")
    if "vertical spacer" in joined or "rebounding-first" in joined:
        add("P&R Roll Man", "Cutter")
    if position in {"PF", "C"}:
        add("Post Up Low")
    if position in {"SG", "SF"} and "3 PT" in plays:
        add("Handoff Receiver")
    if position == "PG" and "3 PT" in plays:
        add("Handoff Receiver", "Isolation Point")
    if not plays:
        add({"PG": "P&R Ball Handler", "SG": "3 PT", "SF": "Cutter", "PF": "Post Up High", "C": "Post Up Low"}.get(position, "Cutter"))
    padded = plays + ["None", "None", "None", "None"]
    return padded[0], padded[1], padded[2], padded[3]


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _coerce_rule_value(spec: PlayerRuleSpec, resolved: Any) -> RuleValue:
    if isinstance(resolved, RuleValue):
        return resolved
    source_rule = f"player_rules_{spec.module}.{spec.function}"
    evidence_keys: tuple[str, ...] = ()
    value = resolved
    if isinstance(resolved, dict):
        value = resolved.get("value")
        source_rule = str(resolved.get("source_rule") or source_rule)
        evidence_keys = tuple(str(key) for key in resolved.get("evidence_keys", ()))
    elif isinstance(resolved, tuple) and len(resolved) == 2:
        value, raw_keys = resolved
        evidence_keys = tuple(str(key) for key in raw_keys)
    return RuleValue(
        field=spec.normalized_name,
        domain=spec.section,
        value=value,
        source_rule=source_rule,
        evidence_keys=evidence_keys,
    )


__all__ = [
    "ATTRIBUTE_RULE_SCHEME",
    "TENDENCY_RULE_SCHEME",
    "PLAYER_RULE_SCHEME",
    "PlayerProfileResult",
    "PlayerRuleResult",
    "PlayerRuleSpec",
    "ProfileValue",
    "RuleValue",
    "derive_player_profile_values",
    "derive_player_rule_values",
    "rule_spec_for",
]
