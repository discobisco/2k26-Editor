from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_mental import (  # type: ignore[import-not-found]  # noqa: E402
    derive_attribute_hands,
    derive_attribute_hustle,
    derive_tendency_isovsaveragedefender,
    derive_tendency_isovselitedefender,
    derive_tendency_isovsgooddefender,
    derive_tendency_isovspoordefender,
    derive_tendency_playdiscipline,
    derive_tendency_rollvspop,
    derive_tendency_transitionspotup,
)


def _evidence(*, quality: float = 0.5, position: str = "SF") -> SimpleNamespace:
    games = 72.0
    return SimpleNamespace(
        season=1955,
        identity={"pos": position, "ht_in_in": 78.0, "wt": 205.0},
        season_info={"lg": "NBA", "pos": position},
        per_game={
            "g": games,
            "mp_per_game": 30.0,
            "ft_percent": 0.45 + 0.45 * quality,
            "trb_per_game": 2.0 + 8.0 * quality,
            "pf_per_game": 1.0 + 3.0 * quality,
            "ast_per_game": 0.5 + 5.0 * quality,
            "fga_per_game": 5.0 + 15.0 * quality,
            "fta_per_game": 1.0 + 6.0 * quality,
        },
        totals={
            "g": games,
            "fg": 100.0 + 400.0 * quality,
            "fga": 360.0 + 1080.0 * quality,
            "ft": 30.0 + 250.0 * quality,
            "fta": 72.0 + 432.0 * quality,
            "pts": 250.0 + 1200.0 * quality,
            "ast": 36.0 + 360.0 * quality,
            "trb": 144.0 + 576.0 * quality,
            "pf": 72.0 + 216.0 * quality,
        },
        per_36={
            "trb_per_36_min": 2.4 + 9.6 * quality,
            "pf_per_36_min": 1.2 + 3.6 * quality,
        },
        advanced={"f_tr": 0.10 + 0.45 * quality},
        shooting={},
        play_by_play={},
        team_totals={},
        team_stats_per_game={
            "g": 72.0,
            "fg_per_game": 40.0,
            "fga_per_game": 90.0,
            "ft_per_game": 20.0,
            "fta_per_game": 28.0,
            "pts_per_game": 100.0,
            "ast_per_game": 24.0,
        },
    )


def _rows() -> tuple[dict[str, object], ...]:
    positions = ("PG", "SG", "SF", "PF", "C")
    rows = []
    for index in range(15):
        quality = (index + 1) / 16.0
        evidence = _evidence(quality=quality, position=positions[index % len(positions)])
        row: dict[str, object] = {"season": 1955}
        for namespace, prefix in (
            ("identity", "player_info"),
            ("season_info", "player_season_info"),
            ("per_game", "player_per_game"),
            ("totals", "player_totals"),
            ("per_36", "player_per_36"),
            ("advanced", "advanced"),
            ("team_stats_per_game", "team_stats_per_game"),
        ):
            row.update({f"{prefix}.{key}": value for key, value in getattr(evidence, namespace).items()})
        rows.append(row)
    return tuple(rows)


def test_hands_and_hustle_use_distinct_historical_execution_and_activity_formulas() -> None:
    rows = _rows()
    low = _evidence(quality=0.15)
    high = _evidence(quality=0.90)

    low_hands = derive_attribute_hands(low, league_player_rows=rows)
    high_hands = derive_attribute_hands(high, league_player_rows=rows)
    low_hustle = derive_attribute_hustle(low, league_player_rows=rows)
    high_hustle = derive_attribute_hustle(high, league_player_rows=rows)

    assert low_hands is not None and high_hands is not None
    assert low_hustle is not None and high_hustle is not None
    assert 25 <= low_hands["value"] < high_hands["value"] <= 99
    assert 25 <= low_hustle["value"] < high_hustle["value"] <= 99
    assert "recipe=historical_hand_eye_and_secure_possession" in high_hands["evidence_keys"]
    assert "recipe=historical_rebound_foul_availability_activity" in high_hustle["evidence_keys"]


def test_iso_defender_classes_share_one_load_score_and_preserve_difficulty_order() -> None:
    evidence = _evidence(quality=0.80, position="PG")
    rows = _rows()
    poor = derive_tendency_isovspoordefender(evidence, league_player_rows=rows)
    average = derive_tendency_isovsaveragedefender(evidence, league_player_rows=rows)
    good = derive_tendency_isovsgooddefender(evidence, league_player_rows=rows)
    elite = derive_tendency_isovselitedefender(evidence, league_player_rows=rows)

    assert all(result is not None for result in (poor, average, good, elite))
    values = [poor["value"], average["value"], good["value"], elite["value"]]  # type: ignore[index]
    assert values == sorted(values, reverse=True)
    recipes = {
        next(key for key in result["evidence_keys"] if key.startswith("recipe="))  # type: ignore[index]
        for result in (poor, average, good, elite)
    }
    assert recipes == {"recipe=historical_creator_isolation_load"}


def test_freelance_behavior_formulas_resolve_independently_with_provenance() -> None:
    evidence = _evidence(quality=0.65, position="SF")
    rows = _rows()
    results = (
        derive_tendency_playdiscipline(evidence, league_player_rows=rows),
        derive_tendency_rollvspop(evidence, league_player_rows=rows),
        derive_tendency_transitionspotup(evidence, league_player_rows=rows),
    )

    assert all(result is not None for result in results)
    assert all(0 <= result["value"] <= 100 for result in results if result is not None)
    assert len({result["source_rule"] for result in results if result is not None}) == 3
    assert all(
        any(key.startswith("pool_calibration=editor_capture_001+002") for key in result["evidence_keys"])
        for result in results
        if result is not None
    )


def test_roll_vs_pop_uses_higher_values_for_rollers_and_lower_values_for_poppers() -> None:
    rows = _rows()
    roller = _evidence(quality=0.50, position="C")
    popper = _evidence(quality=0.50, position="SF")

    roller.per_game["ft_percent"] = 0.50
    roller.advanced["f_tr"] = 0.80
    popper.per_game["ft_percent"] = 0.92
    popper.advanced["f_tr"] = 0.05

    roll_result = derive_tendency_rollvspop(roller, league_player_rows=rows)
    pop_result = derive_tendency_rollvspop(popper, league_player_rows=rows)

    assert roll_result is not None and pop_result is not None
    assert roll_result["value"] > 50
    assert pop_result["value"] < 50
    assert roll_result["value"] > pop_result["value"]
    assert "recipe=historical_screen_roll_touch_role" in roll_result["evidence_keys"]
    assert "scale_direction=higher_roll;lower_pop" in roll_result["evidence_keys"]


def test_new_mental_formulas_require_games_played() -> None:
    evidence = _evidence()
    evidence.per_game["g"] = 0.0
    evidence.totals["g"] = 0.0
    assert derive_attribute_hands(evidence, league_player_rows=_rows()) is None
    assert derive_attribute_hustle(evidence, league_player_rows=_rows()) is None
    assert derive_tendency_playdiscipline(evidence, league_player_rows=_rows()) is None
