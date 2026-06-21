from __future__ import annotations

from typing import Any

from player_rules_core import _attribute, _tendency


_STEAL_STL_G_RANGE = (
    (0.743902, 0.774390, 0.774390, 0.804878, 40, 50),
    (0.421053, 0.781818, 0.802469, 1.000000, 50, 60),
    (0.487805, 0.802740, 0.815483, 1.195122, 60, 70),
    (0.441558, 0.898342, 0.902439, 1.710526, 70, 80),
    (0.657534, 1.161182, 1.146341, 1.478873, 80, 90),
    (0.792683, 1.145146, 1.158537, 1.463415, 90, 99),
)
_BLOCK_SHOT_BLK36_TENDENCY_RANGE = (
    (0.153191, 0.585383, 0.613781, 0.942820, 20, 30),
    (0.613716, 1.039782, 1.049472, 1.614840, 30, 40),
    (0.724099, 1.381977, 1.429442, 1.825879, 40, 50),
    (1.410368, 1.506936, 1.429664, 1.758047, 50, 60),
    (1.788692, 1.788692, 1.788692, 1.788692, 60, 70),
    (1.505046, 1.505046, 1.505046, 1.505046, 80, 90),
    (1.759875, 2.280048, 2.184165, 2.896104, 90, 100),
)
_ONBALL_STEAL_STL36_TENDENCY_RANGE = (
    (0.580405, 0.826449, 0.813260, 1.225532, 10, 20),
    (0.583691, 0.875484, 0.833173, 1.293413, 20, 30),
    (0.710900, 0.990318, 0.979310, 1.557495, 30, 40),
    (0.736744, 1.188400, 1.130890, 1.832420, 40, 50),
    (0.939759, 1.238586, 1.230887, 1.673770, 50, 60),
    (0.867641, 1.138732, 1.161180, 1.369838, 60, 70),
    (1.153739, 1.153739, 1.153739, 1.153739, 70, 80),
    (1.675401, 1.728618, 1.728618, 1.781836, 90, 100),
)
_FOUL_PF36_TENDENCY_RANGE = (
    (3.027391, 3.027391, 3.027391, 3.027391, 0, 10),
    (2.838013, 2.845301, 2.845301, 2.852590, 20, 30),
    (2.285714, 2.759832, 2.720686, 3.258136, 30, 40),
    (2.621290, 3.050407, 3.046735, 3.749277, 40, 50),
    (2.722332, 3.204518, 3.192610, 3.755038, 50, 60),
    (2.976312, 3.510193, 3.605150, 3.937936, 60, 70),
    (4.279108, 4.279108, 4.279108, 4.279108, 70, 80),
)


def derive_attribute_block(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/BLOCK", "attribute_block_direct_2026_v1", (("advanced.blk_percent", 0.70), ("per_game.blk_per_game", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_steal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/STEAL", "attribute_steal_live_range_2026_v1", (("per_game.stl_per_game", 1.0),), league_player_rows=league_player_rows, range_path="per_game.stl_per_game", range_points=_STEAL_STL_G_RANGE)


def derive_attribute_passperception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PASSPERCEPTION", "attribute_passperception_deflection_direct_2026_v1", (("play_by_play.bad_pass_turnover", 0.55), ("advanced.stl_percent", 0.20), ("play_by_play.net_plus_minus_per_100_poss", 0.25)), league_player_rows=league_player_rows)


def derive_attribute_perimeterdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PERIMETERDEFENSE", "attribute_perimeterdefense_direct_2026_v1", (("advanced.dbpm", 0.45), ("advanced.stl_percent", 0.30), ('!team_summary.d_rtg', 0.25)), league_player_rows=league_player_rows)


def derive_attribute_interiordefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/INTERIORDEFENSE", "attribute_interiordefense_direct_2026_v1", (("advanced.dbpm", 0.35), ("advanced.blk_percent", 0.30), ('!team_summary.d_rtg', 0.25), ("advanced.dws", 0.10)), league_player_rows=league_player_rows)


def derive_attribute_helpdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/HELPDEFENSE", "attribute_helpdefense_direct_2026_v1", (("advanced.dbpm", 0.45), ("advanced.dws", 0.30), ('!team_summary.d_rtg', 0.25)), league_player_rows=league_player_rows)


def derive_attribute_defenseconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/DEFENSECONSISTENCY", "attribute_defenseconsistency_direct_2026_v1", (("advanced.dws", 0.45), ("advanced.dbpm", 0.40), ('!team_summary.d_rtg', 0.15)), league_player_rows=league_player_rows)


def derive_attribute_pickandrolldefenseiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/PICKANDROLLDEFENSEIQ", "attribute_pickandrolldefenseiq_direct_2026_v1", (("advanced.dbpm", 0.45), ("play_by_play.net_plus_minus_per_100_poss", 0.25), ('!team_summary.d_rtg', 0.30)), league_player_rows=league_player_rows)


def derive_attribute_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/CONTESTSHOT", "attribute_contestshot_direct_2026_v1", (("advanced.dbpm", 0.40), ("advanced.blk_percent", 0.25), ("advanced.dws", 0.20), ('!team_summary.d_rtg', 0.15)), league_player_rows=league_player_rows)


def derive_tendency_foul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/FOUL", "tendency_foul_live_range_2026_v1", (("per_36.pf_per_36_min", 1.0), ("play_by_play.shooting_foul_committed", 0.0), ("play_by_play.offensive_foul_committed", 0.0)), league_player_rows=league_player_rows, range_path="per_36.pf_per_36_min", range_points=_FOUL_PF36_TENDENCY_RANGE)


def derive_tendency_hardfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/HARDFOUL", "tendency_hardfoul_direct_2026_v1", (("per_game.pf_per_game", 0.55), ("play_by_play.shooting_foul_committed", 0.45)), league_player_rows=league_player_rows)


def derive_tendency_blockshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/BLOCKSHOT", "tendency_blockshot_live_range_2026_v1", (("per_36.blk_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.blk_per_36_min", range_points=_BLOCK_SHOT_BLK36_TENDENCY_RANGE)


def derive_tendency_onballsteal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/ONBALLSTEAL", "tendency_onballsteal_live_range_2026_v1", (("per_36.stl_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.stl_per_36_min", range_points=_ONBALL_STEAL_STL36_TENDENCY_RANGE)


def derive_tendency_passinterception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/PASSINTERCEPTION", "tendency_passinterception_direct_2026_v1", (("play_by_play.bad_pass_turnover", 0.60), ("advanced.stl_percent", 0.40)), league_player_rows=league_player_rows)


def derive_tendency_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/CONTESTSHOT", "tendency_contestshot_direct_2026_v1", (("advanced.dbpm", 0.45), ("advanced.blk_percent", 0.25), ("!team_summary.d_rtg", 0.30)), league_player_rows=league_player_rows)
