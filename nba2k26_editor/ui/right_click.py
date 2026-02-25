"""Deprecated shim for right-click context menu helpers.

Use ``nba2k_editor.ui.context_menu`` instead.
"""
from __future__ import annotations

import warnings

from .context_menu import attach_player_context_menu, attach_team_context_menu

warnings.warn(
    "nba2k_editor.ui.right_click is deprecated; use nba2k_editor.ui.context_menu.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["attach_player_context_menu", "attach_team_context_menu"]
