from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nba2k_editor.franchise.college_dynasty import (
    COLLEGE_GAME_TEAM_COUNT,
    COLLEGE_ROSTER_SIZE,
    COLLEGE_SEASON_PLAYER_SLOT_COUNT,
    COLLEGE_SWEET16_SIZE,
    PROJECTION_STAGE_SEASON,
    PROJECTION_STAGE_SWEET16,
    CollegeDynastyRepository,
)
from nba2k_editor.franchise.models import CollegePlayer, CollegeProgram


FILLER_FIRST_NAME = "A"
FILLER_LAST_NAME = "Z"
FILLER_HEIGHT_INCHES = 60
FILLER_WEIGHT_POUNDS = 100
FILLER_WINGSPAN_INCHES = 60
FILLER_WINGSPAN_CM = 152.4
FILLER_CONTRACT_YEARS = 4
_REQUIRED_PLAYER_FIELDS = (
    "FIRSTNAME",
    "LASTNAME",
    "HEIGHT",
    "WEIGHT",
    "CURRENTTEAM",
    "CONTRACTTEAM",
    "CONTRACTLENGTH",
    "YEARSLEFT",
)


@dataclass(frozen=True)
class CollegeProjectionPreview:
    true_sim_year: int
    stage: str
    team_count: int
    player_slot_count: int
    real_player_count: int
    filler_player_count: int
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class CollegeProjectionApplyResult:
    teams_written: int
    player_records_reset: int
    player_fields_written: int
    verified_player_records: int


@dataclass(frozen=True)
class CollegeProjectionSlotAllocationPreview:
    true_sim_year: int
    stage: str
    missing_slots: tuple[tuple[int, int, str], ...]
    candidate_player_indexes: tuple[int, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class CollegeProjectionSlotAllocationResult:
    linked_slots: int
    player_indexes: tuple[int, ...]


def _loaded_items_by_index(model: Any, domain: str) -> dict[int, Any]:
    return {
        int(item.index): item
        for item in getattr(model, "loaded_items", {}).get(domain, {}).values()
    }


def _entry(model: Any, domain: str, normalized_name: str) -> Any | None:
    return model._field_by_normalized_name(domain, normalized_name)


class CollegeProjectionWriter:
    """Applies a persisted projection only onto already-linked team/player records."""

    def __init__(self, repository: CollegeDynastyRepository, model: Any) -> None:
        self.repository = repository
        self.model = model

    def _team_mapping(self, true_sim_year: int, stage: str) -> dict[int, str]:
        rows = (
            self.repository.list_team_projection(true_sim_year)
            if stage == PROJECTION_STAGE_SEASON
            else self.repository.list_sweet16_projection(true_sim_year)
        )
        return {row.game_team_index: row.program_id for row in rows}

    def preview_missing_slot_allocation(
        self,
        *,
        true_sim_year: int,
        stage: str = PROJECTION_STAGE_SEASON,
    ) -> CollegeProjectionSlotAllocationPreview:
        if stage not in {PROJECTION_STAGE_SEASON, PROJECTION_STAGE_SWEET16}:
            raise ValueError(f"unknown college projection stage: {stage}")
        expected_team_count = COLLEGE_GAME_TEAM_COUNT if stage == PROJECTION_STAGE_SEASON else COLLEGE_SWEET16_SIZE
        mapping = self._team_mapping(true_sim_year, stage)
        teams_by_index = _loaded_items_by_index(self.model, "Teams")
        players_by_index = _loaded_items_by_index(self.model, "Players")
        blockers: list[str] = []
        if len(mapping) != expected_team_count:
            blockers.append(f"{stage} team mapping has {len(mapping)}/{expected_team_count} teams")
        missing_team_indexes = tuple(sorted(set(mapping).difference(teams_by_index)))
        if missing_team_indexes:
            blockers.append(f"team records are not loaded: {missing_team_indexes}")
        current_team_entry = _entry(self.model, "Players", "CURRENTTEAM")
        contract_team_entry = _entry(self.model, "Players", "CONTRACTTEAM")
        if current_team_entry is None:
            blockers.append("Players CURRENTTEAM field is unavailable")
        if contract_team_entry is None:
            blockers.append("Players CONTRACTTEAM field is unavailable")

        used_player_addresses: set[int] = set()
        missing_slots: list[tuple[int, int, str]] = []
        for team_index, team_item in sorted(teams_by_index.items()):
            for roster_slot in range(1, COLLEGE_ROSTER_SIZE + 1):
                slot_field = f"PLAYER{roster_slot}"
                slot_entry = _entry(self.model, "Teams", slot_field)
                if slot_entry is None:
                    blockers.append(f"Teams {slot_field} field is unavailable")
                    continue
                try:
                    pointer = int(
                        self.model.read_entry_value_for_item(slot_entry, team_item).get("raw_value") or 0
                    )
                except Exception as exc:
                    blockers.append(f"cannot read Team {team_index} {slot_field}: {exc}")
                    continue
                if pointer:
                    used_player_addresses.add(pointer)
                elif team_index in mapping:
                    missing_slots.append((team_index, roster_slot, slot_field))

        candidates: list[int] = []
        if current_team_entry is not None:
            for player_index, player_item in sorted(players_by_index.items()):
                if int(player_item.address) in used_player_addresses:
                    continue
                try:
                    current_team = int(
                        self.model.read_entry_value_for_item(current_team_entry, player_item).get("raw_value") or 0
                    )
                except Exception as exc:
                    blockers.append(f"cannot read Players {player_index} CURRENTTEAM: {exc}")
                    continue
                if current_team == 0:
                    candidates.append(player_index)
                if len(candidates) >= len(missing_slots):
                    break
        if len(candidates) < len(missing_slots):
            blockers.append(
                f"only {len(candidates)} unused Free Agency player records are available for {len(missing_slots)} empty slots"
            )
        return CollegeProjectionSlotAllocationPreview(
            true_sim_year=int(true_sim_year),
            stage=stage,
            missing_slots=tuple(missing_slots),
            candidate_player_indexes=tuple(candidates[: len(missing_slots)]),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def allocate_missing_slots(
        self,
        *,
        true_sim_year: int,
        stage: str = PROJECTION_STAGE_SEASON,
    ) -> CollegeProjectionSlotAllocationResult:
        preview = self.preview_missing_slot_allocation(true_sim_year=true_sim_year, stage=stage)
        if not preview.ready:
            raise ValueError("college slot allocation preflight failed:\n- " + "\n- ".join(preview.blockers))
        if not preview.missing_slots:
            return CollegeProjectionSlotAllocationResult(linked_slots=0, player_indexes=())
        teams_by_index = _loaded_items_by_index(self.model, "Teams")
        players_by_index = _loaded_items_by_index(self.model, "Players")
        current_team_entry = _entry(self.model, "Players", "CURRENTTEAM")
        contract_team_entry = _entry(self.model, "Players", "CONTRACTTEAM")
        assignments = tuple(zip(preview.missing_slots, preview.candidate_player_indexes, strict=True))
        originals: list[tuple[Any, Any, object]] = []
        try:
            for (team_index, _roster_slot, slot_field), player_index in assignments:
                team_item = teams_by_index[team_index]
                player_item = players_by_index[player_index]
                slot_entry = _entry(self.model, "Teams", slot_field)
                for entry, item in (
                    (current_team_entry, player_item),
                    (contract_team_entry, player_item),
                    (slot_entry, team_item),
                ):
                    old_value = self.model.read_entry_value_for_item(entry, item).get("raw_value") or 0
                    originals.append((entry, item, old_value))
                self._write(current_team_entry, player_item, int(team_item.address))
                self._write(contract_team_entry, player_item, int(team_item.address))
                self._write(slot_entry, team_item, int(player_item.address))
            for (team_index, _roster_slot, slot_field), player_index in assignments:
                team_item = teams_by_index[team_index]
                player_item = players_by_index[player_index]
                slot_pointer = int(
                    self.model.read_entry_value_for_item(
                        _entry(self.model, "Teams", slot_field), team_item
                    ).get("raw_value")
                    or 0
                )
                current_team = int(
                    self.model.read_entry_value_for_item(current_team_entry, player_item).get("raw_value") or 0
                )
                contract_team = int(
                    self.model.read_entry_value_for_item(contract_team_entry, player_item).get("raw_value") or 0
                )
                if slot_pointer != int(player_item.address):
                    raise RuntimeError(f"allocation verification failed for Team {team_index} {slot_field}")
                if current_team != int(team_item.address) or contract_team != int(team_item.address):
                    raise RuntimeError(f"allocation verification failed for Players {player_index}")
        except Exception as exc:
            rollback_errors: list[str] = []
            for entry, item, old_value in reversed(originals):
                try:
                    self._write(entry, item, old_value)
                except Exception as rollback_exc:
                    rollback_errors.append(
                        f"{getattr(entry, 'normalized_name', entry)} on item {getattr(item, 'index', '?')}: {rollback_exc}"
                    )
            if rollback_errors:
                raise RuntimeError(
                    f"college slot allocation failed: {exc}; rollback failures: {'; '.join(rollback_errors)}"
                ) from exc
            raise
        return CollegeProjectionSlotAllocationResult(
            linked_slots=len(assignments),
            player_indexes=preview.candidate_player_indexes,
        )

    def preview(self, *, true_sim_year: int, stage: str = PROJECTION_STAGE_SEASON) -> CollegeProjectionPreview:
        if stage not in {PROJECTION_STAGE_SEASON, PROJECTION_STAGE_SWEET16}:
            raise ValueError(f"unknown college projection stage: {stage}")
        expected_team_count = COLLEGE_GAME_TEAM_COUNT if stage == PROJECTION_STAGE_SEASON else COLLEGE_SWEET16_SIZE
        expected_player_count = expected_team_count * COLLEGE_ROSTER_SIZE
        mapping = self._team_mapping(true_sim_year, stage)
        projections = self.repository.list_player_projection(true_sim_year, stage=stage)
        programs = {row.program_id: row for row in self.repository.list_programs()}
        players = {row.player_id: row for row in self.repository.list_players()}
        teams_by_index = _loaded_items_by_index(self.model, "Teams")
        game_players_by_index = _loaded_items_by_index(self.model, "Players")
        blockers: list[str] = []
        if not hasattr(self.model, "export_player_roster_snapshot_for_items"):
            blockers.append("player snapshot export is unavailable for rollback")
        if not hasattr(self.model, "apply_player_roster_snapshot"):
            blockers.append("player snapshot apply is unavailable for rollback")
        if len(mapping) != expected_team_count:
            blockers.append(f"{stage} team mapping has {len(mapping)}/{expected_team_count} teams")
        if len(projections) != expected_player_count:
            blockers.append(f"{stage} player mapping has {len(projections)}/{expected_player_count} reserved records")
        missing_team_indexes = tuple(sorted(set(mapping).difference(teams_by_index)))
        if missing_team_indexes:
            blockers.append(f"team records are not loaded: {missing_team_indexes}")
        projected_game_player_indexes = {row.game_player_index for row in projections}
        missing_player_indexes = tuple(sorted(projected_game_player_indexes.difference(game_players_by_index)))
        if missing_player_indexes:
            blockers.append(f"player records are not loaded: {missing_player_indexes}")
        for name in _REQUIRED_PLAYER_FIELDS:
            if _entry(self.model, "Players", name) is None:
                blockers.append(f"Players {name} field is unavailable")
        if _entry(self.model, "Players", "WINGSPAN") is None and _entry(self.model, "Players", "WINGSPANCM") is None:
            blockers.append("Players WINGSPAN/WINGSPANCM field is unavailable")
        if _entry(self.model, "Teams", "TEAMNAME") is None:
            blockers.append("Teams TEAMNAME field is unavailable")
        for team_index, program_id in mapping.items():
            program = programs.get(program_id)
            if program is None:
                blockers.append(f"canonical program is missing: {program_id}")
                continue
            for field_name in program.team_fields:
                if _entry(self.model, "Teams", field_name) is None:
                    blockers.append(f"Teams field is unavailable for {program_id}: {field_name}")
            team_item = teams_by_index.get(team_index)
            if team_item is None:
                continue
            for projection in (row for row in projections if row.game_team_index == team_index):
                player_item = game_players_by_index.get(projection.game_player_index)
                slot_entry = _entry(self.model, "Teams", projection.slot_field)
                if slot_entry is None:
                    blockers.append(f"Teams {projection.slot_field} field is unavailable")
                    continue
                if player_item is None:
                    continue
                try:
                    current_pointer = int(
                        self.model.read_entry_value_for_item(slot_entry, team_item).get("raw_value") or 0
                    )
                except Exception as exc:
                    blockers.append(f"cannot read Team {team_index} {projection.slot_field}: {exc}")
                    continue
                if current_pointer != int(player_item.address):
                    blockers.append(
                        f"Team {team_index} {projection.slot_field} no longer points to reserved player {projection.game_player_index}"
                    )
                if projection.canonical_player_id is not None:
                    canonical = players.get(projection.canonical_player_id)
                    if canonical is None:
                        blockers.append(f"canonical player is missing: {projection.canonical_player_id}")
                        continue
                    for field_name in canonical.player_fields:
                        if _entry(self.model, "Players", field_name) is None:
                            blockers.append(f"Players field is unavailable for {canonical.player_id}: {field_name}")
        real_player_count = sum(row.canonical_player_id is not None for row in projections)
        return CollegeProjectionPreview(
            true_sim_year=int(true_sim_year),
            stage=stage,
            team_count=len(mapping),
            player_slot_count=len(projections),
            real_player_count=real_player_count,
            filler_player_count=len(projections) - real_player_count,
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def _write(self, entry: Any, item: Any, value: object) -> None:
        self.model.write_entry_value_for_item(entry, item, value=value)

    def _write_verified(self, entry: Any, item: Any, value: object, *, raw_pointer: bool = False) -> None:
        self._write(entry, item, value)
        readback = self.model.read_entry_value_for_item(entry, item)
        actual = readback.get("raw_value") if raw_pointer else readback.get("display_value")
        if isinstance(value, (int, float)) and isinstance(actual, (int, float)):
            matches = abs(float(actual) - float(value)) < 0.0001
        else:
            matches = str(actual) == str(value)
        if not matches:
            raise RuntimeError(
                f"write verification failed for {getattr(entry, 'normalized_name', entry)} "
                f"on item {getattr(item, 'index', '?')}: expected {value!r}, read {actual!r}"
            )

    def apply(self, *, true_sim_year: int, stage: str = PROJECTION_STAGE_SEASON) -> CollegeProjectionApplyResult:
        preview = self.preview(true_sim_year=true_sim_year, stage=stage)
        if not preview.ready:
            raise ValueError("college projection preflight failed:\n- " + "\n- ".join(preview.blockers))
        if not hasattr(self.model, "export_player_roster_snapshot_for_items"):
            raise ValueError("model does not expose player snapshot export for projection rollback")
        if not hasattr(self.model, "apply_player_roster_snapshot"):
            raise ValueError("model does not expose player snapshot apply for projection rollback")
        mapping = self._team_mapping(true_sim_year, stage)
        projections = self.repository.list_player_projection(true_sim_year, stage=stage)
        programs = {row.program_id: row for row in self.repository.list_programs()}
        teams_by_index = _loaded_items_by_index(self.model, "Teams")
        players_by_index = _loaded_items_by_index(self.model, "Players")
        player_items = tuple(players_by_index[row.game_player_index] for row in projections)
        player_snapshot = self.model.export_player_roster_snapshot_for_items(player_items)
        team_originals: list[tuple[Any, Any, object]] = []
        for team_index, program_id in sorted(mapping.items()):
            team_item = teams_by_index[team_index]
            field_names = tuple(dict.fromkeys(("TEAMNAME", *programs[program_id].team_fields)))
            for field_name in field_names:
                entry = _entry(self.model, "Teams", field_name)
                original = self.model.read_entry_value_for_item(entry, team_item).get("display_value")
                team_originals.append((entry, team_item, original))
        try:
            return self._apply_preflighted(true_sim_year=true_sim_year, stage=stage)
        except Exception as exc:
            rollback_errors: list[str] = []
            try:
                rollback_result = self.model.apply_player_roster_snapshot(
                    player_snapshot,
                    target_items=player_items,
                    allow_stats=False,
                )
                if int(rollback_result.get("failed", 0)):
                    rollback_errors.append(f"player snapshot restore failed: {rollback_result}")
            except Exception as rollback_exc:
                rollback_errors.append(f"player snapshot restore raised: {rollback_exc}")
            for entry, team_item, original in reversed(team_originals):
                try:
                    self._write_verified(entry, team_item, original)
                except Exception as rollback_exc:
                    rollback_errors.append(
                        f"team field restore failed for item {getattr(team_item, 'index', '?')}: {rollback_exc}"
                    )
            if rollback_errors:
                raise RuntimeError(
                    f"college projection failed: {exc}; rollback failures: {'; '.join(rollback_errors)}"
                ) from exc
            raise

    def _apply_preflighted(
        self,
        *,
        true_sim_year: int,
        stage: str = PROJECTION_STAGE_SEASON,
    ) -> CollegeProjectionApplyResult:
        preview = self.preview(true_sim_year=true_sim_year, stage=stage)
        if not preview.ready:
            raise ValueError("college projection preflight failed:\n- " + "\n- ".join(preview.blockers))
        mapping = self._team_mapping(true_sim_year, stage)
        projections = self.repository.list_player_projection(true_sim_year, stage=stage)
        programs = {row.program_id: row for row in self.repository.list_programs()}
        canonical_players = {row.player_id: row for row in self.repository.list_players()}
        teams_by_index = _loaded_items_by_index(self.model, "Teams")
        game_players_by_index = _loaded_items_by_index(self.model, "Players")

        team_name_entry = _entry(self.model, "Teams", "TEAMNAME")
        current_team_entry = _entry(self.model, "Players", "CURRENTTEAM")
        contract_team_entry = _entry(self.model, "Players", "CONTRACTTEAM")
        contract_length_entry = _entry(self.model, "Players", "CONTRACTLENGTH")
        years_left_entry = _entry(self.model, "Players", "YEARSLEFT")
        original_contract_entry = _entry(self.model, "Players", "ORIGINALCONTRACTYEARS")
        filler_entries = {
            "FIRSTNAME": _entry(self.model, "Players", "FIRSTNAME"),
            "LASTNAME": _entry(self.model, "Players", "LASTNAME"),
            "HEIGHT": _entry(self.model, "Players", "HEIGHT"),
            "WEIGHT": _entry(self.model, "Players", "WEIGHT"),
        }
        wingspan_entry = _entry(self.model, "Players", "WINGSPAN")
        wingspan_value: object = FILLER_WINGSPAN_INCHES
        if wingspan_entry is None:
            wingspan_entry = _entry(self.model, "Players", "WINGSPANCM")
            wingspan_value = FILLER_WINGSPAN_CM

        teams_written = 0
        for game_team_index, program_id in sorted(mapping.items()):
            team_item = teams_by_index[game_team_index]
            program = programs[program_id]
            self._write_verified(team_name_entry, team_item, program.name)
            for field_name, value in program.team_fields.items():
                self._write_verified(_entry(self.model, "Teams", field_name), team_item, value)
            teams_written += 1

        player_records_reset = 0
        player_fields_written = 0
        for projection in projections:
            team_item = teams_by_index[projection.game_team_index]
            player_item = game_players_by_index[projection.game_player_index]
            reset_result = self.model.reset_player_editor_values(item=player_item)
            if int(reset_result.get("failed", 0)):
                raise RuntimeError(
                    f"player reset failed for game player {projection.game_player_index}: {reset_result}"
                )
            player_records_reset += 1
            filler_values = {
                "FIRSTNAME": FILLER_FIRST_NAME,
                "LASTNAME": FILLER_LAST_NAME,
                "HEIGHT": FILLER_HEIGHT_INCHES,
                "WEIGHT": FILLER_WEIGHT_POUNDS,
            }
            for field_name, value in filler_values.items():
                self._write_verified(filler_entries[field_name], player_item, value)
                player_fields_written += 1
            self._write_verified(wingspan_entry, player_item, wingspan_value)
            self._write_verified(current_team_entry, player_item, int(team_item.address), raw_pointer=True)
            self._write_verified(contract_team_entry, player_item, int(team_item.address), raw_pointer=True)
            player_fields_written += 3

            canonical_player: CollegePlayer | None = (
                canonical_players.get(projection.canonical_player_id)
                if projection.canonical_player_id is not None
                else None
            )
            contract_years = FILLER_CONTRACT_YEARS
            if canonical_player is not None:
                for field_name, value in canonical_player.player_fields.items():
                    self._write_verified(_entry(self.model, "Players", field_name), player_item, value)
                    player_fields_written += 1
                contract_years = int(canonical_player.eligibility_remaining)
            self._write_verified(contract_length_entry, player_item, contract_years)
            self._write_verified(years_left_entry, player_item, contract_years)
            player_fields_written += 2
            if original_contract_entry is not None:
                self._write_verified(original_contract_entry, player_item, contract_years)
                player_fields_written += 1

        verified_player_records = 0
        for projection in projections:
            team_item = teams_by_index[projection.game_team_index]
            player_item = game_players_by_index[projection.game_player_index]
            slot_entry = _entry(self.model, "Teams", projection.slot_field)
            slot_pointer = int(self.model.read_entry_value_for_item(slot_entry, team_item).get("raw_value") or 0)
            current_team = int(
                self.model.read_entry_value_for_item(current_team_entry, player_item).get("raw_value") or 0
            )
            contract_team = int(
                self.model.read_entry_value_for_item(contract_team_entry, player_item).get("raw_value") or 0
            )
            if slot_pointer != int(player_item.address):
                raise RuntimeError(f"verification failed for Team {projection.game_team_index} {projection.slot_field}")
            if current_team != int(team_item.address) or contract_team != int(team_item.address):
                raise RuntimeError(f"verification failed for projected player {projection.game_player_index}")
            verified_player_records += 1
        return CollegeProjectionApplyResult(
            teams_written=teams_written,
            player_records_reset=player_records_reset,
            player_fields_written=player_fields_written,
            verified_player_records=verified_player_records,
        )


__all__ = [
    "CollegeProjectionApplyResult",
    "CollegeProjectionPreview",
    "CollegeProjectionSlotAllocationPreview",
    "CollegeProjectionSlotAllocationResult",
    "CollegeProjectionWriter",
    "FILLER_CONTRACT_YEARS",
    "FILLER_FIRST_NAME",
    "FILLER_HEIGHT_INCHES",
    "FILLER_LAST_NAME",
    "FILLER_WEIGHT_POUNDS",
    "FILLER_WINGSPAN_CM",
    "FILLER_WINGSPAN_INCHES",
]
