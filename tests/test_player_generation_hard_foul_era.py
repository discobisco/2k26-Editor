from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

import player_rules_defense  # type: ignore[import-not-found]  # noqa: E402
from player_rules_defense import derive_tendency_hardfoul  # type: ignore[import-not-found]  # noqa: E402


def _evidence(season: int) -> SimpleNamespace:
    return SimpleNamespace(
        season=season,
        season_info={"lg": "NBA"},
        source_context={},
        per_game={"g": 82.0},
        totals={"g": 82.0},

    )


def _base_result(score: float | None) -> dict[str, object]:
    result: dict[str, object] = {
        "value": 42,
        "source_rule": "derive_tendency_hardfoul",
        "evidence_keys": ("player_contact_evidence",),
    }
    if score is not None:
        result["score"] = score
    return result


def test_every_pre_1960_player_receives_maximum_hard_foul() -> None:
    for season in (1947, 1959):
        result = derive_tendency_hardfoul(_evidence(season), league_player_rows=())
        assert result is not None
        assert result["value"] == 100
        assert result["source_rule"] == "derive_tendency_hardfoul_universal_pre_1960_maximum"
        assert "scale_meaning=maximum_2K_propensity_not_literal_event_probability" in result["evidence_keys"]


def test_1960s_and_post_1980s_remain_unresolved_without_hard_foul_classification() -> None:
    for season in (1960, 1969, 1990, 2025):
        assert derive_tendency_hardfoul(_evidence(season), league_player_rows=()) is None


def test_1970s_1980s_bottom_quintile_is_the_explicit_exception(monkeypatch) -> None:
    monkeypatch.setattr(player_rules_defense, "_derive", lambda *args, **kwargs: _base_result(0.20))
    exception = derive_tendency_hardfoul(_evidence(1978), league_player_rows=())
    assert exception is not None
    assert exception["value"] == 42
    assert exception["source_rule"].endswith("_1970s_1980s_low_contact_exception")

    monkeypatch.setattr(player_rules_defense, "_derive", lambda *args, **kwargs: _base_result(0.21))
    maximum = derive_tendency_hardfoul(_evidence(1988), league_player_rows=())
    assert maximum is not None
    assert maximum["value"] == 100
    assert maximum["source_rule"] == "derive_tendency_hardfoul_1970s_1980s_most_players_maximum"


def test_missing_contact_score_does_not_invent_an_exception(monkeypatch) -> None:
    monkeypatch.setattr(player_rules_defense, "_derive", lambda *args, **kwargs: _base_result(None))
    result = derive_tendency_hardfoul(_evidence(1980), league_player_rows=())
    assert result is not None
    assert result["value"] == 100
    assert "exception_not_established=true" in result["evidence_keys"]
