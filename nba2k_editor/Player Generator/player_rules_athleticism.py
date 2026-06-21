from __future__ import annotations

from typing import Any

from player_rules_core import _attribute


def derive_attribute_speed(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/SPEED", "attribute_speed_direct_2026_v1", (("team_summary.pace", 0.35), ("per_game.mp_per_game", 0.25), ("advanced.bpm", 0.20), ("per_game.stl_per_game", 0.20)), league_player_rows=league_player_rows)


def derive_attribute_speedwithball(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    result = _attribute(evidence, "Attributes/SPEEDWITHBALL", "attribute_speedwithball_v1", (("per_game.ast_per_game", 0.45), ("advanced.ast_percent", 0.30), ("team_summary.pace", 0.25)), league_player_rows=league_player_rows)
    speed = derive_attribute_speed(evidence, league_player_rows=league_player_rows)["value"]
    if result["value"] > speed:
        result = dict(result)
        result["value"] = speed
    return result


def derive_attribute_agility(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/AGILITY", "attribute_agility_direct_2026_v1", (("per_game.stl_per_game", 0.35), ("advanced.stl_percent", 0.35), ("team_summary.pace", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_stamina(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/STAMINA", "attribute_stamina_direct_2026_v1", (("per_game.mp_per_game", 0.70), ("per_game.g", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_strength(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/STRENGTH", "attribute_strength_direct_2026_v1", (("per_game.trb_per_game", 0.35), ("advanced.trb_percent", 0.35), ("play_by_play.c_percent", 0.30)), league_player_rows=league_player_rows)


def derive_attribute_vertical(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any]:
    return _attribute(evidence, "Attributes/VERTICAL", "attribute_vertical_direct_2026_v1", (("shooting.num_of_dunks", 0.35), ("shooting.percent_dunks_of_fga", 0.35), ("per_game.blk_per_game", 0.30)), league_player_rows=league_player_rows)
