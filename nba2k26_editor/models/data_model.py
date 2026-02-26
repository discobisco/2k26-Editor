"""
Data model for scanning and editing NBA 2K26 roster data.

This module lifts the non-UI portions of PlayerDataModel from the monolithic
2k26Editor.py so it can be reused by multiple frontends.
"""
from __future__ import annotations

import re
import struct
import threading
import unicodedata
from collections import Counter
from typing import Dict, Literal, Sequence

from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    is_year_offset_field,
    convert_raw_to_year,
    convert_year_to_raw,
    convert_rating_to_raw,
    convert_raw_to_rating,
    convert_minmax_potential_to_raw,
    convert_raw_to_minmax_potential,
    convert_rating_to_tendency_raw,
    convert_tendency_raw_to_rating,
    height_inches_to_raw,
    raw_height_to_inches,
    read_weight,
    write_weight,
    to_int,
)
from ..core import offsets as offsets_mod
from ..core.perf import timed
from ..core.offsets import (
    FIELD_NAME_ALIASES,
    MAX_TEAMS_SCAN,
    MAX_STAFF_SCAN,
    MAX_STADIUM_SCAN,
    FIRST_NAME_ENCODING,
    LAST_NAME_ENCODING,
    MAX_PLAYERS,
    NAME_MAX_CHARS,
    NAME_SUFFIXES,
    NAME_SYNONYMS,
    OFF_FIRST_NAME,
    OFF_LAST_NAME,
    OFF_TEAM_ID,
    OFF_TEAM_NAME,
    OFF_TEAM_PTR,
    PLAYER_PANEL_FIELDS,
    PLAYER_PANEL_OVR_FIELD,
    PLAYER_PTR_CHAINS,
    PLAYER_STRIDE,
    TEAM_FIELD_DEFS,
    TEAM_PLAYER_SLOT_COUNT,
    TEAM_PTR_CHAINS,
    TEAM_RECORD_SIZE,
    TEAM_STRIDE,
    TEAM_NAME_ENCODING,
    TEAM_NAME_LENGTH,
    TEAM_NAME_OFFSET,
    STAFF_PTR_CHAINS,
    STAFF_STRIDE,
    STAFF_RECORD_SIZE,
    STAFF_NAME_ENCODING,
    STADIUM_PTR_CHAINS,
    STADIUM_STRIDE,
    STADIUM_RECORD_SIZE,
    STADIUM_NAME_OFFSET,
    STADIUM_NAME_LENGTH,
    STADIUM_NAME_ENCODING,
    initialize_offsets,
    _load_categories,
)
from ..memory.game_memory import GameMemory
from .player import Player
from .schema import FieldMetadata, FieldWriteSpec

EntityKind = Literal["player", "team", "staff", "stadium"]

FREE_AGENT_TEAM_ID = -1
MAX_TEAMS_SCAN = MAX_TEAMS_SCAN  # re-export for clarity


class PlayerDataModel:
    """High level API for scanning and editing NBA 2K26 player records."""

    def __init__(self, mem: GameMemory, max_players: int = MAX_PLAYERS):
        self.mem: GameMemory = mem
        self.max_players = max_players
        self.players: list[Player] = []
        self.name_index_map: Dict[str, list[int]] = {}
        self.external_loaded = False
        self.team_list: list[tuple[int, str]] = []
        self._team_display_map_cache: dict[int, str] | None = None
        self._team_name_index_cache: dict[str, int] | None = None
        self._ordered_team_names_cache: list[str] | None = None
        self.staff_list: list[tuple[int, str]] = []
        self.stadium_list: list[tuple[int, str]] = []
        self._cached_free_agents: list[Player] = []
        self._player_flag_entries: dict[str, dict[str, object] | None] = {}
        self._player_flag_cache: dict[str, dict[int, bool]] = {}
        self._resolved_player_base: int | None = None
        self._resolved_team_base: int | None = None
        self._resolved_staff_base: int | None = None
        self._resolved_stadium_base: int | None = None
        self._resolved_base_pid: int | None = None
        self._resolved_league_bases: dict[str, int | None] = {}
        self._league_pointer_cache: dict[str, tuple[list[dict[str, object]], int]] = {}
        self._staff_name_fields: dict[str, dict[str, object] | None] = {"first": None, "last": None}
        self._stadium_name_field: dict[str, object] | None = None
        self._dirty_entities: dict[str, bool] = {
            "players": True,
            "teams": True,
            "staff": True,
            "stadiums": True,
        }
        self._name_index_lock = threading.Lock()
        self._name_index_build_token = 0
        # Load offsets even when the game process is not present so the UI can still render categories.
        self.categories: dict[str, list[dict]] = {}
        try:
            offset_target = self.mem.module_name
            if self.mem.open_process():
                offset_target = self.mem.module_name
            target_key = str(offset_target or offsets_mod.MODULE_NAME).lower()
            current_target = str(getattr(offsets_mod, "_current_offset_target", "") or "").lower()
            has_loaded_offsets = isinstance(getattr(offsets_mod, "_offset_config", None), dict)
            if not has_loaded_offsets or current_target != target_key:
                initialize_offsets(target_executable=offset_target, force=False)
            self._sync_offset_constants()
            self.categories = _load_categories()
            self._resolve_name_fields()
        except Exception:
            self.categories = {}
        self.import_partial_matches: dict[str, dict[str, list[dict[str, object]]]] = {}
        # Service layer wrappers keep legacy methods intact while enabling modular usage.
        try:
            from .services.io_codec import IOCodec
            from .services.player_service import PlayerService
            from .services.team_service import TeamService
            from .services.staff_service import StaffService
            from .services.stadium_service import StadiumService

            self.io_codec = IOCodec(self)
            self.player_service = PlayerService(self, self.io_codec)
            self.team_service = TeamService(self, self.io_codec)
            self.staff_service = StaffService(self, self.io_codec)
            self.stadium_service = StadiumService(self, self.io_codec)
        except Exception:
            # Keep model operational even if service modules fail to import.
            self.io_codec = None
            self.player_service = None
            self.team_service = None
            self.staff_service = None
            self.stadium_service = None

    def mark_dirty(self, *entities: str) -> None:
        targets = entities or ("players", "teams", "staff", "stadiums")
        for entity in targets:
            key = str(entity or "").strip().lower()
            if key:
                self._dirty_entities[key] = True

    def clear_dirty(self, *entities: str) -> None:
        targets = entities or ("players", "teams", "staff", "stadiums")
        for entity in targets:
            key = str(entity or "").strip().lower()
            if key:
                self._dirty_entities[key] = False

    def is_dirty(self, entity: str) -> bool:
        return bool(self._dirty_entities.get(str(entity or "").strip().lower(), False))

    # ------------------------------------------------------------------
    # Internal string helpers
    # ------------------------------------------------------------------
    def _make_name_key(self, first: str, last: str, sanitize: bool = False) -> str:
        first_norm = (first or "").strip().lower()
        last_norm = (last or "").strip().lower()
        if sanitize:
            first_norm = re.sub(r"[^a-z0-9]", "", first_norm)
            last_norm = re.sub(r"[^a-z0-9]", "", last_norm)
        key = f"{first_norm} {last_norm}".strip()
        return key

    def _sync_offset_constants(self) -> None:
        """Refresh imported offset constants after initialize_offsets updates the source module."""
        global PLAYER_STRIDE, TEAM_STRIDE, PLAYER_TABLE_RVA, TEAM_TABLE_RVA
        global OFF_FIRST_NAME, OFF_LAST_NAME, OFF_TEAM_PTR, OFF_TEAM_ID, OFF_TEAM_NAME
        global TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_RECORD_SIZE, NAME_MAX_CHARS
        global STAFF_STRIDE, STAFF_RECORD_SIZE, STAFF_NAME_OFFSET, STAFF_NAME_LENGTH, STAFF_NAME_ENCODING
        global STADIUM_STRIDE, STADIUM_RECORD_SIZE, STADIUM_NAME_OFFSET, STADIUM_NAME_LENGTH, STADIUM_NAME_ENCODING
        PLAYER_STRIDE = offsets_mod.PLAYER_STRIDE
        TEAM_STRIDE = offsets_mod.TEAM_STRIDE
        PLAYER_TABLE_RVA = offsets_mod.PLAYER_TABLE_RVA
        TEAM_TABLE_RVA = offsets_mod.TEAM_TABLE_RVA
        OFF_FIRST_NAME = offsets_mod.OFF_FIRST_NAME
        OFF_LAST_NAME = offsets_mod.OFF_LAST_NAME
        OFF_TEAM_PTR = offsets_mod.OFF_TEAM_PTR
        OFF_TEAM_ID = offsets_mod.OFF_TEAM_ID
        OFF_TEAM_NAME = offsets_mod.OFF_TEAM_NAME
        TEAM_NAME_OFFSET = offsets_mod.TEAM_NAME_OFFSET
        TEAM_NAME_LENGTH = offsets_mod.TEAM_NAME_LENGTH
        TEAM_RECORD_SIZE = offsets_mod.TEAM_RECORD_SIZE
        NAME_MAX_CHARS = offsets_mod.NAME_MAX_CHARS
        STAFF_STRIDE = offsets_mod.STAFF_STRIDE
        STAFF_RECORD_SIZE = offsets_mod.STAFF_RECORD_SIZE
        STAFF_NAME_OFFSET = offsets_mod.STAFF_NAME_OFFSET
        STAFF_NAME_LENGTH = offsets_mod.STAFF_NAME_LENGTH
        STAFF_NAME_ENCODING = offsets_mod.STAFF_NAME_ENCODING
        STADIUM_STRIDE = offsets_mod.STADIUM_STRIDE
        STADIUM_RECORD_SIZE = offsets_mod.STADIUM_RECORD_SIZE
        STADIUM_NAME_OFFSET = offsets_mod.STADIUM_NAME_OFFSET
        STADIUM_NAME_LENGTH = offsets_mod.STADIUM_NAME_LENGTH
        STADIUM_NAME_ENCODING = offsets_mod.STADIUM_NAME_ENCODING
        # Name field resolution depends on the active offsets + categories.
        self._resolve_name_fields()
        self._resolved_league_bases.clear()
        self._league_pointer_cache.clear()

    def _resolve_name_fields(self) -> None:
        """Resolve staff/stadium name field metadata from loaded categories."""
        def _string_enc_for_type(field_type: str | None) -> str:
            return self._string_encoding_for_type(field_type)

        def _build_field(entry: dict[str, object] | None, _stride: int) -> dict[str, object] | None:
            if not isinstance(entry, dict):
                return None
            offset_val = to_int(entry.get("address") or entry.get("offset")) or 0
            length_val = to_int(entry.get("length")) or 0
            enc = _string_enc_for_type(str(entry.get("type")))
            requires_deref = bool(
                entry.get("requiresDereference")
                or entry.get("requires_dereference")
                or entry.get("deref")
            )
            deref_offset = to_int(
                entry.get("dereferenceAddress")
                or entry.get("deref_offset")
                or entry.get("dereference_address")
                or entry.get("pointer")
            ) or 0
            return {
                "offset": offset_val,
                "length": length_val,
                "encoding": enc,
                "deref_offset": deref_offset if requires_deref else 0,
                "requires_deref": requires_deref,
            }

        def _find_normalized_field(canonical_category: str, normalized_name: str) -> dict[str, object] | None:
            for entries in self.categories.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if (
                        str(entry.get("canonical_category") or "") == canonical_category
                        and str(entry.get("normalized_name") or "") == normalized_name
                    ):
                        return entry
            return None

        staff_first_entry = _find_normalized_field("Staff Vitals", "FIRSTNAME")
        staff_last_entry = _find_normalized_field("Staff Vitals", "LASTNAME")
        self._staff_name_fields["first"] = _build_field(staff_first_entry, offsets_mod.STAFF_STRIDE)
        self._staff_name_fields["last"] = _build_field(staff_last_entry, offsets_mod.STAFF_STRIDE)
        stadium_entry = _find_normalized_field("Stadium", "ARENANAME")
        self._stadium_name_field = _build_field(stadium_entry, offsets_mod.STADIUM_STRIDE)

        def _log_field(label: str, field: dict[str, object] | None) -> None:
            if not field:
                return
            try:
                deref_flag = "yes" if field.get("requires_deref") else "no"
                print(
                    f"[data_model] {label} name field offset=0x{int(field['offset']):X} "
                    f"len={field['length']} enc={field['encoding']} deref={deref_flag}"
                )
            except Exception:
                pass

        _log_field("staff(first)", self._staff_name_fields.get("first"))
        _log_field("staff(last)", self._staff_name_fields.get("last"))
        _log_field("stadium", self._stadium_name_field)

    def invalidate_base_cache(self) -> None:
        """Clear cached table base pointers so they are re-resolved on demand."""
        self._resolved_player_base = None
        self._resolved_team_base = None
        self._resolved_staff_base = None
        self._resolved_stadium_base = None
        self._resolved_base_pid = None

    def prime_bases(self, *, force: bool = False, open_process: bool = True) -> None:
        """Resolve and cache player/team bases once per process launch."""
        try:
            if open_process and not self.mem.open_process():
                return
        except Exception:
            return
        pid = self.mem.pid
        if pid is None:
            return
        if force or self._resolved_base_pid != pid:
            self._resolved_player_base = None
            self._resolved_team_base = None
            self._resolved_staff_base = None
            self._resolved_stadium_base = None
        self._resolved_base_pid = pid
        self._sync_offset_constants()
        if self._resolved_player_base is None:
            self._resolve_player_base_ptr()
        if self._resolved_team_base is None:
            self._resolve_team_base_ptr()

    def _strip_suffix_string(self, name: str) -> str:
        """
        Remove suffixes (Jr., Sr., III, etc.) from a name string to improve matching.
        """
        parts = re.split(r"[ .]", name or "")
        filtered = [p for p in parts if p and p.lower() not in NAME_SUFFIXES]
        result = " ".join(filtered).strip()
        return result

    def _generate_name_keys(self, first: str, last: str) -> list[str]:
        keys: list[str] = []
        first_variants = [first]
        stripped_first = self._strip_suffix_string(first)
        if stripped_first and stripped_first.lower() != first.lower():
            first_variants.append(stripped_first)
        last_variants = [last]
        stripped_last = self._strip_suffix_string(last)
        if stripped_last and stripped_last.lower() != last.lower():
            last_variants.append(stripped_last)
        for first_variant in first_variants:
            for last_variant in last_variants:
                for sanitize in (False, True):
                    key = self._make_name_key(first_variant, last_variant, sanitize=sanitize)
                    if key and key not in keys:
                        keys.append(key)
        return keys

    @staticmethod
    def _strip_diacritics(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _sanitize_name_token(token: str) -> str:
        base = PlayerDataModel._strip_diacritics(token or "")
        return re.sub(r"[^a-z0-9]", "", base.lower())

    @staticmethod
    def _strip_suffix_words(words: list[str]) -> list[str]:
        if not words:
            return []
        trimmed = list(words)
        while trimmed:
            suffix_token = re.sub(r"[^a-z0-9]", "", trimmed[-1].lower())
            if suffix_token in NAME_SUFFIXES:
                trimmed.pop()
                continue
            break
        return trimmed

    @staticmethod
    def _normalize_family_token(token: str) -> str:
        sanitized = PlayerDataModel._sanitize_name_token(token)
        for suffix in sorted(NAME_SUFFIXES, key=len, reverse=True):
            if sanitized.endswith(suffix):
                sanitized = sanitized[: -len(suffix)]
                break
        return sanitized

    def _build_name_index_map(self) -> None:
        """Rebuild mapping of normalized full names to player indices."""
        self.name_index_map = self._build_name_index_map_from_players(self.players)

    def _build_name_index_map_from_players(self, players: Sequence[Player]) -> dict[str, list[int]]:
        name_index_map: dict[str, list[int]] = {}
        for player in players:
            first = player.first_name or ""
            last = player.last_name or ""
            if not first and not last:
                continue
            for key in self._generate_name_keys(first, last):
                if key:
                    name_index_map.setdefault(key, []).append(player.index)
        return name_index_map

    def _build_name_index_map_async(self) -> None:
        players_snapshot = list(self.players)
        if not players_snapshot:
            self.name_index_map = {}
            return
        with self._name_index_lock:
            self._name_index_build_token += 1
            token = self._name_index_build_token

        def _worker() -> None:
            name_index_map = self._build_name_index_map_from_players(players_snapshot)
            with self._name_index_lock:
                if token != self._name_index_build_token:
                    return
                self.name_index_map = name_index_map

        threading.Thread(target=_worker, name="NameIndexBuilder", daemon=True).start()

    def _match_name_tokens(self, first: str, last: str) -> list[int]:
        """Return roster indices that match the supplied first/last name tokens."""
        first = str(first or "").strip()
        last = str(last or "").strip()
        if not first and not last:
            return []
        keys = self._generate_name_keys(first, last)
        if not keys:
            return []
        seen: set[int] = set()
        matches: list[int] = []
        if self.name_index_map:
            for key in keys:
                for idx in self.name_index_map.get(key, []):
                    if idx not in seen:
                        seen.add(idx)
                        matches.append(idx)
            if matches:
                return matches
        target_keys = set(keys)
        for player in self.players:
            player_keys = self._generate_name_keys(player.first_name, player.last_name)
            if target_keys.intersection(player_keys):
                if player.index not in seen:
                    seen.add(player.index)
                    matches.append(player.index)
        return matches

    def _candidate_name_pairs(self, raw_name: str) -> list[tuple[str, str]]:
        """Derive plausible (first, last) name pairs from raw import values."""
        text = str(raw_name or "").replace("\u00a0", " ")
        text = " ".join(text.split())
        if not text:
            return []
        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add_pair(first: str, last: str) -> None:
            first_clean = (first or "").strip()
            last_clean = (last or "").strip()
            if not first_clean and not last_clean:
                return
            key = (first_clean.lower(), last_clean.lower())
            if key in seen:
                return
            seen.add(key)
            pairs.append((first_clean, last_clean))

        tokens = text.split()
        if len(tokens) == 1:
            add_pair("", tokens[0])
        elif len(tokens) == 2:
            add_pair(tokens[0], tokens[1])
            add_pair(tokens[1], tokens[0])
        else:
            stripped = PlayerDataModel._strip_suffix_words(tokens)
            if len(stripped) >= 2:
                first = " ".join(stripped[:-1])
                last = stripped[-1]
                add_pair(first, last)
            for i in range(1, len(tokens)):
                add_pair(" ".join(tokens[:i]), " ".join(tokens[i:]))
        return pairs

    def get_categories_for_super(self, super_type: str) -> dict[str, list[dict]]:
        """Return categories whose super_type matches the requested type (case-insensitive)."""
        target = (super_type or "").strip().lower()
        if not target:
            return {}
        target_root = target.rstrip("s")
        # Build lower-cased lookups
        super_map = {str(k).lower(): str(v).strip().lower() for k, v in offsets_mod.CATEGORY_SUPER_TYPES.items()}
        canon_map = {str(k).lower(): str(v) for k, v in offsets_mod.CATEGORY_CANONICAL.items()}
        # Omit internal/helper categories that should not render as tabs.
        hidden_cats = {"team pointers"}
        grouped: dict[str, list[dict]] = {}
        for cat_name, fields in (self.categories or {}).items():
            cat_lower = str(cat_name).lower()
            if cat_lower in hidden_cats:
                continue
            if not isinstance(fields, list):
                continue
            category_super = str(super_map.get(cat_lower) or "").strip().lower()
            canon_label = canon_map.get(cat_lower, cat_name)
            matched_fields: list[dict] = []
            for field in fields:
                if not isinstance(field, dict):
                    continue
                field_super = str(
                    field.get("source_super_type")
                    or field.get("super_type")
                    or field.get("superType")
                    or category_super
                ).strip().lower()
                if not field_super:
                    continue
                if field_super != target and field_super.rstrip("s") != target_root:
                    continue
                matched_fields.append(field)
            if matched_fields:
                grouped.setdefault(canon_label, []).extend(matched_fields)
        return grouped

    def get_league_categories(self) -> dict[str, list[dict]]:
        """Convenience wrapper to fetch League super-type categories."""
        return self.get_categories_for_super("League")

    # ------------------------------------------------------------------
    # League helpers
    # ------------------------------------------------------------------
    def _league_context(self) -> tuple[dict[str, object], dict[str, object]]:
        """Return (base_pointers, game_info) for the active offsets version."""
        cfg = getattr(offsets_mod, "_offset_config", None)
        resolver = getattr(offsets_mod, "_resolve_version_context", None)
        if not callable(resolver):
            return {}, {}
        target = offsets_mod._current_offset_target or self.mem.module_name or offsets_mod.MODULE_NAME  # type: ignore[attr-defined]
        try:
            _version_label, base_pointers, game_info = resolver(
                cfg if isinstance(cfg, dict) else None,
                target,
            )
        except Exception:
            return {}, {}
        if not isinstance(base_pointers, dict):
            base_pointers = {}
        if not isinstance(game_info, dict):
            game_info = {}
        return base_pointers or {}, game_info or {}

    def _league_stride(self, pointer_key: str, game_info: dict[str, object]) -> int:
        size_key_map = getattr(offsets_mod, "BASE_POINTER_SIZE_KEY_MAP", {})
        if not isinstance(size_key_map, dict):
            return 0
        size_key = size_key_map.get(pointer_key)
        if not size_key:
            return 0
        return max(0, to_int(game_info.get(size_key)) or 0)

    def _league_pointer_meta(self, pointer_key: str) -> tuple[list[dict[str, object]], int]:
        """Return (pointer_chains, stride) for a given league pointer label."""
        cache_key = pointer_key or ""
        if cache_key in self._league_pointer_cache:
            return self._league_pointer_cache[cache_key]
        base_map, game_info = self._league_context()
        pointer_def = base_map.get(pointer_key) if isinstance(base_map, dict) else None
        chains: list[dict[str, object]] = []
        # Prefer the offsets parser when available to honor complex chain configs.
        parse_chain = getattr(offsets_mod, "_parse_pointer_chain_config", None)
        if callable(parse_chain) and isinstance(pointer_def, dict):
            try:
                parsed = parse_chain(pointer_def)
                if isinstance(parsed, list):
                    chains = parsed
            except Exception:
                chains = []
        stride = self._league_stride(pointer_key, game_info if isinstance(game_info, dict) else {})
        self._league_pointer_cache[cache_key] = (chains, stride)
        return chains, stride

    def _league_category_pointer_map(self) -> dict[str, tuple[str, int]]:
        """Return explicit league category -> (pointer_key, default_limit) mapping from offsets config."""
        cfg = getattr(offsets_mod, "_offset_config", None)
        if not isinstance(cfg, dict):
            return {}
        raw_map = cfg.get("league_category_pointer_map")
        if not isinstance(raw_map, dict):
            return {}
        resolved: dict[str, tuple[str, int]] = {}
        for category_name, mapping in raw_map.items():
            category_key = str(category_name or "").strip()
            if not category_key:
                continue
            pointer_key = ""
            default_limit = 0
            if isinstance(mapping, str):
                pointer_key = str(mapping).strip()
            elif isinstance(mapping, dict):
                pointer_key = str(
                    mapping.get("pointer")
                    or mapping.get("pointer_key")
                    or mapping.get("base_pointer")
                    or ""
                ).strip()
                default_limit = max(
                    0,
                    to_int(
                        mapping.get("max_records")
                        or mapping.get("limit")
                        or mapping.get("default_limit")
                        or 0
                    ),
                )
            if not pointer_key:
                continue
            resolved[category_key] = (pointer_key, default_limit)
        return resolved

    def _league_pointer_for_category(self, category_name: str) -> tuple[str, list[dict[str, object]], int, int]:
        """
        Map a League category to (pointer_key, pointer_chains, stride, default_max_records)
        using explicit category-to-pointer definitions from offsets config only.
        """
        category_key = str(category_name or "").strip()
        pointer_map = self._league_category_pointer_map()
        mapping = pointer_map.get(category_key)
        if mapping is None:
            return "", [], 0, 0
        pointer_key, default_limit = mapping
        chains, stride = self._league_pointer_meta(pointer_key)
        return pointer_key, chains, stride, default_limit

    def _resolve_league_base(self, pointer_key: str, chains: list[dict[str, object]], validator=None) -> int | None:
        if pointer_key in self._resolved_league_bases:
            return self._resolved_league_bases[pointer_key]
        if not self.mem.open_process():
            return None
        for chain in chains or []:
            base = self._resolve_pointer_from_chain(chain)
            if base is None or base <= 0:
                continue
            if validator:
                try:
                    if not validator(base):
                        continue
                except Exception:
                    continue
            self._resolved_league_bases[pointer_key] = base
            try:
                print(f"[data_model] league base '{pointer_key}' resolved to 0x{base:X}")
            except Exception:
                pass
            return base
        self._resolved_league_bases[pointer_key] = None
        return None

    def get_league_records(self, category_name: str, *, max_records: int | None = None) -> list[dict[str, object]]:
        """Read league tables for the requested category; returns a list of record dictionaries."""
        categories = self.get_league_categories()
        fields = categories.get(category_name)
        if not fields:
            return []
        pointer_key, chains, stride, default_limit = self._league_pointer_for_category(category_name)
        if stride <= 0 or not chains:
            return []
        str_fields = [f for f in fields if self._is_string_type(str(f.get("type")))]
        probe_field = str_fields[0] if str_fields else None

        def _validator(base_addr: int) -> bool:
            if probe_field is None:
                return True
            # Some league tables can have an empty first row while later rows are valid.
            # Probe several rows before rejecting a candidate base pointer.
            max_probe_rows = 8
            for probe_idx in range(max_probe_rows):
                record_addr = base_addr + probe_idx * stride
                try:
                    buf = self.mem.read_bytes(record_addr, stride)
                except Exception:
                    break
                value = self.decode_field_value_from_buffer(
                    entity_type="league",
                    entity_index=probe_idx,
                    category=category_name,
                    field_name=str(probe_field.get("name", "")),
                    meta=probe_field,
                    record_buffer=buf,
                    record_addr=record_addr,
                )
                if isinstance(value, str):
                    if value.strip():
                        return True
                    continue
                if value not in (None, "", 0, 0.0):
                    return True
            return False

        base_ptr = self._resolve_league_base(pointer_key, chains, _validator if probe_field else None)
        if base_ptr is None:
            return []
        limit = max_records if max_records is not None else default_limit
        if limit <= 0:
            return []
        records: list[dict[str, object]] = []
        empty_streak = 0
        for idx in range(max(1, limit)):
            record_addr = base_ptr + idx * stride
            try:
                buf = self.mem.read_bytes(record_addr, stride)
            except Exception:
                break
            row: dict[str, object] = {"_index": idx}
            any_values = False
            for field in fields:
                name = str(field.get("name", ""))
                val = self.decode_field_value_from_buffer(
                    entity_type="league",
                    entity_index=idx,
                    category=category_name,
                    field_name=name,
                    meta=field,
                    record_buffer=buf,
                    record_addr=record_addr,
                )
                if isinstance(val, str):
                    val = val.strip()
                row[name] = val
                if val not in (None, "", 0, 0.0):
                    any_values = True
            if any_values:
                records.append(row)
                empty_streak = 0
            else:
                empty_streak += 1
                if empty_streak >= 5:
                    break
        return records

    def _expand_first_name_variants(self, first: str) -> list[str]:
        """Return normalized first-name variants preserving first-name alignment."""
        base = str(first or "").strip()
        if not base:
            return []
        variants: list[str] = []
        seen: set[str] = set()

        def add(token: str) -> None:
            token_clean = (token or "").strip()
            if not token_clean:
                return
            key = token_clean.lower()
            if key in seen:
                return
            seen.add(key)
            variants.append(token_clean)

        add(base)
        ascii_first = self._strip_diacritics(base)
        if ascii_first and ascii_first.lower() != base.lower():
            add(ascii_first)
        if "-" in base:
            add(base.replace("-", " "))
            add(base.replace("-", ""))
        if "'" in base:
            add(base.replace("'", ""))
        if " " in base:
            add(base.split()[0])
        sanitized = self._sanitize_name_token(base)
        if sanitized:
            for synonym in NAME_SYNONYMS.get(sanitized, []):
                add(synonym)
        return variants

    def _expand_last_name_variants(self, last: str) -> list[str]:
        """Return normalized last-name variants preserving surname alignment."""
        base = str(last or "").strip()
        if not base:
            return [""]
        variants: list[str] = []
        seen: set[str] = set()

        def add(token: str) -> None:
            token_clean = (token or "").strip()
            if not token_clean:
                return
            key = token_clean.lower()
            if key in seen:
                return
            seen.add(key)
            variants.append(token_clean)

        add(base)
        ascii_last = self._strip_diacritics(base)
        if ascii_last and ascii_last.lower() != base.lower():
            add(ascii_last)
        stripped_suffix = " ".join(self._strip_suffix_words(base.split())).strip()
        if stripped_suffix and stripped_suffix.lower() != base.lower():
            add(stripped_suffix)
        if "-" in base:
            add(base.replace("-", " "))
            add(base.replace("-", ""))
        if "'" in base:
            add(base.replace("'", ""))
        if " " in base:
            parts = base.split()
            add(parts[-1])
            if len(parts) >= 2:
                add(" ".join(parts[-2:]))
        return variants

    def _name_variants(self, raw_name: str) -> list[str]:
        """Return plausible player name variants derived from an import cell."""
        variants: list[str] = []
        seen: set[str] = set()
        for first, last in self._candidate_name_pairs(raw_name):
            first_variants = self._expand_first_name_variants(first) or [first]
            last_variants = self._expand_last_name_variants(last) or [last]
            for first_name in first_variants:
                for last_name in last_variants:
                    combined = f"{first_name} {last_name}".strip()
                    key = combined.lower()
                    if not combined or key in seen:
                        continue
                    seen.add(key)
                    variants.append(combined)
        return variants

    def _match_player_indices(self, raw_name: str) -> list[int]:
        """Try matching a raw name against the roster using common variants."""
        for first, last in self._candidate_name_pairs(raw_name):
            first_variants = self._expand_first_name_variants(first) or [first]
            last_variants = self._expand_last_name_variants(last) or [last]
            for first_name in first_variants:
                for last_name in last_variants:
                    idxs = self._match_name_tokens(first_name, last_name)
                    if idxs:
                        return idxs
        return []

    @staticmethod
    def _token_similarity(left: str, right: str) -> float:
        """Return a fuzzy similarity score between two sanitized tokens (0.0-1.0+)."""
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        if len(left) == 1 or len(right) == 1:
            return 1.0 if left[0] == right[0] else 0.0
        if left in right or right in left:
            return 0.92
        import difflib

        return difflib.SequenceMatcher(None, left, right).ratio()

    def _rank_roster_candidates(self, raw_name: str, limit: int = 5) -> list[tuple[str, float]]:
        """Return roster names most similar to ``raw_name`` with alignment-aware scoring."""
        combos: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for first, last in self._candidate_name_pairs(raw_name):
            first_variants = self._expand_first_name_variants(first) or [first]
            last_variants = self._expand_last_name_variants(last) or [last]
            for first_name in first_variants:
                for last_name in last_variants:
                    first_s = self._sanitize_name_token(first_name)
                    last_s = self._sanitize_name_token(last_name)
                    first_n = self._normalize_family_token(first_name)
                    last_n = self._normalize_family_token(last_name)
                    key = (first_s, last_s, first_n, last_n)
                    if key in seen:
                        continue
                    seen.add(key)
                    if not first_s and not last_s:
                        continue
                    combos.append(
                        {
                            "first_raw": first_name,
                            "last_raw": last_name,
                            "first_s": first_s,
                            "last_s": last_s,
                            "first_n": first_n,
                            "last_n": last_n,
                        }
                    )
        if not combos:
            return []
        scored: list[tuple[float, Player]] = []
        for player in self.players:
            pf_s = self._sanitize_name_token(player.first_name)
            pl_s = self._sanitize_name_token(player.last_name)
            pf_n = self._normalize_family_token(player.first_name)
            pl_n = self._normalize_family_token(player.last_name)
            best_score = 0.0
            for combo in combos:
                first_score = self._token_similarity(combo["first_s"], pf_s)
                last_score = self._token_similarity(combo["last_s"], pl_s)
                alt_first = self._token_similarity(combo["first_n"], pf_n)
                alt_last = self._token_similarity(combo["last_n"], pl_n)
                combined_first = max(first_score, alt_first)
                combined_last = max(last_score, alt_last)
                if combo["last_s"] and pl_s and combined_last < 0.72:
                    continue
                if combo["first_s"] and pf_s and combined_first < 0.62:
                    initials_match = combo["first_s"][:1] == pf_s[:1]
                    if not initials_match or combined_last < 0.9:
                        continue
                score = (combined_last * 0.7) + (combined_first * 0.3)
                if combo["last_s"] and combo["last_s"] == pl_s:
                    score += 0.08
                if combo["first_s"] and combo["first_s"] == pf_s:
                    score += 0.04
                if combo["first_s"] == pf_s and combo["last_s"] == pl_s:
                    score = 1.3
                if not combo["first_s"]:
                    score = combined_last
                elif not combo["last_s"]:
                    score = combined_first
                if combo["first_s"] and pf_s and combo["first_s"][0] == pf_s[:1]:
                    score += 0.01
                if combo["last_s"] and pl_s and combo["last_s"][0] == pl_s[:1]:
                    score += 0.02
                if score > best_score:
                    best_score = score
            if best_score >= 0.6:
                scored.append((best_score, player))
        scored.sort(key=lambda item: item[0], reverse=True)
        filtered: list[tuple[str, float]] = []
        for score, player in scored:
            if score < 0.75:
                break
            filtered.append((player.full_name, round(score, 3)))
            if len(filtered) >= limit:
                break
        return filtered

    def _partial_name_candidates(self, raw_name: str) -> list[dict[str, object]]:
        ranked = self._rank_roster_candidates(raw_name, limit=6)
        if not ranked:
            return []
        suggestions: list[dict[str, object]] = []
        seen_names: set[str] = set()
        for name, score in ranked:
            if name in seen_names:
                continue
            seen_names.add(name)
            suggestions.append({"name": name, "score": score})
        return suggestions

    def find_player_indices_by_name(self, name: str) -> list[int]:
        """Find player indices matching a given full name."""
        for first, last in self._candidate_name_pairs(name):
            indices = self._match_name_tokens(first, last)
            if indices:
                return indices
        return []

    # ------------------------------------------------------------------
    # Category helpers
    # ------------------------------------------------------------------
    def _normalize_field_name(self, name: object) -> str:
        norm = re.sub(r"[^A-Za-z0-9]", "", str(name)).upper()
        return FIELD_NAME_ALIASES.get(norm, norm)

    # ------------------------------------------------------------------
    # Player scanning
    # ------------------------------------------------------------------
    def _player_record_address(self, player_index: int, *, record_ptr: int | None = None) -> int | None:
        if record_ptr:
            return record_ptr
        if player_index < 0 or player_index >= self.max_players or PLAYER_STRIDE <= 0:
            return None
        base = self._resolve_player_base_ptr()
        if base is None:
            return None
        return base + player_index * PLAYER_STRIDE

    def _team_record_address(self, team_index: int | None = None) -> int | None:
        if team_index is None or team_index < 0:
            return None
        if TEAM_RECORD_SIZE <= 0:
            return None
        base = self._resolve_team_base_ptr()
        if base is None:
            return None
        return base + team_index * TEAM_RECORD_SIZE

    def _staff_record_address(self, staff_index: int | None = None) -> int | None:
        if staff_index is None or staff_index < 0:
            return None
        if STAFF_RECORD_SIZE <= 0:
            return None
        base = self._resolve_staff_base_ptr()
        if base is None:
            return None
        return base + staff_index * STAFF_RECORD_SIZE

    def _stadium_record_address(self, stadium_index: int | None = None) -> int | None:
        if stadium_index is None or stadium_index < 0:
            return None
        if STADIUM_RECORD_SIZE <= 0:
            return None
        base = self._resolve_stadium_base_ptr()
        if base is None:
            return None
        return base + stadium_index * STADIUM_RECORD_SIZE

    def _resolve_pointer_from_chain(self, chain_entry: object) -> int | None:
        """
        Resolve a pointer chain entry produced by the offsets loader.
        Mirrors the monolithic editor logic to avoid divergence.
        """
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        if isinstance(chain_entry, dict):
            base_rva = to_int(chain_entry.get("rva"))
            if base_rva == 0:
                return None
            absolute = bool(chain_entry.get("absolute"))
            direct_table = bool(chain_entry.get("direct_table"))
            try:
                base_addr = base_rva if absolute else self.mem.base_addr + base_rva
                final_offset = to_int(chain_entry.get("final_offset"))
                if direct_table:
                    return base_addr + final_offset
                ptr = self.mem.read_uint64(base_addr)
            except Exception:
                return None
            steps = chain_entry.get("steps") or []
            try:
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    offset = to_int(step.get("offset"))
                    if offset:
                        ptr += offset
                    if step.get("dereference"):
                        if ptr == 0:
                            return None
                        ptr = self.mem.read_uint64(ptr)
                    extra = to_int(step.get("post_add"))
                    if extra:
                        ptr += extra
            except Exception:
                return None
            final_offset = to_int(chain_entry.get("final_offset"))
            if final_offset:
                ptr += final_offset
            return ptr
        return None

    def _resolve_player_base_ptr(self) -> int | None:
        if self._resolved_player_base is not None:
            return self._resolved_player_base
        try:
            if not self.mem.open_process():
                return None
        except Exception:
            return None

        def _validate_player_table(base_addr: int | None) -> bool:
            if base_addr is None:
                return False
            if PLAYER_STRIDE <= 0:
                return False
            if OFF_LAST_NAME < 0 or OFF_FIRST_NAME < 0 or NAME_MAX_CHARS <= 0:
                return False

            def _looks_like_name_token(value: str) -> bool:
                text = (value or "").strip()
                if not text:
                    return False
                if len(text) > NAME_MAX_CHARS:
                    return False
                if any(ord(ch) < 32 for ch in text):
                    return False
                if text.lower().startswith("logo"):
                    return False
                alpha_count = sum(1 for ch in text if ch.isalpha())
                return alpha_count >= 2

            try:
                sample_rows = 8
                min_valid_rows = 3
                min_strong_rows = 2
                valid_rows = 0
                strong_rows = 0
                logo_hits = 0

                team_base = self._resolve_team_base_ptr()
                team_ptr_aligned_rows = 0
                team_id_rows = 0

                for row in range(sample_rows):
                    record_addr = base_addr + (row * PLAYER_STRIDE)
                    first = self._read_string(record_addr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
                    last = self._read_string(record_addr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()

                    if "logo" in first.lower() or "logo" in last.lower():
                        logo_hits += 1

                    first_ok = _looks_like_name_token(first)
                    last_ok = _looks_like_name_token(last)
                    if first_ok or last_ok:
                        valid_rows += 1
                    if first_ok and last_ok:
                        strong_rows += 1

                    if OFF_TEAM_PTR > 0 and team_base is not None and TEAM_STRIDE > 0:
                        try:
                            team_ptr = self.mem.read_uint64(record_addr + OFF_TEAM_PTR)
                        except Exception:
                            team_ptr = 0
                        if team_ptr == 0:
                            team_ptr_aligned_rows += 1
                        elif team_ptr > 0 and team_ptr >= team_base:
                            rel = team_ptr - team_base
                            if rel % TEAM_STRIDE == 0:
                                team_index = int(rel // TEAM_STRIDE)
                                if 0 <= team_index < MAX_TEAMS_SCAN:
                                    team_ptr_aligned_rows += 1
                    elif OFF_TEAM_ID > 0:
                        try:
                            team_id = int(self.mem.read_uint32(record_addr + OFF_TEAM_ID))
                        except Exception:
                            team_id = -1
                        if 0 <= team_id < MAX_TEAMS_SCAN:
                            team_id_rows += 1

                if logo_hits > 0:
                    return False
                if strong_rows < min_strong_rows or valid_rows < min_valid_rows:
                    return False
                if OFF_TEAM_PTR > 0 and team_base is not None and TEAM_STRIDE > 0 and team_ptr_aligned_rows < 2:
                    return False
                if OFF_TEAM_PTR <= 0 and OFF_TEAM_ID > 0 and team_id_rows < 2:
                    return False

                self._resolved_player_base = base_addr
                return True
            except Exception:
                return False

        if PLAYER_PTR_CHAINS:
            for chain in PLAYER_PTR_CHAINS:
                candidate = self._resolve_pointer_from_chain(chain)
                if _validate_player_table(candidate):
                    try:
                        print(f"[data_model] player_base resolved to 0x{candidate:X}")
                    except Exception:
                        pass
                    return self._resolved_player_base
        return None

    # Alias kept for compatibility with migrated logic
    def _resolve_player_table_base(self) -> int | None:
        return self._resolve_player_base_ptr()

    def _resolve_team_base_ptr(self) -> int | None:
        if self._resolved_team_base is not None:
            return self._resolved_team_base
        try:
            if not self.mem.open_process():
                return None
        except Exception:
            return None

        def _is_valid_team_base(base_addr: int | None) -> bool:
            if base_addr is None:
                return False
            if TEAM_STRIDE <= 0:
                return False
            if TEAM_NAME_OFFSET < 0 or TEAM_NAME_LENGTH <= 0:
                return False
            valid_rows = 0
            sample_rows = min(6, MAX_TEAMS_SCAN)
            for row in range(sample_rows):
                record_addr = base_addr + (row * TEAM_STRIDE)
                try:
                    name = self._read_string(record_addr + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                except Exception:
                    continue
                if not name:
                    continue
                if any(ord(ch) < 32 for ch in name):
                    continue
                if "logo" in name.lower():
                    return False
                valid_rows += 1
                if valid_rows >= 2:
                    return True
            return False

        if TEAM_PTR_CHAINS:
            for chain in TEAM_PTR_CHAINS:
                base = self._resolve_pointer_from_chain(chain)
                if _is_valid_team_base(base):
                    self._resolved_team_base = base
                    try:
                        print(f"[data_model] team_base resolved to 0x{base:X}")
                    except Exception:
                        pass
                    return base
        self._resolved_team_base = None
        return None

    def _resolve_staff_base_ptr(self) -> int | None:
        if self._resolved_staff_base is not None:
            return self._resolved_staff_base
        def _log(msg: str) -> None:
            try:
                print(msg)
            except Exception:
                pass
        try:
            if not self.mem.open_process():
                _log("[data_model] staff_base skipped; process not open")
                return None
        except Exception:
            return None

        name_field = self._staff_name_fields.get("first") or self._staff_name_fields.get("last")

        def _is_valid_staff_base(base_addr: int | None) -> bool:
            if base_addr is None:
                _log("[data_model] staff_base candidate is None")
                return False
            if not name_field or name_field.get("offset", 0) <= 0:
                _log("[data_model] staff_base validation: no name field; accepting candidate")
                return True  # no reliable validation; accept candidate
            offset = int(name_field.get("offset") or 0)
            length = int(name_field.get("length") or 0)
            encoding = str(name_field.get("encoding") or STAFF_NAME_ENCODING)
            if length <= 0:
                _log(f"[data_model] staff_base validation: no explicit name length (offset=0x{offset:X}); accepting")
                return True
            try:
                name = self._read_string(base_addr + offset, length, encoding).strip()
            except Exception:
                _log(f"[data_model] staff_base validation: read failed at 0x{base_addr + offset:X}")
                return False
            if not name:
                _log("[data_model] staff_base validation: empty name")
                return False
            if any(ord(ch) < 32 for ch in name):
                _log("[data_model] staff_base validation: control characters in name")
                return False
            return True

        if STAFF_PTR_CHAINS:
            for idx, chain in enumerate(STAFF_PTR_CHAINS):
                base = self._resolve_pointer_from_chain(chain)
                _log(f"[data_model] staff_base candidate[{idx}] = 0x{base:X}" if base is not None else f"[data_model] staff_base candidate[{idx}] = None")
                if _is_valid_staff_base(base):
                    self._resolved_staff_base = base
                    _log(f"[data_model] staff_base resolved to 0x{base:X}")
                    return base
        if STAFF_PTR_CHAINS:
            _log("[data_model] staff_base not resolved; pointer chains present but validation failed")
        else:
            _log("[data_model] staff_base skipped; no pointer chains configured")
        self._resolved_staff_base = None
        return None

    def _resolve_stadium_base_ptr(self) -> int | None:
        if self._resolved_stadium_base is not None:
            return self._resolved_stadium_base
        try:
            if not self.mem.open_process():
                return None
        except Exception:
            return None

        def _is_valid_stadium_base(base_addr: int | None) -> bool:
            if base_addr is None or STADIUM_NAME_OFFSET <= 0 or STADIUM_NAME_LENGTH <= 0:
                return False
            try:
                name = self._read_string(base_addr + STADIUM_NAME_OFFSET, STADIUM_NAME_LENGTH, STADIUM_NAME_ENCODING).strip()
            except Exception:
                return False
            return bool(name)

        name_field = self._stadium_name_field

        def _is_valid_stadium_base(base_addr: int | None) -> bool:
            if base_addr is None:
                return False
            if not name_field or name_field.get("offset", 0) <= 0:
                return True
            offset = int(name_field.get("offset") or 0)
            length = int(name_field.get("length") or 0)
            encoding = str(name_field.get("encoding") or STADIUM_NAME_ENCODING)
            if length <= 0:
                return True
            try:
                name = self._read_string(base_addr + offset, length, encoding).strip()
            except Exception:
                return False
            if not name:
                return False
            return not any(ord(ch) < 32 for ch in name)

        if STADIUM_PTR_CHAINS:
            for chain in STADIUM_PTR_CHAINS:
                base = self._resolve_pointer_from_chain(chain)
                if _is_valid_stadium_base(base):
                    self._resolved_stadium_base = base
                    try:
                        print(f"[data_model] stadium_base resolved to 0x{base:X}")
                    except Exception:
                        pass
                    return base
        if STADIUM_PTR_CHAINS:
            try:
                print("[data_model] stadium_base not resolved; pointer chains present but validation failed")
            except Exception:
                pass
        else:
            try:
                print("[data_model] stadium_base skipped; no pointer chains configured")
            except Exception:
                pass
        self._resolved_stadium_base = None
        return None

    def _scan_team_names(self) -> list[tuple[int, str]]:
        """Read team names from memory using the resolved team table base."""
        if not self.mem.hproc or self.mem.base_addr is None:
            return []
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return []
        teams: list[tuple[int, str]] = []
        for i in range(MAX_TEAMS_SCAN):
            try:
                rec_addr = team_base_ptr + i * TEAM_STRIDE
                name = self._read_string(rec_addr + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
            except Exception:
                continue
            if not name:
                continue
            if any(ord(ch) < 32 or ord(ch) > 126 for ch in name):
                continue
            teams.append((i, name))
        return teams

    def get_team_fields(self, team_idx: int) -> Dict[str, str] | None:
        """Return editable team fields for the given team index."""
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        if TEAM_RECORD_SIZE <= 0 or not TEAM_FIELD_DEFS:
            return None
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return None
        rec_addr = team_base_ptr + team_idx * TEAM_RECORD_SIZE
        fields: Dict[str, str] = {}
        for label, (offset, max_chars, encoding) in TEAM_FIELD_DEFS.items():
            try:
                val = self._read_string(rec_addr + offset, max_chars, encoding).rstrip("\x00")
            except Exception:
                val = ""
            fields[label] = val
        return fields

    def set_team_fields(self, team_idx: int, values: Dict[str, str]) -> bool:
        """Write provided values into the specified team record."""
        if not self.mem.hproc or self.mem.base_addr is None:
            return False
        if TEAM_RECORD_SIZE <= 0 or not TEAM_FIELD_DEFS:
            return False
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return False
        rec_addr = team_base_ptr + team_idx * TEAM_RECORD_SIZE
        success = True
        for label, (offset, max_chars, encoding) in TEAM_FIELD_DEFS.items():
            if label not in values:
                continue
            val = values[label]
            try:
                self._write_string(rec_addr + offset, val, max_chars, encoding)
            except Exception:
                success = False
        return success

    def _scan_all_players(self, limit: int) -> list[Player]:
        """Enumerate player records from the live player table with team resolution."""
        players: list[Player] = []
        mem = self.mem
        player_stride = PLAYER_STRIDE
        if player_stride <= 0 or not mem.hproc or mem.base_addr is None:
            return players
        table_base = self._resolve_player_base_ptr()
        if table_base is None:
            return players
        team_base_ptr = self._resolve_team_base_ptr()
        team_stride = TEAM_STRIDE
        max_count = min(limit, MAX_PLAYERS)
        if team_base_ptr is not None and team_base_ptr > table_base and player_stride > 0:
            max_before_team = int((team_base_ptr - table_base) // player_stride)
            if max_before_team > 0:
                max_count = min(max_count, max_before_team)
        if max_count <= 0:
            return players

        first_enc = self._normalize_encoding_tag(FIRST_NAME_ENCODING)
        last_enc = self._normalize_encoding_tag(LAST_NAME_ENCODING)
        off_first_name = OFF_FIRST_NAME
        off_last_name = OFF_LAST_NAME
        off_team_ptr = OFF_TEAM_PTR
        off_team_id = OFF_TEAM_ID
        off_team_name = OFF_TEAM_NAME
        name_max_chars = NAME_MAX_CHARS
        team_name_length = TEAM_NAME_LENGTH
        team_name_encoding = TEAM_NAME_ENCODING
        read_bytes = mem.read_bytes
        read_uint64_mem = mem.read_uint64
        read_uint32_mem = mem.read_uint32
        read_string = self._read_string
        get_team_display_name = self._get_team_display_name
        append_player = players.append
        team_ptr_cache: dict[int, tuple[str, int | None]] = {}

        def _decode_string(buffer: memoryview, offset: int, max_chars: int, enc: str) -> str:
            if offset < 0 or max_chars <= 0:
                return ""
            if enc == "ascii":
                end = offset + max_chars
                if end > len(buffer):
                    return ""
                raw = buffer[offset:end].tobytes()
                try:
                    text = raw.decode("ascii", errors="ignore")
                except Exception:
                    return ""
            else:
                byte_len = max_chars * 2
                end = offset + byte_len
                if end > len(buffer):
                    return ""
                raw = buffer[offset:end].tobytes()
                try:
                    text = raw.decode("utf-16le", errors="ignore")
                except Exception:
                    return ""
            zero = text.find("\x00")
            if zero != -1:
                text = text[:zero]
            return text

        def _read_uint64(buffer: memoryview, offset: int) -> int | None:
            if offset < 0 or offset + 8 > len(buffer):
                return None
            try:
                return struct.unpack_from("<Q", buffer, offset)[0]
            except Exception:
                return None

        def _read_uint32(buffer: memoryview, offset: int) -> int | None:
            if offset < 0 or offset + 4 > len(buffer):
                return None
            try:
                return struct.unpack_from("<I", buffer, offset)[0]
            except Exception:
                return None

        def _is_ascii_printable(value: str) -> bool:
            return all(32 <= ord(ch) <= 126 for ch in value)

        batch_size = min(6000, max_count)
        for start in range(0, max_count, batch_size):
            batch_count = min(batch_size, max_count - start)
            batch_addr = table_base + start * player_stride
            batch_len = batch_count * player_stride
            try:
                chunk = read_bytes(batch_addr, batch_len)
            except Exception:
                return players

            view = memoryview(chunk)
            for offset_idx in range(batch_count):
                idx = start + offset_idx
                base_offset = offset_idx * player_stride
                p_addr = batch_addr + base_offset
                last_name = _decode_string(view, base_offset + off_last_name, name_max_chars, last_enc).strip()
                first_name = _decode_string(view, base_offset + off_first_name, name_max_chars, first_enc).strip()
                if not first_name and not last_name:
                    continue
                # Skip entries with non-ASCII names (common for uninitialized slots).
                if not _is_ascii_printable(first_name + last_name):
                    continue
                team_name = "Unknown"
                team_id_val: int | None = None
                try:
                    if off_team_ptr > 0:
                        team_ptr = _read_uint64(view, base_offset + off_team_ptr)
                        if team_ptr is None:
                            try:
                                team_ptr = read_uint64_mem(p_addr + off_team_ptr)
                            except Exception:
                                team_ptr = None
                        if team_ptr == 0:
                            team_name = "Free Agents"
                            team_id_val = FREE_AGENT_TEAM_ID
                        elif team_ptr:
                            cached = team_ptr_cache.get(team_ptr)
                            if cached:
                                team_name, team_id_val = cached
                            else:
                                tn = read_string(team_ptr + off_team_name, team_name_length, team_name_encoding).strip()
                                team_name = tn or "Unknown"
                                if team_base_ptr and team_stride > 0:
                                    rel = team_ptr - team_base_ptr
                                    if rel >= 0 and rel % team_stride == 0:
                                        team_id_val = int(rel // team_stride)
                                team_ptr_cache[team_ptr] = (team_name, team_id_val)
                    elif off_team_id > 0:
                        tid_val = _read_uint32(view, base_offset + off_team_id)
                        if tid_val is None:
                            tid_val = read_uint32_mem(p_addr + off_team_id)
                        team_id_val = int(tid_val)
                        team_name = get_team_display_name(team_id_val)
                except Exception:
                    pass
                append_player(
                    Player(
                        idx,
                        first_name,
                        last_name,
                        team_name,
                        team_id_val,
                        record_ptr=p_addr,
                    )
                )
        return players

    # ------------------------------------------------------------------
    # Team scanning
    # ------------------------------------------------------------------
    def scan_team_players(self, team_index: int) -> list[Player]:
        players: list[Player] = []
        if TEAM_PLAYER_SLOT_COUNT <= 0 or not self.mem.hproc or self.mem.base_addr is None:
            return players
        player_table_base = self._resolve_player_base_ptr()
        if player_table_base is None:
            return players
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return players
        record_addr = self._team_record_address(team_index)
        if record_addr is None:
            return players
        try:
            for slot in range(TEAM_PLAYER_SLOT_COUNT):
                try:
                    ptr = self.mem.read_uint64(record_addr + slot * 8)
                except Exception:
                    ptr = 0
                if not ptr:
                    continue
                try:
                    idx = int((ptr - player_table_base) // PLAYER_STRIDE)
                except Exception:
                    idx = -1
                try:
                    last = self._read_string(ptr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                    first = self._read_string(ptr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
                except Exception:
                    continue
                if not first and not last:
                    continue
                players.append(
                    Player(
                        idx if idx >= 0 else len(players),
                        first,
                        last,
                        self._get_team_display_name(team_index),
                        team_index,
                        record_ptr=ptr,
                    )
                )
        except Exception:
            return []
        return players

    def _team_display_map(self) -> dict[int, str]:
        cache = getattr(self, "_team_display_map_cache", None)
        if cache is None:
            team_list = getattr(self, "team_list", [])
            cache = {idx: name for idx, name in team_list}
            self._team_display_map_cache = cache
        return cache

    def _invalidate_team_caches(self) -> None:
        self._team_display_map_cache = None
        self._team_name_index_cache = None
        self._ordered_team_names_cache = None

    def _team_index_for_display_name(self, display_name: str) -> int | None:
        """Resolve a display name back to its team index."""
        if self._team_name_index_cache is None:
            self._team_name_index_cache = {name: idx for idx, name in self.team_list}
        return self._team_name_index_cache.get(display_name)

    def _get_team_display_name(self, team_idx: int) -> str:
        return self._team_display_map().get(team_idx, f"Team {team_idx}")

    def get_teams(self) -> list[str]:
        """Return the list of team names in a logical order."""
        if not self.team_list:
            return []
        if self._ordered_team_names_cache is not None:
            return list(self._ordered_team_names_cache)

        def _classify(entry: tuple[int, str]) -> str:
            tid, name = entry
            lname = name.lower()
            if tid == FREE_AGENT_TEAM_ID or "free" in lname:
                return "free_agents"
            return "normal"

        free_agents: list[str] = []
        remaining: list[tuple[int, str]] = []
        for entry in self.team_list:
            category = _classify(entry)
            if category == "free_agents":
                free_agents.append(entry[1])
            else:
                remaining.append(entry)
        remaining_sorted = [name for _, name in sorted(remaining, key=lambda item: item[0])]
        ordered: list[str] = []
        ordered.extend(free_agents)
        ordered.extend(remaining_sorted)
        self._ordered_team_names_cache = ordered
        return list(ordered)

    def refresh_staff(self) -> list[tuple[int, str]]:
        """Populate staff_list from live memory if pointers are available."""
        with timed("data_model.refresh_staff"):
            self.staff_list = []
            name_first = self._staff_name_fields.get("first")
            name_last = self._staff_name_fields.get("last")
            active_field = name_first or name_last
            if STAFF_RECORD_SIZE <= 0:
                try:
                    print("[data_model] refresh_staff skipped; STAFF_RECORD_SIZE <= 0")
                except Exception:
                    pass
                return self.staff_list
            if not active_field:
                try:
                    print("[data_model] refresh_staff skipped; no staff name field resolved")
                except Exception:
                    pass
                return self.staff_list
            if int(active_field.get("offset", 0)) < 0:
                try:
                    print("[data_model] refresh_staff skipped; staff name offset < 0")
                except Exception:
                    pass
                return self.staff_list
            try:
                if not self.mem.open_process():
                    try:
                        print("[data_model] refresh_staff skipped; process not open")
                    except Exception:
                        pass
                    return self.staff_list
            except Exception:
                return self.staff_list
            base_ptr = self._resolve_staff_base_ptr()
            if base_ptr is None:
                return self.staff_list

            def _read_field(field: dict[str, object] | None, rec_addr: int) -> str:
                if not field:
                    return ""
                offset = int(field.get("offset") or 0)
                length = int(field.get("length") or 0)
                if offset < 0 or length <= 0:
                    return ""
                addr = rec_addr + offset
                try:
                    return self._read_string(addr, length, str(field.get("encoding") or STAFF_NAME_ENCODING)).strip()
                except Exception:
                    return ""

            for idx in range(MAX_STAFF_SCAN):
                rec_addr = base_ptr + idx * STAFF_RECORD_SIZE
                first = _read_field(name_first, rec_addr)
                last = _read_field(name_last, rec_addr)
                name_parts = [part for part in (first, last) if part]
                if not name_parts:
                    continue
                display = " ".join(name_parts).strip()
                if not display or any(ord(ch) < 32 for ch in display):
                    continue
                self.staff_list.append((idx, display))
            self.clear_dirty("staff")
            return self.staff_list

    def get_staff(self) -> list[str]:
        """Return staff names in scan order."""
        return [name for _, name in self.staff_list]

    def refresh_stadiums(self) -> list[tuple[int, str]]:
        """Populate stadium_list from live memory if pointers are available."""
        with timed("data_model.refresh_stadiums"):
            self.stadium_list = []
            name_field = self._stadium_name_field
            if STADIUM_RECORD_SIZE <= 0:
                try:
                    print("[data_model] refresh_stadiums skipped; STADIUM_RECORD_SIZE <= 0")
                except Exception:
                    pass
                return self.stadium_list
            if not name_field:
                try:
                    print("[data_model] refresh_stadiums skipped; no stadium name field resolved")
                except Exception:
                    pass
                return self.stadium_list
            if int(name_field.get("offset", 0)) < 0:
                try:
                    print("[data_model] refresh_stadiums skipped; stadium name offset < 0")
                except Exception:
                    pass
                return self.stadium_list
            try:
                if not self.mem.open_process():
                    try:
                        print("[data_model] refresh_stadiums skipped; process not open")
                    except Exception:
                        pass
                    return self.stadium_list
            except Exception:
                return self.stadium_list
            base_ptr = self._resolve_stadium_base_ptr()
            if base_ptr is None:
                return self.stadium_list

            def _read_field(field: dict[str, object] | None, rec_addr: int) -> str:
                if not field:
                    return ""
                offset = int(field.get("offset") or 0)
                length = int(field.get("length") or 0)
                if offset < 0 or length <= 0:
                    return ""
                addr = rec_addr + offset
                try:
                    return self._read_string(addr, length, str(field.get("encoding") or STADIUM_NAME_ENCODING)).strip()
                except Exception:
                    return ""

            for idx in range(MAX_STADIUM_SCAN):
                rec_addr = base_ptr + idx * STADIUM_RECORD_SIZE
                name = _read_field(name_field, rec_addr)
                if not name or any(ord(ch) < 32 for ch in name):
                    continue
                self.stadium_list.append((idx, name))
            self.clear_dirty("stadiums")
            return self.stadium_list

    def get_stadiums(self) -> list[str]:
        """Return stadium names in scan order."""
        return [name for _, name in self.stadium_list]

    def _build_team_display_list(self, teams: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """Normalize and disambiguate team display names."""
        if not teams:
            return []
        normalized: list[tuple[int, str]] = []
        for idx, name in teams:
            base = (name or f"Team {idx}").strip() or f"Team {idx}"
            normalized.append((idx, base))
        counts = Counter(base.lower() for _, base in normalized)
        display_list: list[tuple[int, str]] = []
        for idx, base in normalized:
            display = base if counts[base.lower()] <= 1 else f"{base} (ID {idx})"
            display_list.append((idx, display))
        return display_list

    def _ensure_team_entry(self, team_id: int, name: str, front: bool = False) -> None:
        if any(tid == team_id for tid, _ in self.team_list):
            return
        if front:
            self.team_list.insert(0, (team_id, name))
        else:
            self.team_list.append((team_id, name))
        self._invalidate_team_caches()

    def _build_team_list_from_players(self, players: list[Player]) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        seen_ids: set[int] = set()
        name_to_temp: dict[str, int] = {}
        next_temp_id = -2
        for player in players:
            if player.team_id == FREE_AGENT_TEAM_ID:
                if FREE_AGENT_TEAM_ID not in seen_ids:
                    entries.append((FREE_AGENT_TEAM_ID, "Free Agents"))
                    seen_ids.add(FREE_AGENT_TEAM_ID)
            elif player.team_id is not None:
                if player.team_id not in seen_ids:
                    base = (player.team or f"Team {player.team_id}").strip() or f"Team {player.team_id}"
                    entries.append((player.team_id, base))
                    seen_ids.add(player.team_id)
            else:
                base = (player.team or "").strip() or "Unknown Team"
                base_l = base.lower()
                if base_l not in name_to_temp:
                    name_to_temp[base_l] = next_temp_id
                    next_temp_id -= 1
                temp_id = name_to_temp[base_l]
                if temp_id not in seen_ids:
                    entries.append((temp_id, base))
                    seen_ids.add(temp_id)
        return entries

    def _apply_team_display_to_players(self, players: list[Player]) -> None:
        """Set player.team names based on team_id mapping when available."""
        display_map = self._team_display_map()
        for p in players:
            if p.team_id is not None and p.team_id in display_map:
                p.team = display_map[p.team_id]

    def _read_panel_entry(self, record_addr: int, entry: dict) -> object | None:
        """Read a raw field value for the player detail panel based on a schema entry."""
        try:
            offset = to_int(entry.get("address") or entry.get("offset") or entry.get("offset_from_base"))
            if offset < 0:
                return None
            requires_deref = bool(entry.get("requiresDereference") or entry.get("requires_deref"))
            deref_offset = to_int(entry.get("dereferenceAddress") or entry.get("deref_offset"))
            target_addr = record_addr + offset
            if requires_deref and deref_offset:
                ptr = self.mem.read_uint64(record_addr + deref_offset)
                if not ptr:
                    return None
                target_addr = ptr + offset
            entry_type = str(entry.get("type", "")).lower()
            start_bit = to_int(entry.get("startBit") or entry.get("start_bit") or 0)
            size_val = to_int(entry.get("size"))
            length_val = to_int(entry.get("length"))
            if entry_type in {"string_utf16", "wstring"}:
                if size_val <= 0:
                    return None
                max_chars = size_val // 2
                return self.mem.read_wstring(target_addr, max_chars).strip("\x00")
            if entry_type in {"string", "text", "cstring", "ascii"}:
                if size_val <= 0:
                    return None
                return self.mem.read_ascii(target_addr, size_val).strip("\x00")
            if entry_type == "float":
                byte_len = size_val if size_val > 0 else ((length_val + 7) // 8 if length_val > 0 else 0)
                if byte_len <= 0:
                    return None
                raw = self.mem.read_bytes(target_addr, byte_len)
                if byte_len == 4:
                    return struct.unpack("<f", raw)[0]
                if byte_len == 8:
                    return struct.unpack("<d", raw)[0]
                return None
            # Some schemas label packed fields as Integer but still set startBit/length.
            # Treat those the same as explicit bitfield entries so we mask correctly.
            is_bitfield = entry_type == "bitfield"
            if not is_bitfield and length_val and length_val > 0:
                if start_bit or (length_val % 8 != 0):
                    is_bitfield = True
            if is_bitfield:
                bit_length = length_val if length_val > 0 else size_val
                if bit_length <= 0:
                    return None
                bits_needed = start_bit + bit_length
                byte_len = (bits_needed + 7) // 8
                if byte_len <= 0:
                    return None
                raw = self.mem.read_bytes(target_addr, byte_len)
                value = int.from_bytes(raw, "little")
                if start_bit:
                    value >>= start_bit
                mask = (1 << bit_length) - 1
                return value & mask
            byte_len = size_val if size_val > 0 else ((length_val + 7) // 8 if length_val > 0 else 0)
            if byte_len <= 0:
                return None
            raw = self.mem.read_bytes(target_addr, byte_len)
            return int.from_bytes(raw, "little")
        except Exception:
            return None

    def get_player_panel_snapshot(self, player: Player) -> dict[str, object]:
        """Return field values required for the player detail panel."""
        snapshot: dict[str, object] = {}
        if not player:
            return snapshot
        if not self.mem.open_process():
            return snapshot
        record_addr = self._player_record_address(player.index, record_ptr=getattr(player, "record_ptr", None))
        if record_addr is None:
            return snapshot
        # Local import to avoid widening the public surface of core.offsets
        from ..core.offsets import _find_offset_entry  # type: ignore

        for label, category, entry_name in PLAYER_PANEL_FIELDS:
            entry = _find_offset_entry(entry_name, category)
            if not entry:
                continue
            value = self.decode_field_value(
                entity_type="player",
                entity_index=player.index,
                category=category,
                field_name=entry_name,
                meta=entry,
                record_ptr=record_addr,
                enum_as_label=True,
            )
            if value is None:
                continue
            snapshot[label] = value
        ovr_entry = _find_offset_entry(PLAYER_PANEL_OVR_FIELD[1], PLAYER_PANEL_OVR_FIELD[0])
        if ovr_entry:
            overall_val = self.decode_field_value(
                entity_type="player",
                entity_index=player.index,
                category=PLAYER_PANEL_OVR_FIELD[0],
                field_name=PLAYER_PANEL_OVR_FIELD[1],
                meta=ovr_entry,
                record_ptr=record_addr,
            )
            if overall_val is not None:
                snapshot["Overall"] = overall_val
        return snapshot

    def _collect_assigned_player_indexes(self) -> set[int]:
        """Return the set of player indices currently assigned to team rosters."""
        assigned: set[int] = set()
        if not self.team_list:
            return assigned
        if not self.mem.hproc or self.mem.base_addr is None:
            return assigned
        player_base = self._resolve_player_base_ptr()
        team_base_ptr = self._resolve_team_base_ptr()
        if player_base is None or team_base_ptr is None or TEAM_STRIDE <= 0:
            return assigned
        stride = PLAYER_STRIDE or 1
        for team_idx, _ in self.team_list:
            if team_idx is None or team_idx < 0:
                continue
            try:
                rec_addr = team_base_ptr + team_idx * TEAM_STRIDE
            except Exception:
                continue
            for slot in range(TEAM_PLAYER_SLOT_COUNT):
                try:
                    ptr = self.mem.read_uint64(rec_addr + slot * 8)
                except Exception:
                    ptr = 0
                if not ptr:
                    continue
                try:
                    idx = int((ptr - player_base) // stride)
                except Exception:
                    continue
                if 0 <= idx < self.max_players:
                    assigned.add(idx)
        return assigned

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh_players(self) -> None:
        """Populate team and player information from live memory only."""
        with timed("data_model.refresh_players"):
            self.team_list = []
            self._invalidate_team_caches()
            self.players = []
            self.external_loaded = False
            self._cached_free_agents = []
            self._player_flag_entries = {}
            self._player_flag_cache = {}
            self.name_index_map = {}

            if not self.mem.open_process():
                return
            # Reuse resolved bases for the same process; invalidate when offsets/bases change.
            self.prime_bases(force=False, open_process=False)

            team_base = self._resolve_team_base_ptr()
            teams: list[tuple[int, str]] = []
            if team_base is not None:
                teams = self._scan_team_names() or []
                if teams:
                    def _team_sort_key_pair(item: tuple[int, str]) -> tuple[int, str]:
                        idx, name = item
                        return (1 if name.strip().lower().startswith("team ") else 0, name)

                    ordered_teams = sorted(teams, key=_team_sort_key_pair)
                    self.team_list = self._build_team_display_list(ordered_teams)
                    self._invalidate_team_caches()

            players_all = self._scan_all_players(self.max_players)

            self.players = players_all
            self._cached_free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
            self._apply_team_display_to_players(self.players)
            self._build_name_index_map_async()
            self.clear_dirty("players", "teams")

    def get_players_by_team(self, team: str) -> list[Player]:
        team_name = (team or "").strip()
        if not team_name:
            return []
        team_lower = team_name.lower()
        if team_lower == "all players":
            if not self.players:
                return []
            return list(self.players)
        if team_lower.startswith("free"):
            return self._get_free_agents()
        team_idx = None
        for idx, name in self.team_list:
            if name == team_name:
                team_idx = idx
                break
        if team_idx == FREE_AGENT_TEAM_ID:
            return self._get_free_agents()
        if self.players:
            if team_idx is not None:
                return [p for p in self.players if p.team_id == team_idx]
            return [p for p in self.players if p.team == team_name]
        return []

    def update_player(self, player: Player) -> None:
        if not self.mem.hproc or self.mem.base_addr is None or self.external_loaded:
            return
        p_addr = self._player_record_address(player.index, record_ptr=getattr(player, "record_ptr", None))
        if p_addr is None:
            return
        self._write_string(p_addr + OFF_LAST_NAME, player.last_name, NAME_MAX_CHARS, LAST_NAME_ENCODING)
        self._write_string(p_addr + OFF_FIRST_NAME, player.first_name, NAME_MAX_CHARS, FIRST_NAME_ENCODING)

    def copy_player_data(
        self,
        src_index: int,
        dst_index: int,
        categories: list[str],
        *,
        src_record_ptr: int | None = None,
        dst_record_ptr: int | None = None,
    ) -> bool:
        """Copy selected data categories from one player to another."""
        if not self.mem.hproc or self.mem.base_addr is None or self.external_loaded:
            return False
        lower_cats = [c.lower() for c in categories]
        if not lower_cats:
            return False
        src_addr = self._player_record_address(src_index, record_ptr=src_record_ptr)
        dst_addr = self._player_record_address(dst_index, record_ptr=dst_record_ptr)
        if src_addr is None or dst_addr is None:
            return False
        if "full" in lower_cats:
            try:
                data = self.mem.read_bytes(src_addr, PLAYER_STRIDE)
                self.mem.write_bytes(dst_addr, data)
                return True
            except Exception:
                return False
        copied_any = False
        for name in lower_cats:
            matched_key = next((cat_name for cat_name in self.categories.keys() if cat_name.lower() == name), None)
            if not matched_key:
                continue
            field_defs = self.categories.get(matched_key, [])
            for field in field_defs:
                if not isinstance(field, dict):
                    continue
                raw_offset = field.get("offset")
                if raw_offset in (None, ""):
                    continue
                offset_int = to_int(raw_offset)
                start_bit = to_int(field.get("startBit", field.get("start_bit", 0)))
                length = to_int(field.get("length", 0))
                if length <= 0:
                    continue
                requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
                deref_offset = to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
                field_type = str(field.get("type", "")).lower()
                byte_length = to_int(field.get("size") or field.get("byte_length") or field.get("length"))
                raw_val = self.get_field_value_typed(
                    src_index,
                    offset_int,
                    start_bit,
                    length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    field_type=field_type,
                    byte_length=byte_length,
                    record_ptr=src_record_ptr,
                )
                if raw_val is None:
                    continue
                if self.set_field_value_typed(
                    dst_index,
                    offset_int,
                    start_bit,
                    length,
                    raw_val,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    field_type=field_type,
                    byte_length=byte_length,
                    record_ptr=dst_record_ptr,
                ):
                    copied_any = True
        return copied_any

    # ------------------------------------------------------------------
    # Low-level field read/write
    # ------------------------------------------------------------------
    def _normalize_encoding_tag(self, tag: str) -> str:
        enc = (tag or "utf16").lower()
        if enc in ("ascii", "string", "text"):
            return "ascii"
        return "utf16"

    def _read_string(self, addr: int, max_chars: int, encoding: str) -> str:
        enc = self._normalize_encoding_tag(encoding)
        max_len = int(max_chars)
        if max_len <= 0:
            raise ValueError("String length must be positive according to schema.")
        if enc == "ascii":
            return self.mem.read_ascii(addr, max_len)
        return self.mem.read_wstring(addr, max_len)

    def _write_string(self, addr: int, value: str, max_chars: int, encoding: str) -> None:
        enc = self._normalize_encoding_tag(encoding)
        max_len = int(max_chars)
        if max_len <= 0:
            raise ValueError("String length must be positive according to schema.")
        if enc == "ascii":
            self.mem.write_ascii_fixed(addr, value, max_len)
        else:
            self.mem.write_wstring_fixed(addr, value, max_len)

    def _effective_byte_length(self, byte_length_hint: int, length_bits: int, default: int = 4) -> int:
        """
        Heuristically derive a byte length from schema hints.
        Offsets often store either a bit-length or a byte-length; handle both.
        """
        if byte_length_hint and byte_length_hint > 0:
            if byte_length_hint > 8 and byte_length_hint % 8 == 0:
                # Likely provided as bits (e.g., 32, 64)
                return max(1, byte_length_hint // 8)
            return max(1, byte_length_hint)
        if length_bits and length_bits > 0:
            return max(1, (int(length_bits) + 7) // 8)
        return max(1, default)

    # ------------------------------------------------------------------
    # Field display helpers
    # ------------------------------------------------------------------
    def _normalize_field_type(self, field_type: str | None) -> str:
        return str(field_type or "").strip().lower()

    def _is_string_type(self, field_type: str | None) -> bool:
        ftype = self._normalize_field_type(field_type)
        return any(tag in ftype for tag in ("string", "text", "wstring", "wstr", "utf16", "wide", "char"))

    def _string_encoding_for_type(self, field_type: str | None) -> str:
        ftype = self._normalize_field_type(field_type)
        if any(tag in ftype for tag in ("wstring", "wstr", "utf16", "wide")):
            return "utf16"
        if any(tag in ftype for tag in ("ascii", "string", "text", "char")):
            return "ascii"
        return "utf16"

    def _is_float_type(self, field_type: str | None) -> bool:
        ftype = self._normalize_field_type(field_type)
        return "float" in ftype or "double" in ftype

    def _is_pointer_type(self, field_type: str | None) -> bool:
        ftype = self._normalize_field_type(field_type)
        return "pointer" in ftype or "ptr" in ftype

    def _is_color_type(self, field_type: str | None) -> bool:
        ftype = self._normalize_field_type(field_type)
        return "color" in ftype

    def _extract_field_parts(
        self,
        meta: FieldMetadata | dict[str, object],
    ) -> tuple[int, int, int, bool, int, str, int, tuple[str, ...] | None]:
        if isinstance(meta, FieldMetadata):
            return (
                meta.offset,
                meta.start_bit,
                meta.length,
                bool(meta.requires_deref),
                meta.deref_offset,
                meta.data_type or "",
                meta.byte_length,
                meta.values,
            )
        if isinstance(meta, dict):
            offset = to_int(meta.get("offset") or meta.get("address") or meta.get("offset_from_base") or meta.get("hex"))
            start_bit = to_int(meta.get("startBit") or meta.get("start_bit") or 0)
            length = to_int(meta.get("length") or meta.get("size") or meta.get("bitLength") or meta.get("bits"))
            requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
            deref_offset = to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
            field_type = str(meta.get("type") or "")
            byte_length = to_int(
                meta.get("byte_length")
                or meta.get("byteLength")
                or meta.get("lengthBytes")
                or meta.get("size")
                or 0
            )
            values_raw = meta.get("values")
            values: tuple[str, ...] | None = None
            if isinstance(values_raw, (list, tuple)):
                values = tuple(str(v) for v in values_raw)
            return (
                offset,
                start_bit,
                length,
                requires_deref,
                deref_offset,
                field_type,
                byte_length,
                values,
            )
        return (0, 0, 0, False, 0, "", 0, None)

    def _resolve_entity_address(
        self,
        entity_type: str,
        entity_index: int,
        *,
        record_ptr: int | None = None,
    ) -> int | None:
        key = (entity_type or "").strip().lower()
        if key == "player":
            return self._player_record_address(entity_index, record_ptr=record_ptr)
        if key == "team":
            return self._team_record_address(entity_index)
        if key == "staff":
            return self._staff_record_address(entity_index)
        if key == "stadium":
            return self._stadium_record_address(entity_index)
        return None

    def _resolve_field_address(
        self,
        record_addr: int,
        offset: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> int | None:
        addr = record_addr + offset
        if requires_deref and deref_offset:
            try:
                struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
            except Exception:
                struct_ptr = None
            if not struct_ptr:
                return None
            addr = struct_ptr + offset
        return addr

    def _read_entity_field_typed(
        self,
        entity_type: str,
        entity_index: int,
        offset: int,
        start_bit: int,
        length_bits: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        record_ptr: int | None = None,
    ) -> object | None:
        key = (entity_type or "").strip().lower()
        if key == "player":
            return self.get_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
                record_ptr=record_ptr,
            )
        if key == "team":
            return self.get_team_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        if key == "staff":
            return self.get_staff_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        if key == "stadium":
            return self.get_stadium_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        return None

    def _write_entity_field_typed(
        self,
        entity_type: str,
        entity_index: int,
        offset: int,
        start_bit: int,
        length_bits: int,
        value: object,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        record_ptr: int | None = None,
    ) -> bool:
        key = (entity_type or "").strip().lower()
        if key == "player":
            return self.set_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
                record_ptr=record_ptr,
            )
        if key == "team":
            return self.set_team_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        if key == "staff":
            return self.set_staff_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        if key == "stadium":
            return self.set_stadium_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length_bits,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        return False

    def _parse_int_value(self, value: object) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return None

    def _parse_float_value(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_hex_value(self, value: object) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        if text.startswith("#"):
            text = text[1:]
            if not text:
                return None
            try:
                return int(text, 16)
            except ValueError:
                return None
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return None

    def _clamp_enum_index(self, value: int, values: Sequence[str], length_bits: int) -> int:
        if not values:
            return 0
        max_idx = len(values) - 1
        if length_bits > 0:
            max_raw = (1 << length_bits) - 1
            max_idx = min(max_idx, max_raw)
        if value < 0:
            return 0
        if value > max_idx:
            return max_idx
        return value

    def _format_hex_value(self, value: int, length_bits: int, byte_length: int) -> str:
        if length_bits > 0:
            width = max(1, (length_bits + 3) // 4)
            mask = (1 << length_bits) - 1
            value &= mask
        else:
            byte_len = self._effective_byte_length(byte_length, length_bits, default=4)
            width = max(1, byte_len * 2)
            if byte_len > 0:
                value &= (1 << (byte_len * 8)) - 1
        return f"0x{value:0{width}X}"

    def _is_team_pointer_field(
        self,
        entity_type: str,
        category: str,
        field_name: str,
        field_type: str | None,
    ) -> bool:
        if not self._is_pointer_type(field_type):
            return False
        if (entity_type or "").strip().lower() != "player":
            return False
        text = f"{category} {field_name}".strip().lower()
        if "team" not in text:
            return False
        return "address" in text or "pointer" in text

    def _team_pointer_to_display_name(self, pointer_value: int) -> str | None:
        try:
            ptr = int(pointer_value)
        except Exception:
            return None
        if ptr <= 0:
            return None
        try:
            team_base = self._resolve_team_base_ptr()
        except Exception:
            team_base = None
        if team_base is None or TEAM_STRIDE <= 0:
            return None
        rel = ptr - team_base
        if rel < 0 or rel % TEAM_STRIDE != 0:
            return None
        team_idx = int(rel // TEAM_STRIDE)
        if team_idx < 0:
            return None
        try:
            return self._get_team_display_name(team_idx)
        except Exception:
            return f"Team {team_idx}"

    def _team_display_name_to_pointer(self, display_value: object) -> int | None:
        parsed = self._parse_hex_value(display_value)
        if parsed is not None:
            return parsed
        text = str(display_value or "").strip()
        if not text:
            return None
        # Accept mixed labels such as "Lakers (0x1234...)".
        match = re.search(r"0x[0-9a-fA-F]+", text)
        if match:
            try:
                return int(match.group(0), 16)
            except Exception:
                pass
        name_lower = text.lower()
        team_idx: int | None = None
        for idx, name in self.team_list:
            if str(name).strip().lower() == name_lower:
                team_idx = int(idx)
                break
        if team_idx is None:
            token = re.match(r"team\s+(\d+)$", name_lower)
            if token:
                try:
                    team_idx = int(token.group(1))
                except Exception:
                    team_idx = None
        if team_idx is None:
            return None
        try:
            team_base = self._resolve_team_base_ptr()
        except Exception:
            team_base = None
        if team_base is None or TEAM_STRIDE <= 0:
            return None
        return int(team_base + team_idx * TEAM_STRIDE)

    def _coerce_field_value(
        self,
        *,
        entity_type: str,
        category: str,
        field_name: str,
        display_value: object,
        field_type: str,
        values: Sequence[str] | None,
        length_bits: int,
        length_raw: int,
        byte_length: int,
    ) -> tuple[str, object, int, str]:
        entity_key = (entity_type or "").strip().lower()
        name_lower = str(field_name or "").strip().lower()
        category_lower = str(category or "").strip().lower()
        field_type_norm = self._normalize_field_type(field_type)
        if self._is_string_type(field_type_norm):
            try:
                text_val = str(display_value)
            except Exception:
                text_val = ""
            char_limit = length_raw if length_raw > 0 else byte_length
            if char_limit <= 0:
                char_limit = max(len(text_val), 1)
            enc = self._string_encoding_for_type(field_type_norm)
            return ("string", text_val, char_limit, enc)
        if entity_key == "player" and name_lower == "weight":
            fval = self._parse_float_value(display_value)
            if fval is None:
                return ("skip", None, 0, "")
            return ("weight", fval, 0, "")
        if self._is_float_type(field_type_norm):
            fval = self._parse_float_value(display_value)
            if fval is None:
                return ("skip", None, 0, "")
            return ("float", fval, 0, "")
        if values:
            idx_val: int | None
            if isinstance(display_value, str):
                try:
                    idx_val = values.index(display_value)
                except ValueError:
                    idx_val = self._parse_int_value(display_value)
            else:
                idx_val = self._parse_int_value(display_value)
            if idx_val is None:
                idx_val = 0
            idx_val = self._clamp_enum_index(idx_val, values, length_bits)
            return ("int", idx_val, 0, "")
        if self._is_pointer_type(field_type_norm) or self._is_color_type(field_type_norm):
            if self._is_team_pointer_field(entity_type, category, field_name, field_type_norm):
                parsed = self._team_display_name_to_pointer(display_value)
            else:
                parsed = self._parse_hex_value(display_value)
            if parsed is None:
                return ("skip", None, 0, "")
            if length_bits > 0:
                parsed &= (1 << length_bits) - 1
            return ("int", parsed, 0, "")
        if entity_key == "player" and name_lower == "height":
            inches_val = self._parse_int_value(display_value)
            if inches_val is None:
                return ("skip", None, 0, "")
            if inches_val < HEIGHT_MIN_INCHES:
                inches_val = HEIGHT_MIN_INCHES
            if inches_val > HEIGHT_MAX_INCHES:
                inches_val = HEIGHT_MAX_INCHES
            raw_val = height_inches_to_raw(inches_val)
            return ("int", raw_val, 0, "")
        if category_lower in ("attributes", "durability"):
            rating = self._parse_float_value(display_value)
            if rating is None:
                return ("skip", None, 0, "")
            raw_val = convert_rating_to_raw(rating, length_bits or 8)
            return ("int", raw_val, 0, "")
        if category_lower == "potential":
            rating = self._parse_float_value(display_value)
            if rating is None:
                return ("skip", None, 0, "")
            if "min" in name_lower or "max" in name_lower:
                raw_val = convert_minmax_potential_to_raw(rating, length_bits or 8)
            else:
                raw_val = convert_rating_to_raw(rating, length_bits or 8)
            return ("int", raw_val, 0, "")
        if category_lower == "tendencies":
            rating = self._parse_float_value(display_value)
            if rating is None:
                return ("skip", None, 0, "")
            raw_val = convert_rating_to_tendency_raw(rating, length_bits or 8)
            return ("int", raw_val, 0, "")
        if is_year_offset_field(field_name):
            year_val = self._parse_int_value(display_value)
            if year_val is None:
                return ("skip", None, 0, "")
            raw_val = convert_year_to_raw(year_val)
            return ("int", raw_val, 0, "")
        if category_lower == "badges":
            lvl = self._parse_int_value(display_value)
            if lvl is None:
                lvl = 0
            if lvl < 0:
                lvl = 0
            max_raw = (1 << length_bits) - 1 if length_bits > 0 else lvl
            if lvl > max_raw:
                lvl = max_raw
            max_lvl = max(0, len(BADGE_LEVEL_NAMES) - 1)
            if lvl > max_lvl:
                lvl = max_lvl
            return ("int", lvl, 0, "")
        raw_int = self._parse_int_value(display_value)
        if raw_int is None:
            return ("skip", None, 0, "")
        return ("int", raw_int, 0, "")

    def coerce_field_value(
        self,
        *,
        entity_type: str,
        category: str,
        field_name: str,
        meta: FieldMetadata | dict[str, object],
        display_value: object,
    ) -> tuple[str, object, int, str]:
        (
            _offset,
            _start_bit,
            length_bits,
            _requires_deref,
            _deref_offset,
            field_type,
            byte_length,
            values,
        ) = self._extract_field_parts(meta)
        length_raw = length_bits
        if length_bits <= 0 and byte_length > 0:
            length_bits = byte_length * 8
        return self._coerce_field_value(
            entity_type=entity_type,
            category=category,
            field_name=field_name,
            display_value=display_value,
            field_type=field_type or "",
            values=values,
            length_bits=length_bits,
            length_raw=length_raw,
            byte_length=byte_length,
        )

    def decode_field_value(
        self,
        *,
        entity_type: str,
        entity_index: int,
        category: str,
        field_name: str,
        meta: FieldMetadata | dict[str, object],
        record_ptr: int | None = None,
        enum_as_label: bool = False,
    ) -> object | None:
        (
            offset,
            start_bit,
            length_bits,
            requires_deref,
            deref_offset,
            field_type,
            byte_length,
            values,
        ) = self._extract_field_parts(meta)
        field_type_norm = self._normalize_field_type(field_type)
        length_raw = length_bits
        if length_bits <= 0 and byte_length > 0:
            length_bits = byte_length * 8
        name_lower = str(field_name or "").strip().lower()
        category_lower = str(category or "").strip().lower()
        if self._is_string_type(field_type_norm):
            if not self.mem.open_process():
                return None
            record_addr = self._resolve_entity_address(entity_type, entity_index, record_ptr=record_ptr)
            if record_addr is None:
                return None
            addr = self._resolve_field_address(
                record_addr,
                offset,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
            if addr is None:
                return None
            max_chars = length_raw if length_raw > 0 else byte_length
            if max_chars <= 0:
                max_chars = NAME_MAX_CHARS if "name" in name_lower and NAME_MAX_CHARS > 0 else 64
            enc = self._string_encoding_for_type(field_type_norm)
            try:
                return self._read_string(addr, max_chars, enc)
            except Exception:
                return None
        if entity_type.strip().lower() == "player" and name_lower == "weight":
            if not self.mem.open_process():
                return None
            record_addr = self._resolve_entity_address(entity_type, entity_index, record_ptr=record_ptr)
            if record_addr is None:
                return None
            addr = self._resolve_field_address(
                record_addr,
                offset,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
            if addr is None:
                return None
            try:
                return int(round(read_weight(self.mem, addr)))
            except Exception:
                return None
        raw_val = self._read_entity_field_typed(
            entity_type,
            entity_index,
            offset,
            start_bit,
            length_bits,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type_norm,
            byte_length=byte_length,
            record_ptr=record_ptr,
        )
        if raw_val is None:
            return None
        if self._is_float_type(field_type_norm):
            return raw_val
        raw_int = to_int(raw_val)
        if values:
            idx = self._clamp_enum_index(raw_int, values, length_bits)
            if enum_as_label:
                return values[idx]
            return idx
        if self._is_pointer_type(field_type_norm) or self._is_color_type(field_type_norm):
            if self._is_team_pointer_field(entity_type, category, field_name, field_type_norm):
                team_name = self._team_pointer_to_display_name(raw_int)
                if team_name:
                    return team_name
            return self._format_hex_value(raw_int, length_bits, byte_length)
        if entity_type.strip().lower() == "player" and name_lower == "height":
            inches = raw_height_to_inches(raw_int)
            if inches < HEIGHT_MIN_INCHES:
                inches = HEIGHT_MIN_INCHES
            if inches > HEIGHT_MAX_INCHES:
                inches = HEIGHT_MAX_INCHES
            return inches
        if category_lower in ("attributes", "durability"):
            return convert_raw_to_rating(raw_int, length_bits or 8)
        if category_lower == "potential":
            if "min" in name_lower or "max" in name_lower:
                return convert_raw_to_minmax_potential(raw_int, length_bits or 8)
            return convert_raw_to_rating(raw_int, length_bits or 8)
        if category_lower == "tendencies":
            return convert_tendency_raw_to_rating(raw_int, length_bits or 8)
        if is_year_offset_field(field_name):
            return convert_raw_to_year(raw_int)
        if category_lower == "badges":
            max_lvl = max(0, len(BADGE_LEVEL_NAMES) - 1)
            if raw_int < 0:
                return 0
            if raw_int > max_lvl:
                return max_lvl
            return raw_int
        return raw_int

    def decode_field_value_from_buffer(
        self,
        *,
        entity_type: str,
        entity_index: int,
        category: str,
        field_name: str,
        meta: FieldMetadata | dict[str, object],
        record_buffer: bytes | bytearray | memoryview,
        record_addr: int | None = None,
        record_ptr: int | None = None,
        enum_as_label: bool = False,
    ) -> object | None:
        """
        Decode a field value from a pre-read record buffer to avoid per-field memory reads.
        Falls back to live reads when the field requires dereferencing.
        """
        (
            offset,
            start_bit,
            length_bits,
            requires_deref,
            deref_offset,
            field_type,
            byte_length,
            values,
        ) = self._extract_field_parts(meta)
        field_type_norm = self._normalize_field_type(field_type)
        length_raw = length_bits
        if length_bits <= 0 and byte_length > 0:
            length_bits = byte_length * 8
        name_lower = str(field_name or "").strip().lower()
        category_lower = str(category or "").strip().lower()
        if requires_deref and deref_offset:
            return self.decode_field_value(
                entity_type=entity_type,
                entity_index=entity_index,
                category=category,
                field_name=field_name,
                meta=meta,
                record_ptr=record_ptr,
                enum_as_label=enum_as_label,
            )

        buf = memoryview(record_buffer)
        if self._is_string_type(field_type_norm):
            max_chars = length_raw if length_raw > 0 else byte_length
            if max_chars <= 0:
                max_chars = NAME_MAX_CHARS if "name" in name_lower and NAME_MAX_CHARS > 0 else 64
            enc = self._string_encoding_for_type(field_type_norm)
            try:
                if max_chars <= 0 or offset < 0:
                    return None
                if enc == "ascii":
                    byte_len = max_chars
                    end = offset + byte_len
                    if end > len(buf):
                        return None
                    raw = buf[offset:end].tobytes()
                    text = raw.decode("ascii", errors="ignore")
                else:
                    byte_len = max_chars * 2
                    end = offset + byte_len
                    if end > len(buf):
                        return None
                    raw = buf[offset:end].tobytes()
                    text = raw.decode("utf-16le", errors="ignore")
                zero = text.find("\x00")
                if zero != -1:
                    text = text[:zero]
                return text
            except Exception:
                return None

        if entity_type.strip().lower() == "player" and name_lower == "weight":
            try:
                if offset < 0 or offset + 4 > len(buf):
                    return None
                raw = buf[offset:offset + 4].tobytes()
                return int(round(struct.unpack("<f", raw)[0]))
            except Exception:
                return None

        if self._is_float_type(field_type_norm):
            try:
                byte_len = self._effective_byte_length(byte_length, length_bits, default=4)
                if offset < 0 or offset + byte_len > len(buf):
                    return None
                fmt = "<d" if byte_len >= 8 else "<f"
                raw = buf[offset:offset + (8 if fmt == "<d" else 4)].tobytes()
                return struct.unpack(fmt, raw[: 8 if fmt == "<d" else 4])[0]
            except Exception:
                return None

        raw_int: int
        try:
            if length_bits <= 0:
                return None
            bits_needed = start_bit + length_bits
            bytes_needed = (bits_needed + 7) // 8
            if offset < 0 or offset + bytes_needed > len(buf):
                return None
            raw = buf[offset:offset + bytes_needed].tobytes()
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length_bits) - 1
            raw_int = value & mask
        except Exception:
            return None

        if values:
            idx = self._clamp_enum_index(raw_int, values, length_bits)
            if enum_as_label:
                return values[idx]
            return idx
        if self._is_pointer_type(field_type_norm) or self._is_color_type(field_type_norm):
            if self._is_team_pointer_field(entity_type, category, field_name, field_type_norm):
                team_name = self._team_pointer_to_display_name(raw_int)
                if team_name:
                    return team_name
            return self._format_hex_value(raw_int, length_bits, byte_length)
        if entity_type.strip().lower() == "player" and name_lower == "height":
            inches = raw_height_to_inches(raw_int)
            if inches < HEIGHT_MIN_INCHES:
                inches = HEIGHT_MIN_INCHES
            if inches > HEIGHT_MAX_INCHES:
                inches = HEIGHT_MAX_INCHES
            return inches
        if category_lower in ("attributes", "durability"):
            return convert_raw_to_rating(raw_int, length_bits or 8)
        if category_lower == "potential":
            if "min" in name_lower or "max" in name_lower:
                return convert_raw_to_minmax_potential(raw_int, length_bits or 8)
            return convert_raw_to_rating(raw_int, length_bits or 8)
        if category_lower == "tendencies":
            return convert_tendency_raw_to_rating(raw_int, length_bits or 8)
        if is_year_offset_field(field_name):
            return convert_raw_to_year(raw_int)
        if category_lower == "badges":
            max_lvl = max(0, len(BADGE_LEVEL_NAMES) - 1)
            if raw_int < 0:
                return 0
            if raw_int > max_lvl:
                return max_lvl
            return raw_int
        return raw_int

    def encode_field_value(
        self,
        *,
        entity_type: str,
        entity_index: int,
        category: str,
        field_name: str,
        meta: FieldMetadata | dict[str, object],
        display_value: object,
        record_ptr: int | None = None,
    ) -> bool:
        (
            offset,
            start_bit,
            length_bits,
            requires_deref,
            deref_offset,
            field_type,
            byte_length,
            _values,
        ) = self._extract_field_parts(meta)
        length_raw = length_bits
        if length_bits <= 0 and byte_length > 0:
            length_bits = byte_length * 8
        kind, value, char_limit, enc = self._coerce_field_value(
            entity_type=entity_type,
            category=category,
            field_name=field_name,
            display_value=display_value,
            field_type=field_type or "",
            values=_values,
            length_bits=length_bits,
            length_raw=length_raw,
            byte_length=byte_length,
        )
        if kind == "skip":
            return False
        if kind == "string":
            if not self.mem.open_process():
                return False
            record_addr = self._resolve_entity_address(entity_type, entity_index, record_ptr=record_ptr)
            if record_addr is None:
                return False
            addr = self._resolve_field_address(
                record_addr,
                offset,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
            if addr is None:
                return False
            try:
                self._write_string(addr, str(value), int(char_limit), enc)
                return True
            except Exception:
                return False
        if kind == "weight":
            if not self.mem.open_process():
                return False
            record_addr = self._resolve_entity_address(entity_type, entity_index, record_ptr=record_ptr)
            if record_addr is None:
                return False
            addr = self._resolve_field_address(
                record_addr,
                offset,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
            if addr is None:
                return False
            try:
                if isinstance(value, (int, float)):
                    weight_val = float(value)
                else:
                    weight_val = float(str(value).strip())
            except Exception:
                return False
            return write_weight(self.mem, addr, weight_val)
        return self._write_entity_field_typed(
            entity_type,
            entity_index,
            offset,
            start_bit,
            length_bits,
            value,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=self._normalize_field_type(field_type),
            byte_length=byte_length,
            record_ptr=record_ptr,
        )

    def _load_external_roster(self) -> list[Player] | None:
        """Placeholder for future offline roster loading; currently disabled."""
        return None

    def get_field_value(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
        *,
        record_ptr: int | None = None,
    ) -> int | None:
        try:
            if not self.mem.open_process():
                return None
            record_addr = self._player_record_address(player_index, record_ptr=record_ptr)
            if record_addr is None:
                return None
            if requires_deref and deref_offset:
                try:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                except Exception:
                    return None
                if not struct_ptr:
                    return None
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            raw = self.mem.read_bytes(addr, bytes_needed)
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length) - 1
            return value & mask
        except Exception:
            return None

    def get_field_value_typed(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
        *,
        field_type: str | None = None,
        byte_length: int = 0,
        record_ptr: int | None = None,
    ) -> object | None:
        """
        Read a field value with awareness of its declared type.
        Floats are decoded as IEEE-754; all other types fall back to bitfield reads.
        """
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return None
                record_addr = self._player_record_address(player_index, record_ptr=record_ptr)
                if record_addr is None:
                    return None
                addr = record_addr + offset
                if requires_deref and deref_offset:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                    if not struct_ptr:
                        return None
                    addr = struct_ptr + offset
                byte_len = self._effective_byte_length(byte_length, length, default=4)
                fmt = "<d" if byte_len >= 8 else "<f"
                raw = self.mem.read_bytes(addr, 8 if fmt == "<d" else 4)
                return struct.unpack(fmt, raw[: 8 if fmt == "<d" else 4])[0]
            except Exception:
                return None
        return self.get_field_value(
            player_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            record_ptr=record_ptr,
        )

    def get_team_field_value(
        self,
        team_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> int | None:
        """Read a bitfield from the specified team record."""
        try:
            if not self.mem.open_process():
                return None
            record_addr = self._team_record_address(team_index)
            if record_addr is None:
                return None
            if requires_deref and deref_offset:
                try:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                except Exception:
                    return None
                if not struct_ptr:
                    return None
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            raw = self.mem.read_bytes(addr, bytes_needed)
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length) - 1
            return value & mask
        except Exception:
            return None

    def _write_field_bits(
        self,
        record_addr: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        try:
            target_addr = record_addr + offset
            cache = deref_cache
            if requires_deref and deref_offset:
                struct_ptr: int | None
                cached = cache.get(deref_offset) if cache is not None else None
                if cached is None:
                    try:
                        struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                    except Exception:
                        struct_ptr = None
                    if cache is not None:
                        cache[deref_offset] = struct_ptr or 0
                else:
                    struct_ptr = cached or None
                if not struct_ptr:
                    return False
                target_addr = struct_ptr + offset
            value = int(value)
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            data = bytearray(self.mem.read_bytes(target_addr, bytes_needed))
            current = int.from_bytes(data, "little")
            mask = ((1 << length) - 1) << start_bit
            new_val = (current & ~mask) | ((value << start_bit) & mask)
            if new_val == current:
                return True
            new_bytes = new_val.to_bytes(bytes_needed, "little")
            self.mem.write_bytes(target_addr, new_bytes)
            return True
        except Exception:
            return False

    def _apply_field_assignments(
        self,
        record_addr: int,
        assignments: Sequence[FieldWriteSpec],
    ) -> int:
        if not assignments:
            return 0
        applied = 0
        deref_cache: dict[int, int] = {}
        for offset, start_bit, length, value, requires_deref, deref_offset in assignments:
            if self._write_field_bits(
                record_addr,
                offset,
                start_bit,
                length,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            ):
                applied += 1
        return applied

    def set_field_value(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
        *,
        record_ptr: int | None = None,
    ) -> bool:
        try:
            if not self.mem.open_process():
                return False
            record_addr = self._player_record_address(player_index, record_ptr=record_ptr)
            if record_addr is None:
                return False
            return self._write_field_bits(
                record_addr,
                offset,
                start_bit,
                length,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
        except Exception:
            return False

    def set_field_value_typed(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: object,
        requires_deref: bool = False,
        deref_offset: int = 0,
        *,
        field_type: str | None = None,
        byte_length: int = 0,
        record_ptr: int | None = None,
    ) -> bool:
        """
        Write a field value with awareness of its declared type.
        Floats are encoded as IEEE-754; all other types fall back to bitfield writes.
        """
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return False
                record_addr = self._player_record_address(player_index, record_ptr=record_ptr)
                if record_addr is None:
                    return False
                addr = record_addr + offset
                if requires_deref and deref_offset:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                    if not struct_ptr:
                        return False
                    addr = struct_ptr + offset
                byte_len = self._effective_byte_length(byte_length, length, default=4)
                fmt = "<d" if byte_len >= 8 else "<f"
                if isinstance(value, (int, float)):
                    fval = float(value)
                else:
                    fval = float(str(value).strip())
                data = struct.pack(fmt, fval)
                data = data[: 8 if fmt == "<d" else 4]
                self.mem.write_bytes(addr, data)
                return True
            except Exception:
                return False
        try:
            if isinstance(value, (int, float, bool)):
                int_val = int(value)
            else:
                text = str(value).strip()
                if not text:
                    return False
                int_val = int(text)
        except Exception:
            return False
        return self.set_field_value(
            player_index,
            offset,
            start_bit,
            length,
            int_val,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            record_ptr=record_ptr,
        )

    def set_team_field_value(
        self,
        team_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        """Write a bitfield into the specified team record."""
        try:
            if not self.mem.open_process():
                return False
            record_addr = self._team_record_address(team_index)
            if record_addr is None:
                return False
            return self._write_field_bits(
                record_addr,
                offset,
                start_bit,
                length,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        except Exception:
            return False

    def _get_entity_field_value_typed(
        self,
        entity_kind: EntityKind,
        entity_index: int,
        offset: int,
        start_bit: int,
        length: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
    ) -> object | None:
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return None
                record_addr = self._resolve_entity_address(entity_kind, entity_index)
                if record_addr is None:
                    return None
                addr = self._resolve_field_address(
                    record_addr,
                    offset,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                )
                if addr is None:
                    return None
                byte_len = self._effective_byte_length(byte_length, length, default=4)
                fmt = "<d" if byte_len >= 8 else "<f"
                raw = self.mem.read_bytes(addr, 8 if fmt == "<d" else 4)
                return struct.unpack(fmt, raw[: 8 if fmt == "<d" else 4])[0]
            except Exception:
                return None
        if entity_kind == "team":
            return self.get_team_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
        if entity_kind == "staff":
            return self.get_staff_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
        if entity_kind == "stadium":
            return self.get_stadium_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
        return None

    def _set_entity_field_value_typed(
        self,
        entity_kind: EntityKind,
        entity_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: object,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return False
                record_addr = self._resolve_entity_address(entity_kind, entity_index)
                if record_addr is None:
                    return False
                addr = self._resolve_field_address(
                    record_addr,
                    offset,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                )
                if addr is None:
                    return False
                byte_len = self._effective_byte_length(byte_length, length, default=4)
                fmt = "<d" if byte_len >= 8 else "<f"
                fval = float(value) if isinstance(value, (int, float)) else float(str(value).strip())
                data = struct.pack(fmt, fval)
                self.mem.write_bytes(addr, data[: 8 if fmt == "<d" else 4])
                return True
            except Exception:
                return False

        try:
            if isinstance(value, (int, float, bool)):
                int_val = int(value)
            else:
                text = str(value).strip()
                if not text:
                    return False
                int_val = int(text)
        except Exception:
            return False

        if entity_kind == "team":
            return self.set_team_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                int_val,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        if entity_kind == "staff":
            return self.set_staff_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                int_val,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        if entity_kind == "stadium":
            return self.set_stadium_field_value(
                entity_index,
                offset,
                start_bit,
                length,
                int_val,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        return False

    def get_team_field_value_typed(
        self,
        team_index: int,
        offset: int,
        start_bit: int,
        length: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
    ) -> object | None:
        return self._get_entity_field_value_typed(
            "team",
            team_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
        )

    def set_team_field_value_typed(
        self,
        team_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: object,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        return self._set_entity_field_value_typed(
            "team",
            team_index,
            offset,
            start_bit,
            length,
            value,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
            deref_cache=deref_cache,
        )

    # ------------------------------------------------------------------
    # Staff/Stadium field access
    # ------------------------------------------------------------------
    def get_staff_field_value(
        self,
        staff_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> int | None:
        try:
            if not self.mem.open_process():
                return None
            record_addr = self._staff_record_address(staff_index)
            if record_addr is None:
                return None
            if requires_deref and deref_offset:
                struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                if not struct_ptr:
                    return None
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            raw = self.mem.read_bytes(addr, bytes_needed)
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length) - 1
            return value & mask
        except Exception:
            return None

    def get_staff_field_value_typed(
        self,
        staff_index: int,
        offset: int,
        start_bit: int,
        length: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
    ) -> object | None:
        return self._get_entity_field_value_typed(
            "staff",
            staff_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
        )

    def set_staff_field_value(
        self,
        staff_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        try:
            if not self.mem.open_process():
                return False
            record_addr = self._staff_record_address(staff_index)
            if record_addr is None:
                return False
            return self._write_field_bits(
                record_addr,
                offset,
                start_bit,
                length,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        except Exception:
            return False

    def set_staff_field_value_typed(
        self,
        staff_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: object,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        return self._set_entity_field_value_typed(
            "staff",
            staff_index,
            offset,
            start_bit,
            length,
            value,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
            deref_cache=deref_cache,
        )

    def get_stadium_field_value(
        self,
        stadium_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> int | None:
        try:
            if not self.mem.open_process():
                return None
            record_addr = self._stadium_record_address(stadium_index)
            if record_addr is None:
                return None
            if requires_deref and deref_offset:
                struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                if not struct_ptr:
                    return None
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            raw = self.mem.read_bytes(addr, bytes_needed)
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length) - 1
            return value & mask
        except Exception:
            return None

    def get_stadium_field_value_typed(
        self,
        stadium_index: int,
        offset: int,
        start_bit: int,
        length: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
    ) -> object | None:
        return self._get_entity_field_value_typed(
            "stadium",
            stadium_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
        )

    def set_stadium_field_value(
        self,
        stadium_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        try:
            if not self.mem.open_process():
                return False
            record_addr = self._stadium_record_address(stadium_index)
            if record_addr is None:
                return False
            return self._write_field_bits(
                record_addr,
                offset,
                start_bit,
                length,
                value,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                deref_cache=deref_cache,
            )
        except Exception:
            return False

    def set_stadium_field_value_typed(
        self,
        stadium_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: object,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
        field_type: str | None = None,
        byte_length: int = 0,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        return self._set_entity_field_value_typed(
            "stadium",
            stadium_index,
            offset,
            start_bit,
            length,
            value,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            field_type=field_type,
            byte_length=byte_length,
            deref_cache=deref_cache,
        )

    # ------------------------------------------------------------------
    # Helpers for free agents and teams
    # ------------------------------------------------------------------
    def _player_flag_entry(self, entry_name: str) -> dict | None:
        if entry_name in self._player_flag_entries:
            return self._player_flag_entries[entry_name]
        # Local import to avoid widening the public surface of core.offsets
        from ..core.offsets import _find_offset_entry  # type: ignore

        entry = _find_offset_entry(entry_name, "Vitals") or _find_offset_entry(entry_name)
        self._player_flag_entries[entry_name] = entry
        return entry

    def _read_player_flag(self, player: Player, entry_name: str) -> bool:
        if not player or not self.mem.open_process():
            return False
        entry = self._player_flag_entry(entry_name)
        if not entry:
            return False
        cached = self._player_flag_cache.setdefault(entry_name, {})
        if player.index in cached:
            return cached[player.index]
        record_addr = self._player_record_address(player.index, record_ptr=getattr(player, "record_ptr", None))
        if record_addr is None:
            cached[player.index] = False
            return False
        value = self.decode_field_value(
            entity_type="player",
            entity_index=player.index,
            category="Vitals",
            field_name=entry_name,
            meta=entry,
            record_ptr=record_addr,
        )
        flag = bool(to_int(value))
        cached[player.index] = flag
        return flag

    def is_player_draft_prospect(self, player: Player) -> bool:
        return self._read_player_flag(player, "IS_DRAFT_PROSPECT")

    def is_player_hidden(self, player: Player) -> bool:
        return self._read_player_flag(player, "IS_HIDDEN")

    def get_draft_prospects(self) -> list[Player]:
        if not self.players or not self.mem.open_process():
            return []
        if not self._player_flag_entry("IS_DRAFT_PROSPECT"):
            return []
        return [p for p in self.players if self.is_player_draft_prospect(p)]

    def is_player_free_agent_group(self, player: Player) -> bool:
        entry_hidden = self._player_flag_entry("IS_HIDDEN")
        entry_draft = self._player_flag_entry("IS_DRAFT_PROSPECT")
        if not entry_hidden or not entry_draft or not self.mem.open_process():
            return bool(player and (player.team_id == FREE_AGENT_TEAM_ID or (player.team or "").strip().lower().startswith("free")))
        return (not self.is_player_hidden(player)) and (not self.is_player_draft_prospect(player))

    def get_free_agents_by_flags(self) -> list[Player]:
        if not self.players or not self.mem.open_process():
            return []
        entry_hidden = self._player_flag_entry("IS_HIDDEN")
        entry_draft = self._player_flag_entry("IS_DRAFT_PROSPECT")
        if not entry_hidden or not entry_draft:
            return self._get_free_agents()
        return [p for p in self.players if self.is_player_free_agent_group(p)]

    def _get_free_agents(self) -> list[Player]:
        if self._cached_free_agents:
            return list(self._cached_free_agents)
        if not self.players:
            players = self._scan_all_players(self.max_players)
            if players:
                self.players = players
                self._apply_team_display_to_players(self.players)
                self._build_name_index_map_async()
        if not self.players:
            return []
        free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
        if free_agents:
            self._cached_free_agents = list(free_agents)
            return list(free_agents)
        assigned = self._collect_assigned_player_indexes()
        if assigned:
            free_agents = [p for p in self.players if p.index not in assigned]
        else:
            free_agents = [p for p in self.players if (p.team or "").strip().lower().startswith("free")]
        self._cached_free_agents = list(free_agents)
        return list(free_agents)


__all__ = ["PlayerDataModel"]
