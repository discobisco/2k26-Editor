from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.draft_room import TeamProfile
from nba2k_editor.franchise.growth_model import growth_facts_dict
from nba2k_editor.franchise.llm_view import FranchiseRosterSlot, build_franchise_llm_view
from nba2k_editor.franchise.llm_tasks import DEFAULT_TEAM_PROFILE_DIR, FranchiseLlmTask, build_franchise_llm_task, franchise_team_context, run_franchise_llm_task, team_profile_payload
from nba2k_editor.franchise.models import FranchiseRecord, TeamRecommendation


@dataclass(frozen=True)
class TeamRecommendationRequest:
    team_index: int
    team_label: str
    task: FranchiseLlmTask


def _roster_for_team(roster_slots: Iterable[FranchiseRosterSlot], team_index: int) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "player_index": slot.player_index,
            "player_label": slot.player_label,
            "team_slot": slot.team_slot,
            "team_slot_field": slot.team_slot_field,
            "offseason_progression": growth_facts_dict(slot.offseason_progression_facts),
        }
        for slot in roster_slots
        if int(slot.team_index) == int(team_index)
    )


def build_team_recommendation_prompt(
    record: FranchiseRecord,
    *,
    team_index: int,
    team_label: str,
    roster: Iterable[dict[str, object]],
    profile: TeamProfile,
) -> str:
    payload = {
        "task": "franchise_team_gm_recommendation",
        "rules": [
            "You are acting only as the external LLM front office for the requested team.",
            "The user controls all teams in NBA 2K; recommend one action only and do not claim it was applied.",
            "Return only valid JSON. No markdown. No prose outside JSON.",
            "Do not recommend drafting, trading, or signing functional filler players such as forty overall, A Z, or similar while any real player is available.",
            "Use true_sim_year for era reasoning, not the in-game year label.",
            "Use offseason_progression only for offseason player progression/development context, not fantasy draft decisions.",
        ],
        "franchise": {
            "true_sim_year": record.setup.start_year,
            "user_team_index": record.setup.user_team_index,
            "llm_gm_team_indexes": list(record.setup.llm_gm_team_indexes),
            "fantasy_draft": record.setup.fantasy_draft,
        },
        "team": {
            "team_index": int(team_index),
            "team_label": str(team_label),
            "staff_profile": team_profile_payload(profile),
            "current_roster": tuple(roster),
        },
        "allowed_recommendation_types": [
            "draft_strategy",
            "trade_target",
            "trade_block",
            "signing_target",
            "release_candidate",
            "rotation_need",
            "scouting_focus",
            "season_goal",
            "owner_constraint",
            "offseason_player_progression",
            "no_action",
        ],
        "required_json_schema": {
            "team_index": int(team_index),
            "team_label": str(team_label),
            "recommended_action": "one concrete recommendation only",
            "reasoning": "short explanation grounded in roster/profile/era",
            "owner_approval_required": "boolean",
            "blocked_reason": "empty string if not blocked; otherwise why the action should not proceed",
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_team_recommendation_requests(
    record: FranchiseRecord,
    model: object,
    *,
    profile_dir: str | Path = DEFAULT_TEAM_PROFILE_DIR,
    progression_season: int | None = None,
    growth_data_root: str | Path | None = None,
) -> tuple[TeamRecommendationRequest, ...]:
    selected_progression_season = record.setup.start_year if progression_season is None else int(progression_season)
    view = build_franchise_llm_view(model, progression_season=selected_progression_season, growth_data_root=growth_data_root)
    requests: list[TeamRecommendationRequest] = []
    for team_index in record.setup.llm_gm_team_indexes:
        index = int(team_index)
        context = franchise_team_context(record, index, profile_dir=profile_dir)
        roster = _roster_for_team(view.roster_slots, index)
        prompt = build_team_recommendation_prompt(
            record,
            team_index=index,
            team_label=context.team_label,
            roster=roster,
            profile=context.profile,
        )
        requests.append(
            TeamRecommendationRequest(
                team_index=index,
                team_label=context.team_label,
                task=build_franchise_llm_task(
                    context,
                    task_name="franchise_team_gm_recommendation",
                    prompt=prompt,
                    system_prompt="Return only valid JSON for the requested NBA2K franchise team-GM recommendation.",
                ),
            )
        )
    return tuple(requests)


def parse_team_recommendation_response(text: str) -> dict[str, object]:
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
    for key in ("team_index", "team_label", "recommended_action", "reasoning", "owner_approval_required", "blocked_reason"):
        if key not in payload:
            raise ValueError(f"LLM response missing {key}")
    return payload


def _json_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    text = str(value).strip().casefold()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0", ""}:
        return False
    raise ValueError("owner_approval_required must be boolean")


def recommendation_from_response(request: TeamRecommendationRequest, response: str) -> TeamRecommendation:
    parsed = parse_team_recommendation_response(response)
    parsed_team_index = int(str(parsed["team_index"]))
    if parsed_team_index != int(request.team_index):
        raise ValueError("LLM response team_index does not match requested team")
    return TeamRecommendation(
        team_index=request.team_index,
        team_label=str(parsed["team_label"]),
        recommended_action=str(parsed["recommended_action"]),
        reasoning=str(parsed["reasoning"]),
        owner_approval_required=_json_bool(parsed["owner_approval_required"]),
        blocked_reason=str(parsed["blocked_reason"]),
        raw_llm_response=response,
        status="pending",
    )


def run_team_recommendation_request(
    request: TeamRecommendationRequest,
    *,
    client: Any | None = None,
) -> TeamRecommendation:
    response = run_franchise_llm_task(request.task, client=client)
    return recommendation_from_response(request, response)


def run_team_recommendation_requests(
    requests: Iterable[TeamRecommendationRequest],
    *,
    client: Any | None = None,
) -> tuple[TeamRecommendation, ...]:
    return tuple(run_team_recommendation_request(request, client=client) for request in requests)
