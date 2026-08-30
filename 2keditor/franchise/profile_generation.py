from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from nba2k_editor.franchise.draft_room import PREGENERATED_TEAM_PROFILE_DIRECTORY
from nba2k_editor.franchise.llm_tasks import franchise_team_profile_directory
from nba2k_editor.franchise.models import FranchiseRecord, FranchiseTeamOption


def pregenerated_team_profile_path(team_index: int) -> Path:
    return PREGENERATED_TEAM_PROFILE_DIRECTORY / f"team_{int(team_index):02d}_profile.md"


def team_profile_path(record: FranchiseRecord, team_index: int) -> Path:
    directory = franchise_team_profile_directory(record)
    return directory / f"team_{int(team_index):02d}_profile.md"


def team_profile_is_valid(record: FranchiseRecord, team: FranchiseTeamOption) -> bool:
    path = team_profile_path(record, team.team_index)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    required_markers = (
        "type: franchise_manager_team_profile",
        f"team_index: {int(team.team_index)}",
        f"# Franchise Team {int(team.team_index):02d} Profile",
    )
    return all(marker in text for marker in required_markers)


def missing_team_profile_indexes(record: FranchiseRecord) -> tuple[int, ...]:
    return tuple(
        int(team.team_index)
        for team in record.team_options
        if not team_profile_is_valid(record, team)
    )


def team_profiles_complete(record: FranchiseRecord) -> bool:
    return bool(record.franchise_id and record.profile_directory and record.team_options) and not missing_team_profile_indexes(record)


def copy_missing_team_profiles(
    record: FranchiseRecord,
    *,
    team_indexes: Iterable[int] | None = None,
) -> tuple[Path, ...]:
    if not record.franchise_id or not record.profile_directory:
        raise ValueError("franchise-scoped team profile storage is not configured")

    teams_by_index = {int(team.team_index): team for team in record.team_options}
    requested_indexes = (
        {int(index) for index in team_indexes}
        if team_indexes is not None
        else set(missing_team_profile_indexes(record))
    )
    unknown_indexes = tuple(sorted(requested_indexes.difference(teams_by_index)))
    if unknown_indexes:
        raise ValueError(f"profile copies requested teams outside this franchise: {unknown_indexes}")

    destination_directory = franchise_team_profile_directory(record)
    destination_directory.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for team_index in sorted(requested_indexes):
        source = pregenerated_team_profile_path(team_index)
        if not source.is_file():
            raise FileNotFoundError(f"pregenerated team profile is missing: {source}")
        destination = team_profile_path(record, team_index)
        shutil.copy2(source, destination)
        if destination.read_bytes() != source.read_bytes():
            raise OSError(f"copied team profile does not match its source: {destination}")
        copied.append(destination)
    return tuple(copied)
