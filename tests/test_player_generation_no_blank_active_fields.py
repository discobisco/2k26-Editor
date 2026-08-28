from __future__ import annotations

import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from display import _nonblank_display_value  # type: ignore[import-not-found]  # noqa: E402


def test_generated_table_cells_never_render_blank() -> None:
    assert _nonblank_display_value(None) == "N/A"
    assert _nonblank_display_value("") == "N/A"
    assert _nonblank_display_value("   ") == "N/A"
    assert _nonblank_display_value(0) == "0"
    assert _nonblank_display_value(25) == "25"
