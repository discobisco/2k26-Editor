from __future__ import annotations

from pathlib import Path

import pytest

from nba2k_editor.franchise.llm_tasks import franchise_team_context
from nba2k_editor.franchise.models import FranchiseSetup, FranchiseTeamOption
from nba2k_editor.franchise.profile_generation import (
    copy_missing_team_profiles,
    missing_team_profile_indexes,
    pregenerated_team_profile_path,
    team_profile_path,
    team_profiles_complete,
)
from nba2k_editor.franchise.storage import FranchiseRepository


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


def test_missing_profiles_are_copied_from_the_pregenerated_team_profiles(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)

    copied = copy_missing_team_profiles(record)

    assert copied == (team_profile_path(record, 0), team_profile_path(record, 5))
    for team_index in (0, 5):
        assert team_profile_path(record, team_index).read_bytes() == pregenerated_team_profile_path(team_index).read_bytes()
    assert team_profiles_complete(record) is True
    context = franchise_team_context(record, 5)
    assert context.profile.exists is True
    assert context.profile.path == str(team_profile_path(record, 5))


def test_copy_retry_only_replaces_missing_or_invalid_profiles(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    copy_missing_team_profiles(record)
    existing_path = team_profile_path(record, 0)
    existing_path.write_text(existing_path.read_text(encoding="utf-8") + "Persistent history marker\n", encoding="utf-8")
    team_profile_path(record, 5).unlink()

    copied = copy_missing_team_profiles(record)

    assert copied == (team_profile_path(record, 5),)
    assert "Persistent history marker" in existing_path.read_text(encoding="utf-8")
    assert team_profile_path(record, 5).read_bytes() == pregenerated_team_profile_path(5).read_bytes()
    assert team_profiles_complete(record) is True


def test_invalid_profile_is_replaced_by_its_pregenerated_copy(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)
    invalid_path = team_profile_path(record, 5)
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text("wrong profile\n", encoding="utf-8")

    assert missing_team_profile_indexes(record) == (0, 5)

    copied = copy_missing_team_profiles(record)

    assert copied == (team_profile_path(record, 0), team_profile_path(record, 5))
    assert invalid_path.read_bytes() == pregenerated_team_profile_path(5).read_bytes()


def test_copy_rejects_team_indexes_outside_the_saved_franchise(tmp_path: Path) -> None:
    record = franchise_record(tmp_path)

    with pytest.raises(ValueError, match="outside this franchise"):
        copy_missing_team_profiles(record, team_indexes=(29,))
