from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from nba2k_editor.franchise.draft_room import DraftPoolPlayer, DraftPosition
from nba2k_editor.franchise.llm_client import LLMClient
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
) -> LlmDraftPickResult:
    client = LLMClient()
    if not client.available():
        raise RuntimeError(
            "LLM unavailable. Start Hermes API Server on 127.0.0.1:8642 and make API_SERVER_KEY available, "
            "or set FRANCHISE_HERMES_API_KEY."
        )
    prompt = build_fantasy_draft_pick_prompt(
        record=record,
        position=position,
        available_players=tuple(available_players),
        drafted_picks=tuple(drafted_picks),
    )
    response = client.generate(prompt)
    parsed = parse_fantasy_draft_pick_response(response)
    return LlmDraftPickResult(
        response=response,
        selected_player_index=int(str(parsed["selected_player_index"])),
        selected_player_label=str(parsed["selected_player_label"]),
        rationale=str(parsed.get("rationale") or ""),
    )
