from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose, isfinite
from typing import Any, Callable

import player_rules_athleticism as athleticism
import player_rules_defense as defense
import player_rules_mental as mental
import player_rules_offense as offense
import player_rules_rebounding as rebounding
from player_era_context import player_era_context
from player_evidence import PlayerEvidence
from player_special_rules import researched_defense_quality_rule_for
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







    ('Tendencies/CRASH', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_crash'),
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
_EXTERNAL_RULE_OWNERS = {"Attributes/FREETHROW": "player_generator.model_free_throw_inverse"}
_APPROVED_FIXED_PROVENANCE = {"durability.default_90_pending_injury_database"}
_ELIGIBILITY_ONLY_SOURCE_PATHS = {"per_game.g", "totals.g"}
_FORBIDDEN_PROVENANCE_FRAGMENTS = (
    "role-band",
    "position band",
    "aggregate_position_mean=",
    "ordinary_pool_distribution_q25_median_q75=",
    "field_specific_historical_fallback",
)
_COMPARISON_POPULATION_CACHE: dict[
    tuple[int, int, str],
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
    required_fields = _required_rule_fields(active_field_keys)
    positions = positions or select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    if not positions.primary or not _has_required_games_played(evidence):
        return _complete_required_rule_fields({}, required_fields)

    formula_values = derive_formula_rule_values(
        evidence,
        positions=positions,
        league_player_rows=league_player_rows,
    )
    if active_field_keys is not None:
        formula_values = {key: value for key, value in formula_values.items() if key in active_field_keys}
    return _complete_required_rule_fields(formula_values, required_fields)


def _complete_required_rule_fields(
    values: dict[str, RuleValue],
    required_fields: set[str],
) -> PlayerRuleResult:
    """Guarantee that every active Attribute/Tendency has a generated value.

    Exact formulas remain authoritative. When an exact field cannot resolve,
    use the established legal set-value contract instead of omitting the
    candidate and exposing a blank/stale game value.
    """
    completed = dict(values)
    for field_key in sorted(required_fields - set(completed)):
        is_attribute = field_key.startswith("Attributes/")
        completed[field_key] = RuleValue(
            value=25 if is_attribute else 0,
            source_rule="required_active_field_set_value",
            evidence_keys=(
                f"unresolved_exact_source={field_key}",
                "set_value_contract=attribute_25" if is_attribute else "set_value_contract=tendency_0",
                "blank_prevention=active_field_must_resolve",
                "stale_game_value_allowed=false",
            ),
        )
    return PlayerRuleResult(values=completed, unresolved_fields=())


def derive_formula_rule_values(
    evidence: PlayerEvidence,
    *,
    positions: PositionSelection | None = None,
    league_player_rows: Any = (),
) -> dict[str, RuleValue]:
    if not _has_required_games_played(evidence):
        return {}
    values: dict[str, RuleValue] = {}
    rows = _same_season_same_league_rows(evidence, league_player_rows)
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
        if not _formula_has_live_input(evidence, field_key, value, owner_module=spec.module):
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


def _formula_has_live_input(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
    *,
    owner_module: str,
) -> bool:
    lowered_rule = value.source_rule.lower()
    provenance_text = "\n".join((lowered_rule, *(key.lower() for key in value.evidence_keys)))
    if (
        "role_fallback" in lowered_rule
        or "random" in lowered_rule
        or "named_player" in lowered_rule
        or any(fragment in provenance_text for fragment in _FORBIDDEN_PROVENANCE_FRAGMENTS)
    ):
        return False
    if (
        value.source_rule.startswith("derive_attribute_")
        and "durability" in value.source_rule
        and any(key in _APPROVED_FIXED_PROVENANCE for key in value.evidence_keys)
    ):
        return True
    if _is_approved_pre_line_value(evidence, value):
        return True
    if _is_approved_historical_hard_foul(evidence, field_key, value):
        return True
    if _is_approved_intangibles_floor(evidence, field_key, value):
        return True
    if _is_approved_zero_attempt_three_point(evidence, field_key, value):
        return True
    if _is_approved_researched_defense_override(evidence, field_key, value):
        return True
    if _is_approved_offball_action_anchor(evidence, field_key, value):
        return True
    candidate_paths = tuple(
        dict.fromkeys(
            key
            for raw_key in value.evidence_keys
            if "=" not in (key := raw_key[1:] if raw_key.startswith("!") else raw_key)
        )
    )
    live_paths = tuple(
        key for key in candidate_paths
        if _source_path_has_value(evidence, key)
        or _documented_owner_feature_has_numeric_value(evidence, owner_module, key)
    )
    if any(
        key not in _ELIGIBILITY_ONLY_SOURCE_PATHS
        and (
            _source_path_has_numeric_value(evidence, key)
            or _documented_owner_feature_has_numeric_value(evidence, owner_module, key)
        )
        for key in live_paths
    ):
        return True
    if _is_documented_field_fallback(value, live_paths):
        return True
    return False


def _is_approved_pre_line_value(evidence: PlayerEvidence, value: RuleValue) -> bool:
    context = player_era_context(evidence)
    if context.has_three_point_line or "three_point_line=none" not in value.evidence_keys:
        return False
    if not value.source_rule.endswith("_pre_line"):
        return False
    if value.source_rule.startswith("derive_attribute_3point"):
        return value.value == 25
    if value.source_rule.startswith("derive_tendency_") and "3point" in value.source_rule:
        return value.value == 0
    return False


def _is_approved_historical_hard_foul(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
) -> bool:
    if field_key != "Tendencies/HARDFOUL" or int(evidence.season) >= 1960:
        return False
    if value.value != 100 or value.source_rule != "derive_tendency_hardfoul_universal_pre_1960_maximum":
        return False
    return {
        "season_boundary=season_ending_year<1960",
        "HARDFOUL=100",
        "scale_meaning=maximum_2K_propensity_not_literal_event_probability",
    }.issubset(value.evidence_keys)


def _is_approved_zero_attempt_three_point(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
) -> bool:
    attempts = _float(evidence.totals.get("x3pa"))
    if attempts is None or attempts > 0.0:
        return False
    if field_key == "Attributes/3POINT":
        return value.value == 25 and value.source_rule == "derive_attribute_3point_no_made_attempt_evidence"
    if field_key == "Tendencies/3POINTSHOT":
        return value.value == 0 and value.source_rule == "derive_tendency_3pointshot_zero_attempts"
    return False


def _is_approved_researched_defense_override(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
) -> bool:
    player_id = str(evidence.player_id or evidence.identity.get("player_id") or "").strip().upper()
    team = str(evidence.team or evidence.season_info.get("team") or "").strip().upper()
    league = str(evidence.season_info.get("lg") or "").strip().upper()
    special_rule = researched_defense_quality_rule_for(
        season=int(evidence.season),
        league=league,
        player_id=player_id,
        team=team,
    )
    if special_rule is None:
        return False
    expected_value = special_rule.expected_values_by_field.get(field_key)
    if expected_value is None or value.value != expected_value:
        return False
    expected_rule = f"derive_attribute_{field_key.split('/', 1)[1].lower()}_researched_exact_player_override"
    if value.source_rule != expected_rule:
        return False
    required_provenance = set(special_rule.provenance_evidence_keys)
    return required_provenance.issubset(value.evidence_keys)


def _is_approved_offball_action_anchor(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
) -> bool:
    fields = {
        "Tendencies/MIDOFFSCREENSHOT": ("offscreen", 0),
        "Tendencies/3POINTOFFSCREENSHOT": ("offscreen", 0),
        "Tendencies/MIDSPOTUPSHOT": ("spotup", 1),
        "Tendencies/3POINTSPOTUPSHOT": ("spotup", 1),
    }
    action_spec = fields.get(field_key)
    if action_spec is None:
        return False
    player_id = str(evidence.player_id or evidence.identity.get("player_id") or "").strip().lower()
    anchors = getattr(offense, "_OFFBALL_ACTION_ANCHORS", {})
    anchor = anchors.get(player_id) if isinstance(anchors, dict) else None
    if not isinstance(anchor, tuple) or len(anchor) != 2:
        return False
    action, index = action_spec
    expected = int(anchor[index])
    expected_rule = f"derive_tendency_{field_key.split('/', 1)[1].lower()}_approved_behavior_anchor"
    return (
        value.value == expected
        and value.source_rule == expected_rule
        and f"player_id={player_id}" in value.evidence_keys
        and f"approved_{action}_anchor={expected}" in value.evidence_keys
        and "names_are_display_only;exact_player_id_authors_the_anchor" in value.evidence_keys
    )


def _is_approved_intangibles_floor(
    evidence: PlayerEvidence,
    field_key: str,
    value: RuleValue,
) -> bool:
    if field_key != "Attributes/INTANGIBLES" or value.value != 25:
        return False
    if value.source_rule != "derive_attribute_intangibles":
        return False
    raw_vorp = _float(evidence.advanced.get("vorp"))
    return raw_vorp is None or raw_vorp <= 0.0


def _is_documented_field_fallback(value: RuleValue, live_paths: tuple[str, ...]) -> bool:
    if not live_paths or not value.source_rule.endswith("_field_specific_context_substitute"):
        return False
    required_prefix_groups = (
        ("unavailable_direct_source=",),
        ("substitute_source=", "substitute_evidence="),
        ("validity=", "field_validity="),
    )
    return all(
        any(key.startswith(prefix) for key in value.evidence_keys for prefix in prefixes)
        for prefixes in required_prefix_groups
    )


def _source_path_has_numeric_value(evidence: PlayerEvidence, path: str) -> bool:
    namespace, sep, key = path.partition(".")
    if not sep:
        return False
    source = getattr(evidence, namespace, None)
    if not isinstance(source, dict) or key not in source:
        return False
    return _float(source.get(key)) is not None


def _documented_owner_feature_has_numeric_value(
    evidence: PlayerEvidence,
    owner_module: str,
    path: str,
) -> bool:
    if owner_module == "offense":
        if path.startswith("derived."):
            helper = getattr(offense, "_derived_value", None)
            return callable(helper) and _float(helper(evidence, path.split(".", 1)[1])) is not None
        if path.startswith("role."):
            helper = getattr(offense, "_role_value", None)
            return callable(helper) and _float(helper(evidence, path.split(".", 1)[1])) is not None
    if owner_module == "defense" and path.startswith(("crafted.", "derived.")):
        helper = getattr(defense, "_feature_value", None)
        return callable(helper) and _float(helper(evidence, path)) is not None
    return False


def _required_rule_fields(active_field_keys: set[str] | None) -> set[str]:
    requested = set(PLAYER_RULE_SCHEME) if active_field_keys is None else {
        key for key in active_field_keys if key.startswith(("Attributes/", "Tendencies/"))
    }
    return requested - set(_EXTERNAL_RULE_OWNERS)


def _has_required_games_played(evidence: PlayerEvidence) -> bool:
    games = _float(evidence.per_game.get("g"))
    return games is not None and games > 0.0


def _same_season_same_league_rows(evidence: PlayerEvidence, rows: Any) -> tuple[dict[str, Any], ...]:
    context = player_era_context(evidence)
    if not context.league or int(evidence.season) <= 0:
        return ()
    cache_key = (id(rows), int(evidence.season), context.league)
    cached = _COMPARISON_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    selected: list[dict[str, Any]] = []
    for row in tuple(rows or ()):
        if not isinstance(row, dict):
            continue
        row_season = _row_context_value(row, "season", "player_season_info.season", "season_info.season")
        row_league = _row_context_value(row, "player_season_info.lg", "season_info.lg", "lg")
        if _int_round(row_season) != int(evidence.season):
            continue
        if str(row_league or "").strip().upper() != context.league:
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


def _source_path_has_value(evidence: PlayerEvidence, path: str) -> bool:
    namespace, sep, key = path.partition(".")
    if not sep:
        return False
    source = getattr(evidence, namespace, None)
    if not isinstance(source, dict) or key not in source:
        return False
    value = source.get(key)
    return value is not None and value != ""


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
