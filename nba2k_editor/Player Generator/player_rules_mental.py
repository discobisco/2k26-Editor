from __future__ import annotations

from typing import Any

from player_rules_core import _attribute, _tendency


def derive_attribute_hands(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/HANDS", "attribute_hands_direct_2026_v1", (("!advanced.tov_percent", 0.45), ("per_game.ast_per_game", 0.30), ("shooting.percent_assisted_x2p_fg", 0.25)), league_player_rows=league_player_rows)


def derive_attribute_hustle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/HUSTLE", "attribute_hustle_direct_2026_v1", (("per_game.orb_per_game", 0.25), ("per_game.stl_per_game", 0.25), ("per_game.blk_per_game", 0.25), ("per_game.mp_per_game", 0.25)), league_player_rows=league_player_rows)


def derive_attribute_intangibles(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/INTANGIBLES", "attribute_intangibles_direct_2026_v1", (("advanced.ws", 0.45), ("advanced.bpm", 0.35), ("team_summary.n_rtg", 0.20)), league_player_rows=league_player_rows)


def derive_attribute_potential(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/POTENTIAL", "attribute_potential_direct_2026_v1", (("advanced.bpm", 0.45), ("advanced.vorp", 0.35), ("per_game.mp_per_game", 0.20)), league_player_rows=league_player_rows)


def derive_tendency_playdiscipline(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/PLAYDISCIPLINE", "tendency_playdiscipline_direct_2026_v1", (("!advanced.tov_percent", 0.55), ("!per_game.pf_per_game", 0.45)), league_player_rows=league_player_rows)


def derive_tendency_touches(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _tendency(evidence, "Tendencies/TOUCHES", "tendency_touches_direct_2026_v1", (("advanced.usg_percent", 0.55), ("per_game.mp_per_game", 0.25), ("per_game.fga_per_game", 0.20)), league_player_rows=league_player_rows)
