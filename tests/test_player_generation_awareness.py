from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import derive_formula_rule_values, derive_neighbor_rule_values  # type: ignore[import-not-found]
from stat_neighbor_framework import PositionSelection  # type: ignore[import-not-found]


def _evidence(*, ows: object, dws: object) -> PlayerEvidence:
    return PlayerEvidence(
        player_id="test",
        season=2025,
        team="TST",
        identity={},
        season_info={"pos": "PG"},
        per_game={"pts_per_game": 99.0},
        totals={},
        per_36={},
        per_100={},
        advanced={
            "ows": ows,
            "dws": dws,
            "ts_percent": 0.99,
            "dbpm": 99.0,
        },
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={"d_rtg": 1.0},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )


def _row(*, ows: float, dws: float) -> dict[str, float]:
    return {"advanced.ows": ows, "advanced.dws": dws}


def test_offensive_and_defensive_awareness_use_only_ows_and_dws() -> None:
    values = derive_formula_rule_values(
        _evidence(ows=2.0, dws=4.0),
        league_player_rows=(
            _row(ows=1.0, dws=1.0),
            _row(ows=2.0, dws=2.0),
            _row(ows=4.0, dws=4.0),
        ),
    )

    offense = values["Attributes/OFFENSIVECONSISTENCY"]
    defense = values["Attributes/DEFENSECONSISTENCY"]
    assert offense.value == 74
    assert offense.source_rule == "derive_attribute_offensiveconsistency_ows"
    assert offense.evidence_keys == ("advanced.ows",)
    assert defense.value == 99
    assert defense.source_rule == "derive_attribute_defenseconsistency_dws"
    assert defense.evidence_keys == ("advanced.dws",)


def test_awareness_is_unresolved_without_its_win_share_source() -> None:
    rows = (_row(ows=1.0, dws=1.0),)

    missing_offense = derive_formula_rule_values(
        _evidence(ows=None, dws=1.0),
        league_player_rows=rows,
    )
    missing_defense = derive_formula_rule_values(
        _evidence(ows=1.0, dws=None),
        league_player_rows=rows,
    )

    assert "Attributes/OFFENSIVECONSISTENCY" not in missing_offense
    assert "Attributes/DEFENSECONSISTENCY" not in missing_defense


@dataclass(frozen=True)
class _Suggestion:
    value: int
    source_rule: str
    evidence_keys: tuple[str, ...]


class _NeighborModel:
    def suggestions_for_evidence(self, *, evidence: Any, positions: Any) -> dict[str, _Suggestion]:
        return {
            "Attributes/OFFENSIVECONSISTENCY": _Suggestion(25, "neighbor_offense", ("neighbor",)),
            "Attributes/DEFENSECONSISTENCY": _Suggestion(25, "neighbor_defense", ("neighbor",)),
            "Attributes/BALLCONTROL": _Suggestion(45, "neighbor_ballcontrol", ("neighbor",)),
        }


def test_awareness_is_not_authored_or_blended_by_neighbor_model() -> None:
    values = derive_neighbor_rule_values(
        _evidence(ows=2.0, dws=4.0),
        PositionSelection("PG", None, ("PG",), (("PG", 1.0),)),
        model=_NeighborModel(),
    )

    assert "Attributes/OFFENSIVECONSISTENCY" not in values
    assert "Attributes/DEFENSECONSISTENCY" not in values
    assert values["Attributes/BALLCONTROL"].value == 45
