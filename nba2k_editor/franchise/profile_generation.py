from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.llm_client import LLMClient
from nba2k_editor.franchise.llm_tasks import (
    FranchiseLlmTask,
    build_franchise_llm_task,
    franchise_team_context,
    franchise_team_profile_directory,
    run_franchise_llm_task,
)
from nba2k_editor.franchise.llm_view import build_franchise_llm_view, franchise_roster_payload_for_team
from nba2k_editor.franchise.models import FranchiseRecord, FranchiseTeamOption


@dataclass(frozen=True)
class TeamProfileGenerationRequest:
    team_index: int
    team_label: str
    gm_control: str
    task: FranchiseLlmTask


@dataclass(frozen=True)
class GeneratedTeamProfile:
    team_index: int
    team_label: str
    gm_control: str
    organizational_identity: str
    owner: str
    general_manager: str
    coach: str
    scout: str
    raw_response: str


def team_profile_path(record: FranchiseRecord, team_index: int) -> Path:
    directory = franchise_team_profile_directory(record)
    return directory / f"team_{int(team_index):02d}_profile.md"


def team_profile_is_valid(record: FranchiseRecord, team: FranchiseTeamOption) -> bool:
    path = team_profile_path(record, team.team_index)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    gm_control = "human" if int(team.team_index) == int(record.setup.user_team_index) else "llm"
    gm_heading = "Human-controlled" if gm_control == "human" else "LLM-controlled"
    headings = (
        "## Organizational Identity",
        "## Owner (LLM-controlled)",
        f"## General Manager ({gm_heading})",
        "## Coach (LLM-controlled)",
        "## Scout (LLM-controlled)",
    )
    required_markers = (
        f"team_index: {int(team.team_index)}",
        f"team_label: {json.dumps(team.label)}",
        f"gm_control: {gm_control}",
        "status: active",
        *headings,
    )
    if not all(marker in text for marker in required_markers):
        return False
    for position, heading in enumerate(headings):
        section_start = text.find(heading) + len(heading)
        section_end = text.find(headings[position + 1], section_start) if position + 1 < len(headings) else len(text)
        if not text[section_start:section_end].strip():
            return False
    return True


def missing_team_profile_indexes(record: FranchiseRecord) -> tuple[int, ...]:
    return tuple(
        int(team.team_index)
        for team in record.team_options
        if not team_profile_is_valid(record, team)
    )


def team_profiles_complete(record: FranchiseRecord) -> bool:
    return bool(record.franchise_id and record.profile_directory and record.team_options) and not missing_team_profile_indexes(record)


def build_team_profile_generation_prompt(
    record: FranchiseRecord,
    *,
    team_index: int,
    team_label: str,
    roster: Iterable[dict[str, object]],
) -> str:
    gm_control = "human" if int(team_index) == int(record.setup.user_team_index) else "llm"
    gm_rule = (
        "The human user is this team's General Manager. Do not invent an autonomous GM persona; describe how the Owner, Coach, and Scout work with the human GM."
        if gm_control == "human"
        else "Create a persistent LLM-controlled General Manager identity for this CPU-controlled team."
    )
    payload = {
        "task": "generate_persistent_franchise_team_profile",
        "rules": [
            "Create a distinct persistent staff identity for this one franchise team.",
            "Owner, Coach, and Scout are LLM-controlled on every team.",
            gm_rule,
            "Ground basketball context in the supplied true simulation year, team label, and current roster.",
            "Do not invent player facts, contracts, transactions, records, or staff employment facts that are not supplied.",
            "The profile persists across phases and seasons, so write durable identities, decision styles, priorities, tensions, and working relationships rather than a one-turn recommendation.",
            "Return only valid JSON. No markdown and no prose outside JSON.",
        ],
        "franchise": {
            "franchise_id": record.franchise_id,
            "true_sim_year": record.setup.start_year,
            "user_team_index": record.setup.user_team_index,
            "fantasy_draft": record.setup.fantasy_draft,
        },
        "team": {
            "team_index": int(team_index),
            "team_label": str(team_label),
            "gm_control": gm_control,
            "current_roster": tuple(roster),
        },
        "required_json_schema": {
            "team_index": int(team_index),
            "team_label": str(team_label),
            "gm_control": gm_control,
            "organizational_identity": "durable team identity and priorities",
            "owner": "persistent Owner identity, goals, constraints, and management style",
            "general_manager": "human-GM working relationship when gm_control is human; otherwise persistent LLM GM identity and roster-building philosophy",
            "coach": "persistent Coach identity, system, priorities, and relationship with the GM",
            "scout": "persistent Scout identity, evaluation philosophy, biases, and relationship with the GM",
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_team_profile_generation_requests(
    record: FranchiseRecord,
    model: object,
    *,
    team_indexes: Iterable[int] | None = None,
) -> tuple[TeamProfileGenerationRequest, ...]:
    if not record.franchise_id or not record.profile_directory:
        raise ValueError("franchise-scoped team profile storage is not configured")
    requested_indexes = (
        {int(index) for index in team_indexes}
        if team_indexes is not None
        else set(missing_team_profile_indexes(record))
    )
    view = build_franchise_llm_view(model)
    requests: list[TeamProfileGenerationRequest] = []
    for team in record.team_options:
        team_index = int(team.team_index)
        if team_index not in requested_indexes:
            continue
        gm_control = "human" if team_index == int(record.setup.user_team_index) else "llm"
        context = franchise_team_context(record, team_index, team_label=team.label)
        prompt = build_team_profile_generation_prompt(
            record,
            team_index=team_index,
            team_label=team.label,
            roster=franchise_roster_payload_for_team(view.roster_slots, team_index),
        )
        requests.append(
            TeamProfileGenerationRequest(
                team_index=team_index,
                team_label=team.label,
                gm_control=gm_control,
                task=build_franchise_llm_task(
                    context,
                    task_name="generate_persistent_franchise_team_profile",
                    prompt=prompt,
                    system_prompt="Return only valid JSON for the requested persistent NBA2K franchise team profile.",
                ),
            )
        )
    unknown_indexes = requested_indexes.difference(request.team_index for request in requests)
    if unknown_indexes:
        raise ValueError(f"profile generation requested teams outside this franchise: {tuple(sorted(unknown_indexes))}")
    return tuple(requests)


def _response_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(line for line in stripped.splitlines() if not line.strip().startswith("```")).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM profile response did not contain a JSON object")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM profile response JSON must be an object")
    return payload


def generated_team_profile_from_response(
    request: TeamProfileGenerationRequest,
    response: str,
) -> GeneratedTeamProfile:
    payload = _response_object(response)
    required_text = (
        "team_label",
        "gm_control",
        "organizational_identity",
        "owner",
        "general_manager",
        "coach",
        "scout",
    )
    if "team_index" not in payload:
        raise ValueError("LLM profile response missing team_index")
    for key in required_text:
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"LLM profile response missing {key}")
    if int(str(payload["team_index"])) != int(request.team_index):
        raise ValueError("LLM profile response team_index does not match requested team")
    if str(payload["team_label"]).strip() != request.team_label:
        raise ValueError("LLM profile response team_label does not match requested team")
    gm_control = str(payload["gm_control"]).strip().casefold()
    if gm_control != request.gm_control:
        raise ValueError("LLM profile response gm_control does not match franchise role ownership")
    return GeneratedTeamProfile(
        team_index=request.team_index,
        team_label=request.team_label,
        gm_control=gm_control,
        organizational_identity=str(payload["organizational_identity"]).strip(),
        owner=str(payload["owner"]).strip(),
        general_manager=str(payload["general_manager"]).strip(),
        coach=str(payload["coach"]).strip(),
        scout=str(payload["scout"]).strip(),
        raw_response=response,
    )


def render_generated_team_profile(profile: GeneratedTeamProfile) -> str:
    gm_heading = "Human-controlled" if profile.gm_control == "human" else "LLM-controlled"
    return "\n".join(
        (
            "---",
            f"name: {json.dumps(profile.team_label + ' Franchise Staff')}",
            f"team_index: {profile.team_index}",
            f"team_label: {json.dumps(profile.team_label)}",
            f"gm_control: {profile.gm_control}",
            "status: active",
            "---",
            f"# {profile.team_label} Franchise Staff",
            "",
            "## Organizational Identity",
            profile.organizational_identity,
            "",
            "## Owner (LLM-controlled)",
            profile.owner,
            "",
            f"## General Manager ({gm_heading})",
            profile.general_manager,
            "",
            "## Coach (LLM-controlled)",
            profile.coach,
            "",
            "## Scout (LLM-controlled)",
            profile.scout,
            "",
        )
    )


def write_generated_team_profile(record: FranchiseRecord, profile: GeneratedTeamProfile) -> Path:
    path = team_profile_path(record, profile.team_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(render_generated_team_profile(profile), encoding="utf-8")
    temporary_path.replace(path)
    return path


def generate_team_profiles(
    record: FranchiseRecord,
    requests: Iterable[TeamProfileGenerationRequest],
    *,
    client: Any | None = None,
) -> tuple[GeneratedTeamProfile, ...]:
    active_client = client or LLMClient.for_franchise_gm()
    generated: list[GeneratedTeamProfile] = []
    for request in requests:
        response = run_franchise_llm_task(request.task, client=active_client)
        profile = generated_team_profile_from_response(request, response)
        write_generated_team_profile(record, profile)
        generated.append(profile)
    return tuple(generated)


def generate_missing_team_profiles(
    record: FranchiseRecord,
    model: object,
    *,
    client: Any | None = None,
) -> tuple[GeneratedTeamProfile, ...]:
    requests = build_team_profile_generation_requests(record, model)
    return generate_team_profiles(record, requests, client=client)
