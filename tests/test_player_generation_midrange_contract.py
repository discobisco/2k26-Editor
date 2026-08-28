from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_offense import (  # type: ignore[import-not-found]  # noqa: E402
    derive_tendency_3pointoffscreenshot,
    derive_tendency_3pointspotupshot,
    derive_tendency_contestedjumpermid,
    derive_tendency_contestedjumpermidrange,
    derive_tendency_drivepullupmid,
    derive_tendency_drivepullupmidrange,
    derive_tendency_midoffscreenshot,
    derive_tendency_midshot,
    derive_tendency_midspotupshot,
)



def _generic_midrange_evidence(*, index: int = 7) -> SimpleNamespace:
    share = index / 12.0
    return SimpleNamespace(
        player_id="",
        team="",
        season=1949,
        identity={"pos": "F-C", "ht_in_in": 76.0 + index * 0.4, "wt": 180.0 + index * 6.0},
        season_info={"lg": "BAA", "pos": "F-C"},
        per_game={
            "g": 60.0,
            "fga_per_game": 8.0 + 12.0 * share,
            "fg_percent": 0.350 + 0.10 * share,
            "ft_percent": 0.500 + 0.40 * share,
        },
        totals={"g": 60.0, "fga": 480.0 + 720.0 * share, "ft": 80.0 + 180.0 * share, "fta": 140.0 + 220.0 * share},
        per_36={},
        per_100={},
        advanced={"f_tr": 0.10 + 0.35 * share},
        shooting={
            "percent_fga_from_x10_16_range": 0.10 + 0.28 * share,
            "percent_fga_from_x16_3p_range": 0.08 + 0.22 * share,
            "percent_assisted_x2p_fg": 0.25 + 0.60 * share,
        },
        play_by_play={},
        team_stats_per_game={"g": 60.0, "fga_per_game": 80.0},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
    )


def _population_rows() -> tuple[dict[str, object], ...]:
    rows = []
    for index in range(1, 12):
        evidence = _generic_midrange_evidence(index=index)
        row: dict[str, object] = {"season": 1949}
        for namespace, prefix in (
            ("identity", "player_info"),
            ("season_info", "player_season_info"),
            ("per_game", "player_per_game"),
            ("totals", "player_totals"),
            ("advanced", "advanced"),
            ("shooting", "player_shooting"),
            ("team_stats_per_game", "team_stats_per_game"),
        ):
            row.update({f"{prefix}.{key}": value for key, value in getattr(evidence, namespace).items()})
        rows.append(row)
    return tuple(rows)


def test_approved_midrange_action_substitutes_resolve_and_keep_aliases_identical() -> None:
    evidence = _generic_midrange_evidence()
    rows = _population_rows()
    contested = derive_tendency_contestedjumpermid(evidence, league_player_rows=rows)
    contested_alias = derive_tendency_contestedjumpermidrange(evidence, league_player_rows=rows)
    pullup = derive_tendency_drivepullupmid(evidence, league_player_rows=rows)
    pullup_alias = derive_tendency_drivepullupmidrange(evidence, league_player_rows=rows)
    offscreen = derive_tendency_midoffscreenshot(evidence, league_player_rows=rows)
    spotup = derive_tendency_midspotupshot(evidence, league_player_rows=rows)

    assert all(result is not None for result in (contested, contested_alias, pullup, pullup_alias, offscreen, spotup))
    assert contested["value"] == contested_alias["value"]  # type: ignore[index]
    assert pullup["value"] == pullup_alias["value"]  # type: ignore[index]
    assert len({pullup["value"], offscreen["value"], spotup["value"]}) > 1  # type: ignore[index]
    assert all(
        any(key.startswith("pool_calibration=field-exact") for key in result["evidence_keys"])
        for result in (contested, contested_alias, pullup, pullup_alias)
        if result is not None
    )
    assert "range_decision_contract=MID_or_3PT_is_selected_before_offscreen_or_spotup" in offscreen["evidence_keys"]  # type: ignore[index]
    assert "range_decision_contract=MID_or_3PT_is_selected_before_offscreen_or_spotup" in spotup["evidence_keys"]  # type: ignore[index]


def test_midrange_action_tendencies_do_not_use_free_throw_percentage_as_action_authorship() -> None:
    rows = _population_rows()
    low_ft = _generic_midrange_evidence()
    high_ft = copy.deepcopy(low_ft)
    low_ft.per_game["ft_percent"] = 0.30
    high_ft.per_game["ft_percent"] = 0.99

    rules = (
        derive_tendency_contestedjumpermid,
        derive_tendency_drivepullupmid,
        derive_tendency_midoffscreenshot,
        derive_tendency_midspotupshot,
    )
    assert [rule(low_ft, league_player_rows=rows)["value"] for rule in rules] == [  # type: ignore[index]
        rule(high_ft, league_player_rows=rows)["value"] for rule in rules  # type: ignore[index]
    ]


def test_historical_midshot_tendency_does_not_use_free_throw_percentage() -> None:
    rows = _population_rows()
    low_ft = _generic_midrange_evidence()
    high_ft = copy.deepcopy(low_ft)
    low_ft.shooting = {}
    high_ft.shooting = {}
    low_ft.per_game["ft_percent"] = 0.30
    high_ft.per_game["ft_percent"] = 0.99

    low = derive_tendency_midshot(low_ft, league_player_rows=rows)
    high = derive_tendency_midshot(high_ft, league_player_rows=rows)

    assert low is not None and high is not None
    assert low["value"] == high["value"]
    assert "recipe=historical_midrange_attempt_role" in low["evidence_keys"]
    assert "per_game.ft_percent" not in low["evidence_keys"]


def test_user_approved_offball_action_anchors_apply_to_mid_and_three_after_range_selection() -> None:
    expected = {
        "thompkl01": (95, 95),
        "hamilri01": (100, 5),
        "curryst01": (100, 25),
        "millere01": (100, 13),
        "onealsh01": (0, 0),
        "abdulka01": (0, 0),
    }
    for player_id, (offscreen_value, spotup_value) in expected.items():
        evidence = _generic_midrange_evidence()
        evidence.season = 2025
        evidence.season_info["lg"] = "NBA"
        evidence.identity["player_id"] = player_id
        evidence.player_id = player_id
        mid_offscreen = derive_tendency_midoffscreenshot(evidence, league_player_rows=())
        three_offscreen = derive_tendency_3pointoffscreenshot(evidence, league_player_rows=())
        mid_spotup = derive_tendency_midspotupshot(evidence, league_player_rows=())
        three_spotup = derive_tendency_3pointspotupshot(evidence, league_player_rows=())
        assert mid_offscreen is not None and three_offscreen is not None
        assert mid_spotup is not None and three_spotup is not None
        assert mid_offscreen["value"] == three_offscreen["value"] == offscreen_value
        assert mid_spotup["value"] == three_spotup["value"] == spotup_value
