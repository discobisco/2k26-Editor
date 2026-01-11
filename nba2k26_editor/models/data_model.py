"""
Data model for scanning and editing NBA 2K26 roster data.

This module lifts the non-UI portions of PlayerDataModel from the monolithic
2k26Editor.py so it can be reused by multiple frontends.
"""
from __future__ import annotations

import copy
import json
import os
import random
import re
import struct
import threading
import unicodedata
from collections import Counter
from typing import Any, Dict, Sequence, Iterable
from typing import Callable

from ..ai.detection import LocalAIDetectionResult
from ..core.config import CACHE_DIR, BASE_DIR
from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    BADGE_NAME_TO_VALUE,
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    format_height_inches,
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
from ..core.offsets import (
    ATTR_IMPORT_ORDER,
    DRAFT_CLASS_TEAM_ID,
    DUR_IMPORT_ORDER,
    FIELD_NAME_ALIASES,
    MAX_TEAMS_SCAN,
    MAX_STAFF_SCAN,
    MAX_STADIUM_SCAN,
    FIRST_NAME_ENCODING,
    LAST_NAME_ENCODING,
    MAX_DRAFT_PLAYERS,
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
    PLAYER_TABLE_RVA,
    POTENTIAL_IMPORT_ORDER,
    TEAM_FIELD_DEFS,
    TEAM_PLAYER_SLOT_COUNT,
    TEAM_PTR_CHAINS,
    TEAM_RECORD_SIZE,
    TEAM_STRIDE,
    TEAM_TABLE_RVA,
    TEAM_NAME_ENCODING,
    TEAM_NAME_LENGTH,
    TEAM_NAME_OFFSET,
    TEND_IMPORT_ORDER,
    STAFF_PTR_CHAINS,
    STAFF_STRIDE,
    STAFF_RECORD_SIZE,
    STAFF_NAME_OFFSET,
    STAFF_NAME_LENGTH,
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
        self.team_name_map: Dict[int, str] = {}
        self.team_list: list[tuple[int, str]] = []
        self.staff_list: list[tuple[int, str]] = []
        self.stadium_list: list[tuple[int, str]] = []
        self._cached_free_agents: list[Player] = []
        self.draft_players: list[Player] = []
        self._resolved_player_base: int | None = None
        self._resolved_team_base: int | None = None
        self._resolved_draft_base: int | None = None
        self._resolved_staff_base: int | None = None
        self._resolved_stadium_base: int | None = None
        self._resolved_base_pid: int | None = None
        self._name_index_lock = threading.Lock()
        self._name_index_build_token = 0
        team_candidates = [
            "2K26 Team Data (10.18.24).txt",
            "2K26 Team Data.txt",
        ]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for name in team_candidates:
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                mapping = self.parse_team_comments(path)
                if mapping:
                    self.team_name_map = mapping
                break
        # Load offsets even when the game process is not present so the UI can still render categories.
        self.categories: dict[str, list[dict]] = {}
        try:
            offset_target = self.mem.module_name
            if self.mem.open_process():
                offset_target = self.mem.module_name
            initialize_offsets(target_executable=offset_target, force=True)
            self._sync_offset_constants()
            self.categories = _load_categories()
        except Exception:
            self.categories = {}
        self._reorder_categories()
        self.import_partial_matches: dict[str, dict[str, list[dict[str, object]]]] = {}

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

    def invalidate_base_cache(self) -> None:
        """Clear cached table base pointers so they are re-resolved on demand."""
        self._resolved_player_base = None
        self._resolved_team_base = None
        self._resolved_draft_base = None
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
            self._resolved_draft_base = None
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
        # Build lower-cased lookups
        super_map = {str(k).lower(): str(v).lower() for k, v in offsets_mod.CATEGORY_SUPER_TYPES.items()}
        canon_map = {str(k).lower(): str(v) for k, v in offsets_mod.CATEGORY_CANONICAL.items()}
        # Omit internal/helper categories that should not render as tabs.
        hidden_cats = {"team pointers"}
        grouped: dict[str, list[dict]] = {}
        for cat_name, fields in (self.categories or {}).items():
            cat_lower = str(cat_name).lower()
            if cat_lower in hidden_cats:
                continue
            mapped = super_map.get(cat_lower)
            if mapped != target:
                continue
            canon_label = canon_map.get(cat_lower, cat_name)
            grouped.setdefault(canon_label, []).extend(fields if isinstance(fields, list) else [])
        return grouped

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

    def _normalize_header_name(self, name: object) -> str:
        norm = re.sub(r"[^A-Za-z0-9]", "", str(name).upper())
        if not norm:
            return ""
        return FIELD_NAME_ALIASES.get(norm, norm)

    def _reorder_categories(self) -> None:
        """
        Reorder categories and fields to mirror the monolith:
        - peel durability fields out of Attributes into a Durability category
        - reorder key categories using import-order lists
        - drop team-only categories from the player UI
        """
        cats = self.categories if isinstance(self.categories, dict) else {}
        self.categories = cats
        # Drop team-centric categories from the player editor
        for skip in ("Teams", "Team Players"):
            cats.pop(skip, None)

        def _normalize_field_name_local(field: dict) -> str:
            return self._normalize_field_name(field.get("name", ""))

        # Extract durability fields from Attributes into their own category
        if "Attributes" in cats:
            attr_fields = cats.get("Attributes", [])
            new_attr: list[dict] = []
            dura_fields = cats.get("Durability", [])
            for fld in attr_fields:
                name = fld.get("name", "")
                norm = self._normalize_field_name(name)
                if norm and "DURABILITY" in norm and norm not in ("MISCDURABILITY",):
                    dura_fields.append(fld)
                else:
                    new_attr.append(fld)
            cats["Attributes"] = new_attr
            if dura_fields:
                cats["Durability"] = dura_fields

        def _reorder_category(cat_name: str, import_order: list[str]) -> None:
            fields = cats.get(cat_name, [])
            if not fields:
                return
            remaining = list(fields)
            reordered: list[dict] = []
            for hdr in import_order:
                norm_hdr = self._normalize_header_name(hdr)
                if not norm_hdr:
                    continue
                best_idx = -1
                best_score = 3  # lower is better
                for idx, fdef in enumerate(remaining):
                    norm_field = _normalize_field_name_local(fdef)
                    if not norm_field:
                        continue
                    score = None
                    if norm_hdr == norm_field:
                        score = 0
                    elif norm_hdr in norm_field:
                        score = 1
                    elif norm_field in norm_hdr:
                        score = 2
                    if score is None or score >= best_score:
                        continue
                    best_idx = idx
                    best_score = score
                    if score == 0:
                        break
                if best_idx >= 0:
                    reordered.append(remaining.pop(best_idx))
            reordered.extend(remaining)
            cats[cat_name] = reordered

        _reorder_category("Attributes", ATTR_IMPORT_ORDER)
        _reorder_category("Tendencies", TEND_IMPORT_ORDER)
        _reorder_category("Durability", DUR_IMPORT_ORDER)
        _reorder_category("Potential", POTENTIAL_IMPORT_ORDER)
        ordered: dict[str, list[dict]] = {}
        preferred = ["Body", "Vitals", "Attributes", "Durability", "Potential", "Tendencies", "Badges"]
        for name in preferred:
            if name in cats:
                ordered[name] = cats[name]
        for name, fields in cats.items():
            if name not in ordered:
                ordered[name] = fields
        self.categories = ordered

    # ------------------------------------------------------------------
    # Cheat Engine team table support
    # ------------------------------------------------------------------
    def parse_team_comments(self, filepath: str) -> Dict[int, str]:
        """Parse the <Comments> section of a CE table to extract team names."""
        mapping: Dict[int, str] = {}
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            start = text.find("<Comments>")
            end = text.find("</Comments>", start + 1)
            if start == -1 or end == -1:
                return mapping
            comments = text[start + len("<Comments>") : end]
            for line in comments.strip().splitlines():
                line = line.strip()
                if not line or "-" not in line:
                    continue
                idx_str, name = line.split("-", 1)
                idx_str = idx_str.strip()
                name = name.strip()
                base = 16 if any(c in idx_str.upper() for c in "ABCDEF") else 10
                try:
                    idx = int(idx_str, base)
                    mapping[idx] = name
                except ValueError:
                    continue
        except Exception:
            pass
        return mapping

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
                final_offset = to_int(chain_entry.get("final_offset") or chain_entry.get("finalOffset"))
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
                    extra = to_int(
                        step.get("post_add")
                        or step.get("postAdd")
                        or step.get("post")
                        or step.get("post_offset")
                        or step.get("postOffset")
                        or step.get("final_offset")
                        or step.get("finalOffset")
                    )
                    if extra:
                        ptr += extra
            except Exception:
                return None
            final_offset = to_int(chain_entry.get("final_offset") or chain_entry.get("finalOffset"))
            if final_offset:
                ptr += final_offset
            return ptr
        if isinstance(chain_entry, tuple) and len(chain_entry) == 3:
            try:
                rva_off, final_off, extra_deref = chain_entry
                p0_addr = self.mem.base_addr + rva_off
                p = self.mem.read_uint64(p0_addr)
                if extra_deref:
                    if p == 0:
                        return None
                    p = self.mem.read_uint64(p)
                return p + final_off
            except Exception:
                return None
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
            try:
                # Looser validation: accept base if any probe yields printable text, and
                # fall back to stride alignment without text if probes are empty.
                probe_offsets: list[tuple[int, int, str]] = []
                if OFF_LAST_NAME >= 0:
                    probe_offsets.append((OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING))
                if OFF_FIRST_NAME >= 0:
                    probe_offsets.append((OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING))
                if not probe_offsets:
                    self._resolved_player_base = base_addr
                    return True
                for offset, max_chars, encoding in probe_offsets:
                    raw = self._read_string(base_addr + offset, max_chars, encoding).strip()
                    if raw:
                        self._resolved_player_base = base_addr
                        return True
            except Exception:
                return False
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
            if TEAM_NAME_OFFSET < 0 or TEAM_NAME_LENGTH <= 0:
                return True  # no reliable validation available; accept candidate
            try:
                name = self._read_string(base_addr + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
            except Exception:
                return False
            if not name:
                return False
            return not any(ord(ch) < 32 or ord(ch) > 126 for ch in name)

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
        try:
            if not self.mem.open_process():
                return None
        except Exception:
            return None

        def _is_valid_staff_base(base_addr: int | None) -> bool:
            if base_addr is None or STAFF_NAME_OFFSET <= 0 or STAFF_NAME_LENGTH <= 0:
                return False
            try:
                name = self._read_string(base_addr + STAFF_NAME_OFFSET, STAFF_NAME_LENGTH, STAFF_NAME_ENCODING).strip()
            except Exception:
                return False
            return bool(name)

        if STAFF_PTR_CHAINS:
            for chain in STAFF_PTR_CHAINS:
                base = self._resolve_pointer_from_chain(chain)
                if _is_valid_staff_base(base):
                    self._resolved_staff_base = base
                    return base
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

        if STADIUM_PTR_CHAINS:
            for chain in STADIUM_PTR_CHAINS:
                base = self._resolve_pointer_from_chain(chain)
                if _is_valid_stadium_base(base):
                    self._resolved_stadium_base = base
                    return base
        self._resolved_stadium_base = None
        return None

    def _resolve_draft_base_ptr(self) -> int | None:
        if self._resolved_draft_base is not None:
            return self._resolved_draft_base
        try:
            if not self.mem.open_process():
                return None
        except Exception:
            return None
        from ..core.offsets import DRAFT_PTR_CHAINS

        def _is_valid_draft_base(base_addr: int | None) -> bool:
            if base_addr is None:
                return False
            has_last = OFF_LAST_NAME >= 0 and NAME_MAX_CHARS > 0
            has_first = OFF_FIRST_NAME >= 0 and NAME_MAX_CHARS > 0
            if not (has_last or has_first):
                return True  # no validation available; accept candidate
            try:
                first = self._read_string(base_addr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
                last = self._read_string(base_addr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
            except Exception:
                return False
            if not first and not last:
                return False
            combined = (first or "") + (last or "")
            return not any(ord(ch) < 32 or ord(ch) > 126 for ch in combined)

        if DRAFT_PTR_CHAINS:
            for chain in DRAFT_PTR_CHAINS:
                candidate = self._resolve_pointer_from_chain(chain)
                if _is_valid_draft_base(candidate):
                    self._resolved_draft_base = candidate
                    try:
                        print(f"[data_model] draft_base resolved to 0x{candidate:X}")
                    except Exception:
                        pass
                    return candidate
        self._resolved_draft_base = None
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
        if PLAYER_STRIDE <= 0 or not self.mem.hproc or self.mem.base_addr is None:
            return players
        table_base = self._resolve_player_base_ptr()
        if table_base is None:
            return players
        team_base_ptr = self._resolve_team_base_ptr()
        team_stride = TEAM_STRIDE
        max_count = min(limit, MAX_PLAYERS)
        if team_base_ptr is not None and team_base_ptr > table_base and PLAYER_STRIDE > 0:
            max_before_team = int((team_base_ptr - table_base) // PLAYER_STRIDE)
            if max_before_team > 0:
                max_count = min(max_count, max_before_team)
        if max_count <= 0:
            return players

        first_enc = self._normalize_encoding_tag(FIRST_NAME_ENCODING)
        last_enc = self._normalize_encoding_tag(LAST_NAME_ENCODING)
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

        batch_size = min(6000, max_count)
        batch_fallback_enabled = False
        for start in range(0, max_count, batch_size):
            batch_count = min(batch_size, max_count - start)
            batch_addr = table_base + start * PLAYER_STRIDE
            batch_len = batch_count * PLAYER_STRIDE
            try:
                chunk = self.mem.read_bytes(batch_addr, batch_len)
            except Exception:
                if not batch_fallback_enabled:
                    return players
                for idx in range(start, start + batch_count):
                    p_addr = table_base + idx * PLAYER_STRIDE
                    try:
                        last_name = self._read_string(p_addr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                        first_name = self._read_string(p_addr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
                    except Exception:
                        continue
                    # Skip entries with non-ASCII names (common for uninitialized slots)
                    name_combo = (first_name or "") + (last_name or "")
                    if any(ord(ch) < 32 or ord(ch) > 126 for ch in name_combo):
                        continue
                    team_name = "Unknown"
                    team_id_val: int | None = None
                    try:
                        if OFF_TEAM_PTR > 0:
                            team_ptr = self.mem.read_uint64(p_addr + OFF_TEAM_PTR)
                            if team_ptr == 0:
                                team_name = "Free Agents"
                                team_id_val = FREE_AGENT_TEAM_ID
                            else:
                                tn = self._read_string(team_ptr + OFF_TEAM_NAME, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                                team_name = tn or "Unknown"
                                if team_base_ptr and team_stride > 0:
                                    rel = team_ptr - team_base_ptr
                                    if rel >= 0 and rel % team_stride == 0:
                                        team_id_val = int(rel // team_stride)
                        elif OFF_TEAM_ID > 0:
                            tid_val = self.mem.read_uint32(p_addr + OFF_TEAM_ID)
                            team_id_val = int(tid_val)
                            team_name = self._get_team_display_name(team_id_val)
                    except Exception:
                        pass
                    if not first_name and not last_name:
                        continue
                    players.append(
                        Player(
                            idx,
                            first_name,
                            last_name,
                            team_name,
                            team_id_val,
                            record_ptr=p_addr,
                        )
                    )
                continue

            view = memoryview(chunk)
            for offset_idx in range(batch_count):
                idx = start + offset_idx
                base_offset = offset_idx * PLAYER_STRIDE
                p_addr = table_base + idx * PLAYER_STRIDE
                last_name = _decode_string(view, base_offset + OFF_LAST_NAME, NAME_MAX_CHARS, last_enc).strip()
                first_name = _decode_string(view, base_offset + OFF_FIRST_NAME, NAME_MAX_CHARS, first_enc).strip()
                # Skip entries with non-ASCII names (common for uninitialized slots)
                name_combo = (first_name or "") + (last_name or "")
                if any(ord(ch) < 32 or ord(ch) > 126 for ch in name_combo):
                    continue
                team_name = "Unknown"
                team_id_val: int | None = None
                try:
                    if OFF_TEAM_PTR > 0:
                        team_ptr = _read_uint64(view, base_offset + OFF_TEAM_PTR)
                        if team_ptr is None:
                            try:
                                team_ptr = self.mem.read_uint64(p_addr + OFF_TEAM_PTR)
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
                                tn = self._read_string(team_ptr + OFF_TEAM_NAME, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                                team_name = tn or "Unknown"
                                if team_base_ptr and team_stride > 0:
                                    rel = team_ptr - team_base_ptr
                                    if rel >= 0 and rel % team_stride == 0:
                                        team_id_val = int(rel // team_stride)
                                team_ptr_cache[team_ptr] = (team_name, team_id_val)
                    elif OFF_TEAM_ID > 0:
                        tid_val = _read_uint32(view, base_offset + OFF_TEAM_ID)
                        if tid_val is None:
                            tid_val = self.mem.read_uint32(p_addr + OFF_TEAM_ID)
                        team_id_val = int(tid_val)
                        team_name = self._get_team_display_name(team_id_val)
                except Exception:
                    pass
                if not first_name and not last_name:
                    continue
                players.append(
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

    def _scan_draft_class_players(self, max_scan: int | None = None) -> list[Player]:
        """Enumerate players stored in the Draft Class table if configured."""
        if not self.mem.hproc or self.mem.base_addr is None:
            return []
        if PLAYER_STRIDE <= 0:
            return []
        # Local import avoids pulling DRAFT_PTR_CHAINS at module import time
        from ..core.offsets import DRAFT_PTR_CHAINS  # type: ignore

        if not DRAFT_PTR_CHAINS:
            return []
        table_base = self._resolve_draft_base_ptr()
        if table_base is None:
            return []
        team_base_ptr = self._resolve_team_base_ptr()
        team_stride = TEAM_STRIDE
        limit = max_scan if max_scan is not None else MAX_DRAFT_PLAYERS
        limit = max(0, min(limit, MAX_DRAFT_PLAYERS))
        players: list[Player] = []
        blank_streak = 0
        BLANK_THRESHOLD = 8
        for i in range(limit):
            p_addr = table_base + i * PLAYER_STRIDE
            try:
                last_name = self._read_string(p_addr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                first_name = self._read_string(p_addr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
            except Exception:
                blank_streak += 1
                if blank_streak >= BLANK_THRESHOLD:
                    break
                continue
            name_combo = (first_name or "") + (last_name or "")
            if any(ord(ch) < 32 or ord(ch) > 126 for ch in name_combo):
                blank_streak += 1
                if blank_streak >= BLANK_THRESHOLD:
                    break
                continue
            if not first_name and not last_name:
                blank_streak += 1
                if blank_streak >= BLANK_THRESHOLD:
                    break
                continue
            blank_streak = 0
            team_name = "Draft Class"
            team_id: int | None = DRAFT_CLASS_TEAM_ID
            try:
                if OFF_TEAM_PTR > 0:
                    team_ptr = self.mem.read_uint64(p_addr + OFF_TEAM_PTR)
                    if team_ptr == 0:
                        team_name = "Free Agents"
                        team_id = FREE_AGENT_TEAM_ID
                    else:
                        tn = self._read_string(team_ptr + OFF_TEAM_NAME, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                        team_name = tn or team_name
                        if team_base_ptr and team_stride > 0:
                            rel = team_ptr - team_base_ptr
                            if rel >= 0 and rel % team_stride == 0:
                                team_id = int(rel // team_stride)
                elif OFF_TEAM_ID > 0:
                    tid_val = self.mem.read_uint32(p_addr + OFF_TEAM_ID)
                    team_id = int(tid_val)
                    team_name = self._get_team_display_name(team_id)
            except Exception:
                pass
            players.append(
                Player(
                    self.max_players + i,
                    first_name,
                    last_name,
                    team_name,
                    team_id,
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
        return {idx: name for idx, name in self.team_list}

    def _team_index_for_display_name(self, display_name: str) -> int | None:
        """Resolve a display name back to its team index."""
        for idx, name in self.team_list:
            if name == display_name:
                return idx
        return None

    def _get_team_display_name(self, team_idx: int) -> str:
        return self._team_display_map().get(team_idx, f"Team {team_idx}")

    def get_teams(self) -> list[str]:
        """Return the list of team names in a logical order."""
        if not self.team_list:
            return []

        def _classify(entry: tuple[int, str]) -> str:
            tid, name = entry
            lname = name.lower()
            if tid == FREE_AGENT_TEAM_ID or "free" in lname:
                return "free_agents"
            if "draft" in lname:
                return "draft_class"
            return "normal"

        free_agents: list[str] = []
        remaining: list[tuple[int, str]] = []
        for entry in self.team_list:
            category = _classify(entry)
            if category == "free_agents":
                free_agents.append(entry[1])
            elif category == "draft_class":
                continue
            else:
                remaining.append(entry)
        remaining_sorted = [name for _, name in sorted(remaining, key=lambda item: item[0])]
        ordered: list[str] = []
        ordered.extend(free_agents)
        ordered.extend(remaining_sorted)
        return ordered

    def refresh_staff(self) -> list[tuple[int, str]]:
        """Populate staff_list from live memory if pointers are available."""
        self.staff_list = []
        if STAFF_RECORD_SIZE <= 0 or STAFF_NAME_LENGTH <= 0 or STAFF_NAME_OFFSET <= 0:
            return self.staff_list
        try:
            if not self.mem.open_process():
                return self.staff_list
        except Exception:
            return self.staff_list
        base_ptr = self._resolve_staff_base_ptr()
        if base_ptr is None:
            return self.staff_list
        for idx in range(MAX_STAFF_SCAN):
            rec_addr = base_ptr + idx * STAFF_RECORD_SIZE
            try:
                first = self._read_string(rec_addr + STAFF_NAME_OFFSET, STAFF_NAME_LENGTH, STAFF_NAME_ENCODING).strip()
            except Exception:
                continue
            name = first
            if not name:
                continue
            self.staff_list.append((idx, name))
        return self.staff_list

    def get_staff(self) -> list[str]:
        """Return staff names in scan order."""
        return [name for _, name in self.staff_list]

    def refresh_stadiums(self) -> list[tuple[int, str]]:
        """Populate stadium_list from live memory if pointers are available."""
        self.stadium_list = []
        if STADIUM_RECORD_SIZE <= 0 or STADIUM_NAME_LENGTH <= 0 or STADIUM_NAME_OFFSET <= 0:
            return self.stadium_list
        try:
            if not self.mem.open_process():
                return self.stadium_list
        except Exception:
            return self.stadium_list
        base_ptr = self._resolve_stadium_base_ptr()
        if base_ptr is None:
            return self.stadium_list
        for idx in range(MAX_STADIUM_SCAN):
            rec_addr = base_ptr + idx * STADIUM_RECORD_SIZE
            try:
                name = self._read_string(rec_addr + STADIUM_NAME_OFFSET, STADIUM_NAME_LENGTH, STADIUM_NAME_ENCODING).strip()
            except Exception:
                continue
            if not name:
                continue
            self.stadium_list.append((idx, name))
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
        self.team_list = []
        self.players = []
        self.external_loaded = False
        self._cached_free_agents = []
        self.draft_players = []
        self.name_index_map = {}

        if not self.mem.open_process():
            return
        self.prime_bases(open_process=False)

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

        players_all = self._scan_all_players(self.max_players)

        self.players = players_all
        self._cached_free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
        self._apply_team_display_to_players(self.players)
        self._build_name_index_map_async()

    def get_players_by_team(self, team: str) -> list[Player]:
        team_name = (team or "").strip()
        if not team_name:
            return []
        team_lower = team_name.lower()
        if team_lower == "all players":
            if not self.players:
                return []
            return list(self.players)
        if "draft" in team_lower:
            return list(self.draft_players)
        if team_lower.startswith("free"):
            return self._get_free_agents()
        team_idx = None
        for idx, name in self.team_list:
            if name == team_name:
                team_idx = idx
                break
        if team_idx == DRAFT_CLASS_TEAM_ID:
            return list(self.draft_players)
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return None
                record_addr = self._team_record_address(team_index)
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
        return self.get_team_field_value(
            team_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return False
                record_addr = self._team_record_address(team_index)
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
        return self.set_team_field_value(
            team_index,
            offset,
            start_bit,
            length,
            int_val,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return None
                record_addr = self._staff_record_address(staff_index)
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
        return self.get_staff_field_value(
            staff_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return False
                record_addr = self._staff_record_address(staff_index)
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
        return self.set_staff_field_value(
            staff_index,
            offset,
            start_bit,
            length,
            int_val,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return None
                record_addr = self._stadium_record_address(stadium_index)
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
        return self.get_stadium_field_value(
            stadium_index,
            offset,
            start_bit,
            length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
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
        ftype = (field_type or "").lower()
        if "float" in ftype:
            try:
                if not self.mem.open_process():
                    return False
                record_addr = self._stadium_record_address(stadium_index)
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
        return self.set_stadium_field_value(
            stadium_index,
            offset,
            start_bit,
            length,
            int_val,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            deref_cache=deref_cache,
        )

    # ------------------------------------------------------------------
    # Helpers for free agents and teams
    # ------------------------------------------------------------------
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
