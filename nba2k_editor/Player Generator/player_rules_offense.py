from __future__ import annotations

from typing import Any

from player_rules_core import _attribute, _tendency


_FREETHROW_FT_PERCENT_RANGE = (
    (0.348214, 0.348214, 0.348214, 0.348214, 40, 50),
    (0.563953, 0.591037, 0.565217, 0.643939, 50, 60),
    (0.569767, 0.651582, 0.654770, 0.703448, 60, 70),
    (0.656863, 0.752457, 0.760417, 0.829268, 70, 80),
    (0.751152, 0.837677, 0.845070, 0.911504, 80, 90),
    (0.858896, 0.910885, 0.911043, 0.970833, 90, 99),
)
_PASS_ACCURACY_AST_G_RANGE = (
    (0.768293, 0.768293, 0.768293, 0.768293, 40, 50),
    (0.802632, 0.815950, 0.815950, 0.829268, 50, 60),
    (0.719512, 1.419119, 1.228804, 2.500000, 60, 70),
    (1.000000, 2.859082, 2.562764, 6.890244, 70, 80),
    (1.878049, 3.881147, 3.465747, 7.439024, 80, 90),
    (2.987805, 6.577542, 6.448780, 9.951220, 90, 99),
)
_PASS_IQ_AST36_RANGE = (
    (1.052436, 1.124347, 1.115287, 1.205318, 30, 40),
    (0.988827, 1.679600, 1.421801, 4.510345, 40, 50),
    (1.368171, 3.133676, 2.880211, 8.270916, 50, 60),
    (1.399568, 3.957919, 3.495693, 8.226304, 60, 70),
    (3.738115, 6.259613, 5.958040, 8.628684, 70, 80),
    (5.436670, 7.973569, 7.534229, 11.106383, 80, 90),
    (9.299317, 10.093190, 10.152263, 10.768918, 90, 99),
)
_PASS_VISION_AST_G_RANGE = (
    (1.000000, 1.000000, 1.000000, 1.000000, 30, 40),
    (0.768293, 0.901945, 0.829268, 1.147541, 40, 50),
    (0.719512, 1.263555, 1.238095, 1.646341, 50, 60),
    (1.109756, 2.496167, 2.341463, 6.329268, 60, 70),
    (2.060976, 3.732120, 3.207317, 8.207317, 70, 80),
    (2.641509, 5.723968, 5.628049, 9.951220, 80, 90),
    (6.891892, 8.515604, 8.642499, 9.826087, 90, 99),
)
_SHOT_FGA36_TENDENCY_RANGE = (
    (4.480418, 4.480418, 4.480418, 4.480418, 20, 30),
    (5.910979, 6.084691, 6.084691, 6.258403, 30, 40),
    (6.877320, 8.416149, 8.521810, 9.629761, 40, 50),
    (8.680851, 10.351438, 10.429950, 12.129830, 50, 60),
    (10.090684, 12.301808, 12.347723, 14.526601, 60, 70),
    (11.773486, 14.197270, 14.405627, 16.143307, 70, 80),
    (14.559242, 16.091936, 15.907655, 19.146814, 80, 90),
    (15.844454, 17.981838, 17.927419, 20.417910, 90, 100),
)
_SHOT_3PT_RATE_TENDENCY_RANGE = (
    (0.008832, 0.050411, 0.047009, 0.118406, 0, 10),
    (0.014648, 0.088337, 0.091020, 0.195735, 10, 20),
    (0.140977, 0.208398, 0.197469, 0.304622, 20, 30),
    (0.215551, 0.263786, 0.269142, 0.305067, 30, 40),
    (0.243469, 0.302608, 0.287340, 0.367299, 40, 50),
    (0.289219, 0.367948, 0.378378, 0.442708, 50, 60),
    (0.345652, 0.438962, 0.444440, 0.519868, 60, 70),
    (0.315141, 0.444422, 0.444257, 0.539597, 70, 80),
    (0.393071, 0.503698, 0.495557, 0.581731, 80, 90),
    (0.396959, 0.496858, 0.496333, 0.559237, 90, 100),
)


def derive_attribute_field_3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/3POINT", "attribute_3point_direct_2026_v1", (("shooting.fg_percent_from_x3p_range", 0.55), ("shooting.percent_fga_from_x3p_range", 0.25), ("shooting.corner_3_point_percent", 0.20)), league_player_rows=league_player_rows)


def derive_attribute_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/CLOSESHOT", "attribute_closeshot_direct_2026_v1", (("shooting.fg_percent_from_x0_3_range", 0.55), ("shooting.fg_percent_from_x3_10_range", 0.45)), league_player_rows=league_player_rows)


def derive_attribute_midrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/MIDRANGE", "attribute_midrange_direct_2026_v1", (("shooting.fg_percent_from_x16_3p_range", 0.70), ("shooting.percent_fga_from_x16_3p_range", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_freethrow(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/FREETHROW", "attribute_freethrow_live_range_2026_v1", (("per_game.ft_percent", 1.0),), league_player_rows=league_player_rows, range_path="per_game.ft_percent", range_points=_FREETHROW_FT_PERCENT_RANGE)


def derive_attribute_drawfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/DRAWFOUL", "attribute_drawfoul_direct_2026_v1", (("play_by_play.shooting_foul_drawn", 0.70), ("advanced.f_tr", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_drivinglayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/DRIVINGLAYUP", "attribute_drivinglayup_direct_2026_v1", (("shooting.percent_fga_from_x0_3_range", 0.18), ("shooting.percent_fga_from_x3_10_range", 0.12), ("advanced.f_tr", 0.20), ("advanced.usg_percent", 0.15), ("play_by_play.and1", 0.15), ("play_by_play.shooting_foul_drawn", 0.15), ("!shooting.percent_assisted_x2p_fg", 0.20), ("!shooting.percent_dunks_of_fga", 0.10)), league_player_rows=league_player_rows)


def derive_attribute_drivingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/DRIVINGDUNK", "attribute_drivingdunk_direct_2026_v1", (("shooting.percent_dunks_of_fga", 0.55), ("shooting.num_of_dunks", 0.35), ("advanced.usg_percent", 0.10)), league_player_rows=league_player_rows)


def derive_attribute_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/STANDINGDUNK", "attribute_standingdunk_direct_2026_v1", (("shooting.percent_dunks_of_fga", 0.45), ("shooting.num_of_dunks", 0.35), ("per_game.orb_per_game", 0.20)), league_player_rows=league_player_rows)


def derive_attribute_passaccuracy(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PASSACCURACY", "attribute_passaccuracy_live_range_2026_v1", (("per_game.ast_per_game", 1.0),), league_player_rows=league_player_rows, range_path="per_game.ast_per_game", range_points=_PASS_ACCURACY_AST_G_RANGE)


def derive_attribute_passvision(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PASSVISION", "attribute_passvision_live_range_2026_v1", (("per_game.ast_per_game", 1.0),), league_player_rows=league_player_rows, range_path="per_game.ast_per_game", range_points=_PASS_VISION_AST_G_RANGE)


def derive_attribute_passiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PASSIQ", "attribute_passiq_live_range_2026_v1", (("per_36.ast_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.ast_per_36_min", range_points=_PASS_IQ_AST36_RANGE)


def derive_attribute_ballcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/BALLCONTROL", "attribute_ballcontrol_direct_2026_v1", (("advanced.usg_percent", 0.35), ("per_game.ast_per_game", 0.35), ("!advanced.tov_percent", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_postfadeaway(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/POSTFADEAWAY", "attribute_postfadeaway_direct_2026_v1", (("shooting.fg_percent_from_x3_10_range", 0.45), ("shooting.percent_fga_from_x3_10_range", 0.30), ("shooting.fg_percent_from_x10_16_range", 0.25)), league_player_rows=league_player_rows)


def derive_attribute_postfade(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/POSTFADE", "attribute_postfade_direct_2026_v1", (("shooting.fg_percent_from_x10_16_range", 0.50), ("shooting.percent_fga_from_x10_16_range", 0.50)), league_player_rows=league_player_rows)


def derive_attribute_posthook(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/POSTHOOK", "attribute_posthook_direct_2026_v1", (("shooting.fg_percent_from_x3_10_range", 0.50), ("shooting.percent_fga_from_x3_10_range", 0.50)), league_player_rows=league_player_rows)


def derive_attribute_postcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/POSTCONTROL", "attribute_postcontrol_direct_2026_v1", (("shooting.percent_fga_from_x3_10_range", 0.35), ("shooting.percent_fga_from_x10_16_range", 0.25), ("advanced.usg_percent", 0.40)), league_player_rows=league_player_rows)


def derive_attribute_offensiveconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/OFFENSIVECONSISTENCY", "attribute_offensiveconsistency_direct_2026_v1", (("advanced.obpm", 0.50), ("advanced.ows", 0.50)), league_player_rows=league_player_rows)


def derive_attribute_iqshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/IQSHOT", "attribute_iqshot_direct_2026_v1", (("advanced.ts_percent", 0.55), ("advanced.ows", 0.45)), league_player_rows=league_player_rows)


def derive_tendency_shot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/SHOT", "tendency_shot_live_range_2026_v1", (("per_36.fga_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.fga_per_36_min", range_points=_SHOT_FGA36_TENDENCY_RANGE)


def derive_tendency_3pointshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/3POINTSHOT", "tendency_3pointshot_live_range_2026_v1", (("advanced.x3p_ar", 1.0),), league_player_rows=league_player_rows, range_path="advanced.x3p_ar", range_points=_SHOT_3PT_RATE_TENDENCY_RANGE)


def derive_tendency_3pointspotupshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/3POINTSPOTUPSHOT", "tendency_3pointspotupshot_direct_2026_v1", (("shooting.percent_assisted_x3p_fg", 0.55), ("per_game.x3pa_per_game", 0.45)), league_player_rows=league_player_rows)


def derive_tendency_drivepullup3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/DRIVEPULLUP3POINT", "tendency_drivepullup3point_direct_2026_v1", (("!shooting.percent_assisted_x3p_fg", 0.55), ("per_game.x3pa_per_game", 0.45)), league_player_rows=league_player_rows)


def derive_tendency_stepbackjumper3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/STEPBACKJUMPER3POINT", "tendency_stepbackjumper3point_direct_2026_v1", (("!shooting.percent_assisted_x3p_fg", 0.60), ("advanced.usg_percent", 0.40)), league_player_rows=league_player_rows)


def derive_tendency_midshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/MIDSHOT", "tendency_midshot_direct_2026_v1", (("shooting.percent_fga_from_x16_3p_range", 0.65), ("shooting.fg_percent_from_x16_3p_range", 0.35)), league_player_rows=league_player_rows)


def derive_tendency_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/CLOSESHOT", "tendency_closeshot_direct_2026_v1", (("shooting.percent_fga_from_x0_3_range", 0.50), ("shooting.percent_fga_from_x3_10_range", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_drivinglayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/DRIVINGLAYUP", "tendency_drivinglayup_direct_2026_v1", (("shooting.percent_fga_from_x0_3_range", 0.20), ("shooting.percent_fga_from_x3_10_range", 0.15), ("advanced.f_tr", 0.20), ("play_by_play.shooting_foul_drawn", 0.20), ("!shooting.percent_assisted_x2p_fg", 0.25)), league_player_rows=league_player_rows)


def derive_tendency_eurosteplayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/EUROSTEPLAYUP", "tendency_eurosteplayup_direct_2026_v1", (("advanced.f_tr", 0.45), ("play_by_play.shooting_foul_drawn", 0.35), ("!shooting.percent_assisted_x2p_fg", 0.20)), league_player_rows=league_player_rows)


def derive_tendency_hopsteplayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/HOPSTEPLAYUP", "tendency_hopsteplayup_direct_2026_v1", (("advanced.f_tr", 0.40), ("play_by_play.and1", 0.30), ("!shooting.percent_assisted_x2p_fg", 0.30)), league_player_rows=league_player_rows)


def derive_tendency_spinlayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/SPINLAYUP", "tendency_spinlayup_direct_2026_v1", (("advanced.f_tr", 0.35), ("advanced.usg_percent", 0.35), ("!shooting.percent_assisted_x2p_fg", 0.30)), league_player_rows=league_player_rows)


def derive_tendency_drivingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/DRIVINGDUNK", "tendency_drivingdunk_direct_2026_v1", (("shooting.percent_dunks_of_fga", 0.60), ("shooting.num_of_dunks", 0.40)), league_player_rows=league_player_rows)


def derive_tendency_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/STANDINGDUNK", "tendency_standingdunk_direct_2026_v1", (("shooting.percent_dunks_of_fga", 0.45), ("shooting.num_of_dunks", 0.35), ("per_game.orb_per_game", 0.20)), league_player_rows=league_player_rows)


def derive_tendency_flashydunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/FLASHYDUNK", "tendency_flashydunk_direct_2026_v1", (("shooting.num_of_dunks", 0.50), ("shooting.percent_dunks_of_fga", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_alleyoop(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/ALLEYOOP", "tendency_alleyoop_direct_2026_v1", (("shooting.num_of_dunks", 0.50), ("shooting.percent_dunks_of_fga", 0.35), ("per_game.orb_per_game", 0.15)), league_player_rows=league_player_rows)


def derive_tendency_postup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/POSTUP", "tendency_postup_direct_2026_v1", (("shooting.percent_fga_from_x3_10_range", 0.45), ("shooting.percent_fga_from_x10_16_range", 0.25), ("advanced.usg_percent", 0.30)), league_player_rows=league_player_rows)


def derive_tendency_postfadeleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/POSTFADELEFT", "tendency_postfadeleft_direct_2026_v1", (("shooting.percent_fga_from_x10_16_range", 0.50), ("shooting.fg_percent_from_x10_16_range", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_postfaderight(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/POSTFADERIGHT", "tendency_postfaderight_direct_2026_v1", (("shooting.percent_fga_from_x10_16_range", 0.50), ("shooting.fg_percent_from_x10_16_range", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_posthookleft(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/POSTHOOKLEFT", "tendency_posthookleft_direct_2026_v1", (("shooting.percent_fga_from_x3_10_range", 0.50), ("shooting.fg_percent_from_x3_10_range", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_posthookright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/POSTHOOKRIGHT", "tendency_posthookright_direct_2026_v1", (("shooting.percent_fga_from_x3_10_range", 0.50), ("shooting.fg_percent_from_x3_10_range", 0.50)), league_player_rows=league_player_rows)
