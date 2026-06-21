from __future__ import annotations

from typing import Any

from player_rules_core import _attribute, _tendency


_OFFENSIVE_REBOUND_ORB36_RANGE = (
    (0.000000, 0.035012, 0.029460, 0.122914, 25, 30),
    (0.034833, 0.343286, 0.311050, 0.744304, 30, 40),
    (0.534227, 0.942640, 0.945904, 1.317560, 40, 50),
    (1.029437, 1.490630, 1.527934, 1.940120, 50, 60),
    (1.477322, 2.111193, 2.294195, 2.492077, 60, 70),
    (2.161880, 2.667591, 2.661583, 3.388422, 70, 80),
    (2.676514, 3.395563, 3.471734, 3.917025, 80, 90),
    (3.471037, 3.824710, 3.862517, 4.140575, 90, 99),
)
_DEFENSIVE_REBOUND_REB36_RANGE = (
    (2.106383, 2.106383, 2.106383, 2.106383, 40, 50),
    (2.621984, 3.231955, 3.224019, 4.442703, 50, 60),
    (3.676596, 5.249960, 5.100152, 7.171026, 60, 70),
    (5.593509, 6.986767, 6.666114, 9.341876, 70, 80),
    (6.603329, 9.072485, 8.988614, 11.132701, 80, 90),
    (9.062069, 10.756930, 10.694784, 12.177316, 90, 99),
)


def derive_attribute_offensiverebound(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/OFFENSIVEREBOUND", "attribute_offensiverebound_live_range_2026_v1", (("per_36.orb_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.orb_per_36_min", range_points=_OFFENSIVE_REBOUND_ORB36_RANGE)


def derive_attribute_defensiverebound(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/DEFENSEREBOUND", "attribute_defensiverebound_live_range_2026_v1", (("per_36.trb_per_36_min", 1.0),), league_player_rows=league_player_rows, range_path="per_36.trb_per_36_min", range_points=_DEFENSIVE_REBOUND_REB36_RANGE)


def derive_tendency_crash(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/CRASH", "tendency_crash_direct_2026_v1", (("advanced.orb_percent", 0.50), ("per_game.orb_per_game", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_putback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/PUTBACK", "tendency_putback_direct_2026_v1", (("per_game.orb_per_game", 0.50), ("shooting.percent_fga_from_x0_3_range", 0.50)), league_player_rows=league_player_rows)


def derive_tendency_putbackdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/PUTBACKDUNK", "tendency_putbackdunk_direct_2026_v1", (("per_game.orb_per_game", 0.40), ("shooting.num_of_dunks", 0.35), ("shooting.percent_dunks_of_fga", 0.25)), league_player_rows=league_player_rows)
