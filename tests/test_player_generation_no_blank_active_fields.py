from __future__ import annotations

import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules import RuleValue, _complete_required_rule_fields  # type: ignore[import-not-found]  # noqa: E402
from display import _nonblank_display_value  # type: ignore[import-not-found]  # noqa: E402


def test_active_rule_completion_emits_no_blank_attribute_or_tendency() -> None:
    existing = RuleValue(
        value=88,
        source_rule="exact_formula",
        evidence_keys=("advanced.dws",),
    )
    result = _complete_required_rule_fields(
        {"Attributes/INTERIORDEFENSE": existing},
        {
            "Attributes/INTERIORDEFENSE",
            "Attributes/HANDS",
            "Tendencies/TOUCHES",
        },
    )

    assert result.unresolved_fields == ()
    assert set(result.values) == {
        "Attributes/INTERIORDEFENSE",
        "Attributes/HANDS",
        "Tendencies/TOUCHES",
    }
    assert result.values["Attributes/INTERIORDEFENSE"] is existing
    assert result.values["Attributes/HANDS"].value == 25
    assert result.values["Tendencies/TOUCHES"].value == 0
    for key in ("Attributes/HANDS", "Tendencies/TOUCHES"):
        completed = result.values[key]
        assert completed.source_rule == "required_active_field_set_value"
        assert "blank_prevention=active_field_must_resolve" in completed.evidence_keys
        assert "stale_game_value_allowed=false" in completed.evidence_keys


def test_generated_table_cells_never_render_blank() -> None:
    assert _nonblank_display_value(None) == "N/A"
    assert _nonblank_display_value("") == "N/A"
    assert _nonblank_display_value("   ") == "N/A"
    assert _nonblank_display_value(0) == "0"
    assert _nonblank_display_value(25) == "25"
