from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Callable

import player_rules_athleticism as athleticism
import player_rules_defense as defense
import player_rules_mental as mental
import player_rules_offense as offense
import player_rules_rebounding as rebounding
from player_era_role import adjust_values as _apply_era_role_playstyle
from player_evidence import PlayerEvidence


POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")


@dataclass(frozen=True)
class PositionSelection:
    primary: str
    secondary: str | None
    all_positions: tuple[str, ...]
    position_weights: tuple[tuple[str, float], ...] = ()


def _parse_listed_positions(value: object) -> tuple[str, ...]:
    text = str(value or "").upper()
    compact = re.sub(r"[^A-Z]+", "", text)
    position_map = {
        "G": ("PG", "SG"),
        "GF": ("SG", "SF"),
        "FG": ("SF", "SG"),
        "F": ("SF", "PF"),
        "FC": ("PF", "C"),
        "CF": ("C", "PF"),
    }
    mapped = position_map.get(compact)
    if mapped:
        return mapped
    found = re.findall(r"\b(?:PG|SG|SF|PF|C)\b", text)
    if found:
        return tuple(dict.fromkeys(found))
    return ()


def select_positions_from_evidence(play_by_play: dict[str, Any], fallback_pos: object = None) -> PositionSelection:
    percent_rows: list[tuple[str, float]] = []
    for pos, col in (
        ("PG", "pg_percent"),
        ("SG", "sg_percent"),
        ("SF", "sf_percent"),
        ("PF", "pf_percent"),
        ("C", "c_percent"),
    ):
        value = _float(play_by_play.get(col))
        if value is not None and value > 0:
            percent_rows.append((pos, value))
    if percent_rows:
        ordered_rows = tuple(sorted(percent_rows, key=lambda item: (-item[1], POSITIONS.index(item[0]))))
        total = sum(value for _pos, value in ordered_rows)
        weights = tuple((pos, value / total) for pos, value in ordered_rows) if total > 0.0 else ()
        ordered = tuple(pos for pos, _ in ordered_rows)
        return PositionSelection(
            primary=ordered[0],
            secondary=ordered[1] if len(ordered) > 1 else None,
            all_positions=ordered,
            position_weights=weights,
        )

    parsed = _parse_listed_positions(fallback_pos)
    return PositionSelection(
        primary=parsed[0] if parsed else "",
        secondary=parsed[1] if len(parsed) > 1 else None,
        all_positions=parsed,
    )


@dataclass(frozen=True)
class ProfileValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class RuleValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerProfileResult:
    values: dict[str, ProfileValue]


@dataclass(frozen=True)
class PlayerRuleResult:
    values: dict[str, RuleValue]
    unresolved_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerRuleSpec:
    field_key: str
    module: str
    function: str


# field_key -> (rule module, derivation function). This is the only thing the
# generator declares about attributes/tendencies: which function computes which
# field. Section, group, ordinal, and *which fields exist* all come from the
# editor's offset layout at generation time -- see derive_formula_rule_values.
_RULE_BINDINGS: dict[str, tuple[str, str]] = {

    'Attributes/BALLCONTROL': ('offense', 'derive_attribute_ballcontrol'),
    'Attributes/DRAWFOUL': ('offense', 'derive_attribute_drawfoul'),
    'Attributes/OFFENSIVECONSISTENCY': ('offense', 'derive_attribute_offensiveconsistency'),
    'Attributes/PASSACCURACY': ('offense', 'derive_attribute_passaccuracy'),
    'Attributes/PASSIQ': ('offense', 'derive_attribute_passiq'),
    'Attributes/PASSVISION': ('offense', 'derive_attribute_passvision'),
    'Attributes/IQSHOT': ('offense', 'derive_attribute_iqshot'),
    'Attributes/3POINT': ('offense', 'derive_attribute_3point'),
    'Attributes/CLOSESHOT': ('offense', 'derive_attribute_closeshot'),
    'Attributes/DRIVINGDUNK': ('offense', 'derive_attribute_drivingdunk'),
    'Attributes/DRIVINGLAYUP': ('offense', 'derive_attribute_drivinglayup'),
    'Attributes/MIDRANGE': ('offense', 'derive_attribute_midrange'),
    'Attributes/POSTCONTROL': ('offense', 'derive_attribute_postcontrol'),
    'Attributes/POSTFADE': ('offense', 'derive_attribute_postfade'),
    'Attributes/POSTHOOK': ('offense', 'derive_attribute_posthook'),
    'Attributes/STANDINGDUNK': ('offense', 'derive_attribute_standingdunk'),
    'Attributes/BLOCK': ('defense', 'derive_attribute_block'),
    'Attributes/DEFENSECONSISTENCY': ('defense', 'derive_attribute_defenseconsistency'),
    'Attributes/HELPDEFENSE': ('defense', 'derive_attribute_helpdefense'),
    'Attributes/INTERIORDEFENSE': ('defense', 'derive_attribute_interiordefense'),
    'Attributes/PASSPERCEPTION': ('defense', 'derive_attribute_passperception'),
    'Attributes/PERIMETERDEFENSE': ('defense', 'derive_attribute_perimeterdefense'),
    'Attributes/STEAL': ('defense', 'derive_attribute_steal'),
    'Attributes/ACCELERATION': ('athleticism', 'derive_attribute_acceleration'),
    'Attributes/AGILITY': ('athleticism', 'derive_attribute_agility'),
    'Attributes/SPEED': ('athleticism', 'derive_attribute_speed'),
    'Attributes/SPEEDWITHBALL': ('athleticism', 'derive_attribute_speedwithball'),
    'Attributes/STAMINA': ('athleticism', 'derive_attribute_stamina'),
    'Attributes/STRENGTH': ('athleticism', 'derive_attribute_strength'),
    'Attributes/VERTICAL': ('athleticism', 'derive_attribute_vertical'),
    'Attributes/BACKDURABILITY': ('athleticism', 'derive_attribute_backdurability'),
    'Attributes/HEADDURABILITY': ('athleticism', 'derive_attribute_headdurability'),
    'Attributes/LEFTANKLEDURABILITY': ('athleticism', 'derive_attribute_leftankledurability'),
    'Attributes/LEFTELBOWDURABILITY': ('athleticism', 'derive_attribute_leftelbowdurability'),
    'Attributes/LEFTFOOTDURABILITY': ('athleticism', 'derive_attribute_leftfootdurability'),
    'Attributes/LEFTHANDDURABILITY': ('athleticism', 'derive_attribute_lefthanddurability'),
    'Attributes/LEFTHIPDURABILITY': ('athleticism', 'derive_attribute_lefthipdurability'),
    'Attributes/LEFTKNEEDURABILITY': ('athleticism', 'derive_attribute_leftkneedurability'),
    'Attributes/LEFTSHOULDERDURABILITY': ('athleticism', 'derive_attribute_leftshoulderdurability'),
    'Attributes/MISCDURABILITY': ('athleticism', 'derive_attribute_miscdurability'),
    'Attributes/NECKDURABILITY': ('athleticism', 'derive_attribute_neckdurability'),
    'Attributes/RIGHTANKLEDURABILITY': ('athleticism', 'derive_attribute_rightankledurability'),
    'Attributes/RIGHTELBOWDURABILITY': ('athleticism', 'derive_attribute_rightelbowdurability'),
    'Attributes/RIGHTFOOTDURABILITY': ('athleticism', 'derive_attribute_rightfootdurability'),
    'Attributes/RIGHTHANDDURABILITY': ('athleticism', 'derive_attribute_righthanddurability'),
    'Attributes/RIGHTHIPDURABILITY': ('athleticism', 'derive_attribute_righthipdurability'),
    'Attributes/RIGHTKNEEDURABILITY': ('athleticism', 'derive_attribute_rightkneedurability'),
    'Attributes/RIGHTSHOULDERDURABILITY': ('athleticism', 'derive_attribute_rightshoulderdurability'),
    'Attributes/HANDS': ('mental', 'derive_attribute_hands'),
    'Attributes/HUSTLE': ('mental', 'derive_attribute_hustle'),
    'Attributes/INTANGIBLES': ('mental', 'derive_attribute_intangibles'),
    'Attributes/LATERALQUICKNESS': ('defense', 'derive_attribute_lateralquickness'),
    'Attributes/PICKANDROLLDEFENSEIQ': ('defense', 'derive_attribute_pickandrolldefenseiq'),
    'Attributes/POTENTIAL': ('mental', 'derive_attribute_potential'),
    'Attributes/CONTESTSHOT': ('defense', 'derive_attribute_contestshot'),
    'Attributes/DEFENSEREBOUND': ('rebounding', 'derive_attribute_defensiverebound'),
    'Attributes/OFFENSIVEREBOUND': ('rebounding', 'derive_attribute_offensiverebound'),







    'Tendencies/CRASH': ('offense', 'derive_tendency_crash'),
    'Tendencies/NOSETUPDRIBBLE': ('offense', 'derive_tendency_setupdribble'),
    'Tendencies/SETUPWITHHESITATION': ('offense', 'derive_tendency_setupwithhesitation'),
    'Tendencies/SETUPWITHSIZEUP': ('offense', 'derive_tendency_setupwithsizeup'),
    'Tendencies/TRIPLETHREATIDLE': ('offense', 'derive_tendency_triplethreatidle'),
    'Tendencies/TRIPLETHREATJABSTEP': ('offense', 'derive_tendency_triplethreatjab'),
    'Tendencies/TRIPLETHREATPUMPFAKE': ('offense', 'derive_tendency_triplethreatpumpfake'),
    'Tendencies/THREATTRIPLESHOT': ('offense', 'derive_tendency_triplethreatshot'),
    'Tendencies/ATTACKSTRONGONDRIVE': ('offense', 'derive_tendency_attackstrongondrive'),
    'Tendencies/DRIVE': ('offense', 'derive_tendency_drive'),
    'Tendencies/DRIVERIGHT': ('offense', 'derive_tendency_driveright'),
    'Tendencies/DRIVINGBEHINDTHEBACK': ('offense', 'derive_tendency_drivingbehindtheback'),
    'Tendencies/DRIBBLECROSSOVER': ('offense', 'derive_tendency_drivingcrossover'),
    'Tendencies/DRIVINGDOUBLECROSSOVER': ('offense', 'derive_tendency_drivingdoublecrossover'),
    'Tendencies/DRIVINGDRIBBLEHESITATION': ('offense', 'derive_tendency_drivingdribblehesitation'),
    'Tendencies/DRIVINGHALFSPIN': ('offense', 'derive_tendency_drivinghalfspin'),
    'Tendencies/DRIVINGINANDOUT': ('offense', 'derive_tendency_drivinginandout'),
    'Tendencies/DRIBBLESPIN': ('offense', 'derive_tendency_drivingspin'),
    'Tendencies/DRIVINGSTEPBACK': ('offense', 'derive_tendency_drivingstepback'),
    'Tendencies/NODRIVINGDRIBBLEMOVE': ('offense', 'derive_tendency_nodrivingdribblemove'),
    'Tendencies/OFFSCREENDRIVE': ('offense', 'derive_tendency_offscreendrive'),
    'Tendencies/SPOTUPDRIVE': ('offense', 'derive_tendency_spotupdrive'),
    'Tendencies/ALLEYOOPPASS': ('offense', 'derive_tendency_alleyoopass'),
    'Tendencies/DISHTOOPENMAN': ('offense', 'derive_tendency_dishtoopenman'),
    'Tendencies/FLASHYPASS': ('offense', 'derive_tendency_flashypass'),
    'Tendencies/POSTAGGRESSIVEBACKDOWN': ('offense', 'derive_tendency_postaggressivebackdown'),
    'Tendencies/POSTBACKDOWN': ('offense', 'derive_tendency_postbackdown'),
    'Tendencies/POSTDRIVE': ('offense', 'derive_tendency_postdrive'),
    'Tendencies/POSTFACEUP': ('offense', 'derive_tendency_postfaceup'),
    'Tendencies/POSTHOPSTEP': ('offense', 'derive_tendency_posthopstep'),
    'Tendencies/POSTSPIN': ('offense', 'derive_tendency_postspin'),
    'Tendencies/POSTUP': ('offense', 'derive_tendency_postup'),
    'Tendencies/ISOVSAVERAGEDEFENDER': ('mental', 'derive_tendency_isovsaveragedefender'),
    'Tendencies/ISOVSELITEDEFENDER': ('mental', 'derive_tendency_isovselitedefender'),
    'Tendencies/ISOVSGOODDEFENDER': ('mental', 'derive_tendency_isovsgooddefender'),
    'Tendencies/ISOVSPOORDEFENDER': ('mental', 'derive_tendency_isovspoordefender'),
    'Tendencies/PLAYDISCIPLINE': ('mental', 'derive_tendency_playdiscipline'),
    'Tendencies/ROLLVSPOP': ('mental', 'derive_tendency_rollvspop'),
    'Tendencies/TOUCHES': ('mental', 'derive_tendency_touches'),
    'Tendencies/TRANSITIONSPOTUP': ('mental', 'derive_tendency_transitionspotup'),
    'Tendencies/BLOCKSHOT': ('defense', 'derive_tendency_blockshot'),
    'Tendencies/CONTESTSHOT': ('defense', 'derive_tendency_contestshot'),
    'Tendencies/FOUL': ('defense', 'derive_tendency_foul'),
    'Tendencies/HARDFOUL': ('defense', 'derive_tendency_hardfoul'),
    'Tendencies/ONBALLSTEAL': ('defense', 'derive_tendency_onballsteal'),
    'Tendencies/PASSINTERCEPTION': ('defense', 'derive_tendency_passinterception'),
    'Tendencies/TAKECHARGE': ('defense', 'derive_tendency_takecharge'),

    'Tendencies/3POINTSHOT': ('offense', 'derive_tendency_3pointshot'),
    'Tendencies/3POINTCENTERLEFTSHOT': ('offense', 'derive_tendency_3pointcenterleftshot'),
    'Tendencies/3POINTCENTERRIGHTSHOT': ('offense', 'derive_tendency_3pointcenterrightshot'),
    'Tendencies/3POINTCENTERSHOT': ('offense', 'derive_tendency_3pointcentershot'),
    'Tendencies/3POINTLEFTSHOT': ('offense', 'derive_tendency_3pointleftshot'),
    'Tendencies/3POINTOFFSCREENSHOT': ('offense', 'derive_tendency_3pointoffscreenshot'),
    'Tendencies/3POINTRIGHTSHOT': ('offense', 'derive_tendency_3pointrightshot'),
    'Tendencies/3POINTSPOTUPSHOT': ('offense', 'derive_tendency_3pointspotupshot'),
    'Tendencies/ALLEYOOP': ('offense', 'derive_tendency_alleyoop'),
    'Tendencies/BASKETUNDERSHOT': ('offense', 'derive_tendency_basketundershot'),
    'Tendencies/CENTERLEFTMIDSHOT': ('offense', 'derive_tendency_centerleftmidshot'),
    'Tendencies/CENTERMIDRIGHTSHOT': ('offense', 'derive_tendency_centermidrightshot'),
    'Tendencies/CENTERMIDSHOT': ('offense', 'derive_tendency_centermidshot'),
    'Tendencies/CLOSESHOT': ('offense', 'derive_tendency_closeshot'),
    'Tendencies/CLOSELEFTSHOT': ('offense', 'derive_tendency_closeleftshot'),
    'Tendencies/CLOSEMIDDLESHOT': ('offense', 'derive_tendency_closemiddleshot'),
    'Tendencies/CLOSERIGHTSHOT': ('offense', 'derive_tendency_closerightshot'),
    'Tendencies/CONTESTEDJUMPER3POINT': ('offense', 'derive_tendency_contestedjumper3point'),
    'Tendencies/CONTESTEDJUMPERMID': ('offense', 'derive_tendency_contestedjumpermid'),
    'Tendencies/CONTESTEDJUMPERMIDRANGE': ('offense', 'derive_tendency_contestedjumpermidrange'),
    'Tendencies/DRIVEPULLUP3POINT': ('offense', 'derive_tendency_drivepullup3point'),
    'Tendencies/DRIVEPULLUPMID': ('offense', 'derive_tendency_drivepullupmid'),
    'Tendencies/DRIVEPULLUPMIDRANGE': ('offense', 'derive_tendency_drivepullupmidrange'),
    'Tendencies/DRIVINGDUNK': ('offense', 'derive_tendency_drivingdunk'),
    'Tendencies/DRIVINGLAYUP': ('offense', 'derive_tendency_drivinglayup'),
    'Tendencies/EUROSTEPLAYUP': ('offense', 'derive_tendency_eurosteplayup'),
    'Tendencies/FLASHYDUNK': ('offense', 'derive_tendency_flashydunk'),
    'Tendencies/FLOATER': ('offense', 'derive_tendency_floater'),
    'Tendencies/FROMPOSTSHOT': ('offense', 'derive_tendency_frompostshot'),
    'Tendencies/HOPPOSTSHOT': ('offense', 'derive_tendency_hoppostshot'),
    'Tendencies/HOPSTEPLAYUP': ('offense', 'derive_tendency_hopsteplayup'),
    'Tendencies/LEFTMIDSHOT': ('offense', 'derive_tendency_leftmidshot'),
    'Tendencies/MIDOFFSCREENSHOT': ('offense', 'derive_tendency_midoffscreenshot'),
    'Tendencies/MIDRIGHTSHOT': ('offense', 'derive_tendency_midrightshot'),
    'Tendencies/MIDSHOT': ('offense', 'derive_tendency_midshot'),
    'Tendencies/MIDSPOTUPSHOT': ('offense', 'derive_tendency_midspotupshot'),
    'Tendencies/POSTDROPSTEP': ('offense', 'derive_tendency_postdropstep'),
    'Tendencies/POSTFADELEFT': ('offense', 'derive_tendency_postfadeleft'),
    'Tendencies/POSTFADERIGHT': ('offense', 'derive_tendency_postfaderight'),
    'Tendencies/POSTHOOKLEFT': ('offense', 'derive_tendency_posthookleft'),
    'Tendencies/POSTHOOKRIGHT': ('offense', 'derive_tendency_posthookright'),
    'Tendencies/POSTSHIMMYSHOT': ('offense', 'derive_tendency_postshimmyshot'),
    'Tendencies/POSTSTEPBACKSHOT': ('offense', 'derive_tendency_poststepbackshot'),
    'Tendencies/POSTUPANDUNDER': ('offense', 'derive_tendency_postupandunder'),
    'Tendencies/PUTBACK': ('rebounding', 'derive_tendency_putback'),
    'Tendencies/PUTBACKDUNK': ('rebounding', 'derive_tendency_putbackdunk'),
    'Tendencies/SPINJUMPER': ('offense', 'derive_tendency_spinjumper'),
    'Tendencies/SPINLAYUP': ('offense', 'derive_tendency_spinlayup'),
    'Tendencies/STANDINGDUNK': ('offense', 'derive_tendency_standingdunk'),
    'Tendencies/STEPBACKJUMPER3POINT': ('offense', 'derive_tendency_stepbackjumper3point'),
    'Tendencies/STEPBACKJUMPERMID': ('offense', 'derive_tendency_stepbackjumpermid'),
    'Tendencies/STEPBACKJUMPERMIDRANGE': ('offense', 'derive_tendency_stepbackjumpermidrange'),
    'Tendencies/STEPTHROUGH': ('offense', 'derive_tendency_stepthrough'),
    'Tendencies/TRANSITIONPULLUP3POINT': ('offense', 'derive_tendency_transitionpullup3point'),
    'Tendencies/USEGLASS': ('offense', 'derive_tendency_useglass'),
    'Tendencies/SHOT': ('offense', 'derive_tendency_shot'),
}
_RULE_MODULES: dict[str, Any] = {
    "offense": offense,
    "defense": defense,
    "rebounding": rebounding,
    "athleticism": athleticism,
    "mental": mental,
}
PLAYER_RULE_SCHEME: dict[str, PlayerRuleSpec] = {
    field_key: PlayerRuleSpec(field_key=field_key, module=module, function=function)
    for field_key, (module, function) in _RULE_BINDINGS.items()
}
_COMPARISON_POPULATION_CACHE: dict[
    tuple[int, int],
    tuple[object, tuple[dict[str, Any], ...]],
] = {}


def derive_player_profile_values(evidence: PlayerEvidence, positions: PositionSelection | None = None) -> PlayerProfileResult:
    values: dict[str, ProfileValue] = {}
    positions = positions or select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    first, last = _split_name(evidence.identity.get("player") or evidence.season_info.get("player") or evidence.player_id)
    _add_profile(values, "Vitals/FIRSTNAME", first, "profile_sql_identity", "player_info.player")
    _add_profile(values, "Vitals/LASTNAME", last, "profile_sql_identity", "player_info.player")

    height = _int_round(evidence.identity.get("ht_in_in"))
    weight = _int_round(evidence.identity.get("wt"))
    _add_profile(values, "Vitals/HEIGHT", height, "profile_sql_bio", "player_info.ht_in_in")
    _add_profile(values, "Vitals/WEIGHT", weight, "profile_sql_bio", "player_info.wt")

    _add_profile(values, "Vitals/POSITION", positions.primary, "profile_sql_position_percent", "play_by_play.position_percent")
    _add_profile(
        values,
        "Vitals/SECONDARYPOSITION",
        positions.secondary if positions.secondary else "N/A",
        "profile_sql_position_percent",
        "play_by_play.position_percent",
    )

    birth = _birth_date_from_source(evidence.identity.get("birth_date"))
    age = _int_round(evidence.season_info.get("age"))
    if age is not None:
        _add_profile(values, "Vitals/AGE", age, "profile_sql_selected_season_age", "season_info.age")
    elif birth:
        _add_profile(values, "Vitals/AGE", int(evidence.season) - birth.year, "profile_sql_birth_date_age_estimate", "player_info.birth_date")
    if birth:
        _add_profile(values, "Vitals/BIRTHMONTH", birth.month, "profile_sql_birth_date", "player_info.birth_date")
        _add_profile(values, "Vitals/BIRTHDAY", birth.day, "profile_sql_birth_date", "player_info.birth_date")

    draft_year = _int_round(_source_value(evidence, "draft_picks.season", "draft.season"))
    draft_round = _int_round(_source_value(evidence, "draft_picks.round", "draft.round"))
    draft_pick = _int_round(_source_value(evidence, "draft_picks.overall_pick", "draft.overall_pick"))
    _add_profile(values, "Vitals/DRAFTYEAR", draft_year, "profile_sql_draft", "draft_picks.season")
    _add_profile(values, "Vitals/DRAFTEDYEAR", draft_year, "profile_sql_draft", "draft_picks.season")
    _add_profile(values, "Vitals/DRAFTROUND", draft_round, "profile_sql_draft", "draft_picks.round")
    _add_profile(values, "Vitals/DRAFTPICKNUMBER", draft_pick, "profile_sql_draft", "draft_picks.overall_pick")
    _add_profile(values, "Vitals/DRAFTPICK", draft_pick, "profile_sql_draft", "draft_picks.overall_pick")
    return PlayerProfileResult(values=values)



def derive_player_rule_values(
    evidence: PlayerEvidence,
    positions: PositionSelection | None = None,
    *,
    league_player_rows: Any = (),
    active_field_keys: set[str] | None = None,
) -> PlayerRuleResult:
    positions = positions or select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    if not positions.primary or not _has_required_games_played(evidence):
        return PlayerRuleResult(values={})

    formula_values = derive_formula_rule_values(
        evidence,
        positions=positions,
        league_player_rows=league_player_rows,
        active_field_keys=active_field_keys,
    )
    return PlayerRuleResult(values=formula_values)


def derive_formula_rule_values(
    evidence: PlayerEvidence,
    *,
    positions: PositionSelection | None = None,
    league_player_rows: Any = (),
    active_field_keys: set[str] | None = None,
) -> dict[str, RuleValue]:
    if not _has_required_games_played(evidence):
        return {}
    # Drive from the editor's field list when it is supplied: a field is
    # generated only if the loaded game exposes it AND a rule is bound to it.
    # Otherwise (standalone/tests) fall back to every bound field.
    field_keys = tuple(sorted(active_field_keys)) if active_field_keys is not None else tuple(PLAYER_RULE_SCHEME)
    values: dict[str, RuleValue] = {}
    rows = _selected_comparison_rows(evidence, league_player_rows)
    for field_key in field_keys:
        spec = PLAYER_RULE_SCHEME.get(field_key)
        if spec is None:
            continue
        rule = getattr(_RULE_MODULES[spec.module], spec.function, None)
        if rule is None:
            continue
        result = _call_formula_rule(
            rule,
            evidence,
            owner_module=spec.module,
            positions=positions,
            league_player_rows=rows,
        )
        value = _coerce_formula_rule_value(field_key, result)
        if value is None:
            continue
        values[field_key] = value
    # Pre-shot-clock (<=1954) playstyle post-pass: push each archetype toward how
    # it was actually played in its era. No-op for every later season and when
    # PLAYERGEN_ERA_ROLE_PLAYSTYLE is disabled.
    values = _apply_era_role_playstyle(evidence, positions, values)
    return _apply_shot_family_gate(values)


# ATD "Shot family vs subtypes": Shot Mid and Shot Three carry the total share for
# their range, and the spot-up / off-screen / pull-up / stepback / contested /
# directional values only choose the *route* once a shot of that range is taken. A
# route cannot be taken more often than the range it belongs to exists, so a family
# total of zero has to zero its whole family -- otherwise a player who took no
# mid-range shots all season still carries a contested-mid or pull-up-mid branch and
# the engine can select it.
#
# Deliberately not listed: SPINJUMPER and THREATTRIPLESHOT. Neither is named for a
# range on the committee sheet (the game fields are "Spin Jumper Tendency" and
# "Triple Threat Shoot"), and the sheet's triple-threat notes treat Shoot as its own
# conditional stationary-catch branch rather than a member of a range family.
_SHOT_FAMILY_GATES: dict[str, tuple[str, ...]] = {
    "Tendencies/MIDSHOT": (
        "Tendencies/MIDSPOTUPSHOT",
        "Tendencies/MIDOFFSCREENSHOT",
        "Tendencies/CONTESTEDJUMPERMID",
        "Tendencies/CONTESTEDJUMPERMIDRANGE",
        "Tendencies/STEPBACKJUMPERMID",
        "Tendencies/STEPBACKJUMPERMIDRANGE",
        "Tendencies/DRIVEPULLUPMID",
        "Tendencies/DRIVEPULLUPMIDRANGE",
        "Tendencies/LEFTMIDSHOT",
        "Tendencies/MIDRIGHTSHOT",
        "Tendencies/CENTERMIDSHOT",
        "Tendencies/CENTERLEFTMIDSHOT",
        "Tendencies/CENTERMIDRIGHTSHOT",
    ),
    "Tendencies/3POINTSHOT": (
        "Tendencies/3POINTSPOTUPSHOT",
        "Tendencies/3POINTOFFSCREENSHOT",
        "Tendencies/CONTESTEDJUMPER3POINT",
        "Tendencies/STEPBACKJUMPER3POINT",
        "Tendencies/DRIVEPULLUP3POINT",
        "Tendencies/TRANSITIONPULLUP3POINT",
        "Tendencies/3POINTLEFTSHOT",
        "Tendencies/3POINTRIGHTSHOT",
        "Tendencies/3POINTCENTERSHOT",
        "Tendencies/3POINTCENTERLEFTSHOT",
        "Tendencies/3POINTCENTERRIGHTSHOT",
    ),
}


def _apply_shot_family_gate(values: dict[str, RuleValue]) -> dict[str, RuleValue]:
    gated = dict(values)
    for parent_key, child_keys in _SHOT_FAMILY_GATES.items():
        parent = gated.get(parent_key)
        # An absent parent is unresolved evidence, not a zero: only an explicit 0
        # closes the family.
        if parent is None or parent.value != 0:
            continue
        for child_key in child_keys:
            child = gated.get(child_key)
            if child is None or child.value == 0:
                continue
            gated[child_key] = replace(
                child,
                value=0,
                source_rule=f"{child.source_rule}_shot_family_gate",
                evidence_keys=child.evidence_keys
                + (
                    f"{parent_key}=0",
                    "atd_rule=shot_family_total_gates_its_route_subtypes",
                    f"ungated_{child_key.split('/')[-1].lower()}={child.value}",
                ),
            )
    return gated


def _clamp_rule_value(field_key: str, value: int) -> int:
    if field_key.startswith("Attributes/"):
        return max(25, min(99, value))
    if field_key.startswith("Tendencies/"):
        return max(0, min(100, value))
    return value


def _call_formula_rule(
    rule: Callable[..., Any],
    evidence: PlayerEvidence,
    *,
    owner_module: str,
    positions: PositionSelection | None,
    league_player_rows: Any,
) -> Any:
    if owner_module == "athleticism":
        return rule(evidence, None, league_player_rows, positions)
    return rule(evidence, league_player_rows=league_player_rows)


def _coerce_formula_rule_value(field_key: str, result: Any) -> RuleValue | None:
    if result is None:
        return None
    if isinstance(result, RuleValue):
        value = result.value
        source_rule = result.source_rule
        evidence_keys = result.evidence_keys
    elif isinstance(result, tuple) and len(result) == 3:
        value, raw_source_rule, raw_evidence_keys = result
        source_rule = str(raw_source_rule or "").strip()
        evidence_keys = tuple(str(key) for key in raw_evidence_keys or ())
    elif isinstance(result, dict) and "value" in result:
        value = result.get("value")
        source_rule = str(result.get("source_rule") or "").strip()
        evidence_keys = tuple(str(key) for key in result.get("evidence_keys") or ())
    else:
        return None
    if not source_rule or not evidence_keys:
        return None
    stored = _int_round(value)
    if stored is None:
        return None
    stored = _clamp_rule_value(field_key, stored)
    return RuleValue(value=stored, source_rule=source_rule, evidence_keys=evidence_keys)


def _has_required_games_played(evidence: PlayerEvidence) -> bool:
    games = _float(evidence.per_game.get("g"))
    return games is not None and games > 0.0


def _selected_comparison_rows(evidence: PlayerEvidence, rows: Any) -> tuple[dict[str, Any], ...]:
    if int(evidence.season) <= 0:
        return ()
    cache_key = (id(rows), int(evidence.season))
    cached = _COMPARISON_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    selected: list[dict[str, Any]] = []
    for row in tuple(rows or ()):
        if not isinstance(row, dict):
            continue
        row_season = _row_context_value(row, "season", "player_season_info.season", "season_info.season")
        if _int_round(row_season) != int(evidence.season):
            continue
        row_games = _row_context_value(row, "player_per_game.g", "per_game.g", "g")
        if (games := _float(row_games)) is None or games <= 0.0:
            continue
        selected.append(row)
    population = tuple(selected)
    _COMPARISON_POPULATION_CACHE[cache_key] = (rows, population)
    return population


def _row_context_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


def _add_profile(values: dict[str, ProfileValue], key: str, value: object, source_rule: str, *evidence_keys: str) -> None:
    if value is None or value == "":
        return
    if isinstance(value, (int, str)):
        stored: int | str = value
    else:
        rounded = _int_round(value)
        stored = rounded if rounded is not None else str(value)
    values[key] = ProfileValue(value=stored, source_rule=source_rule, evidence_keys=tuple(evidence_keys))


def _split_name(value: object) -> tuple[str, str]:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "", ""
    parts = text.split(" ")
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def _birth_date_from_source(value: object) -> datetime | None:
    number = _float(value)
    if number is None:
        return None
    # NBA_DATA_Master stores Excel serial dates in player_info.birth_date.
    return datetime(1899, 12, 30) + timedelta(days=int(number))


def _source_value(evidence: PlayerEvidence, *keys: str) -> object:
    for key in keys:
        if key in evidence.source_context:
            return evidence.source_context[key]
    return None


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _int_round(value: object) -> int | None:
    number = _float(value)
    if number is None:
        return None
    return int(round(number))



__all__ = [
    "PlayerProfileResult",
    "PlayerRuleResult",
    "PlayerRuleSpec",
    "PositionSelection",
    "ProfileValue",
    "RuleValue",
    "derive_formula_rule_values",
    "derive_player_profile_values",
    "derive_player_rule_values",
    "select_positions_from_evidence",
]
