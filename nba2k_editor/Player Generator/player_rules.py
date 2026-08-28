from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Callable

import player_rules_athleticism as athleticism
import player_rules_defense as defense
import player_rules_mental as mental
import player_rules_offense as offense
import player_rules_rebounding as rebounding
from player_evidence import PlayerEvidence
from stat_neighbor_framework import PositionSelection, select_positions_from_evidence


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
    section: str
    group: str
    module: str
    function: str


_RULE_ROWS: tuple[tuple[str, str, str, str, str], ...] = (

    ('Attributes/BALLCONTROL', 'Attributes', 'Offense', 'offense', 'derive_attribute_ballcontrol'),
    ('Attributes/DRAWFOUL', 'Attributes', 'Offense', 'offense', 'derive_attribute_drawfoul'),
    ('Attributes/OFFENSIVECONSISTENCY', 'Attributes', 'Offense', 'offense', 'derive_attribute_offensiveconsistency'),
    ('Attributes/PASSACCURACY', 'Attributes', 'Offense', 'offense', 'derive_attribute_passaccuracy'),
    ('Attributes/PASSIQ', 'Attributes', 'Offense', 'offense', 'derive_attribute_passiq'),
    ('Attributes/PASSVISION', 'Attributes', 'Offense', 'offense', 'derive_attribute_passvision'),
    ('Attributes/IQSHOT', 'Attributes', 'Offense', 'offense', 'derive_attribute_iqshot'),
    ('Attributes/3POINT', 'Attributes', 'Offense', 'offense', 'derive_attribute_3point'),
    ('Attributes/CLOSESHOT', 'Attributes', 'Offense', 'offense', 'derive_attribute_closeshot'),
    ('Attributes/DRIVINGDUNK', 'Attributes', 'Offense', 'offense', 'derive_attribute_drivingdunk'),
    ('Attributes/DRIVINGLAYUP', 'Attributes', 'Offense', 'offense', 'derive_attribute_drivinglayup'),
    ('Attributes/MIDRANGE', 'Attributes', 'Offense', 'offense', 'derive_attribute_midrange'),
    ('Attributes/POSTCONTROL', 'Attributes', 'Offense', 'offense', 'derive_attribute_postcontrol'),
    ('Attributes/POSTFADE', 'Attributes', 'Offense', 'offense', 'derive_attribute_postfade'),
    ('Attributes/POSTHOOK', 'Attributes', 'Offense', 'offense', 'derive_attribute_posthook'),
    ('Attributes/STANDINGDUNK', 'Attributes', 'Offense', 'offense', 'derive_attribute_standingdunk'),
    ('Attributes/BLOCK', 'Attributes', 'Defense', 'defense', 'derive_attribute_block'),
    ('Attributes/DEFENSECONSISTENCY', 'Attributes', 'Defense', 'defense', 'derive_attribute_defenseconsistency'),
    ('Attributes/HELPDEFENSE', 'Attributes', 'Defense', 'defense', 'derive_attribute_helpdefense'),
    ('Attributes/INTERIORDEFENSE', 'Attributes', 'Defense', 'defense', 'derive_attribute_interiordefense'),
    ('Attributes/PASSPERCEPTION', 'Attributes', 'Defense', 'defense', 'derive_attribute_passperception'),
    ('Attributes/PERIMETERDEFENSE', 'Attributes', 'Defense', 'defense', 'derive_attribute_perimeterdefense'),
    ('Attributes/STEAL', 'Attributes', 'Defense', 'defense', 'derive_attribute_steal'),
    ('Attributes/ACCELERATION', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_acceleration'),
    ('Attributes/AGILITY', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_agility'),
    ('Attributes/SPEED', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_speed'),
    ('Attributes/SPEEDWITHBALL', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_speedwithball'),
    ('Attributes/STAMINA', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_stamina'),
    ('Attributes/STRENGTH', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_strength'),
    ('Attributes/VERTICAL', 'Attributes', 'Athleticism', 'athleticism', 'derive_attribute_vertical'),
    ('Attributes/BACKDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_backdurability'),
    ('Attributes/HEADDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_headdurability'),
    ('Attributes/LEFTANKLEDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_leftankledurability'),
    ('Attributes/LEFTELBOWDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_leftelbowdurability'),
    ('Attributes/LEFTFOOTDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_leftfootdurability'),
    ('Attributes/LEFTHANDDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_lefthanddurability'),
    ('Attributes/LEFTHIPDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_lefthipdurability'),
    ('Attributes/LEFTKNEEDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_leftkneedurability'),
    ('Attributes/LEFTSHOULDERDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_leftshoulderdurability'),
    ('Attributes/MISCDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_miscdurability'),
    ('Attributes/NECKDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_neckdurability'),
    ('Attributes/RIGHTANKLEDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_rightankledurability'),
    ('Attributes/RIGHTELBOWDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_rightelbowdurability'),
    ('Attributes/RIGHTFOOTDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_rightfootdurability'),
    ('Attributes/RIGHTHANDDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_righthanddurability'),
    ('Attributes/RIGHTHIPDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_righthipdurability'),
    ('Attributes/RIGHTKNEEDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_rightkneedurability'),
    ('Attributes/RIGHTSHOULDERDURABILITY', 'Attributes', 'Durability', 'athleticism', 'derive_attribute_rightshoulderdurability'),
    ('Attributes/HANDS', 'Attributes', 'Mental', 'mental', 'derive_attribute_hands'),
    ('Attributes/HUSTLE', 'Attributes', 'Mental', 'mental', 'derive_attribute_hustle'),
    ('Attributes/INTANGIBLES', 'Attributes', 'Mental', 'mental', 'derive_attribute_intangibles'),
    ('Attributes/LATERALQUICKNESS', 'Attributes', 'Misc', 'defense', 'derive_attribute_lateralquickness'),
    ('Attributes/PICKANDROLLDEFENSEIQ', 'Attributes', 'Misc', 'defense', 'derive_attribute_pickandrolldefenseiq'),
    ('Attributes/POTENTIAL', 'Attributes', 'Misc', 'mental', 'derive_attribute_potential'),
    ('Attributes/CONTESTSHOT', 'Attributes', 'Misc', 'defense', 'derive_attribute_contestshot'),
    ('Attributes/DEFENSEREBOUND', 'Attributes', 'Rebounding', 'rebounding', 'derive_attribute_defensiverebound'),
    ('Attributes/OFFENSIVEREBOUND', 'Attributes', 'Rebounding', 'rebounding', 'derive_attribute_offensiverebound'),







    ('Tendencies/CRASH', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_crash'),
    ('Tendencies/NOSETUPDRIBBLE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_setupdribble'),
    ('Tendencies/SETUPWITHHESITATION', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_setupwithhesitation'),
    ('Tendencies/SETUPWITHSIZEUP', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_setupwithsizeup'),
    ('Tendencies/TRIPLETHREATIDLE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatidle'),
    ('Tendencies/TRIPLETHREATJABSTEP', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatjab'),
    ('Tendencies/TRIPLETHREATPUMPFAKE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatpumpfake'),
    ('Tendencies/THREATTRIPLESHOT', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatshot'),
    ('Tendencies/ATTACKSTRONGONDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_attackstrongondrive'),
    ('Tendencies/DRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drive'),
    ('Tendencies/DRIVERIGHT', 'Tendencies', 'Driving', 'offense', 'derive_tendency_driveright'),
    ('Tendencies/DRIVINGBEHINDTHEBACK', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingbehindtheback'),
    ('Tendencies/DRIBBLECROSSOVER', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingcrossover'),
    ('Tendencies/DRIVINGDOUBLECROSSOVER', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingdoublecrossover'),
    ('Tendencies/DRIVINGDRIBBLEHESITATION', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingdribblehesitation'),
    ('Tendencies/DRIVINGHALFSPIN', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivinghalfspin'),
    ('Tendencies/DRIVINGINANDOUT', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivinginandout'),
    ('Tendencies/DRIBBLESPIN', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingspin'),
    ('Tendencies/DRIVINGSTEPBACK', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingstepback'),
    ('Tendencies/NODRIVINGDRIBBLEMOVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_nodrivingdribblemove'),
    ('Tendencies/OFFSCREENDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_offscreendrive'),
    ('Tendencies/SPOTUPDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_spotupdrive'),
    ('Tendencies/ALLEYOOPPASS', 'Tendencies', 'Passing', 'offense', 'derive_tendency_alleyoopass'),
    ('Tendencies/DISHTOOPENMAN', 'Tendencies', 'Passing', 'offense', 'derive_tendency_dishtoopenman'),
    ('Tendencies/FLASHYPASS', 'Tendencies', 'Passing', 'offense', 'derive_tendency_flashypass'),
    ('Tendencies/POSTAGGRESSIVEBACKDOWN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postaggressivebackdown'),
    ('Tendencies/POSTBACKDOWN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postbackdown'),
    ('Tendencies/POSTDRIVE', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postdrive'),
    ('Tendencies/POSTFACEUP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfaceup'),
    ('Tendencies/POSTHOPSTEP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthopstep'),
    ('Tendencies/POSTSPIN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postspin'),
    ('Tendencies/POSTUP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postup'),
    ('Tendencies/ISOVSAVERAGEDEFENDER', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_isovsaveragedefender'),
    ('Tendencies/ISOVSELITEDEFENDER', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_isovselitedefender'),
    ('Tendencies/ISOVSGOODDEFENDER', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_isovsgooddefender'),
    ('Tendencies/ISOVSPOORDEFENDER', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_isovspoordefender'),
    ('Tendencies/PLAYDISCIPLINE', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_playdiscipline'),
    ('Tendencies/ROLLVSPOP', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_rollvspop'),
    ('Tendencies/TOUCHES', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_touches'),
    ('Tendencies/TRANSITIONSPOTUP', 'Tendencies', 'Freelance', 'mental', 'derive_tendency_transitionspotup'),
    ('Tendencies/BLOCKSHOT', 'Tendencies', 'Defense', 'defense', 'derive_tendency_blockshot'),
    ('Tendencies/CONTESTSHOT', 'Tendencies', 'Defense', 'defense', 'derive_tendency_contestshot'),
    ('Tendencies/FOUL', 'Tendencies', 'Defense', 'defense', 'derive_tendency_foul'),
    ('Tendencies/HARDFOUL', 'Tendencies', 'Defense', 'defense', 'derive_tendency_hardfoul'),
    ('Tendencies/ONBALLSTEAL', 'Tendencies', 'Defense', 'defense', 'derive_tendency_onballsteal'),
    ('Tendencies/PASSINTERCEPTION', 'Tendencies', 'Defense', 'defense', 'derive_tendency_passinterception'),
    ('Tendencies/TAKECHARGE', 'Tendencies', 'Defense', 'defense', 'derive_tendency_takecharge'),

    ('Tendencies/3POINTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointshot'),
    ('Tendencies/3POINTCENTERLEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointcenterleftshot'),
    ('Tendencies/3POINTCENTERRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointcenterrightshot'),
    ('Tendencies/3POINTCENTERSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointcentershot'),
    ('Tendencies/3POINTLEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointleftshot'),
    ('Tendencies/3POINTOFFSCREENSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointoffscreenshot'),
    ('Tendencies/3POINTRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointrightshot'),
    ('Tendencies/3POINTSPOTUPSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_3pointspotupshot'),
    ('Tendencies/ALLEYOOP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_alleyoop'),
    ('Tendencies/BASKETUNDERSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_basketundershot'),
    ('Tendencies/CENTERLEFTMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centerleftmidshot'),
    ('Tendencies/CENTERMIDRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centermidrightshot'),
    ('Tendencies/CENTERMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centermidshot'),
    ('Tendencies/CLOSESHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closeshot'),
    ('Tendencies/CLOSELEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closeleftshot'),
    ('Tendencies/CLOSEMIDDLESHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closemiddleshot'),
    ('Tendencies/CLOSERIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closerightshot'),
    ('Tendencies/CONTESTEDJUMPER3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumper3point'),
    ('Tendencies/CONTESTEDJUMPERMID', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermid'),
    ('Tendencies/CONTESTEDJUMPERMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermidrange'),
    ('Tendencies/DRIVEPULLUP3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_drivepullup3point'),
    ('Tendencies/DRIVEPULLUPMID', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivepullupmid'),
    ('Tendencies/DRIVEPULLUPMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_drivepullupmidrange'),
    ('Tendencies/DRIVINGDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_drivingdunk'),
    ('Tendencies/DRIVINGLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_drivinglayup'),
    ('Tendencies/EUROSTEPLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_eurosteplayup'),
    ('Tendencies/FLASHYDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_flashydunk'),
    ('Tendencies/FLOATER', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_floater'),
    ('Tendencies/FROMPOSTSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_frompostshot'),
    ('Tendencies/HOPPOSTSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_hoppostshot'),
    ('Tendencies/HOPSTEPLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_hopsteplayup'),
    ('Tendencies/LEFTMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_leftmidshot'),
    ('Tendencies/MIDOFFSCREENSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midoffscreenshot'),
    ('Tendencies/MIDRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midrightshot'),
    ('Tendencies/MIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midshot'),
    ('Tendencies/MIDSPOTUPSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midspotupshot'),
    ('Tendencies/POSTDROPSTEP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postdropstep'),
    ('Tendencies/POSTFADELEFT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfadeleft'),
    ('Tendencies/POSTFADERIGHT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfaderight'),
    ('Tendencies/POSTHOOKLEFT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthookleft'),
    ('Tendencies/POSTHOOKRIGHT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthookright'),
    ('Tendencies/POSTSHIMMYSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postshimmyshot'),
    ('Tendencies/POSTSTEPBACKSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_poststepbackshot'),
    ('Tendencies/POSTUPANDUNDER', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postupandunder'),
    ('Tendencies/PUTBACK', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_putback'),
    ('Tendencies/PUTBACKDUNK', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_putbackdunk'),
    ('Tendencies/SPINJUMPER', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_spinjumper'),
    ('Tendencies/SPINLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_spinlayup'),
    ('Tendencies/STANDINGDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_standingdunk'),
    ('Tendencies/STEPBACKJUMPER3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumper3point'),
    ('Tendencies/STEPBACKJUMPERMID', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_stepbackjumpermid'),
    ('Tendencies/STEPBACKJUMPERMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumpermidrange'),
    ('Tendencies/STEPTHROUGH', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepthrough'),
    ('Tendencies/TRANSITIONPULLUP3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_transitionpullup3point'),
    ('Tendencies/USEGLASS', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_useglass'),
    ('Tendencies/SHOT', 'Tendencies', 'Tendencies', 'offense', 'derive_tendency_shot'),
)
_RULE_MODULES: dict[str, Any] = {
    "offense": offense,
    "defense": defense,
    "rebounding": rebounding,
    "athleticism": athleticism,
    "mental": mental,
}
PLAYER_RULE_SCHEME: dict[str, PlayerRuleSpec] = {
    field_key: PlayerRuleSpec(field_key=field_key, section=section, group=group, module=module, function=function)
    for field_key, section, group, module, function in _RULE_ROWS
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
    )
    if active_field_keys is not None:
        formula_values = {key: value for key, value in formula_values.items() if key in active_field_keys}
    return PlayerRuleResult(values=formula_values)


def derive_formula_rule_values(
    evidence: PlayerEvidence,
    *,
    positions: PositionSelection | None = None,
    league_player_rows: Any = (),
) -> dict[str, RuleValue]:
    if not _has_required_games_played(evidence):
        return {}
    values: dict[str, RuleValue] = {}
    rows = _selected_comparison_rows(evidence, league_player_rows)
    for field_key, spec in PLAYER_RULE_SCHEME.items():
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
    return values


def derive_neighbor_rule_values(evidence: PlayerEvidence, positions: PositionSelection, *, model: Any = None) -> dict[str, RuleValue]:
    # The current neighbor suggestion contract omits source package run_id/player_index,
    # GP, season, and league. Those values cannot be admitted as generation evidence.
    return {}


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
        return rule(evidence, PLAYER_RULE_SCHEME, league_player_rows, positions)
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
    "ProfileValue",
    "RuleValue",
    "derive_formula_rule_values",
    "derive_neighbor_rule_values",
    "derive_player_profile_values",
    "derive_player_rule_values",
]
