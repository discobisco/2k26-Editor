from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_offense import derive_tendency_crash  # type: ignore[import-not-found]  # noqa: E402
from player_rules_rebounding import (  # type: ignore[import-not-found]  # noqa: E402
    derive_attribute_defensiverebound,
    derive_attribute_offensiverebound,
    derive_tendency_putback,
    derive_tendency_putbackdunk,
)


def _evidence(
    *,
    orb_percent: float | None,
    trb_per_36: float | None = None,
    height: float = 80.0,
    weight: float = 225.0,
    games: float = 82.0,
    mpg: float = 28.0,
    drb_percent: float | None = 15.0,
    rim_share: float = 0.45,
    two_makes_per_game: float = 5.0,
    assisted_two_rate: float = 0.50,
) -> SimpleNamespace:
    return SimpleNamespace(
        season=2025,
        identity={"pos": "PF-C", "ht_in_in": height, "wt": weight},
        season_info={"lg": "NBA", "pos": "PF-C"},
        per_game={"g": games, "mp_per_game": mpg},
        totals={"g": games, "mp": games * mpg, "x2p": games * two_makes_per_game, "x3p": 0.0, "fg": games * two_makes_per_game},
        per_36={} if trb_per_36 is None else {"trb_per_36_min": trb_per_36},
        per_100={},
        advanced={
            **({} if orb_percent is None else {"orb_percent": orb_percent}),
            **({} if drb_percent is None else {"drb_percent": drb_percent}),
        },
        shooting={
            "percent_fga_from_x0_3_range": rim_share,
            "percent_assisted_x2p_fg": assisted_two_rate,
        },
        play_by_play={},
        team_stats_per_game={},
        team_summary={},
    )


def _rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "season": 2025,
            "player_season_info.lg": "NBA",
            "player_season_info.pos": "PF-C",
            "player_info.pos": "PF-C",
            "player_info.ht_in_in": 76.0 + index * 0.7,
            "player_info.wt": 195.0 + index * 6.0,
            "player_per_game.g": 82.0,
            "player_per_game.mp_per_game": 8.0 + index * 2.0,
            "player_totals.mp": 82.0 * (8.0 + index * 2.0),
            "advanced.orb_percent": 2.0 + index * 1.2,
            "advanced.drb_percent": 7.0 + index * 1.3,
            "player_totals.g": 82.0,
            "player_totals.x2p": 82.0 * (2.0 + index * 0.5),
            "player_totals.x3p": 0.0,
            "player_totals.fg": 82.0 * (2.0 + index * 0.5),
            "player_shooting.percent_fga_from_x0_3_range": 0.10 + index * 0.05,
            "player_shooting.percent_assisted_x2p_fg": 0.80 - index * 0.04,
            "player_per_36_min.trb_per_36_min": 4.0 + index * 0.8,
        }
        for index in range(14)
    )


def test_putback_uses_demonstrated_offensive_recovery_frequency() -> None:
    rows = _rows()
    low = derive_tendency_putback(_evidence(orb_percent=3.0), league_player_rows=rows)
    high = derive_tendency_putback(_evidence(orb_percent=17.0), league_player_rows=rows)

    assert low is not None and high is not None
    assert 0 <= low["value"] < high["value"] <= 100
    assert "historical_total_rebound_substitute=forbidden" in high["evidence_keys"]
    assert "mapping=field_exact_pool_quantile_curve" in high["evidence_keys"]


def test_putback_shrinks_low_minute_orb_rate_outliers_toward_position_mpg_context() -> None:
    rows = _rows()
    low_volume = derive_tendency_putback(
        _evidence(orb_percent=17.0, games=10.0, mpg=5.0),
        league_player_rows=rows,
    )
    established = derive_tendency_putback(
        _evidence(orb_percent=17.0, games=82.0, mpg=30.0),
        league_player_rows=rows,
    )
    assert low_volume is not None and established is not None
    assert low_volume["value"] < established["value"]
    assert any(key.startswith("minutes_reliability=") for key in low_volume["evidence_keys"])


def test_putback_also_responds_to_zero_to_three_share_and_unassisted_shot_amount() -> None:
    rows = _rows()
    low = derive_tendency_putback(
        _evidence(orb_percent=10.0, rim_share=0.15, two_makes_per_game=2.0, assisted_two_rate=0.90),
        league_player_rows=rows,
    )
    high = derive_tendency_putback(
        _evidence(orb_percent=10.0, rim_share=0.75, two_makes_per_game=8.0, assisted_two_rate=0.20),
        league_player_rows=rows,
    )
    assert low is not None and high is not None
    assert low["value"] < high["value"]
    assert any(key.startswith("zero_to_three_attempt_share_percentile=") for key in high["evidence_keys"])
    assert any(key.startswith("unassisted_two_makes_per_game_percentile=") for key in high["evidence_keys"])


def test_putback_dunk_adds_literal_standing_dunk_choice_without_using_broad_dunk_totals() -> None:
    rows = _rows()
    small = derive_tendency_putbackdunk(
        _evidence(orb_percent=10.0, height=76.0, weight=195.0),
        league_player_rows=rows,
    )
    large = derive_tendency_putbackdunk(
        _evidence(orb_percent=10.0, height=85.0, weight=285.0),
        league_player_rows=rows,
    )

    assert small is not None and large is not None
    assert 0 <= small["value"] < large["value"] <= 100
    assert "broad_or_moving_dunk_totals_excluded=true" in large["evidence_keys"]
    assert any(key.startswith("formula=0.60*generated_PUTBACK_behavior_score") for key in large["evidence_keys"])


def test_total_rebounds_never_manufacture_putback_or_putback_dunk() -> None:
    total_only = _evidence(orb_percent=None, trb_per_36=14.0)
    rows = _rows()
    assert derive_tendency_putback(total_only, league_player_rows=rows) is None
    assert derive_tendency_putbackdunk(total_only, league_player_rows=rows) is None


def test_putback_formulas_require_games_played() -> None:
    evidence = _evidence(orb_percent=12.0)
    evidence.per_game["g"] = 0.0
    assert derive_tendency_putback(evidence, league_player_rows=_rows()) is None
    assert derive_tendency_putbackdunk(evidence, league_player_rows=_rows()) is None


def test_rebound_attributes_use_only_orbr_drbr_plus_minutes_context() -> None:
    rows = _rows()
    evidence = _evidence(orb_percent=12.0, drb_percent=20.0)
    offense = derive_attribute_offensiverebound(evidence, league_player_rows=rows)
    defense = derive_attribute_defensiverebound(evidence, league_player_rows=rows)
    assert offense is not None and defense is not None
    assert "height_weight_raw_rebounds_and_total_rebound_rate_excluded=true" in offense["evidence_keys"]
    assert "height_weight_raw_rebounds_and_total_rebound_rate_excluded=true" in defense["evidence_keys"]


def test_crash_does_not_use_rebounding_body_or_role_as_contact_fall_evidence() -> None:
    rows = _rows()
    low_rebound_small = _evidence(orb_percent=1.0, drb_percent=2.0, height=72.0, weight=170.0)
    high_rebound_large = _evidence(orb_percent=25.0, drb_percent=35.0, height=86.0, weight=300.0)

    assert derive_tendency_crash(low_rebound_small, league_player_rows=rows) is None
    assert derive_tendency_crash(high_rebound_large, league_player_rows=rows) is None


def test_total_rebound_rate_or_frame_never_substitutes_for_missing_orbr_drbr() -> None:
    rows = _rows()
    no_split = _evidence(orb_percent=None, drb_percent=None, trb_per_36=18.0, height=86.0, weight=300.0)
    assert derive_attribute_offensiverebound(no_split, league_player_rows=rows) is None
    assert derive_attribute_defensiverebound(no_split, league_player_rows=rows) is None
    assert derive_tendency_crash(no_split, league_player_rows=rows) is None


def test_historical_sparse_version_remains_when_the_era_has_no_orbr_or_drbr() -> None:
    evidence = _evidence(orb_percent=None, drb_percent=None)
    evidence.season = 1955
    evidence.season_info["lg"] = "NBA"
    evidence.team_stats_per_game["g"] = 72.0
    rows = []
    for index, row in enumerate(_rows()):
        historical = {
            key: value
            for key, value in row.items()
            if not key.startswith("advanced.") and not key.startswith("player_shooting.")
        }
        historical.update(
            {
                "season": 1955,
                "league": "NBA",
                "team_stats_per_game.g": 72.0,
                "player_info.ht_in_in": 72.0 + index * 0.7,
                "player_info.wt": 175.0 + index * 7.0,
            }
        )
        rows.append(historical)

    results = (
        derive_attribute_offensiverebound(evidence, league_player_rows=rows),
        derive_attribute_defensiverebound(evidence, league_player_rows=rows),
        derive_tendency_putback(evidence, league_player_rows=rows),
        derive_tendency_putbackdunk(evidence, league_player_rows=rows),
    )
    assert all(result is not None for result in results)
    assert derive_tendency_crash(evidence, league_player_rows=rows) is None
    assert all(
        result["source_rule"].endswith("_field_specific_context_substitute")
        for result in results
        if result is not None
    )


def test_historical_fallback_is_restored_per_missing_rebound_side() -> None:
    evidence = _evidence(orb_percent=None, drb_percent=20.0)
    evidence.season = 1955
    evidence.season_info["lg"] = "NBA"
    evidence.team_stats_per_game["g"] = 72.0
    rows = []
    for index, row in enumerate(_rows()):
        historical = {
            key: value
            for key, value in row.items()
            if key != "advanced.orb_percent" and not key.startswith("player_shooting.")
        }
        historical.update(
            {
                "season": 1955,
                "league": "NBA",
                "advanced.drb_percent": 12.0 + index,
                "team_stats_per_game.g": 72.0,
                "player_info.ht_in_in": 72.0 + index * 0.7,
                "player_info.wt": 175.0 + index * 7.0,
            }
        )
        rows.append(historical)

    offense = derive_attribute_offensiverebound(evidence, league_player_rows=rows)
    defense = derive_attribute_defensiverebound(evidence, league_player_rows=rows)

    assert offense is not None and defense is not None
    assert offense["source_rule"].endswith("_field_specific_context_substitute")
    assert not defense["source_rule"].endswith("_field_specific_context_substitute")


def test_old_historical_total_rebound_and_frame_path_is_restored() -> None:
    rows = []
    for row in _rows():
        historical = {
            key: value
            for key, value in row.items()
            if not key.startswith("advanced.") and not key.startswith("player_shooting.")
        }
        historical.update({"season": 1955, "league": "NBA"})
        rows.append(historical)

    small = _evidence(orb_percent=None, drb_percent=None, trb_per_36=10.0, height=76.0, weight=195.0)
    large = _evidence(orb_percent=None, drb_percent=None, trb_per_36=10.0, height=84.0, weight=275.0)
    for evidence in (small, large):
        evidence.season = 1955
        evidence.season_info["lg"] = "NBA"

    small_result = derive_attribute_offensiverebound(small, league_player_rows=rows)
    large_result = derive_attribute_offensiverebound(large, league_player_rows=rows)

    assert small_result is not None and large_result is not None
    assert small_result["source_rule"] == "derive_attribute_offensiverebound"
    assert "source_mode=historical_total_rebound_per_36" in small_result["evidence_keys"]
    assert "frame_context_weight=0.12" in small_result["evidence_keys"]
    assert any(key.startswith("historical_substitute=") for key in small_result["evidence_keys"])
    assert small_result["value"] < large_result["value"]
