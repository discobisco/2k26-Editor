"""
Data model for scanning and editing NBA 2K26 roster data.

This module lifts the non-UI portions of PlayerDataModel from the monolithic
2k26Editor.py so it can be reused by multiple frontends.
"""
from __future__ import annotations

import copy
import csv
import json
import os
import random
import re
import struct
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Sequence, Iterable, cast
from typing import Callable

from ..importing import csv_import
from ..ai.detection import LocalAIDetectionResult
from ..core.config import CACHE_DIR, BASE_DIR
from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    BADGE_NAME_TO_VALUE,
    format_height_inches,
    convert_rating_to_raw,
    convert_raw_to_rating,
    convert_minmax_potential_to_raw,
    convert_raw_to_minmax_potential,
    convert_rating_to_tendency_raw,
    convert_tendency_raw_to_rating,
    raw_height_to_inches,
    read_weight,
    write_weight,
    to_int,
)
from ..core import offsets as offsets_mod
from ..core.offsets import (
    ATTR_IMPORT_ORDER,
    COY_IMPORT_LAYOUTS,
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
from .schema import FieldMetadata, FieldWriteSpec, PreparedImportRows, ExportFieldSpec

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
        self.name_index_map.clear()
        for player in self.players:
            first = player.first_name or ""
            last = player.last_name or ""
            if not first and not last:
                continue
            for key in self._generate_name_keys(first, last):
                if key:
                    self.name_index_map.setdefault(key, []).append(player.index)

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

    def _normalize_coy_header_name(self, name: object) -> str:
        norm = re.sub(r"[^A-Za-z0-9]", "", str(name).upper())
        if not norm:
            return ""
        header_synonyms = {
            "LAYUP": "DRIVINGLAYUP",
            "STDUNK": "STANDINGDUNK",
            "DUNK": "DRIVINGDUNK",
            "CLOSE": "CLOSESHOT",
            "MID": "MIDRANGE",
            "3PT": "THREEPOINT",
            "FT": "FREETHROW",
            "PHOOK": "POSTHOOK",
            "PFADE": "POSTFADE",
            "POSTC": "POSTCONTROL",
            "FOUL": "DRAWFOUL",
            "BALL": "BALLCONTROL",
            "SPDBALL": "SPEEDWITHBALL",
            "PASSIQ": "PASSINGIQ",
            "PASS_IQ": "PASSINGIQ",
            "PASS": "PASSINGACCURACY",
            "VISION": "PASSINGVISION",
            "OCNST": "OFFENSIVECONSISTENCY",
            "ID": "INTERIORDEFENSE",
            "PD": "PERIMETERDEFENSE",
            "STEAL": "STEAL",
            "BLOCK": "BLOCK",
            "OREB": "OFFENSIVEREBOUND",
            "DREB": "DEFENSIVEREBOUND",
            "HELPIQ": "HELPDEFENSEIQ",
            "PSPER": "PASSINGPERCEPTION",
            "DCNST": "DEFENSIVECONSISTENCY",
            "SPEED": "SPEED",
            "AGIL": "AGILITY",
            "STR": "STRENGTH",
            "VERT": "VERTICAL",
            "STAM": "STAMINA",
            "INTNGBL": "INTANGIBLES",
            "HSTL": "HUSTLE",
            "DUR": "MISCDURABILITY",
            "POT": "POTENTIAL",
        }
        norm = header_synonyms.get(norm, norm)
        return FIELD_NAME_ALIASES.get(norm, norm)

    def _get_import_order(self, category_name: str) -> list[str]:
        name = (category_name or "").strip().lower()
        if name == "attributes":
            return ATTR_IMPORT_ORDER
        if name == "tendencies":
            return TEND_IMPORT_ORDER
        if name == "durability":
            return DUR_IMPORT_ORDER
        if name == "potential":
            return POTENTIAL_IMPORT_ORDER
        return []

    def _get_import_fields(self, category_name: str, context: str | None = None) -> list[dict]:
        """Return fields ordered according to the import layout for the category."""
        fields = self.categories.get(category_name, [])
        order_map: dict[str, list[str]] = {
            "Attributes": ATTR_IMPORT_ORDER,
            "Tendencies": TEND_IMPORT_ORDER,
            "Durability": DUR_IMPORT_ORDER,
            "Potential": POTENTIAL_IMPORT_ORDER,
        }
        import_order = order_map.get(category_name)
        if not fields or not import_order:
            return list(fields)
        context_key = (context or "").strip().lower()
        if context_key in {"excel", "excel_template"}:
            remaining = list(fields)
            selected: list[dict] = []
            for hdr in import_order:
                match_idx = -1
                for idx, fdef in enumerate(remaining):
                    if str(fdef.get("name", "")).strip() == hdr:
                        match_idx = idx
                        break
                if match_idx >= 0:
                    selected.append(remaining.pop(match_idx))
            if remaining:
                selected.extend(remaining)
            return selected
        norm_header = self._normalize_coy_header_name if context_key == "coy" else self._normalize_header_name
        remaining = list(fields)
        selected: list[dict] = []
        for hdr in import_order:
            norm_hdr = norm_header(hdr)
            match_idx = -1
            for idx, fdef in enumerate(remaining):
                norm_field = self._normalize_field_name(fdef.get("name", ""))
                if norm_hdr == norm_field or norm_hdr in norm_field or norm_field in norm_hdr:
                    match_idx = idx
                    break
            if match_idx >= 0:
                selected.append(remaining.pop(match_idx))
        if remaining:
            selected.extend(remaining)
        return selected

    def prepare_import_rows(
        self,
        category_name: str,
        rows: Sequence[Sequence[str]],
        *,
        context: str = "default",
    ) -> PreparedImportRows | None:
        if not rows:
            return None
        layout_raw = COY_IMPORT_LAYOUTS.get(category_name) if context == "coy" else None
        layout: dict[str, object] | None = layout_raw if isinstance(layout_raw, dict) else None
        if layout:
            norm_header = self._normalize_coy_header_name
            value_columns_raw = layout.get("value_columns")
            value_columns = [int(col) for col in cast(Iterable[int | str], value_columns_raw)] if value_columns_raw else []
            column_headers_raw = layout.get("column_headers")
            column_headers = [str(header) for header in cast(Iterable[Any], column_headers_raw)] if column_headers_raw else []
            skip_names_raw = layout.get("skip_names")
            skip_names = {str(s).strip().lower() for s in cast(Iterable[Any], skip_names_raw)} if skip_names_raw else set()
            name_columns_raw = layout.get("name_columns")
            if name_columns_raw:
                name_columns = [int(col) for col in cast(Iterable[int | str], name_columns_raw)]
            else:
                name_col_fallback = layout.get("name_col")
                name_columns = [int(cast(int | str, name_col_fallback))] if name_col_fallback is not None else [0]
            if column_headers and not value_columns:
                value_columns = list(range(1, 1 + len(column_headers)))
            header_lookup: dict[str, int] = {}
            header_row: list[str] | None = None
            if column_headers:
                for row in rows:
                    normalized_row = [str(cell) for cell in row]
                    if any(
                        normalized_row[col].strip().lower() in skip_names
                        for col in name_columns
                        if col < len(normalized_row)
                    ):
                        header_row = normalized_row
                        break
                if header_row is None:
                    header_row = [str(cell) for cell in rows[0]]
                for idx, cell in enumerate(header_row):
                    norm_cell = norm_header(cell)
                    if norm_cell and norm_cell not in header_lookup:
                        header_lookup[norm_cell] = idx
            resolved_value_indices: list[int] = []
            if column_headers:
                for hdr in column_headers:
                    norm_hdr = norm_header(hdr)
                    if norm_hdr and norm_hdr in header_lookup:
                        resolved_value_indices.append(header_lookup[norm_hdr])
                if resolved_value_indices and len(resolved_value_indices) < max(4, len(column_headers) // 2):
                    resolved_value_indices = []

            def _is_valid_name(cell: str) -> bool:
                normalized = cell.strip()
                if not normalized:
                    return False
                if normalized.lower() in skip_names:
                    return False
                return any(ch.isalpha() for ch in normalized)

            def _row_has_numeric(row: Sequence[str]) -> bool:
                target_columns = resolved_value_indices or value_columns
                if not target_columns and column_headers:
                    target_columns = [i for i in range(len(row)) if i not in name_columns]
                for idx in target_columns:
                    if idx >= len(row):
                        continue
                    cell = row[idx].strip()
                    if cell and any(ch.isdigit() for ch in cell) and not any(ch.isalpha() for ch in cell):
                        return True
                return False

            data_rows: list[list[str]] = []
            for row in rows:
                normalized_row = [str(cell) for cell in row]
                name_value: str | None = None
                used_name_col: int | None = None
                for col in name_columns:
                    if col >= len(normalized_row):
                        continue
                    candidate = normalized_row[col].strip()
                    if _is_valid_name(candidate):
                        name_value = candidate
                        used_name_col = col
                        break
                if not name_value:
                    continue
                if not _row_has_numeric(normalized_row):
                    continue
                values: list[str]
                if column_headers:
                    values = []
                    matched_count = 0
                    for hdr in column_headers:
                        norm_hdr = norm_header(hdr)
                        col_idx = header_lookup.get(norm_hdr)
                        if col_idx is None or col_idx >= len(normalized_row):
                            values.append("")
                        else:
                            matched_count += 1
                            values.append(normalized_row[col_idx])
                    if matched_count < max(4, len(column_headers) // 2):
                        fallback_cols = resolved_value_indices or value_columns
                        if not fallback_cols:
                            fallback_cols = [
                                idx for idx in range(len(normalized_row))
                                if idx != used_name_col
                            ]
                        fallback_cols = fallback_cols[:len(column_headers)]
                        values = [
                            normalized_row[idx] if idx < len(normalized_row) else ""
                            for idx in fallback_cols
                        ]
                else:
                    values = [
                        normalized_row[idx] if idx < len(normalized_row) else ""
                        for idx in value_columns
                    ]
                data_rows.append([name_value, *values])
            if not data_rows:
                return None
            if category_name == "Attributes":
                order_headers = ["Player Name", *ATTR_IMPORT_ORDER]
            elif category_name == "Tendencies":
                order_headers = ["Player Name", *TEND_IMPORT_ORDER]
            elif category_name == "Durability":
                order_headers = ["Player Name", *DUR_IMPORT_ORDER]
            elif category_name == "Potential":
                order_headers = ["Player Name", *POTENTIAL_IMPORT_ORDER]
            else:
                order_headers = []
            return {
                "header": order_headers,
                "data_rows": data_rows,
                "name_col": 0,
                "value_columns": list(range(1, len(order_headers))),
            }
        header = [str(cell) for cell in rows[0]]
        if not header:
            return None
        name_col = 0

        def _simple_norm(token: str) -> str:
            return "".join(ch for ch in str(token).upper() if ch.isalnum())

        first_name_markers = {"FIRSTNAME", "FIRST", "FNAME", "PLAYERFIRST", "PLAYERFIRSTNAME", "GIVENNAME"}
        last_name_markers = {"LASTNAME", "LAST", "LNAME", "PLAYERLAST", "PLAYERLASTNAME", "SURNAME", "FAMILYNAME"}
        normalized_headers = [_simple_norm(cell) for cell in header]
        first_name_col = None
        last_name_col = None
        for idx, norm in enumerate(normalized_headers):
            if not norm:
                continue
            if first_name_col is None and norm in first_name_markers:
                first_name_col = idx
                continue
            if last_name_col is None and norm in last_name_markers:
                last_name_col = idx

        skip_value_cols = {name_col}
        if first_name_col is not None:
            skip_value_cols.add(first_name_col)
        if last_name_col is not None:
            skip_value_cols.add(last_name_col)
        value_columns = [idx for idx in range(len(header)) if idx not in skip_value_cols]
        data_rows = [
            [str(cell) for cell in row]
            for row in rows[1:]
            if any(str(cell).strip() for cell in row)
        ]
        if not value_columns or not data_rows:
            return None
        return {
            "header": header,
            "data_rows": data_rows,
            "name_col": name_col,
            "value_columns": value_columns,
            "first_name_col": first_name_col,
            "last_name_col": last_name_col,
        }

    @staticmethod
    def compose_import_row_name(info: PreparedImportRows, row: Sequence[object]) -> str:
        """Return the best full-name string for a prepared import row."""
        if not row or not info:
            return ""

        def _idx(value: object) -> int | None:
            if isinstance(value, int):
                return value if value >= 0 else None
            try:
                idx_val = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            return idx_val if idx_val >= 0 else None

        first_idx = _idx(info.get("first_name_col"))
        last_idx = _idx(info.get("last_name_col"))
        name_idx = _idx(info.get("name_col"))

        def _piece(idx: int | None) -> str:
            if idx is None or idx < 0 or idx >= len(row):
                return ""
            return str(row[idx]).strip()

        parts: list[str] = []
        first_part = _piece(first_idx)
        last_part = _piece(last_idx)
        if first_part:
            parts.append(first_part)
        if last_part:
            parts.append(last_part)
        if parts:
            return " ".join(parts).strip()
        fallback = _piece(name_idx)
        return fallback.strip() if fallback else ""

    def import_table(
        self,
        category_name: str,
        filepath: str,
        *,
        context: str = "default",
        match_by_name: bool = True,
    ) -> int:
        return csv_import.import_table(self, category_name, filepath, context=context, match_by_name=match_by_name)

    def _import_file_map(
        self,
        file_map: dict[str, str],
        *,
        context: str,
        match_by_name: bool = True,
    ) -> dict[str, int]:
        results: dict[str, int] = {}
        self.import_partial_matches = {}
        for cat, path in file_map.items():
            self.import_partial_matches.setdefault(cat, {})
            if not path or not os.path.isfile(path):
                results[cat] = 0
                continue
            results[cat] = csv_import.import_table(self, cat, path, context=context, match_by_name=match_by_name)
        return results

    @staticmethod
    def _is_blank_cell(value: object) -> bool:
        text = "" if value is None else str(value).strip()
        return text == "" or text.lower() == "nan"

    @staticmethod
    def _read_delimited_rows(path: str) -> tuple[list[list[str]], str]:
        if not path or not os.path.isfile(path):
            return [], ","
        try:
            with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
                sample = handle.readline()
                delimiter = "\t" if "\t" in sample else "," if "," in sample else ";"
                handle.seek(0)
                rows = list(csv.reader(handle, delimiter=delimiter))
            return rows, delimiter
        except Exception:
            return [], ","

    @staticmethod
    def _write_temp_rows(rows: Sequence[Sequence[object]], *, delimiter: str = ",") -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8")
        writer = csv.writer(tmp, delimiter=delimiter)
        writer.writerows(rows)
        tmp.close()
        return tmp.name

    def _extract_tendency_average_map(self, rows: Sequence[Sequence[object]]) -> dict[str, str]:
        """Pull the row-2 averages (cols E-CY) from the TEND tab."""
        if not rows or len(rows) < 2:
            return {}
        norm_header = self._normalize_coy_header_name
        tend_headers = {
            norm_header(name)
            for name in TEND_IMPORT_ORDER
            if norm_header(name)
        }
        header_row = None
        avg_row = None
        for idx, row in enumerate(rows):
            normalized = [norm_header(cell) for cell in row]
            score = sum(1 for norm in normalized if norm and norm in tend_headers)
            if score >= 3:
                header_row = row
                if idx > 0:
                    avg_row = rows[idx - 1]
                break
        if header_row is None:
            header_row = rows[2] if len(rows) > 2 else rows[-1]
            avg_row = rows[1] if len(rows) > 1 else None
        if avg_row is None:
            avg_row = rows[1] if len(rows) > 1 else []
        averages: dict[str, str] = {}
        normalized_header = [norm_header(cell) for cell in header_row]
        for col, norm in enumerate(normalized_header):
            if col < 4:  # start at column E
                continue
            if not norm or avg_row is None or col >= len(avg_row):
                continue
            val = avg_row[col]
            if self._is_blank_cell(val):
                continue
            averages[norm] = str(val).strip()
        return averages

    def _sanitize_attributes_rows(self, rows: Sequence[Sequence[object]]) -> list[list[object]]:
        """Apply COY attribute rules: trim after AJ and fill averages/intangibles."""
        if not rows:
            return []
        max_col = 35  # AJ
        intangibles_col = 34  # AI
        avg_row = rows[0] if rows else []
        sanitized: list[list[object]] = []
        for idx, row in enumerate(rows):
            trimmed = list(row[: max_col + 1])
            if len(trimmed) < max_col + 1:
                trimmed.extend([""] * (max_col + 1 - len(trimmed)))
            if idx >= 2:
                for col in range(1, max_col + 1):
                    if not self._is_blank_cell(trimmed[col]):
                        continue
                    if col == intangibles_col:
                        fallback = "25"
                    else:
                        fallback = ""
                        if avg_row and col < len(avg_row) and not self._is_blank_cell(avg_row[col]):
                            fallback = str(avg_row[col]).strip()
                    if fallback:
                        trimmed[col] = fallback
            sanitized.append(trimmed)
        return sanitized

    def _sanitize_tendencies_rows(
        self, rows: Sequence[Sequence[object]], averages: dict[str, str]
    ) -> list[list[object]]:
        """Fill blank tendencies with the averages from the TEND tab."""
        if not rows or not averages:
            return [list(row) for row in rows]
        header = rows[0]
        header_norm = [self._normalize_coy_header_name(cell) for cell in header]
        sanitized: list[list[object]] = [list(header)]
        for row in rows[1:]:
            trimmed = list(row)
            if len(trimmed) < len(header_norm):
                trimmed.extend([""] * (len(header_norm) - len(trimmed)))
            name_cell = str(trimmed[0]).strip() if trimmed else ""
            if not name_cell:
                sanitized.append(trimmed)
                continue
            for col in range(1, len(header_norm)):
                if col >= len(trimmed):
                    break
                if not self._is_blank_cell(trimmed[col]):
                    continue
                norm_hdr = header_norm[col]
                fallback = averages.get(norm_hdr)
                if fallback is not None:
                    trimmed[col] = fallback
            sanitized.append(trimmed)
        return sanitized

    def _sanitize_durability_rows(self, rows: Sequence[Sequence[object]]) -> list[list[object]]:
        """Default durability blanks to 90 (cols D-S)."""
        if not rows:
            return []
        start_col = 3  # D
        max_col = 18  # S
        sanitized: list[list[object]] = []
        for idx, row in enumerate(rows):
            trimmed = list(row[: max_col + 1])
            if len(trimmed) < max_col + 1:
                trimmed.extend([""] * (max_col + 1 - len(trimmed)))
            if idx >= 1:
                for col in range(start_col, max_col + 1):
                    if self._is_blank_cell(trimmed[col]):
                        trimmed[col] = "90"
            sanitized.append(trimmed)
        return sanitized

    def _sanitize_potential_rows(self, rows: Sequence[Sequence[object]]) -> list[list[object]]:
        """Fill missing potential averages and probabilities with defaults."""
        if not rows:
            return []
        max_col = 9  # J
        defaults = {4: "74", 5: "76", 6: "86", 7: "30", 8: "55", 9: "15"}
        sanitized: list[list[object]] = []
        for idx, row in enumerate(rows):
            trimmed = list(row[: max_col + 1])
            if len(trimmed) < max_col + 1:
                trimmed.extend([""] * (max_col + 1 - len(trimmed)))
            name_cell = str(trimmed[1]).strip() if len(trimmed) > 1 else ""
            if idx >= 4 and name_cell:
                for col, default in defaults.items():
                    if col >= len(trimmed):
                        trimmed.extend([""] * (col + 1 - len(trimmed)))
                    if self._is_blank_cell(trimmed[col]):
                        trimmed[col] = default
            sanitized.append(trimmed)
        return sanitized

    def _prepare_coy_file(self, category_name: str, path: str, *, tend_avg_map: dict[str, str]) -> tuple[str, list[list[object]] | None]:
        rows, delimiter = self._read_delimited_rows(path)
        if not rows:
            return path, None
        if category_name == "Attributes":
            sanitized_rows = self._sanitize_attributes_rows(rows)
        elif category_name == "Tendencies":
            sanitized_rows = self._sanitize_tendencies_rows(rows, tend_avg_map)
        elif category_name == "Durability":
            sanitized_rows = self._sanitize_durability_rows(rows)
        elif category_name == "Potential":
            sanitized_rows = self._sanitize_potential_rows(rows)
        else:
            return path, None
        new_path = self._write_temp_rows(sanitized_rows, delimiter=delimiter)
        return new_path, sanitized_rows

    def import_all(self, file_map: dict[str, str]) -> dict[str, int]:
        """Import multiple tables using default layout rules."""
        return self._import_file_map(file_map, context="default")

    def import_excel_tables(self, file_map: dict[str, str], *, match_by_name: bool = True) -> dict[str, int]:
        """Import tables produced by the Excel workflow."""
        return self._import_file_map(file_map, context="excel", match_by_name=match_by_name)

    def import_excel_template_tables(self, file_map: dict[str, str], *, match_by_name: bool = False) -> dict[str, int]:
        """Import tables produced by the Excel template workflow."""
        return self._import_file_map(file_map, context="excel_template", match_by_name=match_by_name)

    def import_coy_tables(self, file_map: dict[str, str], *, aux_files: dict[str, str] | None = None) -> dict[str, int]:
        """Import tables produced by the COY workflow."""
        tend_avg_map: dict[str, str] = {}
        cleanup: list[str] = []
        if aux_files:
            tend_path = (
                aux_files.get("tendencies_defaults")
                or aux_files.get("tendencies")
                or aux_files.get("TEND")
                or aux_files.get("tend")
            )
            if tend_path:
                rows, _ = self._read_delimited_rows(tend_path)
                tend_avg_map = self._extract_tendency_average_map(rows)
        processed: dict[str, str] = {}
        for cat, path in file_map.items():
            if cat in {"Attributes", "Tendencies", "Durability", "Potential"}:
                new_path, _ = self._prepare_coy_file(cat, path, tend_avg_map=tend_avg_map)
                if new_path != path:
                    cleanup.append(new_path)
                processed[cat] = new_path
            else:
                processed[cat] = path
        try:
            return self._import_file_map(processed, context="coy")
        finally:
            for temp_path in cleanup:
                try:
                    if temp_path and os.path.isfile(temp_path):
                        os.remove(temp_path)
                except Exception:
                    continue

    def _collect_fields_for_export(self, category_names: Sequence[str] | None = None) -> list[ExportFieldSpec]:
        """Gather field definitions for the requested categories."""
        if category_names:
            categories = [name for name in category_names if name in self.categories]
        else:
            categories = list(self.categories.keys())
        collected: list[ExportFieldSpec] = []
        seen: set[tuple] = set()
        for category_name in categories:
            fields_obj = self._get_import_fields(category_name) or self.categories.get(category_name, [])
            if not isinstance(fields_obj, list):
                continue
            for meta in fields_obj:
                if not isinstance(meta, dict):
                    continue
                offset = to_int(meta.get("offset") or meta.get("address") or meta.get("offset_from_base"))
                length = to_int(meta.get("length") or meta.get("bitLength") or meta.get("bits"))
                if offset < 0 or length <= 0:
                    continue
                start_bit = to_int(meta.get("startBit") or meta.get("start_bit") or 0)
                requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
                deref_offset = to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
                name = str(meta.get("name") or meta.get("label") or f"Field {offset}")
                signature = (category_name, name, offset, start_bit, length, requires_deref, deref_offset)
                if signature in seen:
                    continue
                seen.add(signature)
                collected.append(
                    {
                        "category": category_name,
                        "name": name,
                        "offset": offset,
                        "hex": f"0x{offset:X}",
                        "length": length,
                        "start_bit": start_bit,
                        "requires_deref": requires_deref,
                        "deref_offset": deref_offset,
                        "type": str(meta.get("type")) if isinstance(meta.get("type"), str) else None,
                        "meta": meta,
                    }
                )
        return collected

    def export_category_to_csv(self, category_name: str, filepath: str) -> int:
        """Export the specified category to a CSV file."""
        if not filepath:
            return 0
        fields = self._get_import_fields(category_name, context="excel_template") or self.categories.get(category_name, [])
        if not fields:
            return 0
        if not self.mem.open_process():
            raise RuntimeError("Game process not opened; cannot export roster data.")
        if not self.players:
            self.refresh_players()
        if not self.players:
            return 0
        header = ["Player Name"] + [str(field.get("name", f"Field {idx+1}")) for idx, field in enumerate(fields)]
        import csv as _csv

        rows_written = 0
        with open(filepath, "w", newline="", encoding="utf-8") as handle:
            writer = _csv.writer(handle)
            writer.writerow(header)
            for player in self.players:
                row: list[str] = [player.full_name]
                for meta in fields:
                    field_name = str(meta.get("name", "")).lower()
                    offset = to_int(meta.get("offset") or meta.get("address") or meta.get("offset_from_base"))
                    start_bit = to_int(meta.get("startBit") or meta.get("start_bit") or 0)
                    length = to_int(meta.get("length") or meta.get("bitLength") or meta.get("bits"))
                    requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
                    deref_offset = to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
                    field_type = str(meta.get("type") or "").lower()
                    byte_length = to_int(meta.get("size") or meta.get("byte_length") or meta.get("length"))
                    raw_val = self.get_field_value_typed(
                        player.index,
                        offset,
                        start_bit,
                        length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=field_type,
                        byte_length=byte_length,
                        record_ptr=getattr(player, "record_ptr", None),
                    )
                    if raw_val is None:
                        row.append("")
                        continue
                    raw_int = to_int(raw_val)
                    if "float" in field_type:
                        row.append(str(raw_val))
                    elif category_name in ("Attributes", "Durability"):
                        row.append(str(convert_raw_to_rating(raw_int, length or 8)))
                    elif category_name == "Potential":
                        if "min" in field_name or "max" in field_name:
                            row.append(str(convert_raw_to_minmax_potential(raw_int, length or 8)))
                        else:
                            row.append(str(convert_raw_to_rating(raw_int, length or 8)))
                    elif category_name == "Tendencies":
                        row.append(str(convert_tendency_raw_to_rating(raw_int, length or 8)))
                    else:
                        row.append(str(raw_val))
                writer.writerow(row)
                rows_written += 1
        return rows_written

    def export_categories_to_directory(
        self,
        category_names: Sequence[str],
        directory: str,
        *,
        include_raw_records: bool = False,
    ) -> dict[str, tuple[str, int]]:
        """Export multiple categories into the provided directory."""
        if not category_names or not directory:
            return {}
        os.makedirs(directory, exist_ok=True)
        results: dict[str, tuple[str, int]] = {}
        for category_name in category_names:
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", category_name.strip()).strip("_")
            if not safe_name:
                safe_name = "category"
            filename = f"{safe_name.lower()}.csv"
            path = os.path.join(directory, filename)
            try:
                count = self.export_category_to_csv(category_name, path)
            except Exception:
                continue
            if count > 0:
                results[category_name] = (path, count)
            else:
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except Exception:
                    pass
        return results

    def export_player_raw_records(self, directory: str) -> tuple[str, int]:
        """
        Export the full raw player record (PLAYER_STRIDE bytes) for each player into a sub-directory.
        Returns the output directory path and the number of player files written.
        """
        if PLAYER_STRIDE <= 0:
            raise RuntimeError("Player record size (PLAYER_STRIDE) is not defined.")
        if not directory:
            return "", 0
        if not self.mem.open_process():
            raise RuntimeError("Game process not opened; cannot export raw player records.")
        if not self.players:
            self.refresh_players()
        if not self.players:
            return "", 0
        base_addr = self._resolve_player_table_base()
        if base_addr is None:
            raise RuntimeError("Unable to resolve player table base; cannot export raw player records.")
        target_dir = os.path.join(directory, "player_records")
        os.makedirs(target_dir, exist_ok=True)
        count = 0
        for player in self.players:
            try:
                record_addr = self._player_record_address(player.index, record_ptr=getattr(player, "record_ptr", None))
                if record_addr is None:
                    continue
                raw = self.mem.read_bytes(record_addr, PLAYER_STRIDE)
            except Exception:
                continue
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", player.full_name).strip("_")
            if not safe_name:
                safe_name = f"player_{player.index:04d}"
            filename = f"{player.index:04d}_{safe_name}.bin"
            filepath = os.path.join(target_dir, filename)
            try:
                with open(filepath, "wb") as dump:
                    dump.write(raw)
            except Exception:
                continue
            count += 1
        return target_dir, count

    # ------------------------------------------------------------------
    # Excel template export helpers (non-COY)
    # ------------------------------------------------------------------
    def _resolve_category_super(self, category_name: str) -> str:
        """Return the canonical super type for a category, defaulting to Players."""
        super_map = getattr(offsets_mod, "CATEGORY_SUPER_TYPES", {}) or {}
        lookup = super_map.get(category_name) or super_map.get(category_name.lower())
        return str(lookup or "Players")

    def _read_entity_string(
        self,
        base_addr: int,
        offset: int,
        max_chars: int,
        encoding: str,
        *,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> str:
        """Read a string field from an entity record with optional dereference."""
        addr = base_addr
        if requires_deref and deref_offset:
            try:
                deref_ptr = self.mem.read_uint64(base_addr + deref_offset)
            except Exception:
                deref_ptr = None
            if not deref_ptr:
                return ""
            addr = deref_ptr
        try:
            return self._read_string(addr + offset, max_chars, encoding).rstrip("\x00")
        except Exception:
            return ""

    def _decode_export_value(
        self,
        category_name: str,
        meta: dict[str, object],
        *,
        entity_index: int,
        entity_type: str = "player",
        record_ptr: int | None = None,
    ) -> object | None:
        """Decode a single field for export, handling strings and numeric conversions."""
        offset = to_int(meta.get("offset") or meta.get("address") or meta.get("offset_from_base"))
        start_bit = to_int(meta.get("startBit") or meta.get("start_bit") or 0)
        length = to_int(meta.get("length") or meta.get("bitLength") or meta.get("bits"))
        requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
        deref_offset = to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
        field_type = str(meta.get("type") or "").lower()
        byte_length = to_int(meta.get("size") or meta.get("byte_length") or meta.get("length"))
        field_name = str(meta.get("name", "")).lower()
        if "string" in field_type or "text" in field_type:
            max_chars = length if length > 0 else NAME_MAX_CHARS if "name" in field_name else max(16, byte_length or 0)
            encoding = "ascii" if "string" in field_type and "wstring" not in field_type else "utf16"
            if entity_type == "player":
                rec_addr = record_ptr or self._player_record_address(entity_index)
            else:
                rec_addr = self._team_record_address(entity_index)
            if rec_addr is None:
                return ""
            return self._read_entity_string(
                rec_addr,
                offset,
                max_chars,
                encoding,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
            )
        if entity_type == "player":
            raw_val = self.get_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
                record_ptr=record_ptr,
            )
        else:
            raw_val = self.get_team_field_value_typed(
                entity_index,
                offset,
                start_bit,
                length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                field_type=field_type,
                byte_length=byte_length,
            )
        if raw_val is None:
            return None
        if "float" in field_type:
            return raw_val
        raw_int = to_int(raw_val)
        if category_name in ("Attributes", "Durability"):
            return convert_raw_to_rating(raw_int, length or 8)
        if category_name == "Potential":
            if "min" in field_name or "max" in field_name:
                return convert_raw_to_minmax_potential(raw_int, length or 8)
            return convert_raw_to_rating(raw_int, length or 8)
        if category_name == "Tendencies":
            return convert_tendency_raw_to_rating(raw_int, length or 8)
        return raw_val

    def _build_category_dataframe(
        self,
        category_name: str,
        columns: Sequence[str],
        *,
        super_type: str,
        progress_cb: Callable[[int, int, str], None] | None = None,
        progress_offset: int = 0,
        progress_total: int = 0,
    ) -> tuple[object, int]:
        """Construct a DataFrame-like object for the requested category and column order."""
        fields = self._get_import_fields(category_name) or self.categories.get(category_name, [])
        if not fields:
            return None, 0
        column_order = [str(col) for col in columns if str(col).strip()]
        if not column_order:
            column_order = ["Player Name"] + [
                str(f.get("name", f"Field {idx+1}")) for idx, f in enumerate(fields) if isinstance(f, dict)
            ]
        spec_map: dict[str, dict] = {}
        for meta in fields:
            if not isinstance(meta, dict):
                continue
            name = str(meta.get("name", "")).strip()
            if not name:
                continue
            spec_map.setdefault(name, meta)
        rows: list[list[object]] = []
        if super_type.lower() == "players":
            if not self.mem.open_process():
                raise RuntimeError("Game process not opened; cannot export roster data.")
            if not self.players:
                self.refresh_players()
            entities = list(self.players or [])
            if not entities:
                return None, 0
            column_plan: list[tuple[str, dict | None]] = []
            for col in column_order:
                col_key = str(col).strip()
                if col_key in {"Player Name", "Name"}:
                    column_plan.append(("player_name", None))
                    continue
                if col_key == "First Name":
                    column_plan.append(("first_name", spec_map.get(col_key)))
                    continue
                if col_key == "Last Name":
                    column_plan.append(("last_name", spec_map.get(col_key)))
                    continue
                spec = spec_map.get(col_key)
                if spec is None:
                    column_plan.append(("blank", None))
                else:
                    column_plan.append(("field", spec))
            for player in entities:
                try:
                    rec_ptr = self._player_record_address(player.index, record_ptr=getattr(player, "record_ptr", None))
                except Exception:
                    rec_ptr = None
                row: list[object] = []
                for kind, spec in column_plan:
                    if kind == "player_name":
                        row.append(player.full_name)
                        continue
                    if kind == "first_name":
                        value = player.first_name
                        if not value and spec is not None:
                            val = self._decode_export_value(
                                category_name,
                                spec,
                                entity_index=player.index,
                                entity_type="player",
                                record_ptr=rec_ptr,
                            )
                            value = "" if val is None else val
                        row.append(value)
                        continue
                    if kind == "last_name":
                        value = player.last_name
                        if not value and spec is not None:
                            val = self._decode_export_value(
                                category_name,
                                spec,
                                entity_index=player.index,
                                entity_type="player",
                                record_ptr=rec_ptr,
                            )
                            value = "" if val is None else val
                        row.append(value)
                        continue
                    if kind == "field" and spec is not None:
                        val = self._decode_export_value(
                            category_name,
                            spec,
                            entity_index=player.index,
                            entity_type="player",
                            record_ptr=rec_ptr,
                        )
                        row.append("" if val is None else val)
                        continue
                    row.append("")
                rows.append(row)
                if progress_cb:
                    progress_cb(progress_offset + len(rows), progress_total or len(entities), category_name)
        elif super_type.lower() == "teams":
            if not self.mem.open_process():
                raise RuntimeError("Game process not opened; cannot export team data.")
            teams = self.get_teams()
            if not teams:
                return None, 0
            column_plan: list[tuple[str, dict | None]] = []
            for col in column_order:
                col_key = str(col).strip()
                if col_key in {"Team Name", "Name"}:
                    column_plan.append(("team_name", None))
                    continue
                spec = spec_map.get(col_key)
                if spec is None:
                    column_plan.append(("blank", None))
                else:
                    column_plan.append(("field", spec))
            for idx, name in enumerate(teams):
                rec_ptr = self._team_record_address(idx)
                row: list[object] = []
                for kind, spec in column_plan:
                    if kind == "team_name":
                        row.append(name)
                        continue
                    if kind == "field" and spec is not None:
                        val = self._decode_export_value(
                            category_name,
                            spec,
                            entity_index=idx,
                            entity_type="team",
                            record_ptr=rec_ptr,
                        )
                        row.append("" if val is None else val)
                        continue
                    row.append("")
                rows.append(row)
                if progress_cb:
                    progress_cb(progress_offset + len(rows), progress_total or len(teams), category_name)
        else:
            return None, 0
        try:
            import pandas as _pd  # type: ignore
        except Exception as exc:  # pragma: no cover - only triggered if pandas missing
            raise RuntimeError("Pandas is required for Excel export. Install with: pip install pandas openpyxl") from exc
        df = _pd.DataFrame(rows, columns=column_order)
        return df, len(rows)

    def export_to_excel_templates(
        self,
        category_names: Sequence[str] | None,
        output_dir: str,
        *,
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, tuple[str, int]]:
        """
        Export the requested categories into Excel workbooks using the bundled templates.
        Returns a mapping of category -> (workbook path, rows exported).
        """
        if not output_dir:
            return {}
        os.makedirs(output_dir, exist_ok=True)
        template_dir = Path(BASE_DIR) / "importing"
        template_files = {
            "Players": template_dir / "ImportPlayers.xlsx",
            "Teams": template_dir / "ImportTeams.xlsx",
            "Staff": template_dir / "ImportStaff.xlsx",
            "Stadiums": template_dir / "ImportStadiums.xlsx",
        }
        available_templates = {k: v for k, v in template_files.items() if v.is_file()}
        if not available_templates:
            raise RuntimeError("No Excel templates were found in the importing folder.")
        try:
            import pandas as _pd  # type: ignore
        except Exception as exc:  # pragma: no cover - handled at runtime
            raise RuntimeError("Pandas is required for Excel export. Install with: pip install pandas openpyxl") from exc
        results: dict[str, tuple[str, int]] = {}
        super_map = getattr(offsets_mod, "CATEGORY_SUPER_TYPES", {}) or {}
        super_map_lower = {str(k).lower(): str(v) for k, v in super_map.items()}
        requested = {c for c in (category_names or self.categories.keys()) if c in self.categories}
        template_targets: dict[Path, list[str]] = {}
        for category in requested:
            cat_super = super_map_lower.get(category.lower(), "Players")
            dest_tpl = available_templates.get(cat_super) or available_templates.get(cat_super.capitalize())
            if not dest_tpl:
                continue
            try:
                _pd.ExcelFile(dest_tpl)
            except Exception:
                continue
            template_targets.setdefault(dest_tpl, []).append(category)
        # Estimate total work for progress tracking (rows written)
        player_count = 0
        team_count = 0
        player_cats = [cat for cat in requested if super_map_lower.get(cat.lower(), "Players").lower() == "players"]
        team_cats = [cat for cat in requested if super_map_lower.get(cat.lower(), "").lower() == "teams"]
        if player_cats:
            if not self.players:
                self.refresh_players()
            player_count = len(self.players or [])
        if team_cats:
            team_count = len(self.get_teams())
        total_rows = (player_count * len(player_cats)) + (team_count * len(team_cats))
        progress_done = 0

        for tpl_path, categories in template_targets.items():
            try:
                tpl_reader = _pd.ExcelFile(tpl_path)
            except Exception:
                continue
            writer_path = Path(output_dir) / tpl_path.name
            with _pd.ExcelWriter(writer_path, engine="openpyxl") as writer:
                for sheet_name in tpl_reader.sheet_names:
                    sheet_key = str(sheet_name)
                    if sheet_key not in categories:
                        # Preserve template structure for unused sheets
                        try:
                            tpl_reader.parse(sheet_name).to_excel(writer, sheet_name=sheet_key, index=False)
                        except Exception:
                            _pd.DataFrame().to_excel(writer, sheet_name=sheet_key, index=False)
                        continue
                    try:
                        tpl_df = tpl_reader.parse(sheet_name)
                    except Exception:
                        tpl_df = _pd.DataFrame()
                    super_type = self._resolve_category_super(sheet_key)
                    columns = (
                        list(tpl_df.columns)
                        if not tpl_df.empty or tpl_df.columns.size
                        else list(tpl_reader.parse(sheet_name, nrows=0).columns)
                    )
                    df, count = self._build_category_dataframe(
                        sheet_key,
                        columns,
                        super_type=super_type,
                        progress_cb=progress_cb,
                        progress_offset=progress_done,
                        progress_total=total_rows,
                    )
                    if df is None:
                        tpl_df.to_excel(writer, sheet_name=sheet_key, index=False)
                        continue
                    df_obj = cast(Any, df)
                    df_obj.to_excel(writer, sheet_name=sheet_key, index=False)
                    results[sheet_key] = (str(writer_path), count)
                    progress_done += count
                    if progress_cb:
                        progress_cb(progress_done, total_rows, sheet_key)
        return results

    def export_offsets_long_form(self, filepath: str, categories: Sequence[str] | None = None) -> int:
        """Export offsets for the specified categories (or all) into a long-form CSV."""
        if not filepath:
            return 0
        field_specs = self._collect_fields_for_export(categories)
        if not field_specs:
            return 0
        if not self.mem.open_process():
            raise RuntimeError("Game process not opened; cannot export roster data.")
        if not self.players:
            self.refresh_players()
        if not self.players:
            return 0
        field_specs.sort(key=lambda item: (str(item["category"]), str(item["name"])))
        import csv as _csv

        rows_written = 0
        with open(filepath, "w", newline="", encoding="utf-8") as handle:
            writer = _csv.writer(handle)
            writer.writerow(
                [
                    "Player Name",
                    "Category",
                    "Field",
                    "Type",
                    "Address",
                    "Hex",
                    "Start Bit",
                    "Length",
                    "Requires Dereference",
                    "Dereference Offset",
                    "Raw Value",
                    "Display Value",
                ]
            )
            for player in self.players:
                for spec in field_specs:
                    raw_value = self.get_field_value(
                        player.index,
                        spec["offset"],
                        spec["start_bit"],
                        spec["length"],
                        requires_deref=spec["requires_deref"],
                        deref_offset=spec["deref_offset"],
                        record_ptr=getattr(player, "record_ptr", None),
                    )
                    display_val: str | int | float | None
                    if raw_value is None:
                        display_val = None
                    else:
                        raw_int = to_int(raw_value)
                        category = spec["category"]
                        field_name = str(spec.get("name", "")).lower()
                        if category in ("Attributes", "Durability"):
                            display_val = convert_raw_to_rating(raw_int, spec["length"] or 8)
                        elif category == "Potential":
                            if "min" in field_name or "max" in field_name:
                                display_val = convert_raw_to_minmax_potential(raw_int, spec["length"] or 8)
                            else:
                                display_val = convert_raw_to_rating(raw_int, spec["length"] or 8)
                        elif category == "Tendencies":
                            display_val = convert_tendency_raw_to_rating(raw_int, spec["length"] or 8)
                        else:
                            display_val = raw_value
                    writer.writerow(
                        [
                            player.full_name,
                            spec["category"],
                            spec["name"],
                            spec.get("type") or "",
                            spec["offset"],
                            spec["hex"],
                            spec["start_bit"],
                            spec["length"],
                            spec["requires_deref"],
                            spec["deref_offset"],
                            "" if raw_value is None else raw_value,
                            "" if display_val is None else display_val,
                        ]
                    )
                    rows_written += 1
        return rows_written

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
        for idx in range(max_count):
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
        if players:
            non_ascii = 0
            allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -'")
            for p in players:
                name = (p.first_name or "") + (p.last_name or "")
                if any(ch not in allowed for ch in name):
                    non_ascii += 1
            if non_ascii > len(players) * 0.5:
                return []
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
            value = self._read_panel_entry(record_addr, entry)
            if value is None:
                continue
            values_list = entry.get("values")
            if isinstance(values_list, list) and isinstance(value, int) and 0 <= value < len(values_list):
                value = values_list[value]
            snapshot[label] = value
        ovr_entry = _find_offset_entry(PLAYER_PANEL_OVR_FIELD[1], PLAYER_PANEL_OVR_FIELD[0])
        if ovr_entry:
            overall_val = self._read_panel_entry(record_addr, ovr_entry)
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
        self._resolved_player_base = None
        self._resolved_team_base = None
        self._resolved_draft_base = None
        self._cached_free_agents = []
        self.draft_players = []
        self.name_index_map.clear()

        if not self.mem.open_process():
            return

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
        if not players_all and self.team_list:
            # Fallback: derive the player list from team roster pointers when the sequential
            # player-table scan produces no results (e.g., stale/absent player base pointer).
            seen_ptrs: set[int] = set()
            gathered: list[Player] = []
            for team_idx, _name in self.team_list:
                roster = self.scan_team_players(team_idx)
                for player in roster:
                    ptr = getattr(player, "record_ptr", None)
                    if ptr is None:
                        continue
                    if ptr in seen_ptrs:
                        continue
                    seen_ptrs.add(ptr)
                    if player.index < 0:
                        player.index = len(gathered)
                    gathered.append(player)
            if gathered:
                players_all = gathered
            else:
                return

        if not self.team_list:
            self.team_list = self._build_team_list_from_players(players_all)

        if any(p.team_id == FREE_AGENT_TEAM_ID for p in players_all):
            self._ensure_team_entry(FREE_AGENT_TEAM_ID, "Free Agents", front=True)

        self.players = players_all
        self._cached_free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
        self._apply_team_display_to_players(self.players)
        self._build_name_index_map()

        from ..core.offsets import DRAFT_PTR_CHAINS  # local import to avoid cycles

        if DRAFT_PTR_CHAINS:
            draft_players = self._scan_draft_class_players(MAX_DRAFT_PLAYERS)
            if draft_players:
                self.draft_players = draft_players

    def get_players_by_team(self, team: str) -> list[Player]:
        team_name = (team or "").strip()
        if not team_name:
            return []
        team_lower = team_name.lower()
        if team_lower == "all players":
            if not self.players:
                players = self._scan_all_players(self.max_players)
                if players:
                    self.players = players
                    self._build_name_index_map()
                elif self.team_list:
                    # Fallback when player-table scan fails but team rosters are available.
                    seen: set[int] = set()
                    roster_players: list[Player] = []
                    for tid, _name in self.team_list:
                        for p in self.scan_team_players(tid):
                            ptr = getattr(p, "record_ptr", None)
                            if ptr is None or ptr in seen:
                                continue
                            seen.add(ptr)
                            if p.index < 0:
                                p.index = len(roster_players)
                            roster_players.append(p)
                    if roster_players:
                        self.players = roster_players
                        self._build_name_index_map()
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
        if team_idx is not None and team_idx >= 0:
            live_players = self.scan_team_players(team_idx)
            if live_players:
                return live_players
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
                self._build_name_index_map()
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
