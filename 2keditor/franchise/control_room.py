from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nba2k_editor.franchise.draft_room import build_fantasy_draft_markdown
from nba2k_editor.franchise.llm_view import build_franchise_llm_markdown


@dataclass(frozen=True)
class FranchiseScreenContext:
    mode: str
    source_screens: tuple[str, ...]
    player_count: int
    team_count: int
    target_executable: str
    runtime_status: str


def build_franchise_screen_context(model: Any) -> FranchiseScreenContext:
    loaded = getattr(model, "loaded_items", {})
    runtime_status = model.runtime_status_text() if hasattr(model, "runtime_status_text") else "unknown"
    return FranchiseScreenContext(
        mode="read_only_screen_context",
        source_screens=("Players", "Teams"),
        player_count=len(loaded.get("Players", {})),
        team_count=len(loaded.get("Teams", {})),
        target_executable=str(getattr(model, "target_executable", "")),
        runtime_status=str(runtime_status),
    )


def build_screen_context_markdown(model: Any) -> str:
    context = build_franchise_screen_context(model)
    return "\n".join(
        (
            "## Screen Context: loaded Players and Teams",
            f"Mode: {context.mode}",
            f"Target: {context.target_executable}",
            f"Runtime: {context.runtime_status}",
            f"Loaded Players: {context.player_count}",
            f"Loaded Teams: {context.team_count}",
        )
    )


def build_franchise_control_room_markdown(
    model: Any,
    *,
    user_team_index: int = 0,
    team_count: int = 30,
    current_pick_number: int = 1,
    profile_dir: str | Path = Path("nba2k_editor") / "franchise" / "team_profiles",
) -> str:
    return "\n\n".join(
        (
            "# Franchise Manager Control Room",
            build_screen_context_markdown(model),
            "## Team Profiles\nTeam Profiles: team_00_profile.md through team_29_profile.md",
            "## Franchise Workflow\nFantasy Draft Room: one workflow\nFuture franchise decisions: trades, rotations, contracts, scouting, and season actions",
            build_franchise_llm_markdown(model),
            build_fantasy_draft_markdown(
                model,
                user_team_index=user_team_index,
                team_count=team_count,
                current_pick_number=current_pick_number,
                profile_dir=profile_dir,
            ),
            "No game-memory write, save, import, apply is performed by this control room markdown.",
        )
    )
