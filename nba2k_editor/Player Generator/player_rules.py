from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from player_evidence import PlayerEvidence

ATTRIBUTE_FIELD_GROUPS: dict[str, str] = {'Attributes/3POINT': 'Offense',
 'Attributes/ACCELERATION': 'Athleticism',
 'Attributes/AGILITY': 'Athleticism',
 'Attributes/BACKDURABILITY': 'Durability',
 'Attributes/BALLCONTROL': 'Offense',
 'Attributes/BLOCK': 'Defense',
 'Attributes/CACHCEDOVR': 'Misc',
 'Attributes/CLOSESHOT': 'Offense',
 'Attributes/CONTESTSHOT': 'Misc',
 'Attributes/DEFENSECONSISTENCY': 'Defense',
 'Attributes/DEFENSEREBOUND': 'Rebounding',
 'Attributes/DRAWFOUL': 'Offense',
 'Attributes/DRIVINGDUNK': 'Offense',
 'Attributes/DRIVINGLAYUP': 'Offense',
 'Attributes/FREETHROW': 'Offense',
 'Attributes/HANDS': 'Mental',
 'Attributes/HEADDURABILITY': 'Durability',
 'Attributes/HELPDEFENSE': 'Defense',
 'Attributes/HUSTLE': 'Mental',
 'Attributes/INTANGIBLES': 'Mental',
 'Attributes/INTERIORDEFENSE': 'Defense',
 'Attributes/IQSHOT': 'Offense',
 'Attributes/LATERALQUICKNESS': 'Misc',
 'Attributes/LEFTANKLEDURABILITY': 'Durability',
 'Attributes/LEFTELBOWDURABILITY': 'Durability',
 'Attributes/LEFTFOOTDURABILITY': 'Durability',
 'Attributes/LEFTHANDDURABILITY': 'Durability',
 'Attributes/LEFTHIPDURABILITY': 'Durability',
 'Attributes/LEFTKNEEDURABILITY': 'Durability',
 'Attributes/LEFTSHOULDERDURABILITY': 'Durability',
 'Attributes/MAXOVR': 'Misc',
 'Attributes/MIDRANGE': 'Offense',
 'Attributes/MINOVR': 'Misc',
 'Attributes/MISCDURABILITY': 'Durability',
 'Attributes/NECKDURABILITY': 'Durability',
 'Attributes/OFFENSIVECONSISTENCY': 'Offense',
 'Attributes/OFFENSIVEREBOUND': 'Rebounding',
 'Attributes/PASSACCURACY': 'Offense',
 'Attributes/PASSIQ': 'Offense',
 'Attributes/PASSPERCEPTION': 'Defense',
 'Attributes/PASSVISION': 'Offense',
 'Attributes/PERIMETERDEFENSE': 'Defense',
 'Attributes/PICKANDROLLDEFENSEIQ': 'Misc',
 'Attributes/POSTCONTROL': 'Offense',
 'Attributes/POSTFADE': 'Offense',
 'Attributes/POSTFADEAWAY': 'Misc',
 'Attributes/POSTHOOK': 'Offense',
 'Attributes/POTENTIAL': 'Misc',
 'Attributes/RIGHTANKLEDURABILITY': 'Durability',
 'Attributes/RIGHTELBOWDURABILITY': 'Durability',
 'Attributes/RIGHTFOOTDURABILITY': 'Durability',
 'Attributes/RIGHTHANDDURABILITY': 'Durability',
 'Attributes/RIGHTHIPDURABILITY': 'Durability',
 'Attributes/RIGHTKNEEDURABILITY': 'Durability',
 'Attributes/RIGHTSHOULDERDURABILITY': 'Durability',
 'Attributes/SPEED': 'Athleticism',
 'Attributes/SPEEDWITHBALL': 'Athleticism',
 'Attributes/STAMINA': 'Athleticism',
 'Attributes/STANDINGDUNK': 'Offense',
 'Attributes/STEAL': 'Defense',
 'Attributes/STRENGTH': 'Athleticism',
 'Attributes/VERTICAL': 'Athleticism'}

TENDENCY_FIELD_GROUPS: dict[str, str] = {'Tendencies/3CENTER': 'Hot Zones',
 'Tendencies/3LEFT': 'Hot Zones',
 'Tendencies/3LEFTCENTER': 'Hot Zones',
 'Tendencies/3POINTCENTERLEFTSHOT': 'Jump Shooting',
 'Tendencies/3POINTCENTERRIGHTSHOT': 'Jump Shooting',
 'Tendencies/3POINTCENTERSHOT': 'Jump Shooting',
 'Tendencies/3POINTLEFTSHOT': 'Jump Shooting',
 'Tendencies/3POINTOFFSCREENSHOT': 'Jump Shooting',
 'Tendencies/3POINTRIGHTSHOT': 'Jump Shooting',
 'Tendencies/3POINTSHOT': 'Jump Shooting',
 'Tendencies/3POINTSPOTUPSHOT': 'Jump Shooting',
 'Tendencies/3RIGHT': 'Hot Zones',
 'Tendencies/3RIGHTCENTER': 'Hot Zones',
 'Tendencies/ALLEYOOP': 'Layups And Dunks',
 'Tendencies/ALLEYOOPPASS': 'Passing',
 'Tendencies/ATTACKSTRONGONDRIVE': 'Driving',
 'Tendencies/BASKETUNDERSHOT': 'Jump Shooting',
 'Tendencies/BLOCKSHOT': 'Defense',
 'Tendencies/CENTER3': 'Hot Zones',
 'Tendencies/CENTERLEFTMIDSHOT': 'Jump Shooting',
 'Tendencies/CENTERMIDRIGHTSHOT': 'Jump Shooting',
 'Tendencies/CENTERMIDSHOT': 'Jump Shooting',
 'Tendencies/CLOSELEFT': 'Hot Zones',
 'Tendencies/CLOSELEFTSHOT': 'Jump Shooting',
 'Tendencies/CLOSEMIDDLE': 'Hot Zones',
 'Tendencies/CLOSEMIDDLESHOT': 'Jump Shooting',
 'Tendencies/CLOSERIGHT': 'Hot Zones',
 'Tendencies/CLOSERIGHTSHOT': 'Jump Shooting',
 'Tendencies/CLOSESHOT': 'Jump Shooting',
 'Tendencies/CONTESTEDJUMPER3POINT': 'Jump Shooting',
 'Tendencies/CONTESTEDJUMPERMID': 'Jump Shooting',
 'Tendencies/CONTESTEDJUMPERMIDRANGE': 'Jump Shooting',
 'Tendencies/CONTESTSHOT': 'Defense',
 'Tendencies/CRASH': 'Layups And Dunks',
 'Tendencies/DISHTOOPENMAN': 'Passing',
 'Tendencies/DRIBBLECROSSOVER': 'Driving',
 'Tendencies/DRIBBLESPIN': 'Driving',
 'Tendencies/DRIVE': 'Driving',
 'Tendencies/DRIVEPULLUP3POINT': 'Jump Shooting',
 'Tendencies/DRIVEPULLUPMID': 'Driving',
 'Tendencies/DRIVEPULLUPMIDRANGE': 'Jump Shooting',
 'Tendencies/DRIVERIGHT': 'Driving',
 'Tendencies/DRIVINGBEHINDTHEBACK': 'Driving',
 'Tendencies/DRIVINGDOUBLECROSSOVER': 'Driving',
 'Tendencies/DRIVINGDRIBBLEHESITATION': 'Driving',
 'Tendencies/DRIVINGDUNK': 'Layups And Dunks',
 'Tendencies/DRIVINGHALFSPIN': 'Driving',
 'Tendencies/DRIVINGINANDOUT': 'Driving',
 'Tendencies/DRIVINGLAYUP': 'Layups And Dunks',
 'Tendencies/DRIVINGSTEPBACK': 'Driving',
 'Tendencies/EUROSTEPLAYUP': 'Layups And Dunks',
 'Tendencies/FLASHYDUNK': 'Layups And Dunks',
 'Tendencies/FLASHYPASS': 'Passing',
 'Tendencies/FLOATER': 'Layups And Dunks',
 'Tendencies/FOUL': 'Defense',
 'Tendencies/FROMPOSTSHOT': 'Post Game',
 'Tendencies/HARDFOUL': 'Defense',
 'Tendencies/HOPPOSTSHOT': 'Post Game',
 'Tendencies/HOPSTEPLAYUP': 'Layups And Dunks',
 'Tendencies/ISOVSAVERAGEDEFENDER': 'Freelance',
 'Tendencies/ISOVSELITEDEFENDER': 'Freelance',
 'Tendencies/ISOVSGOODDEFENDER': 'Freelance',
 'Tendencies/ISOVSPOORDEFENDER': 'Freelance',
 'Tendencies/LEFT3': 'Hot Zones',
 'Tendencies/LEFTMIDSHOT': 'Jump Shooting',
 'Tendencies/MIDOFFSCREENSHOT': 'Jump Shooting',
 'Tendencies/MIDRANGECENTER': 'Hot Zones',
 'Tendencies/MIDRANGELEFT': 'Hot Zones',
 'Tendencies/MIDRANGELEFTCENTER': 'Hot Zones',
 'Tendencies/MIDRANGERIGHT': 'Hot Zones',
 'Tendencies/MIDRANGERIGHTCENTER': 'Hot Zones',
 'Tendencies/MIDRIGHTSHOT': 'Jump Shooting',
 'Tendencies/MIDSHOT': 'Jump Shooting',
 'Tendencies/MIDSPOTUPSHOT': 'Jump Shooting',
 'Tendencies/NODRIVINGDRIBBLEMOVE': 'Driving',
 'Tendencies/NOSETUPDRIBBLE': 'Drive Setup',
 'Tendencies/OFFSCREENDRIVE': 'Driving',
 'Tendencies/ONBALLSTEAL': 'Defense',
 'Tendencies/PASSINTERCEPTION': 'Defense',
 'Tendencies/PLAYDISCIPLINE': 'Freelance',
 'Tendencies/POSTAGGRESSIVEBACKDOWN': 'Post Game',
 'Tendencies/POSTBACKDOWN': 'Post Game',
 'Tendencies/POSTDRIVE': 'Post Game',
 'Tendencies/POSTDROPSTEP': 'Post Game',
 'Tendencies/POSTFACEUP': 'Post Game',
 'Tendencies/POSTFADELEFT': 'Post Game',
 'Tendencies/POSTFADERIGHT': 'Post Game',
 'Tendencies/POSTHOOKLEFT': 'Post Game',
 'Tendencies/POSTHOOKRIGHT': 'Post Game',
 'Tendencies/POSTHOPSTEP': 'Post Game',
 'Tendencies/POSTSHIMMYSHOT': 'Post Game',
 'Tendencies/POSTSPIN': 'Post Game',
 'Tendencies/POSTSTEPBACKSHOT': 'Post Game',
 'Tendencies/POSTUP': 'Post Game',
 'Tendencies/POSTUPANDUNDER': 'Post Game',
 'Tendencies/PUTBACK': 'Layups And Dunks',
 'Tendencies/PUTBACKDUNK': 'Layups And Dunks',
 'Tendencies/RIGHT3': 'Hot Zones',
 'Tendencies/ROLLVSPOP': 'Freelance',
 'Tendencies/SETUPWITHHESITATION': 'Drive Setup',
 'Tendencies/SETUPWITHSIZEUP': 'Drive Setup',
 'Tendencies/SHOT': 'Tendencies',
 'Tendencies/SPINJUMPER': 'Jump Shooting',
 'Tendencies/SPINLAYUP': 'Layups And Dunks',
 'Tendencies/SPOTUPDRIVE': 'Driving',
 'Tendencies/STANDINGDUNK': 'Layups And Dunks',
 'Tendencies/STEPBACKJUMPER3POINT': 'Jump Shooting',
 'Tendencies/STEPBACKJUMPERMID': 'Drive Setup',
 'Tendencies/STEPBACKJUMPERMIDRANGE': 'Jump Shooting',
 'Tendencies/STEPTHROUGH': 'Jump Shooting',
 'Tendencies/TAKECHARGE': 'Defense',
 'Tendencies/THREATTRIPLESHOT': 'Drive Setup',
 'Tendencies/TOUCHES': 'Freelance',
 'Tendencies/TRANSITIONPULLUP3POINT': 'Jump Shooting',
 'Tendencies/TRANSITIONSPOTUP': 'Freelance',
 'Tendencies/TRIPLETHREATIDLE': 'Drive Setup',
 'Tendencies/TRIPLETHREATJABSTEP': 'Drive Setup',
 'Tendencies/TRIPLETHREATPUMPFAKE': 'Drive Setup',
 'Tendencies/UNDERBASKET': 'Hot Zones',
 'Tendencies/USEGLASS': 'Jump Shooting'}

ATTRIBUTE_FIELDS: set[str] = set(ATTRIBUTE_FIELD_GROUPS)
TENDENCY_FIELDS: set[str] = set(TENDENCY_FIELD_GROUPS)
PROFILE_FIELDS: set[str] = {
    "Vitals/FIRSTNAME",
    "Vitals/LASTNAME",
    "Vitals/HEIGHT",
    "Vitals/HEIGHTCM",
    "Vitals/WEIGHT",
    "Vitals/WEIGHTKG",
    "Vitals/POSITION",
    "Vitals/COLLEGEFROM",
    "Vitals/YEARSPRO",
}

_ATTRIBUTE_RANGE = (25, 99)
_TENDENCY_RANGE = (0, 100)


@dataclass(frozen=True)
class RuleValue:
    field: str
    domain: str
    value: int
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerRuleResult:
    values: dict[str, RuleValue]
    skipped: dict[str, str]


@dataclass(frozen=True)
class ProfileValue:
    field: str
    domain: str
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerProfileResult:
    values: dict[str, ProfileValue]
    skipped: dict[str, str]


def derive_player_profile_values(evidence: PlayerEvidence) -> PlayerProfileResult:
    values: dict[str, ProfileValue] = {}
    skipped: dict[str, str] = {}

    first_name, last_name = _split_player_name(_clean_text(evidence.identity.get("player")))
    _add_profile(values, skipped, "FIRSTNAME", first_name, "profile_name_v1", ("identity.player",))
    _add_profile(values, skipped, "LASTNAME", last_name, "profile_name_v1", ("identity.player",))

    height_in = _int_number(evidence.identity, "ht_in_in")
    _add_profile(values, skipped, "HEIGHT", height_in, "profile_height_v1", ("identity.ht_in_in",))
    _add_profile(
        values,
        skipped,
        "HEIGHTCM",
        _round_half_up(height_in * 2.54) if height_in is not None else None,
        "profile_height_metric_v1",
        ("identity.ht_in_in",),
    )

    weight_lb = _int_number(evidence.identity, "wt")
    _add_profile(values, skipped, "WEIGHT", weight_lb, "profile_weight_v1", ("identity.wt",))
    _add_profile(
        values,
        skipped,
        "WEIGHTKG",
        round(weight_lb * 0.45359237) if weight_lb is not None else None,
        "profile_weight_metric_v1",
        ("identity.wt",),
    )

    position = _clean_text(evidence.season_info.get("pos")) or _clean_text(evidence.identity.get("pos"))
    _add_profile(values, skipped, "POSITION", position, "profile_position_v1", ("season_info.pos", "identity.pos"))

    college_from = _clean_text(evidence.identity.get("colleges"))
    _add_profile(values, skipped, "COLLEGEFROM", college_from, "profile_college_from_v1", ("identity.colleges",))

    years_pro = _int_number(evidence.season_info, "experience")
    if years_pro is None:
        start_year = _int_number(evidence.identity, "from")
        years_pro = max(0, evidence.season - start_year) if start_year is not None else None
    _add_profile(values, skipped, "YEARSPRO", years_pro, "profile_years_pro_v1", ("season_info.experience", "identity.from"))

    return PlayerProfileResult(values=values, skipped=skipped)


def derive_player_rule_values(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Iterable[dict[str, Any]] = (),
) -> PlayerRuleResult:
    rows = tuple(league_player_rows)
    scores = _score_profile(evidence, rows)
    values: dict[str, RuleValue] = {}
    skipped: dict[str, str] = {}

    for key in sorted(ATTRIBUTE_FIELDS):
        field = key.split("/", 1)[1]
        resolved = _attribute_score(field, ATTRIBUTE_FIELD_GROUPS[key], scores)
        if resolved is None:
            skipped[key] = _missing_reason(field, scores)
            continue
        score, evidence_keys = resolved
        values[key] = _rule("Attributes", field, _to_attribute(score), f"attribute_{_rule_name(field)}_v1", evidence_keys)

    for key in sorted(TENDENCY_FIELDS):
        field = key.split("/", 1)[1]
        resolved = _tendency_score(field, TENDENCY_FIELD_GROUPS[key], scores)
        if resolved is None:
            skipped[key] = _missing_reason(field, scores)
            continue
        score, evidence_keys = resolved
        values[key] = _rule("Tendencies", field, _to_tendency(score), f"tendency_{_rule_name(field)}_v1", evidence_keys)

    return PlayerRuleResult(values=values, skipped=skipped)


def _score_profile(evidence: PlayerEvidence, rows: tuple[dict[str, Any], ...]) -> dict[str, tuple[float | None, tuple[str, ...]]]:
    ppg = _number(evidence.per_game, "pts_per_game")
    ast = _number(evidence.per_game, "ast_per_game")
    trb = _number(evidence.per_game, "trb_per_game")
    orb = _number(evidence.per_game, "orb_per_game")
    drb = _number(evidence.per_game, "drb_per_game")
    stl = _number(evidence.per_game, "stl_per_game")
    blk = _number(evidence.per_game, "blk_per_game")
    fg = _number(evidence.per_game, "fg_percent")
    three_pct = _number(evidence.per_game, "x3p_percent")
    three_att = _number(evidence.per_game, "x3pa_per_game")
    ft = _number(evidence.per_game, "ft_percent")
    usage = _number(evidence.advanced, "usg_percent")
    ts = _number(evidence.advanced, "ts_percent")
    per = _number(evidence.advanced, "per")
    rim_share = _number(evidence.shooting, "percent_fga_from_x0_3_range")
    dunk_share = _number(evidence.shooting, "percent_dunks_of_fga")
    dunks = _number(evidence.shooting, "num_of_dunks")
    pg_pct = _number(evidence.play_by_play, "pg_percent")
    sg_pct = _number(evidence.play_by_play, "sg_percent")
    sf_pct = _number(evidence.play_by_play, "sf_percent")
    pf_pct = _number(evidence.play_by_play, "pf_percent")
    c_pct = _number(evidence.play_by_play, "c_percent")
    team_o = _number(evidence.team_summary, "o_rtg")
    team_d = _number(evidence.team_summary, "d_rtg")
    pace = _number(evidence.team_summary, "pace")
    team_three_att = _number(evidence.team_stats_per_game, "x3pa_per_game")

    guard_share = _clamp01(((pg_pct or 0.0) + (sg_pct or 0.0)) / 100.0) if any(v is not None for v in (pg_pct, sg_pct)) else _position_share(evidence, {"G", "PG", "SG"})
    wing_share = _clamp01(((sg_pct or 0.0) + (sf_pct or 0.0)) / 100.0) if any(v is not None for v in (sg_pct, sf_pct)) else _position_share(evidence, {"G", "F", "SG", "SF"})
    big_share = _clamp01(((pf_pct or 0.0) + (c_pct or 0.0)) / 100.0) if any(v is not None for v in (pf_pct, c_pct)) else _position_share(evidence, {"F", "C", "PF"})

    scoring = _combine((_rank_or_scale(ppg, rows, "pts_per_game", 0.0, 35.0), 0.65), (_scale_or_none(usage, 8.0, 38.0), 0.35))
    efficiency = _combine((_scale_or_none(ts, 0.45, 0.70), 0.70), (_scale_or_none(fg, 0.38, 0.60), 0.30))
    team_context = _scale_or_none(((team_o or 110.0) - (team_d or 115.0)), -15.0, 15.0)
    three = None if three_pct is None or three_att is None or three_att <= 0 else _combine((_scale_or_none(three_pct, 0.24, 0.44), 0.72), (_rank_or_scale(three_att, rows, "x3pa_per_game", 0.0, 10.0), 0.28))
    three_volume = None if three_att is None else _combine((_scale_or_none(three_att / max(team_three_att or 35.0, 1.0), 0.0, 0.28), 0.60), (_rank_or_scale(three_att, rows, "x3pa_per_game", 0.0, 10.0), 0.40))
    free_throw = None if ft is None else _combine((_scale_or_none(ft, 0.45, 0.92), 0.80), (_rank_or_scale(ft, rows, "ft_percent", 0.45, 0.92), 0.20))
    mid = _combine((_scale_or_none(fg, 0.38, 0.55), 0.45), (_invert(three_volume), 0.20), (_scale_or_none(ppg, 0.0, 28.0), 0.35))
    inside = _combine((_scale_or_none(rim_share, 0.0, 0.70), 0.55), (_scale_or_none(fg, 0.38, 0.62), 0.25), (_scale_or_none(ppg, 0.0, 28.0), 0.20))
    dunk = _combine((_scale_or_none(dunk_share, 0.0, 0.25), 0.65), (_scale_or_none(dunks, 0.0, 120.0), 0.35))
    pass_score = _rank_or_scale(ast, rows, "ast_per_game", 0.0, 11.0)
    rebound = _rank_or_scale(trb, rows, "trb_per_game", 0.0, 16.0)
    off_rebound = _rank_or_scale(orb if orb is not None else ((trb or 0.0) * 0.3 if trb is not None else None), rows, "trb_per_game", 0.0, 16.0)
    def_rebound = _rank_or_scale(drb if drb is not None else ((trb or 0.0) * 0.7 if trb is not None else None), rows, "trb_per_game", 0.0, 16.0)
    steal = _scale_or_none(stl, 0.0, 2.5)
    block = _scale_or_none(blk, 0.0, 4.0)
    defense = _combine((steal, 0.35), (block, 0.30), (_invert(team_context), 0.20), (rebound, 0.15))
    athletic = _combine((_scale_or_none(pace, 92.0, 104.0), 0.30), (guard_share, 0.25), (dunk, 0.25), (rebound, 0.20))
    post = _combine((big_share, 0.35), (inside, 0.35), (rebound, 0.20), (dunk, 0.10))
    handle = _combine((guard_share, 0.35), (pass_score, 0.35), (_scale_or_none(usage, 8.0, 38.0), 0.30))
    mental = _combine((_scale_or_none(per, 5.0, 28.0), 0.35), (pass_score, 0.20), (efficiency, 0.25), (team_context, 0.20))
    offensive_consistency = _combine((scoring, 0.48), (efficiency, 0.28), (team_context, 0.24))
    shot_tendency = _combine((_scale_or_none(usage, 8.0, 38.0), 0.65), (_scale_or_none(ppg, 0.0, 35.0), 0.35))
    drive = _combine((guard_share, 0.30), (inside, 0.30), (athletic, 0.25), (handle, 0.15))
    durability = _durability_score(evidence)

    return {
        "scoring": (scoring, ("per_game.pts_per_game", "advanced.usg_percent")),
        "efficiency": (efficiency, ("advanced.ts_percent", "per_game.fg_percent")),
        "offensive_consistency": (offensive_consistency, ("per_game.pts_per_game", "advanced.ts_percent", "team_summary.o_rtg", "team_summary.d_rtg")),
        "three": (three, ("per_game.x3p_percent", "per_game.x3pa_per_game")),
        "three_volume": (three_volume, ("per_game.x3pa_per_game", "team_stats_per_game.x3pa_per_game")),
        "free_throw": (free_throw, ("per_game.ft_percent",)),
        "mid": (mid, ("per_game.fg_percent", "per_game.pts_per_game")),
        "inside": (inside, ("shooting.percent_fga_from_x0_3_range", "per_game.fg_percent")),
        "dunk": (dunk, ("shooting.percent_dunks_of_fga", "shooting.num_of_dunks")),
        "pass": (pass_score, ("per_game.ast_per_game",)),
        "handle": (handle, ("play_by_play.pg_percent", "per_game.ast_per_game", "advanced.usg_percent")),
        "rebound": (rebound, ("per_game.trb_per_game",)),
        "off_rebound": (off_rebound, ("per_game.orb_per_game", "per_game.trb_per_game")),
        "def_rebound": (def_rebound, ("per_game.drb_per_game", "per_game.trb_per_game")),
        "steal": (steal, ("per_game.stl_per_game",)),
        "block": (block, ("per_game.blk_per_game",)),
        "defense": (defense, ("per_game.stl_per_game", "per_game.blk_per_game", "team_summary.d_rtg")),
        "athletic": (athletic, ("team_summary.pace", "play_by_play.pg_percent", "shooting.num_of_dunks", "per_game.trb_per_game")),
        "post": (post, ("play_by_play.pf_percent", "play_by_play.c_percent", "shooting.percent_fga_from_x0_3_range")),
        "mental": (mental, ("advanced.per", "per_game.ast_per_game", "advanced.ts_percent", "team_summary.o_rtg")),
        "shot": (shot_tendency, ("advanced.usg_percent", "per_game.pts_per_game")),
        "drive": (drive, ("play_by_play.pg_percent", "shooting.percent_fga_from_x0_3_range", "team_summary.pace")),
        "durability": (durability, ("season_info", "per_game.games_played")),
        "guard_share": (guard_share, ("play_by_play.pg_percent", "play_by_play.sg_percent", "season_info.pos")),
        "wing_share": (wing_share, ("play_by_play.sg_percent", "play_by_play.sf_percent", "season_info.pos")),
        "big_share": (big_share, ("play_by_play.pf_percent", "play_by_play.c_percent", "season_info.pos")),
        "team_context": (team_context, ("team_summary.o_rtg", "team_summary.d_rtg")),
    }


def _attribute_score(field: str, group: str, scores: dict[str, tuple[float | None, tuple[str, ...]]]) -> tuple[float, tuple[str, ...]] | None:
    selector = {
        "3POINT": "three", "FREETHROW": "free_throw", "DEFENSEREBOUND": "def_rebound", "OFFENSIVEREBOUND": "off_rebound",
        "PASSACCURACY": "pass", "PASSIQ": "pass", "PASSVISION": "pass", "STEAL": "steal", "BLOCK": "block",
        "CLOSESHOT": "inside", "DRIVINGDUNK": "dunk", "STANDINGDUNK": "dunk", "OFFENSIVECONSISTENCY": "offensive_consistency",
        "MIDRANGE": "mid", "IQSHOT": "efficiency", "DRAWFOUL": "inside", "DRIVINGLAYUP": "inside",
        "BALLCONTROL": "handle", "SPEEDWITHBALL": "handle", "POSTFADE": "post", "POSTHOOK": "post", "POSTCONTROL": "post", "POSTFADEAWAY": "post",
        "INTERIORDEFENSE": "defense", "PERIMETERDEFENSE": "defense", "PASSPERCEPTION": "steal", "HELPDEFENSE": "defense", "DEFENSECONSISTENCY": "defense",
        "CONTESTSHOT": "defense", "PICKANDROLLDEFENSEIQ": "defense", "LATERALQUICKNESS": "athletic", "ACCELERATION": "athletic", "AGILITY": "athletic",
        "SPEED": "athletic", "STAMINA": "athletic", "STRENGTH": "post", "VERTICAL": "dunk", "HANDS": "mental", "HUSTLE": "mental",
        "INTANGIBLES": "mental", "POTENTIAL": "mental", "CACHCEDOVR": "offensive_consistency", "MAXOVR": "offensive_consistency", "MINOVR": "offensive_consistency",
    }
    if group == "Durability" or field.endswith("DURABILITY"):
        return _get_score(scores, "durability")
    source = selector.get(field)
    if source is None:
        source = {"Offense": "scoring", "Defense": "defense", "Athleticism": "athletic", "Mental": "mental", "Misc": "mental", "Rebounding": "rebound"}.get(group, "mental")
    return _get_score(scores, source)


def _tendency_score(field: str, group: str, scores: dict[str, tuple[float | None, tuple[str, ...]]]) -> tuple[float, tuple[str, ...]] | None:
    if field in {"3POINTSHOT", "3POINTCENTERSHOT", "3POINTLEFTSHOT", "3POINTCENTERLEFTSHOT", "3POINTRIGHTSHOT", "3POINTCENTERRIGHTSHOT", "3POINTOFFSCREENSHOT", "3POINTSPOTUPSHOT", "STEPBACKJUMPER3POINT", "TRANSITIONPULLUP3POINT", "DRIVEPULLUP3POINT", "CENTER3", "LEFT3", "RIGHT3", "3CENTER", "3LEFT", "3LEFTCENTER", "3RIGHT", "3RIGHTCENTER"}:
        return _get_score(scores, "three_volume")
    if field in {"CONTESTEDJUMPER3POINT"}:
        return _blend_scores(scores, (("three_volume", 0.70), ("shot", 0.30)))
    if "MID" in field or "JUMPER" in field or field in {"SPINJUMPER", "STEPTHROUGH"}:
        return _get_score(scores, "mid")
    if "CLOSE" in field or field in {"BASKETUNDERSHOT", "UNDERBASKET", "FLOATER"}:
        return _get_score(scores, "inside")
    if "DUNK" in field or field in {"ALLEYOOP", "PUTBACK", "CRASH"}:
        return _get_score(scores, "dunk")
    if "LAYUP" in field:
        return _get_score(scores, "inside")
    if "DRIVE" in field or "DRIBBLE" in field or group in {"Driving", "Drive Setup"}:
        return _get_score(scores, "drive")
    if "PASS" in field or field in {"DISHTOOPENMAN", "ALLEYOOPPASS"} or group == "Passing":
        return _get_score(scores, "pass")
    if "POST" in field or group == "Post Game" or field in {"FROMPOSTSHOT"}:
        return _get_score(scores, "post")
    if group == "Defense" or field in {"BLOCKSHOT", "CONTESTSHOT", "ONBALLSTEAL", "PASSINTERCEPTION", "TAKECHARGE"}:
        return _get_score(scores, "defense")
    if group == "Hot Zones":
        if "3" in field:
            return _get_score(scores, "three")
        if "MID" in field:
            return _get_score(scores, "mid")
        return _get_score(scores, "inside")
    if field == "TOUCHES" or field == "SHOT" or group == "Freelance":
        return _get_score(scores, "shot")
    if field in {"PLAYDISCIPLINE", "ROLLVSPOP"}:
        return _get_score(scores, "mental")
    if field in {"FOUL", "HARDFOUL"}:
        defense = _get_score(scores, "defense")
        if defense is None:
            return None
        score, keys = defense
        return (1.0 - score, keys)
    return _get_score(scores, "shot")


def _add_profile(
    values: dict[str, ProfileValue],
    skipped: dict[str, str],
    field: str,
    value: int | str | None,
    source_rule: str,
    evidence_keys: tuple[str, ...],
) -> None:
    key = f"Vitals/{field}"
    if value is None or value == "":
        skipped[key] = "missing required profile evidence"
        return
    values[key] = ProfileValue(field=field, domain="Vitals", value=value, source_rule=source_rule, evidence_keys=evidence_keys)


def _split_player_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "NA" or text.lower() == "none":
        return None
    return text


def _int_number(row: dict[str, Any], key: str) -> int | None:
    number = _number(row, key)
    if number is None:
        return None
    return round(number)


def _get_score(scores: dict[str, tuple[float | None, tuple[str, ...]]], key: str) -> tuple[float, tuple[str, ...]] | None:
    score, evidence_keys = scores[key]
    if score is None:
        return None
    return (_clamp01(score), evidence_keys)


def _blend_scores(scores: dict[str, tuple[float | None, tuple[str, ...]]], parts: tuple[tuple[str, float], ...]) -> tuple[float, tuple[str, ...]] | None:
    total = 0.0
    weight_total = 0.0
    keys: list[str] = []
    for name, weight in parts:
        value = _get_score(scores, name)
        if value is None:
            continue
        score, evidence_keys = value
        total += score * weight
        weight_total += weight
        keys.extend(evidence_keys)
    if weight_total <= 0:
        return None
    return (_clamp01(total / weight_total), tuple(dict.fromkeys(keys)))


def _missing_reason(field: str, scores: dict[str, tuple[float | None, tuple[str, ...]]]) -> str:
    if "3POINT" in field or field.startswith("3") or "3" in field:
        return "missing three-point evidence"
    if "DUNK" in field or "CLOSE" in field or "LAYUP" in field:
        return "missing shooting/inside evidence"
    if "PASS" in field:
        return "missing passing evidence"
    return "missing required evidence"


def _durability_score(evidence: PlayerEvidence) -> float:
    games = _number(evidence.per_game, "g") or _number(evidence.per_game, "games") or _number(evidence.per_game, "games_played")
    if games is None:
        return 0.74
    return _scale(games, 20.0, 82.0)


def _position_share(evidence: PlayerEvidence, markers: set[str]) -> float:
    text = str(evidence.season_info.get("pos") or evidence.identity.get("pos") or "").upper()
    if not text:
        return 0.5
    parts = {part.strip() for part in text.replace("-", "/").split("/") if part.strip()}
    return 1.0 if parts & markers else 0.0


def _combine(*parts: tuple[float | None, float]) -> float | None:
    total = 0.0
    weight_total = 0.0
    for value, weight in parts:
        if value is None:
            continue
        total += _clamp01(value) * weight
        weight_total += weight
    if weight_total <= 0.0:
        return None
    return _clamp01(total / weight_total)


def _invert(value: float | None) -> float | None:
    if value is None:
        return None
    return 1.0 - _clamp01(value)


def _rule(domain: str, field: str, value: int, source_rule: str, evidence_keys: tuple[str, ...]) -> RuleValue:
    return RuleValue(field=field, domain=domain, value=value, source_rule=source_rule, evidence_keys=evidence_keys)


def _rule_name(field: str) -> str:
    return field.lower().replace("+", "plus").replace("-", "minus").replace("#", "num")


def _to_attribute(score: float) -> int:
    return _bounded(round(_ATTRIBUTE_RANGE[0] + _clamp01(score) * (_ATTRIBUTE_RANGE[1] - _ATTRIBUTE_RANGE[0])), *_ATTRIBUTE_RANGE)


def _to_tendency(score: float) -> int:
    return _bounded(round(_clamp01(score) * _TENDENCY_RANGE[1]), *_TENDENCY_RANGE)


def _rank_or_scale(value: float | None, rows: tuple[dict[str, Any], ...], key: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    population = tuple(_number(row, key) for row in rows)
    numeric_population = tuple(item for item in population if item is not None)
    if numeric_population:
        less_or_equal = sum(1 for item in numeric_population if item <= value)
        return _clamp01(less_or_equal / len(numeric_population))
    return _scale(value, low, high)


def _scale_or_none(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    return _scale(value, low, high)


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("scale high must be greater than low")
    return _clamp01((value - low) / (high - low))


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() == "NA":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _bounded(value: int, low: int, high: int) -> int:
    return min(high, max(low, value))


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


__all__ = [
    "ATTRIBUTE_FIELD_GROUPS",
    "TENDENCY_FIELD_GROUPS",
    "ATTRIBUTE_FIELDS",
    "TENDENCY_FIELDS",
    "PROFILE_FIELDS",
    "PlayerRuleResult",
    "PlayerProfileResult",
    "ProfileValue",
    "RuleValue",
    "derive_player_profile_values",
    "derive_player_rule_values",
]
