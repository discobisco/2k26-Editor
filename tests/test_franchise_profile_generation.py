from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from nba2k_editor.franchise.models import FranchiseSetup, FranchiseTeamOption
from nba2k_editor.franchise.llm_tasks import franchise_team_context
from nba2k_editor.franchise.profile_generation import (
    build_team_profile_generation_requests,
    generate_missing_team_profiles,
    missing_team_profile_indexes,
    team_profile_path,
    team_profiles_complete,
)
from nba2k_editor.franchise.storage import FranchiseRepository


@dataclass(frozen=True)
class FakeItem:
    index: int
    display_label: str


class ProfileGenerationModel:
    def __init__(self) -> None:
        self.player = FakeItem(7, "[7] Actual Player")
        self.loaded_items = {
            "Players": {self.player.display_label: self.player},
            "Teams": {
                "[0] Team Zero": FakeItem(0, "[0] Team Zero"),
                "[5] User Team": FakeItem(5, "[5] User Team"),
            },
        }

    def player_roster_slot_items_for_team_items(self, _teams):
        return (
            (
                self.player,
                {
                    "team_index": 0,
                    "team_label": "Team Zero",
                    "team_slot": 0,
                    "team_slot_field": "PLAYER0",
                },
            ),
        )


class FakeProfileClient:
    def __init__(self, *, fail_on_team: int | None = None) -> None:
        self.fail_on_team = fail_on_team
        self.calls: list[int] = []

    def available(self) -> bool:
        return True

    def generate(self, prompt: str, *, system_prompt: str) -> str:
        payload = json.loads(prompt)
        team = payload["team"]
        team_index = int(team["team_index"])
        self.calls.append(team_index)
        if team_index == self.fail_on_team:
            raise RuntimeError(f"profile generation failed for team {team_index}")
        gm_control = str(team["gm_control"])
        return json.dumps(
            {
                "team_index": team_index,
                "team_label": team["team_label"],
                "gm_control": gm_control,
                "organizational_identity": f"Identity for team {team_index}",
                "owner": f"Owner {team_index} has durable constraints.",
                "general_manager": (
                    "The human user owns all GM decisions."
                    if gm_control == "human"
                    else f"GM {team_index} builds the roster."
                ),
                "coach": f"Coach {team_index} owns the system.",
                "scout": f"Scout {team_index} evaluates players.",
            }
        )


def franchise_record(tmp_path: Path):
    repository = FranchiseRepository(tmp_path / "franchise.sqlite")
    return repository.replace_franchise(
        FranchiseSetup(
            start_year=1998,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=False,
            user_team_index=5,
        ),
        (
            FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),
            FranchiseTeamOption(5, "User Team", "[5] User Team"),
        ),
    )


def test_repository_persists_every_active_team_and_franchise_scoped_profile_directory(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    loaded = FranchiseRepository(tmp_path / "franchise.sqlite").load()

    assert tuple(team.team_index for team in loaded.team_options) == (0, 5)
    assert loaded.setup.llm_gm_team_indexes == (0,)
    assert loaded.franchise_id == record.franchise_id
    assert loaded.profile_directory == record.profile_directory
    assert Path(loaded.profile_directory).parent.name == "team_profiles"
    assert missing_team_profile_indexes(loaded) == (0, 5)


def test_generation_requests_include_cpu_and_user_team_with_correct_gm_ownership(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)

    requests = build_team_profile_generation_requests(record, ProfileGenerationModel())
    payloads = {request.team_index: json.loads(request.task.prompt) for request in requests}

    assert tuple(request.team_index for request in requests) == (0, 5)
    assert payloads[0]["team"]["gm_control"] == "llm"
    assert payloads[5]["team"]["gm_control"] == "human"
    assert payloads[0]["team"]["current_roster"][0]["player_label"] == "[7] Actual Player"
    assert payloads[5]["team"]["current_roster"] == []
    assert any("Owner, Coach, and Scout are LLM-controlled on every team" in rule for rule in payloads[5]["rules"])


def test_generation_writes_persistent_profiles_for_all_roles_and_human_user_gm(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    client = FakeProfileClient()

    generated = generate_missing_team_profiles(record, ProfileGenerationModel(), client=client)

    assert tuple(profile.team_index for profile in generated) == (0, 5)
    assert client.calls == [0, 5]
    assert team_profiles_complete(record) is True
    cpu_text = team_profile_path(record, 0).read_text(encoding="utf-8")
    user_text = team_profile_path(record, 5).read_text(encoding="utf-8")
    assert "gm_control: llm" in cpu_text
    assert "## General Manager (LLM-controlled)" in cpu_text
    assert "gm_control: human" in user_text
    assert "## General Manager (Human-controlled)" in user_text
    assert "## Owner (LLM-controlled)" in user_text
    assert "## Coach (LLM-controlled)" in user_text
    assert "## Scout (LLM-controlled)" in user_text
    context = franchise_team_context(record, 5)
    assert context.profile.exists is True
    assert context.profile.path == str(team_profile_path(record, 5))


def test_malformed_or_wrong_role_profile_remains_missing(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    malformed_path = team_profile_path(record, 5)
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        "---\nteam_index: 5\nteam_label: \"User Team\"\ngm_control: llm\nstatus: active\n---\n",
        encoding="utf-8",
    )

    assert missing_team_profile_indexes(record) == (0, 5)
    assert team_profiles_complete(record) is False


def test_retry_generates_only_missing_profile_without_overwriting_existing_identity(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    first_client = FakeProfileClient()
    generate_missing_team_profiles(record, ProfileGenerationModel(), client=first_client)
    existing_path = team_profile_path(record, 0)
    existing_path.write_text(existing_path.read_text(encoding="utf-8") + "Persistent history marker\n", encoding="utf-8")
    team_profile_path(record, 5).unlink()

    retry_client = FakeProfileClient()
    generated = generate_missing_team_profiles(record, ProfileGenerationModel(), client=retry_client)

    assert tuple(profile.team_index for profile in generated) == (5,)
    assert retry_client.calls == [5]
    assert "Persistent history marker" in existing_path.read_text(encoding="utf-8")
    assert team_profiles_complete(record) is True


def test_partial_failure_preserves_completed_profile_for_retry(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)

    with pytest.raises(RuntimeError, match="team 5"):
        generate_missing_team_profiles(record, ProfileGenerationModel(), client=FakeProfileClient(fail_on_team=5))

    assert team_profile_path(record, 0).is_file()
    assert not team_profile_path(record, 5).exists()
    assert missing_team_profile_indexes(record) == (5,)
