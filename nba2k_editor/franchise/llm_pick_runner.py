from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.draft_room import (
    DraftPoolPlayer,
    DraftPosition,
    available_players as remaining_players,
    draft_position,
    draft_turn_owner,
    find_available_player,
    find_available_player_by_index,
    stored_pick_from_player,
)
from nba2k_editor.franchise.llm_tasks import build_franchise_llm_task, franchise_team_context, run_franchise_llm_task
from nba2k_editor.franchise.models import FantasyDraftState, FantasyDraftStoredPick, FranchiseRecord
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


def run_llm_fantasy_draft_picks_until_user(
    *,
    record: FranchiseRecord,
    state: FantasyDraftState,
    team_labels: dict[int, str],
    available_players: Iterable[DraftPoolPlayer],
    drafted_picks: Iterable[FantasyDraftStoredPick],
    profile_dir: str | Path | None = None,
    client: Any | None = None,
) -> tuple[FantasyDraftStoredPick, ...]:
    pool = tuple(available_players)
    picks = list(drafted_picks)
    generated: list[FantasyDraftStoredPick] = []
    pick_number = int(state.current_pick_number)
    while True:
        position = draft_position(
            pick_number,
            team_count=state.team_count,
            user_team_index=state.user_team_index,
            team_labels=team_labels,
            team_order=state.team_order,
        )
        owner = draft_turn_owner(position, record)
        if owner == "user":
            break
        if owner != "llm":
            raise ValueError(f"Draft pick {pick_number} is not controlled by an AI league team.")
        available = remaining_players(pool, picks)
        if not available:
            raise ValueError("No active players remain in the fantasy draft pool.")
        result = run_llm_fantasy_draft_pick(
            record=record,
            position=position,
            available_players=available,
            drafted_picks=picks,
            profile_dir=profile_dir,
            client=client,
        )
        player = find_available_player_by_index(available, (), result.selected_player_index)
        if player is None:
            player = find_available_player(available, (), result.selected_player_label)
        if player is None:
            raise ValueError("LLM selected a player that is not available")
        pick = stored_pick_from_player(
            player,
            position=position,
            picked_by="llm",
            raw_llm_response=result.response,
            rationale=result.rationale,
        )
        generated.append(pick)
        picks.append(pick)
        pick_number += 1
    return tuple(generated)


def validate_llm_fantasy_draft_pick_batch(
    *,
    record: FranchiseRecord,
    state: FantasyDraftState,
    team_labels: dict[int, str],
    pool: Iterable[DraftPoolPlayer],
    drafted_picks: Iterable[FantasyDraftStoredPick],
    generated_picks: Iterable[FantasyDraftStoredPick],
) -> tuple[FantasyDraftStoredPick, ...]:
    players = tuple(pool)
    picks = list(drafted_picks)
    generated = tuple(generated_picks)
    if not generated:
        raise ValueError("AI draft-pick batch is empty.")
    validated: list[FantasyDraftStoredPick] = []
    for offset, result in enumerate(generated):
        position = draft_position(
            state.current_pick_number + offset,
            team_count=state.team_count,
            user_team_index=state.user_team_index,
            team_labels=team_labels,
            team_order=state.team_order,
        )
        if draft_turn_owner(position, record) != "llm":
            raise ValueError("The draft pick changed before the AI results returned.")
        if result.pick_number != position.pick_number or result.team_index != position.team_index:
            raise ValueError("The AI draft-pick batch does not match the current draft order.")
        player = find_available_player_by_index(players, picks, result.player_index)
        if player is None:
            raise ValueError("AI selected a player that is not available")
        pick = stored_pick_from_player(
            player,
            position=position,
            picked_by="llm",
            raw_llm_response=result.raw_llm_response,
            rationale=result.rationale,
        )
        validated.append(pick)
        picks.append(pick)
    next_position = draft_position(
        state.current_pick_number + len(validated),
        team_count=state.team_count,
        user_team_index=state.user_team_index,
        team_labels=team_labels,
        team_order=state.team_order,
    )
    if draft_turn_owner(next_position, record) != "user":
        raise ValueError("AI draft picks stopped before the next user pick.")
    return tuple(validated)
