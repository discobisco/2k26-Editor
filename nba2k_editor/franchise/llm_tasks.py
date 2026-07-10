from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nba2k_editor.franchise.draft_room import TeamProfile, load_team_profile
from nba2k_editor.franchise.llm_client import LLMClient
from nba2k_editor.franchise.models import FranchiseRecord


DEFAULT_TEAM_PROFILE_DIR = Path("nba2k_editor") / "franchise" / "team_profiles"


@dataclass(frozen=True)
class FranchiseTeamContext:
    team_index: int
    team_label: str
    profile: TeamProfile


@dataclass(frozen=True)
class FranchiseLlmTask:
    task_name: str
    team_index: int
    team_label: str
    profile: TeamProfile
    prompt: str
    system_prompt: str


def franchise_team_label(record: FranchiseRecord, team_index: int) -> str:
    for team in record.team_options:
        if int(team.team_index) == int(team_index):
            return str(team.label)
    return f"Team {int(team_index)}"


def team_profile_payload(profile: TeamProfile, max_chars: int = 6000) -> dict[str, object]:
    return {
        "exists": profile.exists,
        "name": profile.name,
        "path": profile.path,
        "body": profile.body[:max_chars],
    }


def franchise_team_context(
    record: FranchiseRecord,
    team_index: int,
    *,
    team_label: str | None = None,
    profile_dir: str | Path = DEFAULT_TEAM_PROFILE_DIR,
) -> FranchiseTeamContext:
    index = int(team_index)
    return FranchiseTeamContext(
        team_index=index,
        team_label=str(team_label or franchise_team_label(record, index)),
        profile=load_team_profile(index, profile_dir),
    )


def build_franchise_llm_task(
    context: FranchiseTeamContext,
    *,
    task_name: str,
    prompt: str,
    system_prompt: str,
) -> FranchiseLlmTask:
    return FranchiseLlmTask(
        task_name=task_name,
        team_index=context.team_index,
        team_label=context.team_label,
        profile=context.profile,
        prompt=prompt,
        system_prompt=system_prompt,
    )


def run_franchise_llm_task(task: FranchiseLlmTask, *, client: Any | None = None) -> str:
    llm = client or LLMClient.for_franchise_gm()
    if not llm.available():
        raise RuntimeError(
            "LLM unavailable. Start Hermes API Server on 127.0.0.1:8642 and make API_SERVER_KEY available, "
            "or set FRANCHISE_HERMES_API_KEY."
        )
    return llm.generate(task.prompt, system_prompt=task.system_prompt)
