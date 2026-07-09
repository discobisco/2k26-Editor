from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FranchiseSelectedRecord:
    label: str
    values: dict[str, str]


@dataclass(frozen=True)
class FranchiseRosterSlot:
    team_index: int
    team_label: str
    team_slot: int
    team_slot_field: str
    player_label: str
    player_index: int


@dataclass(frozen=True)
class FranchiseLLMView:
    mode: str
    source_screens: tuple[str, ...]
    target_executable: str
    runtime_status: str
    player_count: int
    team_count: int
    selected_player: FranchiseSelectedRecord | None
    selected_team: FranchiseSelectedRecord | None
    roster_slots: tuple[FranchiseRosterSlot, ...]


def _loaded_items(model: Any, domain: str) -> dict[str, Any]:
    return dict(getattr(model, "loaded_items", {}).get(domain, {}))


def _selected_item(model: Any, domain: str) -> Any | None:
    if hasattr(model, "selected_item"):
        return model.selected_item(domain)
    return getattr(model, "selected_items", {}).get(domain)


def _selected_label(item: Any | None) -> str:
    if item is None:
        return ""
    return str(getattr(item, "display_label", getattr(item, "label", "")))


def _string_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in values.items()}


def build_franchise_llm_view(model: Any) -> FranchiseLLMView:
    players = _loaded_items(model, "Players")
    teams = _loaded_items(model, "Teams")
    selected_player_item = _selected_item(model, "Players")
    selected_team_item = _selected_item(model, "Teams")
    selected_player = None
    if selected_player_item is not None and hasattr(model, "selected_player_detail_values"):
        selected_player = FranchiseSelectedRecord(_selected_label(selected_player_item), _string_values(model.selected_player_detail_values()))
    selected_team = None
    if selected_team_item is not None and hasattr(model, "selected_team_summary_values"):
        selected_team = FranchiseSelectedRecord(_selected_label(selected_team_item), _string_values(model.selected_team_summary_values()))
    roster_rows = model.player_roster_slot_items_for_team_items(tuple(teams.values())) if hasattr(model, "player_roster_slot_items_for_team_items") else ()
    roster_slots = tuple(
        FranchiseRosterSlot(
            team_index=int(placement["team_index"]),
            team_label=str(placement["team_label"]),
            team_slot=int(placement["team_slot"]),
            team_slot_field=str(placement["team_slot_field"]),
            player_label=str(getattr(player, "display_label", getattr(player, "label", ""))),
            player_index=int(getattr(player, "index")),
        )
        for player, placement in roster_rows
    )
    runtime_status = model.runtime_status_text() if hasattr(model, "runtime_status_text") else "unknown"
    return FranchiseLLMView(
        mode="read_only",
        source_screens=("Players", "Teams"),
        target_executable=str(getattr(model, "target_executable", "")),
        runtime_status=str(runtime_status),
        player_count=len(players),
        team_count=len(teams),
        selected_player=selected_player,
        selected_team=selected_team,
        roster_slots=roster_slots,
    )


def build_franchise_llm_markdown(model: Any) -> str:
    view = build_franchise_llm_view(model)
    lines = [
        "# Franchise Manager LLM View",
        "",
        "Mode: read-only",
        "Do not edit, write, save, or import from this context.",
        f"Target: {view.target_executable}",
        f"Runtime: {view.runtime_status}",
        f"Loaded Players: {view.player_count}",
        f"Loaded Teams: {view.team_count}",
        "",
        "## Selected Player",
    ]
    if view.selected_player is None:
        lines.append("None")
    else:
        lines.append(view.selected_player.label)
        lines.extend(f"{key}: {value}" for key, value in view.selected_player.values.items())
    lines.append("")
    lines.append("## Selected Team")
    if view.selected_team is None:
        lines.append("None")
    else:
        lines.append(view.selected_team.label)
        lines.extend(f"{key}: {value}" for key, value in view.selected_team.values.items())
    lines.append("")
    lines.append("## Roster Slots")
    if not view.roster_slots:
        lines.append("None")
    for slot in view.roster_slots:
        lines.append(f"Team {slot.team_index} {slot.team_label} {slot.team_slot_field}: {slot.player_label}")
    return "\n".join(lines)
