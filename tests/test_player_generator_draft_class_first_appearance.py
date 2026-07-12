from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generator import DraftClassMode, generate_draft_class_proposals  # type: ignore[import-not-found]
import display  # type: ignore[import-not-found]

SOURCE_ROOT = GENERATOR_DIR / "NBA Player Data"


def _names(draft_class) -> set[str]:
    return {str(proposal.identity.get("player") or "") for proposal in draft_class.proposals}


def test_first_appearance_1948_class_is_1948_minus_1947() -> None:
    draft_class = generate_draft_class_proposals(
        1947,
        mode=DraftClassMode.FIRST_APPEARANCE,
        source_root=SOURCE_ROOT,
    )

    names = _names(draft_class)
    assert draft_class.rookie_season == 1948
    assert len(draft_class.proposals) == 98
    assert "Warren Ajax" in names
    assert "John Abramovic" not in names
    assert all(proposal.identity["draft_class_mode"] == "first_appearance" for proposal in draft_class.proposals)
    assert all(proposal.identity["draft_class_base_season"] == 1947 for proposal in draft_class.proposals)


def test_first_appearance_1949_class_subtracts_1947_and_1948() -> None:
    class_1948 = generate_draft_class_proposals(
        1947,
        mode=DraftClassMode.FIRST_APPEARANCE,
        source_root=SOURCE_ROOT,
    )
    class_1949 = generate_draft_class_proposals(
        1948,
        mode=DraftClassMode.FIRST_APPEARANCE,
        source_root=SOURCE_ROOT,
    )

    names_1948 = _names(class_1948)
    names_1949 = _names(class_1949)
    assert class_1949.rookie_season == 1949
    assert len(class_1949.proposals) == 114
    assert "Len Alterman" in names_1949
    assert "Warren Ajax" not in names_1949
    assert names_1948.isdisjoint(names_1949)


def test_first_appearance_can_use_explicit_non_1947_base_season() -> None:
    draft_class = generate_draft_class_proposals(
        1898,
        mode=DraftClassMode.FIRST_APPEARANCE,
        source_root=SOURCE_ROOT,
        base_season=1898,
    )

    assert draft_class.rookie_season == 1899
    assert all(proposal.identity["draft_class_base_season"] == 1898 for proposal in draft_class.proposals)


def test_draft_class_import_uses_draft_class_snapshot_target_items() -> None:
    candidate = SimpleNamespace(field_key="Vitals/FIRSTNAME", display_value="Rookie")
    proposal = SimpleNamespace(
        player_id="rookie01",
        team="BOS",
        identity={"player": "Rookie One"},
        field_candidates=(candidate,),
    )
    state = display.GeneratorDisplayState(
        source_loaded=True,
        seasons=("1947",),
        selected_season="1947",
        league_filters=("All leagues",),
        selected_league="All leagues",
        position_filters=("All positions",),
        selected_position="All positions",
        source_team_filters=("All source teams",),
        selected_source_team="All source teams",
        players=(),
        selected_player="",
        status="built",
        generated_proposals=(proposal,),
        preview_target="Draft Class",
    )

    class Model:
        def __init__(self) -> None:
            self.snapshot = None
            self.target_items = None

        def player_items_for_team_filter(self, selected):
            assert selected == "Draft Class"
            return {"Slot 0": SimpleNamespace(domain="Players", index=0, address=0x2000)}

        def apply_player_roster_snapshot(self, snapshot, *, target_items, progress_callback=None):
            self.snapshot = snapshot
            self.target_items = tuple(target_items)
            return {"succeeded": 1, "failed": 0, "skipped": 0}

    model = Model()
    result = display.import_draft_class_display_state(model, state)

    assert model.snapshot is not None
    assert model.target_items is not None
    assert model.snapshot["domain"] == "Players"
    assert model.snapshot["records"][0]["fields"] == {"Vitals/FIRSTNAME": {"display_value": "Rookie"}}
    assert model.target_items[0].domain == "Players"
    assert "Imported 1/1 generated draft players to Draft Class" in result.status
