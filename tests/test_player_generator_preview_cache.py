from __future__ import annotations

import sys
from importlib import import_module
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

display = import_module("display")


def _state(*, season: str = "2025", players: tuple[str, ...] | None = None) -> Any:
    labels = players or (
        "Player One | AAA | p1",
        "Player Two | BBB | p2",
    )
    return display.GeneratorDisplayState(
        source_loaded=True,
        seasons=("2025", "2026"),
        selected_season=season,
        league_filters=("All leagues",),
        selected_league="All leagues",
        position_filters=("All positions",),
        selected_position="All positions",
        source_team_filters=("All source teams",),
        selected_source_team="All source teams",
        players=labels,
        selected_player=labels[0],
        status="Loaded",
    )


def _install_fake_generator(monkeypatch):
    calls = {"context": 0, "generate": 0, "selected_leagues": []}

    contracts = ModuleType("contracts")

    class GeneratorInputContract:
        def __init__(self, *, season, source_root, output_target, selected_league=None):
            self.season = season
            self.source_root = source_root
            self.output_target = output_target
            self.selected_league = selected_league

    class OutputTarget:
        PREVIEW = "preview"

    setattr(contracts, "GeneratorInputContract", GeneratorInputContract)
    setattr(contracts, "OutputTarget", OutputTarget)

    generator = ModuleType("player_generator")

    def season_context_index(contract):
        calls["context"] += 1
        calls["selected_leagues"].append(contract.selected_league)
        return contract.season

    def generate_player_proposals_from_index(season_index):
        calls["generate"] += 1
        proposals = (
            SimpleNamespace(player_id="p1", team="AAA", identity={}, field_candidates=()),
            SimpleNamespace(player_id="p2", team="BBB", identity={}, field_candidates=()),
        )
        return SimpleNamespace(proposals=proposals, season=season_index)

    setattr(generator, "season_context_index", season_context_index)
    setattr(generator, "generate_player_proposals_from_index", generate_player_proposals_from_index)
    monkeypatch.setitem(sys.modules, "contracts", contracts)
    monkeypatch.setitem(sys.modules, "player_generator", generator)
    monkeypatch.setattr(display, "_ensure_generator_import_path", lambda: None)
    monkeypatch.setattr(display, "update_generator_display_selection", lambda state, **_kwargs: state)
    return calls


def test_repeated_display_preview_reuses_full_season_proposal_cache(monkeypatch) -> None:
    calls = _install_fake_generator(monkeypatch)

    first = display.generate_generator_preview_display_state(_state())
    second = display.generate_generator_preview_display_state(first)

    assert calls == {"context": 1, "generate": 1, "selected_leagues": ["All leagues"]}
    assert first.proposal_cache_season == "2025"
    assert first.proposal_cache_league == "All leagues"
    assert len(first.proposal_cache) == 2
    assert second.proposal_cache is first.proposal_cache
    assert tuple(proposal.player_id for proposal in second.generated_proposals) == ("p1", "p2")


def test_filter_only_display_preview_refilters_cache_without_regeneration(monkeypatch) -> None:
    calls = _install_fake_generator(monkeypatch)
    first = display.generate_generator_preview_display_state(_state())
    filtered = replace(
        first,
        players=("Player Two | BBB | p2",),
        selected_player="Player Two | BBB | p2",
        generated_proposals=(),
        player_rows=(),
    )

    second = display.generate_generator_preview_display_state(filtered)

    assert calls == {"context": 1, "generate": 1, "selected_leagues": ["All leagues"]}
    assert second.proposal_cache is first.proposal_cache
    assert tuple(proposal.player_id for proposal in second.generated_proposals) == ("p2",)


def test_display_preview_rebuilds_cache_for_a_different_season(monkeypatch) -> None:
    calls = _install_fake_generator(monkeypatch)
    first = display.generate_generator_preview_display_state(_state())
    next_season = replace(first, selected_season="2026", proposal_cache_season="2025")

    second = display.generate_generator_preview_display_state(next_season)

    assert calls == {
        "context": 2,
        "generate": 2,
        "selected_leagues": ["All leagues", "All leagues"],
    }
    assert second.proposal_cache_season == "2026"


def test_display_preview_rebuilds_cache_and_contract_for_a_different_league(monkeypatch) -> None:
    calls = _install_fake_generator(monkeypatch)
    first = display.generate_generator_preview_display_state(_state())
    aba = replace(
        first,
        league_filters=("All leagues", "ABA", "NBA"),
        selected_league="ABA",
    )

    second = display.generate_generator_preview_display_state(aba)

    assert calls == {
        "context": 2,
        "generate": 2,
        "selected_leagues": ["All leagues", "ABA"],
    }
    assert second.proposal_cache_season == "2025"
    assert second.proposal_cache_league == "ABA"
