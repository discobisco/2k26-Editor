from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

import player_rules_athleticism as athleticism
import player_rules_defense as defense
import player_rules_mental as mental
import player_rules_offense as offense
import player_rules_rebounding as rebounding
from player_evidence import PlayerEvidence
from stat_neighbor_framework import PositionSelection, hot_zone_neutral_values, load_latest_stat_neighbor_model, select_positions_from_evidence


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


@dataclass(frozen=True)
class PlayerRuleSpec:
    field_key: str
    section: str
    group: str
    module: str
    function: str


_RULE_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    ('Attributes/3POINT', 'Attributes', 'Offense', 'offense', 'derive_attribute_field_3point'),
    ('Attributes/BALLCONTROL', 'Attributes', 'Offense', 'offense', 'derive_attribute_ballcontrol'),
    ('Attributes/CLOSESHOT', 'Attributes', 'Offense', 'offense', 'derive_attribute_closeshot'),
    ('Attributes/DRAWFOUL', 'Attributes', 'Offense', 'offense', 'derive_attribute_drawfoul'),
    ('Attributes/DRIVINGDUNK', 'Attributes', 'Offense', 'offense', 'derive_attribute_drivingdunk'),
    ('Attributes/DRIVINGLAYUP', 'Attributes', 'Offense', 'offense', 'derive_attribute_drivinglayup'),
    ('Attributes/FREETHROW', 'Attributes', 'Offense', 'offense', 'derive_attribute_freethrow'),
    ('Attributes/MIDRANGE', 'Attributes', 'Offense', 'offense', 'derive_attribute_midrange'),
    ('Attributes/OFFENSIVECONSISTENCY', 'Attributes', 'Offense', 'offense', 'derive_attribute_offensiveconsistency'),
    ('Attributes/PASSACCURACY', 'Attributes', 'Offense', 'offense', 'derive_attribute_passaccuracy'),
    ('Attributes/PASSIQ', 'Attributes', 'Offense', 'offense', 'derive_attribute_passiq'),
    ('Attributes/PASSVISION', 'Attributes', 'Offense', 'offense', 'derive_attribute_passvision'),
    ('Attributes/POSTFADE', 'Attributes', 'Offense', 'offense', 'derive_attribute_postfade'),
    ('Attributes/POSTHOOK', 'Attributes', 'Offense', 'offense', 'derive_attribute_posthook'),
    ('Attributes/POSTCONTROL', 'Attributes', 'Offense', 'offense', 'derive_attribute_postcontrol'),
    ('Attributes/IQSHOT', 'Attributes', 'Offense', 'offense', 'derive_attribute_iqshot'),
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
    ('Attributes/CACHCEDOVR', 'Attributes', 'Misc', 'mental', 'derive_attribute_cachcedovr'),
    ('Attributes/LATERALQUICKNESS', 'Attributes', 'Misc', 'defense', 'derive_attribute_lateralquickness'),
    ('Attributes/MAXOVR', 'Attributes', 'Misc', 'mental', 'derive_attribute_maxovr'),
    ('Attributes/MINOVR', 'Attributes', 'Misc', 'mental', 'derive_attribute_minovr'),
    ('Attributes/PICKANDROLLDEFENSEIQ', 'Attributes', 'Misc', 'defense', 'derive_attribute_pickandrolldefenseiq'),
    ('Attributes/POSTFADEAWAY', 'Attributes', 'Misc', 'mental', 'derive_attribute_postfadeaway'),
    ('Attributes/POTENTIAL', 'Attributes', 'Misc', 'mental', 'derive_attribute_potential'),
    ('Attributes/CONTESTSHOT', 'Attributes', 'Misc', 'defense', 'derive_attribute_contestshot'),
    ('Attributes/DEFENSEREBOUND', 'Attributes', 'Rebounding', 'rebounding', 'derive_attribute_defenserebound'),
    ('Attributes/OFFENSIVEREBOUND', 'Attributes', 'Rebounding', 'rebounding', 'derive_attribute_offensiverebound'),
    ('Tendencies/CONTESTEDJUMPER3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumper3point'),
    ('Tendencies/CONTESTEDJUMPERMID', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermid'),
    ('Tendencies/CONTESTEDJUMPERMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_contestedjumpermidrange'),
    ('Tendencies/DRIVEPULLUP3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_drivepullup3point'),
    ('Tendencies/DRIVEPULLUPMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_drivepullupmidrange'),
    ('Tendencies/3POINTOFFSCREENSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointoffscreenshot'),
    ('Tendencies/MIDOFFSCREENSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midoffscreenshot'),
    ('Tendencies/3POINTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointshot'),
    ('Tendencies/3POINTCENTERSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcentershot'),
    ('Tendencies/3POINTLEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointleftshot'),
    ('Tendencies/3POINTCENTERLEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcenterleftshot'),
    ('Tendencies/3POINTRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointrightshot'),
    ('Tendencies/3POINTCENTERRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointcenterrightshot'),
    ('Tendencies/CLOSESHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closeshot'),
    ('Tendencies/CLOSELEFTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closeleftshot'),
    ('Tendencies/CLOSEMIDDLESHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closemiddleshot'),
    ('Tendencies/CLOSERIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_closerightshot'),
    ('Tendencies/MIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midshot'),
    ('Tendencies/CENTERMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centermidshot'),
    ('Tendencies/LEFTMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_leftmidshot'),
    ('Tendencies/CENTERLEFTMIDSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centerleftmidshot'),
    ('Tendencies/MIDRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midrightshot'),
    ('Tendencies/CENTERMIDRIGHTSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_centermidrightshot'),
    ('Tendencies/BASKETUNDERSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_basketundershot'),
    ('Tendencies/SPINJUMPER', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_spinjumper'),
    ('Tendencies/3POINTSPOTUPSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_field_3pointspotupshot'),
    ('Tendencies/MIDSPOTUPSHOT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_midspotupshot'),
    ('Tendencies/STEPTHROUGH', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepthrough'),
    ('Tendencies/STEPBACKJUMPER3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumper3point'),
    ('Tendencies/STEPBACKJUMPERMIDRANGE', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_stepbackjumpermidrange'),
    ('Tendencies/TRANSITIONPULLUP3POINT', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_transitionpullup3point'),
    ('Tendencies/USEGLASS', 'Tendencies', 'Jump Shooting', 'offense', 'derive_tendency_useglass'),
    ('Tendencies/ALLEYOOP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_alleyoop'),
    ('Tendencies/CRASH', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_crash'),
    ('Tendencies/DRIVINGDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_drivingdunk'),
    ('Tendencies/DRIVINGLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_drivinglayup'),
    ('Tendencies/EUROSTEPLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_eurosteplayup'),
    ('Tendencies/FLASHYDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_flashydunk'),
    ('Tendencies/FLOATER', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_floater'),
    ('Tendencies/HOPSTEPLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_hopsteplayup'),
    ('Tendencies/PUTBACK', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_putback'),
    ('Tendencies/PUTBACKDUNK', 'Tendencies', 'Layups And Dunks', 'rebounding', 'derive_tendency_putbackdunk'),
    ('Tendencies/SPINLAYUP', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_spinlayup'),
    ('Tendencies/STANDINGDUNK', 'Tendencies', 'Layups And Dunks', 'offense', 'derive_tendency_standingdunk'),
    ('Tendencies/NOSETUPDRIBBLE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_nosetupdribble'),
    ('Tendencies/SETUPWITHHESITATION', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_setupwithhesitation'),
    ('Tendencies/SETUPWITHSIZEUP', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_setupwithsizeup'),
    ('Tendencies/STEPBACKJUMPERMID', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_stepbackjumpermid'),
    ('Tendencies/TRIPLETHREATIDLE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatidle'),
    ('Tendencies/TRIPLETHREATJABSTEP', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatjabstep'),
    ('Tendencies/TRIPLETHREATPUMPFAKE', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_triplethreatpumpfake'),
    ('Tendencies/THREATTRIPLESHOT', 'Tendencies', 'Drive Setup', 'offense', 'derive_tendency_threattripleshot'),
    ('Tendencies/ATTACKSTRONGONDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_attackstrongondrive'),
    ('Tendencies/DRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drive'),
    ('Tendencies/DRIVEPULLUPMID', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivepullupmid'),
    ('Tendencies/DRIVERIGHT', 'Tendencies', 'Driving', 'offense', 'derive_tendency_driveright'),
    ('Tendencies/DRIVINGBEHINDTHEBACK', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingbehindtheback'),
    ('Tendencies/DRIBBLECROSSOVER', 'Tendencies', 'Driving', 'offense', 'derive_tendency_dribblecrossover'),
    ('Tendencies/DRIVINGDOUBLECROSSOVER', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingdoublecrossover'),
    ('Tendencies/DRIVINGDRIBBLEHESITATION', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingdribblehesitation'),
    ('Tendencies/DRIVINGHALFSPIN', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivinghalfspin'),
    ('Tendencies/DRIVINGINANDOUT', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivinginandout'),
    ('Tendencies/DRIBBLESPIN', 'Tendencies', 'Driving', 'offense', 'derive_tendency_dribblespin'),
    ('Tendencies/DRIVINGSTEPBACK', 'Tendencies', 'Driving', 'offense', 'derive_tendency_drivingstepback'),
    ('Tendencies/NODRIVINGDRIBBLEMOVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_nodrivingdribblemove'),
    ('Tendencies/OFFSCREENDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_offscreendrive'),
    ('Tendencies/SPOTUPDRIVE', 'Tendencies', 'Driving', 'offense', 'derive_tendency_spotupdrive'),
    ('Tendencies/ALLEYOOPPASS', 'Tendencies', 'Passing', 'offense', 'derive_tendency_alleyooppass'),
    ('Tendencies/DISHTOOPENMAN', 'Tendencies', 'Passing', 'offense', 'derive_tendency_dishtoopenman'),
    ('Tendencies/FLASHYPASS', 'Tendencies', 'Passing', 'offense', 'derive_tendency_flashypass'),
    ('Tendencies/POSTAGGRESSIVEBACKDOWN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postaggressivebackdown'),
    ('Tendencies/POSTBACKDOWN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postbackdown'),
    ('Tendencies/POSTDRIVE', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postdrive'),
    ('Tendencies/POSTDROPSTEP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postdropstep'),
    ('Tendencies/POSTFACEUP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfaceup'),
    ('Tendencies/POSTFADELEFT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfadeleft'),
    ('Tendencies/POSTFADERIGHT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postfaderight'),
    ('Tendencies/POSTHOOKLEFT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthookleft'),
    ('Tendencies/POSTHOOKRIGHT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthookright'),
    ('Tendencies/HOPPOSTSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_hoppostshot'),
    ('Tendencies/POSTHOPSTEP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_posthopstep'),
    ('Tendencies/POSTSHIMMYSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postshimmyshot'),
    ('Tendencies/POSTSPIN', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postspin'),
    ('Tendencies/POSTSTEPBACKSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_poststepbackshot'),
    ('Tendencies/POSTUP', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postup'),
    ('Tendencies/POSTUPANDUNDER', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_postupandunder'),
    ('Tendencies/FROMPOSTSHOT', 'Tendencies', 'Post Game', 'offense', 'derive_tendency_frompostshot'),
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
    ('Tendencies/CENTER3', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_center3'),
    ('Tendencies/CLOSELEFT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_closeleft'),
    ('Tendencies/CLOSEMIDDLE', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_closemiddle'),
    ('Tendencies/CLOSERIGHT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_closeright'),
    ('Tendencies/LEFT3', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_left3'),
    ('Tendencies/MIDRANGECENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_midrangecenter'),
    ('Tendencies/MIDRANGELEFT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_midrangeleft'),
    ('Tendencies/MIDRANGELEFTCENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_midrangeleftcenter'),
    ('Tendencies/MIDRANGERIGHT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_midrangeright'),
    ('Tendencies/MIDRANGERIGHTCENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_midrangerightcenter'),
    ('Tendencies/RIGHT3', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_right3'),
    ('Tendencies/3CENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_field_3center'),
    ('Tendencies/3LEFT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_field_3left'),
    ('Tendencies/3LEFTCENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_field_3leftcenter'),
    ('Tendencies/3RIGHT', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_field_3right'),
    ('Tendencies/3RIGHTCENTER', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_field_3rightcenter'),
    ('Tendencies/UNDERBASKET', 'Tendencies', 'Hot Zones', 'offense', 'derive_tendency_underbasket'),
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
_FIRST_THREE_POINT_SEASON = 1969
_THREE_POINT_HOT_ZONE_FIELDS = {
    "CENTER3",
    "LEFT3",
    "RIGHT3",
    "3CENTER",
    "3LEFT",
    "3LEFTCENTER",
    "3RIGHT",
    "3RIGHTCENTER",
}


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
    if birth:
        _add_profile(values, "Vitals/BIRTHYEAR", birth.year, "profile_sql_birth_date", "player_info.birth_date")
        _add_profile(values, "Vitals/BIRTHMONTH", birth.month, "profile_sql_birth_date", "player_info.birth_date")
        _add_profile(values, "Vitals/BIRTHDAY", birth.day, "profile_sql_birth_date", "player_info.birth_date")
    elif (age := _int_round(evidence.season_info.get("age"))) is not None:
        _add_profile(values, "Vitals/BIRTHYEAR", int(evidence.season) - age, "profile_sql_age_estimate", "season_info.age")

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
    if not positions.primary:
        return PlayerRuleResult(values={})

    fixed_pre_1969_fields = _pre_1969_three_point_field_keys(evidence, active_field_keys)
    formula_values = derive_formula_rule_values(
        evidence,
        league_player_rows=league_player_rows,
        excluded_field_keys=fixed_pre_1969_fields,
    )
    try:
        model = load_latest_stat_neighbor_model()
    except FileNotFoundError:
        model = None
    neighbor_values = derive_neighbor_rule_values(evidence, positions, model=model)
    if fixed_pre_1969_fields:
        neighbor_values = {key: value for key, value in neighbor_values.items() if key not in fixed_pre_1969_fields}
    if active_field_keys is not None:
        formula_values = {key: value for key, value in formula_values.items() if key in active_field_keys}
        neighbor_values = {key: value for key, value in neighbor_values.items() if key in active_field_keys}
    values = merge_rule_sources(formula_values=formula_values, neighbor_values=neighbor_values)

    for field_key in fixed_pre_1969_fields:
        values[field_key] = RuleValue(
            value=25 if field_key.startswith("Attributes/") else 0,
            source_rule="fixed_pre_1969_no_three_point_line",
            evidence_keys=("season_info.season", f"season={_evidence_season(evidence)}", "pre_1969_no_three_point_line"),
        )

    if active_field_keys is None or "Attributes/INTANGIBLES" in active_field_keys:
        values["Attributes/INTANGIBLES"] = RuleValue(
            value=25,
            source_rule="fixed_intangibles_25",
            evidence_keys=("fixed_intangibles_25",),
        )

    ft_percent = _float(evidence.per_game.get("ft_percent"))
    if ft_percent is not None:
        values["Attributes/FREETHROW"] = RuleValue(
            value=max(25, min(99, int(round(ft_percent * 100.0)))),
            source_rule="ft_percent_direct",
            evidence_keys=("player_per_game.ft_percent", f"ft_percent={ft_percent:.6f}"),
        )
    for key, suggestion in hot_zone_neutral_values().items():
        values.setdefault(key, RuleValue(value=suggestion.value, source_rule=suggestion.source_rule, evidence_keys=suggestion.evidence_keys))
    return PlayerRuleResult(values=values)


def _is_pre_1969(evidence: PlayerEvidence) -> bool:
    season = _evidence_season(evidence)
    return season is not None and season < _FIRST_THREE_POINT_SEASON


def _pre_1969_three_point_field_keys(evidence: PlayerEvidence, active_field_keys: set[str] | None) -> set[str]:
    if not _is_pre_1969(evidence):
        return set()
    return {
        field_key
        for field_key in PLAYER_RULE_SCHEME
        if _is_three_point_rule_field(field_key) and (active_field_keys is None or field_key in active_field_keys)
    }


def _evidence_season(evidence: PlayerEvidence) -> int | None:
    season = _int_round(getattr(evidence, "season", None))
    if season is not None:
        return season
    return _int_round(getattr(evidence, "season_info", {}).get("season"))


def _is_three_point_rule_field(field_key: str) -> bool:
    section, _sep, name = field_key.partition("/")
    if field_key == "Attributes/3POINT":
        return True
    return section == "Tendencies" and ("3POINT" in name or name in _THREE_POINT_HOT_ZONE_FIELDS)


def derive_formula_rule_values(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Any = (),
    excluded_field_keys: set[str] | None = None,
) -> dict[str, RuleValue]:
    values: dict[str, RuleValue] = {}
    rows = tuple(league_player_rows or ())
    excluded = excluded_field_keys or set()
    for field_key, spec in PLAYER_RULE_SCHEME.items():
        if field_key in excluded:
            continue
        if field_key == "Attributes/FREETHROW":
            ft_percent = _float(evidence.per_game.get("ft_percent"))
            if ft_percent is None:
                continue
            values[field_key] = RuleValue(
                value=max(25, min(99, int(round(ft_percent * 100.0)))),
                source_rule="derive_attribute_freethrow",
                evidence_keys=("per_game.ft_percent", f"ft_percent={ft_percent:.6f}"),
            )
            continue
        rule = getattr(_RULE_MODULES[spec.module], spec.function)
        result = _call_formula_rule(rule, evidence, league_player_rows=rows)
        value = _coerce_formula_rule_value(field_key, result)
        if value is None:
            continue
        if not _formula_has_live_input(evidence, value.evidence_keys):
            continue
        if not rows:
            continue
        values[field_key] = value
    return values


def derive_neighbor_rule_values(evidence: PlayerEvidence, positions: PositionSelection, *, model: Any = None) -> dict[str, RuleValue]:
    if model is None:
        try:
            model = load_latest_stat_neighbor_model()
        except FileNotFoundError:
            return {}
    suggestions = model.suggestions_for_evidence(evidence=evidence, positions=positions)
    return {
        key: RuleValue(value=suggestion.value, source_rule=suggestion.source_rule, evidence_keys=suggestion.evidence_keys)
        for key, suggestion in suggestions.items()
    }


def merge_rule_sources(*, formula_values: dict[str, RuleValue], neighbor_values: dict[str, RuleValue]) -> dict[str, RuleValue]:
    values: dict[str, RuleValue] = {}
    for field_key in sorted(set(formula_values) | set(neighbor_values)):
        merged = _merge_one_rule_value(field_key, formula=formula_values.get(field_key), neighbor=neighbor_values.get(field_key))
        if merged is not None:
            values[field_key] = merged
    return values


def _merge_one_rule_value(field_key: str, *, formula: RuleValue | None, neighbor: RuleValue | None) -> RuleValue | None:
    if formula is None and neighbor is None:
        return None
    if formula is not None and neighbor is None:
        return RuleValue(
            value=formula.value,
            source_rule="hybrid_formula_only",
            evidence_keys=formula.evidence_keys + (f"formula_value={formula.value}", f"formula_source={formula.source_rule}"),
        )
    if neighbor is not None and formula is None:
        return RuleValue(
            value=neighbor.value,
            source_rule="hybrid_neighbor_only",
            evidence_keys=neighbor.evidence_keys + (f"neighbor_value={neighbor.value}", f"neighbor_source={neighbor.source_rule}"),
        )
    assert formula is not None and neighbor is not None
    formula_number = _float(formula.value)
    neighbor_number = _float(neighbor.value)
    if formula_number is None or neighbor_number is None:
        return RuleValue(
            value=neighbor.value,
            source_rule="hybrid_neighbor_preferred_non_numeric",
            evidence_keys=formula.evidence_keys + neighbor.evidence_keys + (
                f"formula_value={formula.value}",
                f"neighbor_value={neighbor.value}",
                f"formula_source={formula.source_rule}",
                f"neighbor_source={neighbor.source_rule}",
                "merge_policy=neighbor_preferred_non_numeric",
            ),
        )
    neighbor_weight = _neighbor_merge_weight(neighbor)
    formula_weight = 1.0 - neighbor_weight
    merged = int(round(formula_number * formula_weight + neighbor_number * neighbor_weight))
    merged = _clamp_rule_value(field_key, merged)
    return RuleValue(
        value=merged,
        source_rule="hybrid_formula_neighbor_merge",
        evidence_keys=formula.evidence_keys + neighbor.evidence_keys + (
            f"formula_value={formula.value}",
            f"neighbor_value={neighbor.value}",
            f"formula_source={formula.source_rule}",
            f"neighbor_source={neighbor.source_rule}",
            f"merge_policy=formula_weight_{formula_weight:.2f}_neighbor_weight_{neighbor_weight:.2f}",
        ),
    )


def _neighbor_merge_weight(neighbor: RuleValue) -> float:
    common_features = 0
    for key in neighbor.evidence_keys:
        if key.startswith("common_features="):
            try:
                common_features = max(common_features, int(float(key.split("=", 1)[1])))
            except ValueError:
                pass
    if common_features >= 2:
        return 0.70
    if any(key == "field_source=exact_player_match_rows" for key in neighbor.evidence_keys):
        return 0.30
    return 0.50


def _clamp_rule_value(field_key: str, value: int) -> int:
    if field_key.startswith("Attributes/"):
        return max(25, min(99, value))
    if field_key.startswith("Tendencies/"):
        return max(0, min(100, value))
    return value


def _call_formula_rule(rule: Callable[..., Any], evidence: PlayerEvidence, *, league_player_rows: Any) -> Any:
    try:
        return rule(evidence, league_player_rows=league_player_rows)
    except TypeError:
        return rule(evidence)


def _coerce_formula_rule_value(field_key: str, result: Any) -> RuleValue | None:
    if result is None:
        return None
    if isinstance(result, RuleValue):
        return result
    if not isinstance(result, dict) or "value" not in result:
        return None
    value = result.get("value")
    if value is None or value == "":
        return None
    if isinstance(value, (int, str)):
        stored: int | str = value
    else:
        rounded = _int_round(value)
        if rounded is None:
            return None
        stored = rounded
    if isinstance(stored, int):
        stored = _clamp_rule_value(field_key, stored)
    source_rule = str(result.get("source_rule") or "formula_rule")
    evidence_keys = tuple(str(key) for key in result.get("evidence_keys") or ())
    return RuleValue(value=stored, source_rule=source_rule, evidence_keys=evidence_keys)


def _formula_has_live_input(evidence: PlayerEvidence, evidence_keys: tuple[str, ...]) -> bool:
    for key in evidence_keys:
        if "=" in key:
            continue
        if _source_path_has_value(evidence, key):
            return True
    return False


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
        return float(value)
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
    "derive_matched_formula_rule_values",
    "derive_neighbor_rule_values",
    "derive_player_profile_values",
    "derive_player_rule_values",
    "merge_rule_sources",
]
