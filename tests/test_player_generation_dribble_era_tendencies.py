from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

import player_rules_offense  # type: ignore[import-not-found]  # noqa: E402
from player_rules import RuleValue, _formula_has_live_input  # type: ignore[import-not-found]  # noqa: E402
from player_rules_offense import (  # type: ignore[import-not-found]  # noqa: E402
    derive_tendency_drivingbehindtheback,
    derive_tendency_drivingcrossover,
    derive_tendency_drivingdoublecrossover,
    derive_tendency_drivingdribblehesitation,
    derive_tendency_drivinghalfspin,
    derive_tendency_drivinginandout,
    derive_tendency_drivingspin,
    derive_tendency_drivingstepback,
    derive_tendency_eurosteplayup,
    derive_tendency_hopsteplayup,
    derive_tendency_nodrivingdribblemove,
    derive_tendency_setupdribble,
    derive_tendency_setupwithhesitation,
    derive_tendency_setupwithsizeup,
)


DRIBBLE_MOVE_CASES = (
    ("SETUPWITHHESITATION", derive_tendency_setupwithhesitation, 1942),
    ("SETUPWITHSIZEUP", derive_tendency_setupwithsizeup, 1967),
    ("DRIVINGCROSSOVER", derive_tendency_drivingcrossover, 1955),
    ("DRIVINGDOUBLECROSSOVER", derive_tendency_drivingdoublecrossover, 1990),
    ("DRIVINGSPIN", derive_tendency_drivingspin, 1955),
    ("DRIVINGHALFSPIN", derive_tendency_drivinghalfspin, 1999),
    ("DRIVINGSTEPBACK", derive_tendency_drivingstepback, 1970),
    ("DRIVINGBEHINDTHEBACK", derive_tendency_drivingbehindtheback, 1955),
    ("DRIVINGDRIBBLEHESITATION", derive_tendency_drivingdribblehesitation, 1942),
    ("DRIVINGINANDOUT", derive_tendency_drivinginandout, 1989),
    ("EUROSTEPLAYUP", derive_tendency_eurosteplayup, 2002),
    ("HOPSTEPLAYUP", derive_tendency_hopsteplayup, 2002),
)


@pytest.mark.parametrize(("field", "derive", "first_season"), DRIBBLE_MOVE_CASES)
def test_dribble_move_tendency_is_literal_zero_before_first_supported_season(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    derive,
    first_season: int,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(player_rules_offense, "_derive", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = derive(SimpleNamespace(season=first_season - 1), league_player_rows=("protected-row",))

    assert result == {
        "value": 0,
        "source_rule": f"derive_tendency_{field.lower()}_historical_introduction_gate",
        "evidence_keys": (
            f"season_ending_year={first_season - 1}",
            f"first_supported_season_ending_year={first_season}",
            "historically_unavailable_move_tendency=0",
            "post_threshold_formula_unchanged=true",
        ),
    }
    assert calls == []


DRIBBLE_MOVE_FIELD_KEYS = {
    "SETUPWITHHESITATION": "Tendencies/SETUPWITHHESITATION",
    "SETUPWITHSIZEUP": "Tendencies/SETUPWITHSIZEUP",
    "DRIVINGCROSSOVER": "Tendencies/DRIBBLECROSSOVER",
    "DRIVINGDOUBLECROSSOVER": "Tendencies/DRIVINGDOUBLECROSSOVER",
    "DRIVINGSPIN": "Tendencies/DRIBBLESPIN",
    "DRIVINGHALFSPIN": "Tendencies/DRIVINGHALFSPIN",
    "DRIVINGSTEPBACK": "Tendencies/DRIVINGSTEPBACK",
    "DRIVINGBEHINDTHEBACK": "Tendencies/DRIVINGBEHINDTHEBACK",
    "DRIVINGDRIBBLEHESITATION": "Tendencies/DRIVINGDRIBBLEHESITATION",
    "DRIVINGINANDOUT": "Tendencies/DRIVINGINANDOUT",
    "EUROSTEPLAYUP": "Tendencies/EUROSTEPLAYUP",
    "HOPSTEPLAYUP": "Tendencies/HOPSTEPLAYUP",
}


@pytest.mark.parametrize(("field", "derive", "first_season"), DRIBBLE_MOVE_CASES)
def test_dribble_move_historical_zero_is_retained_by_rule_assembly(
    field: str,
    derive,
    first_season: int,
) -> None:
    evidence = SimpleNamespace(season=first_season - 1)
    result = derive(evidence)
    assert result is not None
    value = RuleValue(
        value=result["value"],
        source_rule=result["source_rule"],
        evidence_keys=result["evidence_keys"],
    )

    assert _formula_has_live_input(
        evidence,
        DRIBBLE_MOVE_FIELD_KEYS[field],
        value,
        owner_module="offense",
    )


@pytest.mark.parametrize(("field", "derive", "first_season"), DRIBBLE_MOVE_CASES)
def test_dribble_move_tendency_uses_unchanged_formula_at_and_after_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    derive,
    first_season: int,
) -> None:
    expected = {
        "value": 73,
        "source_rule": "legacy_formula",
        "evidence_keys": ("legacy_evidence",),
    }
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_derive(*args, **kwargs):
        calls.append((args, kwargs))
        return expected

    monkeypatch.setattr(player_rules_offense, "_derive", fake_derive)
    rows = ("protected-row",)

    at_cutoff = derive(SimpleNamespace(season=first_season), league_player_rows=rows)
    after_cutoff = derive(SimpleNamespace(season=first_season + 1), league_player_rows=rows)

    assert at_cutoff is expected
    assert after_cutoff is expected
    assert len(calls) == 2
    for args, kwargs in calls:
        assert args[1] == field
        assert args[3] is rows
        assert kwargs == {"tendency": True}


def test_inverse_dribble_control_tendencies_are_not_era_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {
        "value": 61,
        "source_rule": "legacy_inverse_formula",
        "evidence_keys": ("legacy_inverse_evidence",),
    }
    calls: list[str] = []

    def fake_derive(_rule, field, *_args, **_kwargs):
        calls.append(field)
        return expected

    monkeypatch.setattr(player_rules_offense, "_derive", fake_derive)
    evidence = SimpleNamespace(season=1941)

    assert derive_tendency_setupdribble(evidence) is expected
    assert derive_tendency_nodrivingdribblemove(evidence) is expected
    assert calls == ["SETUPDRIBBLE", "NODRIVINGDRIBBLEMOVE"]
