from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_era_context import filter_same_league_rows, player_era_context  # type: ignore[import-not-found]
from player_rules import derive_player_profile_values  # type: ignore[import-not-found]
from player_rules_offense import (  # type: ignore[import-not-found]
    _recorded_assists_available,
    derive_attribute_3point,
    derive_attribute_closeshot,
    derive_attribute_midrange,
    derive_tendency_3pointshot,
    derive_tendency_closeshot,
    derive_tendency_midshot,
    midrange_make_probability_for_rating,
    midrange_rating_for_make_probability,
)


def test_nbl_assist_absence_uses_the_same_1952_stat_boundary() -> None:
    assert not _recorded_assists_available(SimpleNamespace(season=1949, season_info={"lg": "NBL"}, per_game={}))
    assert _recorded_assists_available(SimpleNamespace(season=1952, season_info={"lg": "NBL"}, per_game={}))


def _evidence(
    *,
    season: int,
    league: str,
    x3p_percent: float | None = None,
    x3pa_per_game: float | None = None,
    x3pa_total: float | None = None,
    x3p_ar: float | None = None,
    fga_per_game: float | None = None,
    ft_percent: float | None = None,
    shooting: dict[str, float] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        season=season,
        season_info={"lg": league},
        source_context={},
        identity={},
        per_game={
            "g": 20,
            "x3p_percent": x3p_percent,
            "x3pa_per_game": x3pa_per_game,
            "fga_per_game": fga_per_game,
            "ft_percent": ft_percent,
        },
        totals={"x3pa": x3pa_total},
        per_36={},
        per_100={},
        advanced={"x3p_ar": x3p_ar},
        shooting=shooting or {},
        play_by_play={},
        team_stats_per_game={},
        team_summary={},
        opponent_stats_per_game={},
    )


def _rows() -> tuple[dict[str, float], ...]:
    return (
        {
            "per_game.x3p_percent": 0.250,
            "per_game.x3pa_per_game": 1.0,
            "advanced.x3p_ar": 0.10,
            "shooting.fg_percent_from_x0_3_range": 0.50,
            "shooting.fg_percent_from_x3_10_range": 0.35,
            "shooting.fg_percent_from_x10_16_range": 0.35,
            "shooting.fg_percent_from_x16_3p_range": 0.34,
            "shooting.percent_fga_from_x0_3_range": 0.10,
            "shooting.percent_fga_from_x3_10_range": 0.10,
            "shooting.percent_fga_from_x10_16_range": 0.10,
            "shooting.percent_fga_from_x16_3p_range": 0.10,
        },
        {
            "per_game.x3p_percent": 0.350,
            "per_game.x3pa_per_game": 4.0,
            "advanced.x3p_ar": 0.35,
            "shooting.fg_percent_from_x0_3_range": 0.70,
            "shooting.fg_percent_from_x3_10_range": 0.50,
            "shooting.fg_percent_from_x10_16_range": 0.50,
            "shooting.fg_percent_from_x16_3p_range": 0.48,
            "shooting.percent_fga_from_x0_3_range": 0.35,
            "shooting.percent_fga_from_x3_10_range": 0.25,
            "shooting.percent_fga_from_x10_16_range": 0.30,
            "shooting.percent_fga_from_x16_3p_range": 0.25,
        },
    )


def test_three_point_line_is_league_specific() -> None:
    assert player_era_context(_evidence(season=1976, league="NBA")).has_three_point_line is False
    assert player_era_context(_evidence(season=1976, league="ABA")).has_three_point_line is True
    assert player_era_context(_evidence(season=1980, league="NBA")).has_three_point_line is True


def test_shortened_nba_line_is_explicit_context() -> None:
    context = player_era_context(_evidence(season=1996, league="NBA"))
    assert context.has_shortened_nba_three_point_line is True
    assert context.three_point_line == "nba_shortened_1995_1997"

    result = derive_attribute_3point(
        _evidence(season=1996, league="NBA", x3p_percent=0.350),
        league_player_rows=_rows(),
    )
    assert result is not None
    assert "three_point_line=nba_shortened_1995_1997" in result["evidence_keys"]


def test_comparison_population_is_same_league_only() -> None:
    rows = (
        {"player_season_info.lg": "NBA", "player_id": "nba"},
        {"player_season_info.lg": "ABA", "player_id": "aba"},
    )
    evidence = _evidence(season=1976, league="ABA")
    assert filter_same_league_rows(evidence, rows) == (rows[1],)


def test_pre_line_nba_three_point_tendency_is_zero_but_aba_is_ranked() -> None:
    nba = derive_tendency_3pointshot(
        _evidence(season=1976, league="NBA", x3pa_per_game=4.0, x3p_ar=0.35),
        league_player_rows=_rows(),
    )
    aba = derive_tendency_3pointshot(
        _evidence(season=1976, league="ABA", x3pa_per_game=4.0, x3p_ar=0.35),
        league_player_rows=_rows(),
    )
    assert nba is not None and nba["value"] == 0
    assert aba is not None and aba["value"] > 0


def test_no_three_point_attempts_always_produce_attribute_floor() -> None:
    result = derive_attribute_3point(
        _evidence(
            season=2025,
            league="NBA",
            x3p_percent=0.500,
            x3pa_per_game=0.0,
            x3pa_total=0.0,
        ),
        league_player_rows=_rows(),
    )
    assert result is not None
    assert result["value"] == 25
    assert result["source_rule"] == "derive_attribute_3point_no_made_attempt_evidence"


def test_total_fga_cannot_change_three_point_tendency() -> None:
    low_fga = derive_tendency_3pointshot(
        _evidence(season=2025, league="NBA", x3pa_per_game=4.0, x3p_ar=0.35, fga_per_game=5.0),
        league_player_rows=_rows(),
    )
    high_fga = derive_tendency_3pointshot(
        _evidence(season=2025, league="NBA", x3pa_per_game=4.0, x3p_ar=0.35, fga_per_game=40.0),
        league_player_rows=_rows(),
    )
    assert low_fga == high_fga
    assert low_fga is not None
    assert "per_game.fga_per_game" not in low_fga["evidence_keys"]


def test_close_and_mid_fields_are_unresolved_without_distance_data() -> None:
    evidence = _evidence(season=1990, league="NBA", fga_per_game=30.0)
    rows = _rows()
    assert derive_attribute_closeshot(evidence, league_player_rows=rows) is None
    assert derive_attribute_midrange(evidence, league_player_rows=rows) is None
    assert derive_tendency_closeshot(evidence, league_player_rows=rows) is None
    assert derive_tendency_midshot(evidence, league_player_rows=rows) is None


def test_close_and_mid_fields_use_only_distance_data() -> None:
    shooting = {
        "fg_percent_from_x0_3_range": 0.70,
        "fg_percent_from_x3_10_range": 0.50,
        "fg_percent_from_x10_16_range": 0.50,
        "fg_percent_from_x16_3p_range": 0.48,
        "percent_fga_from_x0_3_range": 0.35,
        "percent_fga_from_x3_10_range": 0.25,
        "percent_fga_from_x10_16_range": 0.30,
        "percent_fga_from_x16_3p_range": 0.25,
    }
    evidence = _evidence(season=2025, league="NBA", fga_per_game=99.0, shooting=shooting)
    for result in (
        derive_attribute_closeshot(evidence, league_player_rows=_rows()),
        derive_attribute_midrange(evidence, league_player_rows=_rows()),
        derive_tendency_closeshot(evidence, league_player_rows=_rows()),
        derive_tendency_midshot(evidence, league_player_rows=_rows()),
    ):
        assert result is not None
        assert "per_game.fga_per_game" not in result["evidence_keys"]


def test_three_to_ten_changes_close_but_never_midrange() -> None:
    base = {
        "fg_percent_from_x0_3_range": 0.60,
        "fg_percent_from_x10_16_range": 0.40,
        "fg_percent_from_x16_3p_range": 0.38,
        "percent_fga_from_x0_3_range": 0.20,
        "percent_fga_from_x3_10_range": 0.20,
        "percent_fga_from_x10_16_range": 0.20,
        "percent_fga_from_x16_3p_range": 0.20,
    }
    low = _evidence(
        season=2025,
        league="NBA",
        fga_per_game=20.0,
        shooting={**base, "fg_percent_from_x3_10_range": 0.10},
    )
    high = _evidence(
        season=2025,
        league="NBA",
        fga_per_game=20.0,
        shooting={**base, "fg_percent_from_x3_10_range": 0.90},
    )

    rows = tuple(
        {
            "player_per_game.g": 82.0,
            "player_season_info.season": 2025.0,
            "player_season_info.lg": "NBA",
            "player_shooting.fg_percent_from_x0_3_range": 0.45 + 0.05 * index,
            "player_shooting.fg_percent_from_x3_10_range": 0.25 + 0.10 * index,
            "player_shooting.fg_percent_from_x10_16_range": 0.30 + 0.05 * index,
            "player_shooting.fg_percent_from_x16_3p_range": 0.28 + 0.05 * index,
        }
        for index in range(5)
    )
    mid_low = derive_attribute_midrange(low, league_player_rows=rows)
    mid_high = derive_attribute_midrange(high, league_player_rows=rows)
    close_low = derive_attribute_closeshot(low, league_player_rows=rows)
    close_high = derive_attribute_closeshot(high, league_player_rows=rows)

    assert mid_low is not None and mid_high is not None
    assert close_low is not None and close_high is not None
    assert mid_low["value"] == mid_high["value"]
    assert "shooting.fg_percent_from_x3_10_range" not in mid_low["evidence_keys"]
    assert "shooting.fg_percent_from_x3_10_range" not in mid_high["evidence_keys"]
    assert close_low["value"] != close_high["value"]
    assert "shooting.fg_percent_from_x3_10_range" in close_low["evidence_keys"]
    assert "shooting.fg_percent_from_x3_10_range" in close_high["evidence_keys"]


def test_midrange_response_map_matches_user_observed_context_anchors() -> None:
    expected = {
        25: {"spot_up": 0.0015, "off_screen": 0.0015, "pull_up": 0.0015, "contested": 0.0015},
        80: {"spot_up": 0.45, "off_screen": 0.40, "pull_up": 0.40, "contested": 0.35},
        99: {"spot_up": 0.55, "off_screen": 0.50, "pull_up": 0.50, "contested": 0.45},
    }
    for rating, contexts in expected.items():
        for context, probability in contexts.items():
            assert midrange_make_probability_for_rating(rating, context=context) == probability


def test_historical_ft_half_maps_to_midrange_attribute() -> None:
    expected = {0.50: 55, 0.60: 62, 0.70: 68, 0.80: 74, 0.90: 80, 1.00: 90}
    for ft_percent, rating in expected.items():
        result = derive_attribute_midrange(
            _evidence(season=1947, league="BAA", ft_percent=ft_percent),
            league_player_rows=_rows(),
        )
        assert result is not None
        assert result["value"] == rating
        assert result["source_rule"] == "derive_attribute_midrange_historical_ft_half_open_spot_up_response_map"
        assert "context_weighting=none" in result["evidence_keys"]
        assert "ft_percent_does_not_author_action_tendencies=true" in result["evidence_keys"]


def test_midrange_open_spot_up_response_inverse_anchors() -> None:
    assert midrange_make_probability_for_rating(25, context="spot_up") == 0.0015
    assert midrange_make_probability_for_rating(80, context="spot_up") == 0.45
    assert midrange_make_probability_for_rating(99, context="spot_up") == 0.55
    assert midrange_rating_for_make_probability(0.0015, context="spot_up") == 25
    assert midrange_rating_for_make_probability(0.45, context="spot_up") == 80
    assert midrange_rating_for_make_probability(0.55, context="spot_up") == 99


def test_profile_authors_selected_season_age_not_removed_birthyear_field() -> None:
    evidence = SimpleNamespace(
        player_id="age-test",
        season=1996,
        team="TST",
        identity={"player": "Age Test", "birth_date": 30000.0},
        season_info={"age": 27, "pos": "PG"},
        play_by_play={},
        source_context={},
    )
    positions = SimpleNamespace(primary="PG", secondary=None)
    values = derive_player_profile_values(evidence, positions=positions).values
    assert values["Vitals/AGE"].value == 27
    assert values["Vitals/AGE"].evidence_keys == ("season_info.age",)
    assert "Vitals/BIRTHYEAR" not in values
