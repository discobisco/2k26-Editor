from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class OffsetRuntimeApplyResult:
    module_name: str | None
    scalar_updates: dict[str, Any]
    chain_updates: dict[str, list[dict[str, object]]]
    mapping_updates: dict[str, Any]
    errors: list[str]
    warnings: list[str]


class OffsetRuntimeInstaller:
    def __init__(
        self,
        *,
        combined_offsets: list[dict[str, object]],
        base_pointers: dict[str, Any],
        game_info: dict[str, Any],
        required_live_base_pointer_keys: tuple[str, ...],
        base_pointer_size_key_map: dict[str, str | None],
        required_offset_schema_fields: dict[str, tuple[str, str]],
        team_field_specs: tuple[tuple[str, str], ...],
        to_int: Callable[[object], int],
        parse_pointer_chain_config: Callable[[dict | None], list[dict[str, object]]],
    ) -> None:
        self.combined_offsets = combined_offsets
        self.base_pointers = base_pointers
        self.game_info = game_info
        self.required_live_base_pointer_keys = required_live_base_pointer_keys
        self.base_pointer_size_key_map = base_pointer_size_key_map
        self.required_offset_schema_fields = required_offset_schema_fields
        self.team_field_specs = team_field_specs
        self.to_int = to_int
        self.parse_pointer_chain_config = parse_pointer_chain_config
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def build(self) -> OffsetRuntimeApplyResult:
        module_name = str(self.game_info.get("executable") or "").strip() or None
        has_live_staff = "Staff" in self.base_pointers
        has_live_stadium = "Stadium" in self.base_pointers
        self._validate_base_pointers(has_live_staff=has_live_staff, has_live_stadium=has_live_stadium)

        scalar_updates = self._build_stride_defaults()
        chain_updates = {
            "PLAYER_PTR_CHAINS": [],
            "TEAM_PTR_CHAINS": [],
            "DRAFT_PTR_CHAINS": [],
            "STAFF_PTR_CHAINS": [],
            "STADIUM_PTR_CHAINS": [],
        }
        mapping_updates = {"TEAM_FIELD_DEFS": {}}

        scalar_updates.update(self._install_player_runtime(chain_updates))
        scalar_updates.update(self._install_team_runtime(chain_updates, mapping_updates))
        scalar_updates.update(self._install_staff_runtime(has_live_staff, chain_updates))
        scalar_updates.update(self._install_stadium_runtime(has_live_stadium, chain_updates))

        return OffsetRuntimeApplyResult(
            module_name=module_name,
            scalar_updates=scalar_updates,
            chain_updates=chain_updates,
            mapping_updates=mapping_updates,
            errors=self.errors,
            warnings=self.warnings,
        )

    def _pointer_address(self, defn: dict[str, object] | None) -> tuple[int, bool]:
        if not isinstance(defn, dict):
            return 0, False
        if "address" not in defn:
            return 0, False
        return self.to_int(defn.get("address")), True

    def _entry_address(self, entry: dict[str, object]) -> int:
        return self.to_int(entry.get("address") or entry.get("offset") or entry.get("hex"))

    def _find_schema_field(self, source_file: str, normalized_name: str) -> dict[str, object] | None:
        source_key = str(source_file or "").strip().casefold()
        normalized_key = str(normalized_name or "").strip().upper()
        if not source_key or not normalized_key:
            return None
        candidates: list[dict[str, object]] = []
        for entry in self.combined_offsets:
            if str(entry.get("source_offsets_file") or "").strip().casefold() != source_key:
                continue
            if str(entry.get("normalized_name") or "").strip().upper() != normalized_key:
                continue
            candidates.append(entry)
        if not candidates:
            return None

        def _score(candidate: dict[str, object]) -> tuple[int, int, int, int, int]:
            category_text = str(candidate.get("canonical_category") or candidate.get("category") or "").strip().lower()
            non_stats = 0 if category_text.startswith("stats") else 1
            deref_raw = (
                candidate.get("dereferenceAddress")
                or candidate.get("deref_offset")
                or candidate.get("dereference_address")
            )
            has_deref = 1 if self.to_int(deref_raw) > 0 else 0
            addr = self._entry_address(candidate)
            addr_valid = 1 if addr > 0 else 0
            length_val = self.to_int(candidate.get("length"))
            return (non_stats, has_deref, addr_valid, addr, length_val)

        return max(candidates, key=_score)

    def _require_field(self, key_name: str) -> dict[str, object] | None:
        source_file, norm_name = self.required_offset_schema_fields[key_name]
        entry = self._find_schema_field(source_file, norm_name)
        if not isinstance(entry, dict):
            self.errors.append(f"Missing required offset field '{source_file}:{norm_name}'.")
            return None
        return entry

    def _validate_base_pointers(self, *, has_live_staff: bool, has_live_stadium: bool) -> None:
        required_base_pointer_keys = list(self.required_live_base_pointer_keys)
        if has_live_staff:
            required_base_pointer_keys.append("Staff")
        if has_live_stadium:
            required_base_pointer_keys.append("Stadium")
        for key_name in required_base_pointer_keys:
            entry = self.base_pointers.get(key_name)
            if not isinstance(entry, dict):
                self.errors.append(f"Missing required base pointer '{key_name}'.")
                continue
            addr_val, has_addr = self._pointer_address(entry)
            if not has_addr:
                self.errors.append(f"Base pointer '{key_name}' is missing required 'address' value.")
                continue
            if addr_val <= 0:
                self.errors.append(f"Base pointer '{key_name}' address must be > 0.")
        for pointer_key, size_key in self.base_pointer_size_key_map.items():
            if pointer_key not in self.base_pointers:
                continue
            entry = self.base_pointers.get(pointer_key)
            if not isinstance(entry, dict):
                self.errors.append(f"Base pointer '{pointer_key}' must be an object.")
                continue
            if size_key is None:
                continue
            size_val = self.to_int(self.game_info.get(size_key))
            if size_val <= 0:
                self.errors.append(f"Missing or invalid game_info '{size_key}' for base pointer '{pointer_key}'.")

    def _build_stride_defaults(self) -> dict[str, Any]:
        player_stride = max(0, self.to_int(self.game_info.get("playerSize")) or 0)
        team_stride = max(0, self.to_int(self.game_info.get("teamSize")) or 0)
        staff_stride = max(0, self.to_int(self.game_info.get("staffSize")) or 0)
        stadium_stride = max(0, self.to_int(self.game_info.get("stadiumSize")) or 0)
        return {
            "PLAYER_STRIDE": player_stride,
            "TEAM_STRIDE": team_stride,
            "STAFF_STRIDE": staff_stride,
            "STADIUM_STRIDE": stadium_stride,
            "TEAM_RECORD_SIZE": team_stride,
            "STAFF_RECORD_SIZE": staff_stride,
            "STADIUM_RECORD_SIZE": stadium_stride,
            "STAFF_NAME_OFFSET": 0,
            "STAFF_NAME_LENGTH": 0,
            "STAFF_NAME_ENCODING": "utf16",
            "STADIUM_NAME_OFFSET": 0,
            "STADIUM_NAME_LENGTH": 0,
            "STADIUM_NAME_ENCODING": "utf16",
            "NAME_MAX_CHARS": 20,
        }

    def _resolve_pointer_chains(self, pointer_key: str, empty_error: str) -> tuple[int, list[dict[str, object]]]:
        base_entry = self.base_pointers.get(pointer_key)
        addr, addr_defined = self._pointer_address(base_entry if isinstance(base_entry, dict) else None)
        if not addr_defined:
            return 0, []
        chains = self.parse_pointer_chain_config(base_entry if isinstance(base_entry, dict) else None)
        if not chains:
            self.errors.append(empty_error)
        return addr, chains

    def _install_player_runtime(self, chain_updates: dict[str, list[dict[str, object]]]) -> dict[str, Any]:
        scalar_updates: dict[str, Any] = {}
        player_addr, player_chains = self._resolve_pointer_chains(
            "Player",
            "Player base pointer chain produced no resolvable entries.",
        )
        scalar_updates["PLAYER_TABLE_RVA"] = player_addr
        chain_updates["PLAYER_PTR_CHAINS"] = player_chains

        draft_entry = self.base_pointers.get("DraftClass")
        if isinstance(draft_entry, dict):
            chain_updates["DRAFT_PTR_CHAINS"] = self.parse_pointer_chain_config(draft_entry)

        first_entry = self._require_field("player_first_name")
        first_offset = self._entry_address(first_entry) if isinstance(first_entry, dict) else 0
        if first_offset < 0:
            self.errors.append("Vitals/FIRSTNAME address must be >= 0.")
            first_offset = 0
        first_len = self.to_int((first_entry or {}).get("length"))
        if first_len <= 0:
            self.errors.append("Vitals/FIRSTNAME length must be > 0.")
        scalar_updates["OFF_FIRST_NAME"] = first_offset
        scalar_updates["FIRST_NAME_ENCODING"] = "ascii" if str((first_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"

        last_entry = self._require_field("player_last_name")
        last_offset = self._entry_address(last_entry) if isinstance(last_entry, dict) else 0
        if last_offset < 0:
            self.errors.append("Vitals/LASTNAME address must be >= 0.")
            last_offset = 0
        last_len = self.to_int((last_entry or {}).get("length"))
        if last_len <= 0:
            self.errors.append("Vitals/LASTNAME length must be > 0.")
        scalar_updates["OFF_LAST_NAME"] = last_offset
        scalar_updates["LAST_NAME_ENCODING"] = "ascii" if str((last_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"
        if first_len > 0 or last_len > 0:
            scalar_updates["NAME_MAX_CHARS"] = max(first_len or 0, last_len or 0)

        team_entry = self._require_field("player_current_team")
        off_team_ptr = self.to_int(
            (team_entry or {}).get("dereferenceAddress")
            or (team_entry or {}).get("deref_offset")
            or (team_entry or {}).get("dereference_address")
        )
        if off_team_ptr <= 0:
            team_type = str((team_entry or {}).get("type_normalized") or (team_entry or {}).get("type") or "").strip().lower()
            if team_type in {"pointer", "address", "ptr", "uint64", "ulonglong", "qword"}:
                off_team_ptr = self._entry_address(team_entry) if isinstance(team_entry, dict) else 0
        if off_team_ptr < 0:
            self.errors.append("Vitals/CURRENTTEAM dereference address must be >= 0.")
            off_team_ptr = 0
        off_team_id = self._entry_address(team_entry) if isinstance(team_entry, dict) else 0
        if off_team_id <= 0:
            self.errors.append("Vitals/CURRENTTEAM address must be > 0.")
        scalar_updates["OFF_TEAM_PTR"] = off_team_ptr
        scalar_updates["OFF_TEAM_ID"] = off_team_id
        return scalar_updates

    def _install_team_runtime(
        self,
        chain_updates: dict[str, list[dict[str, object]]],
        mapping_updates: dict[str, Any],
    ) -> dict[str, Any]:
        scalar_updates: dict[str, Any] = {}
        team_addr, team_chains = self._resolve_pointer_chains(
            "Team",
            "Team base pointer chain produced no resolvable entries.",
        )
        scalar_updates["TEAM_TABLE_RVA"] = team_addr
        chain_updates["TEAM_PTR_CHAINS"] = team_chains

        team_name_entry = self._require_field("team_name")
        team_name_offset = self._entry_address(team_name_entry) if isinstance(team_name_entry, dict) else 0
        if team_name_offset < 0:
            self.errors.append("Team Vitals/TEAMNAME address must be >= 0.")
            team_name_offset = 0
        team_name_length = self.to_int((team_name_entry or {}).get("length")) or 0
        if team_name_length <= 0:
            self.errors.append("Team Vitals/TEAMNAME length must be > 0.")
        team_name_type = str((team_name_entry or {}).get("type", "")).lower()
        team_name_encoding = "ascii" if team_name_type in ("string", "text") else "utf16"
        scalar_updates.update(
            {
                "TEAM_NAME_OFFSET": team_name_offset,
                "TEAM_NAME_LENGTH": team_name_length,
                "TEAM_NAME_ENCODING": team_name_encoding,
                "OFF_TEAM_NAME": team_name_offset,
            }
        )

        team_player_entries = [entry for entry in self.combined_offsets if str(entry.get("canonical_category", "")) == "Team Players"]
        if team_player_entries:
            scalar_updates["TEAM_PLAYER_SLOT_COUNT"] = len(team_player_entries)

        team_field_defs: dict[str, tuple[int, int, str]] = {}
        for label, normalized_name in self.team_field_specs:
            entry_obj = self._find_schema_field("offsets_teams.json", normalized_name)
            if not isinstance(entry_obj, dict):
                continue
            offset = self._entry_address(entry_obj)
            length_val = self.to_int(entry_obj.get("length"))
            entry_type = str(entry_obj.get("type", "")).lower()
            if offset <= 0 or length_val <= 0:
                continue
            if entry_type not in ("wstring", "string", "text"):
                continue
            encoding = "ascii" if entry_type in ("string", "text") else "utf16"
            team_field_defs[label] = (offset, length_val, encoding)
        mapping_updates["TEAM_FIELD_DEFS"] = team_field_defs
        return scalar_updates

    def _install_staff_runtime(
        self,
        has_live_staff: bool,
        chain_updates: dict[str, list[dict[str, object]]],
    ) -> dict[str, Any]:
        if not has_live_staff:
            return {}
        scalar_updates: dict[str, Any] = {}
        _staff_addr, staff_chains = self._resolve_pointer_chains(
            "Staff",
            "Staff base pointer chain produced no resolvable entries.",
        )
        chain_updates["STAFF_PTR_CHAINS"] = staff_chains

        staff_first_entry = self._require_field("staff_first_name")
        staff_last_entry = self._require_field("staff_last_name")
        staff_name_length = self.to_int((staff_first_entry or {}).get("length")) or 0
        if staff_name_length <= 0:
            self.errors.append("Staff Vitals/FIRSTNAME length must be > 0.")
        if isinstance(staff_last_entry, dict):
            last_staff_len = self.to_int(staff_last_entry.get("length"))
            if last_staff_len <= 0:
                self.errors.append("Staff Vitals/LASTNAME length must be > 0.")
        scalar_updates.update(
            {
                "STAFF_NAME_OFFSET": self._entry_address(staff_first_entry) if isinstance(staff_first_entry, dict) else 0,
                "STAFF_NAME_LENGTH": staff_name_length,
                "STAFF_NAME_ENCODING": "ascii" if str((staff_first_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16",
            }
        )
        return scalar_updates

    def _install_stadium_runtime(
        self,
        has_live_stadium: bool,
        chain_updates: dict[str, list[dict[str, object]]],
    ) -> dict[str, Any]:
        if not has_live_stadium:
            return {}
        scalar_updates: dict[str, Any] = {}
        _stadium_addr, stadium_chains = self._resolve_pointer_chains(
            "Stadium",
            "Stadium base pointer chain produced no resolvable entries.",
        )
        chain_updates["STADIUM_PTR_CHAINS"] = stadium_chains

        stadium_name_entry = self._require_field("stadium_name")
        stadium_name_offset = self._entry_address(stadium_name_entry) if isinstance(stadium_name_entry, dict) else 0
        if stadium_name_offset < 0:
            self.errors.append("Stadium/ARENANAME address must be >= 0.")
            stadium_name_offset = 0
        stadium_name_length = self.to_int((stadium_name_entry or {}).get("length")) or 0
        if stadium_name_length <= 0:
            self.errors.append("Stadium/ARENANAME length must be > 0.")
        scalar_updates.update(
            {
                "STADIUM_NAME_OFFSET": stadium_name_offset,
                "STADIUM_NAME_LENGTH": stadium_name_length,
                "STADIUM_NAME_ENCODING": "ascii" if str((stadium_name_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16",
            }
        )
        return scalar_updates
