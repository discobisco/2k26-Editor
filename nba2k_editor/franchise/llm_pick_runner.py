from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.draft_room import DraftPoolPlayer, DraftPosition
from nba2k_editor.franchise.llm_tasks import build_franchise_llm_task, franchise_team_context, run_franchise_llm_task
from nba2k_editor.franchise.models import FantasyDraftStoredPick, FranchiseRecord
from nba2k_editor.franchise.prompts import build_fantasy_draft_pick_prompt, parse_fantasy_draft_pick_response


@dataclass(frozen=True)
class LlmDraftPickResult:
    response: str
    selected_player_index: int
    selected_player_label: str
    rationale: str


def run_llm_fantasy_draft_pick(
    *,
    record: FranchiseRecord,
    position: DraftPosition,
    available_players: Iterable[DraftPoolPlayer],
    drafted_picks: Iterable[FantasyDraftStoredPick],
    profile_dir: str | Path | None = None,
    client: Any | None = None,
) -> LlmDraftPickResult:
    context = franchise_team_context(record, position.team_index, team_label=position.team_label, profile_dir=profile_dir)
    prompt = build_fantasy_draft_pick_prompt(
        record=record,
        position=position,
        team_profile=context.profile,
        available_players=tuple(available_players),
        drafted_picks=tuple(drafted_picks),
    )
    task = build_franchise_llm_task(
        context,
        task_name="fantasy_draft_pick",
        prompt=prompt,
        system_prompt="Return only valid JSON for the requested NBA2K fantasy draft decision.",
    )
    response = run_franchise_llm_task(task, client=client)
    parsed = parse_fantasy_draft_pick_response(response)
    return LlmDraftPickResult(
        response=response,
        selected_player_index=int(str(parsed["selected_player_index"])),
        selected_player_label=str(parsed["selected_player_label"]),
        rationale=str(parsed.get("rationale") or ""),
    )
