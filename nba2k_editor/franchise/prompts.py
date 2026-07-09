from __future__ import annotations

import json
from typing import Iterable

from nba2k_editor.franchise.draft_room import DraftPoolPlayer, DraftPosition
from nba2k_editor.franchise.models import FantasyDraftStoredPick, FranchiseRecord


def build_fantasy_draft_pick_prompt(
    *,
    record: FranchiseRecord,
    position: DraftPosition,
    available_players: Iterable[DraftPoolPlayer],
    drafted_picks: Iterable[FantasyDraftStoredPick],
    max_players: int = 80,
) -> str:
    available = tuple(available_players)[:max_players]
    picks = tuple(drafted_picks)[-20:]
    payload = {
        "task": "fantasy_draft_pick",
        "rules": [
            "You are acting only as the GM for the on-clock team.",
            "The user controls the user_team_index team; never act for that team.",
            "Pick exactly one player from available_players.",
            "Do not pick functional filler players such as forty overall, A Z, or similar while any real player is available.",
            "Return only valid JSON. No markdown. No prose outside JSON.",
        ],
        "franchise": {
            "true_start_year": record.setup.start_year,
            "user_team_index": record.setup.user_team_index,
            "llm_gm_team_indexes": list(record.setup.llm_gm_team_indexes),
            "fantasy_draft": record.setup.fantasy_draft,
        },
        "current_pick": {
            "pick_number": position.pick_number,
            "round_number": position.round_number,
            "team_index": position.team_index,
            "team_label": position.team_label,
        },
        "recent_picks": [
            {
                "pick_number": pick.pick_number,
                "team_index": pick.team_index,
                "player_index": pick.player_index,
                "player_label": pick.player_label,
            }
            for pick in picks
        ],
        "available_players": [
            {
                "player_index": player.player_index,
                "player_label": player.player_label,
                "source_team_index": player.source_team_index,
                "source_slot_field": player.source_slot_field,
            }
            for player in available
        ],
        "required_json_schema": {
            "team_index": position.team_index,
            "pick_number": position.pick_number,
            "selected_player_index": "integer from available_players",
            "selected_player_label": "exact player_label from available_players",
            "rationale": "short reason for this pick",
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def parse_fantasy_draft_pick_response(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain JSON object")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON must be an object")
    for key in ("team_index", "pick_number", "selected_player_index", "selected_player_label", "rationale"):
        if key not in payload:
            raise ValueError(f"LLM response missing {key}")
    return payload
