from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

_GENERATOR_DIR = Path(__file__).resolve().parent
_DEFAULT_IDENTITY_DIR = _GENERATOR_DIR / "Positional Identities"
_FILE_BY_POSITION = {
    "PG": "PGs.txt",
    "SG": "SGs.txt",
    "SF": "SFs.txt",
    "PF": "PFs.txt",
    "C": "Cs.txt",
}
_POSITION_ORDER = ("PG", "SG", "SF", "PF", "C")
_EXACT_POSITION_LISTINGS = set(_POSITION_ORDER)
_POSITION_PAIR_BY_LISTING = {
    "G": ("PG", "SG"),
    "G-F": ("SG", "SF"),
    "F-G": ("SF", "SG"),
    "F": ("SF", "PF"),
    "C-F": ("C", "PF"),
    "F-C": ("PF", "C"),
}
_ROLE_RE = re.compile(r"^\s*(\d+)\)\s+(.+?)\s*$")
_CATEGORY_RE = re.compile(r"^\s*([A-Z])\)\s+(.+?)\s*$")
_DETAIL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /-]+):\s*(.*)\s*$")


@dataclass(frozen=True)
class PositionalIdentityRole:
    position: str
    index: int
    name: str
    category: str
    details: dict[str, str]

    @property
    def role_key(self) -> str:
        return f"{self.position}/{self.name}"


@dataclass(frozen=True)
class PositionalIdentityMatch:
    role_key: str
    position: str
    role_name: str
    reason: str
    evidence_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role_key": self.role_key,
            "position": self.position,
            "role_name": self.role_name,
            "reason": self.reason,
            "evidence_keys": self.evidence_keys,
        }


@dataclass(frozen=True)
class PositionalIdentityCatalog:
    roles: tuple[PositionalIdentityRole, ...]

    def roles_for_position(self, position: str) -> tuple[PositionalIdentityRole, ...]:
        normalized = _normalize_position(position)
        return tuple(role for role in self.roles if role.position == normalized)

    def find_role(self, position: str, name_contains: str) -> PositionalIdentityRole | None:
        normalized = _normalize_position(position)
        needle = _norm_text(name_contains)
        for role in self.roles:
            if role.position == normalized and needle in _norm_text(role.name):
                return role
        return None


def load_positional_identity_catalog(root: str | Path | None = None) -> PositionalIdentityCatalog:
    directory = Path(root) if root is not None else _DEFAULT_IDENTITY_DIR
    return _cached_catalog(str(directory.expanduser().resolve()))


@lru_cache(maxsize=None)
def _cached_catalog(directory: str) -> PositionalIdentityCatalog:
    root = Path(directory)
    roles: list[PositionalIdentityRole] = []
    for position, filename in _FILE_BY_POSITION.items():
        path = root / filename
        if not path.exists():
            continue
        roles.extend(_parse_position_file(position, path))
    return PositionalIdentityCatalog(roles=tuple(roles))


def classify_positional_identities(
    evidence: Any,
    *,
    catalog: PositionalIdentityCatalog | None = None,
) -> tuple[PositionalIdentityMatch, ...]:
    catalog = catalog if catalog is not None else load_positional_identity_catalog()
    position = primary_position_from_evidence(evidence)
    if not position:
        return ()

    stats = _IdentityStats.from_evidence(evidence)
    matches: list[PositionalIdentityMatch] = []

    if position == "PG":
        if _gte(stats.x3pa, 7.0) and (stats.x3p_pct is None or stats.x3p_pct >= 0.34) and _gte(stats.usage, 23.0):
            _append_match(matches, catalog, "PG", "Pull-Up Three", "high-volume pull-up/spacing guard profile", ("per_game.x3pa_per_game", "per_game.x3p_percent", "advanced.usg_percent"))
        if _gte(stats.ast, 6.0) or _gte(stats.ast_pct, 28.0):
            _append_match(matches, catalog, "PG", "PnR Maestro", "primary guard creation and assist pressure", ("per_game.ast_per_game", "advanced.ast_percent", "play_by_play.pg_percent"))
        if _lt(stats.usage, 18.0) and _gte(stats.ast, 4.0):
            _append_match(matches, catalog, "PG", "Low-Usage Game Manager", "low-usage organizer profile", ("advanced.usg_percent", "per_game.ast_per_game"))

    elif position == "SG":
        if _gte(stats.x3pa, 5.0) and (stats.x3p_pct is None or stats.x3p_pct >= 0.34):
            _append_match(matches, catalog, "SG", "Above-the-Break Spot-Up Specialist", "high-volume two-guard spacing profile", ("per_game.x3pa_per_game", "per_game.x3p_percent"))
        if _gte(stats.x3pa, 6.0) and _gte(stats.mp, 28.0):
            _append_match(matches, catalog, "SG", "Movement Shooter", "heavy minutes plus high three-point volume", ("per_game.x3pa_per_game", "per_game.mp_per_game"))
        if _gte(stats.fta, 4.5) and _gte(stats.rim_share, 0.25):
            _append_match(matches, catalog, "SG", "Closeout Slasher", "free-throw pressure and rim share", ("per_game.fta_per_game", "shooting.percent_fga_from_x0_3_range"))

    elif position == "SF":
        if _gte(stats.x3pa, 4.0) and (stats.x3p_pct is None or stats.x3p_pct >= 0.33):
            _append_match(matches, catalog, "SF", "Slot/45 Shooter", "wing spacing and catch-shoot profile", ("per_game.x3pa_per_game", "per_game.x3p_percent"))
        if _gte(stats.ast, 5.0) or _gte(stats.ast_pct, 24.0):
            _append_match(matches, catalog, "SF", "Point Forward Primary Initiator", "forward playmaking load", ("per_game.ast_per_game", "advanced.ast_percent"))
        if _gte(stats.fta, 4.5) and _gte(stats.rim_share, 0.30):
            _append_match(matches, catalog, "SF", "Power Slasher", "contact wing rim pressure", ("per_game.fta_per_game", "shooting.percent_fga_from_x0_3_range"))

    elif position == "PF":
        if _gte(stats.x3pa, 3.0) and (stats.x3p_pct is None or stats.x3p_pct >= 0.33):
            _append_match(matches, catalog, "PF", "Above-the-Break Stretch 4", "frontcourt shooting gravity", ("per_game.x3pa_per_game", "per_game.x3p_percent"))
        if _gte(stats.ast, 5.0) or _gte(stats.ast_pct, 25.0):
            _append_match(matches, catalog, "PF", "Point Forward 4", "power-forward initiation and passing load", ("per_game.ast_per_game", "advanced.ast_percent"))
        if _gte(stats.dunks, 80.0) or _gte(stats.dunk_share, 0.15):
            _append_match(matches, catalog, "PF", "Vertical Spacer", "frontcourt dunk/lob pressure", ("shooting.num_of_dunks", "shooting.percent_dunks_of_fga"))

    elif position == "C":
        if _gte(stats.ast, 5.0) or _gte(stats.ast_pct, 25.0):
            _append_match(matches, catalog, "C", "Point Center", "center initiation and assist creation", ("per_game.ast_per_game", "advanced.ast_percent", "play_by_play.c_percent"))
            _append_match(matches, catalog, "C", "High-Post Hub", "center hub passing profile", ("per_game.ast_per_game", "advanced.ast_percent"))
        if _gte(stats.x3pa, 2.5) and (stats.x3p_pct is None or stats.x3p_pct >= 0.33):
            _append_match(matches, catalog, "C", "Pick-and-Pop Center", "center perimeter shooting gravity", ("per_game.x3pa_per_game", "per_game.x3p_percent"))
        if _gte(stats.dunks, 80.0) or _gte(stats.dunk_share, 0.20):
            _append_match(matches, catalog, "C", "Vertical Spacer", "lob/dunk pressure center profile", ("shooting.num_of_dunks", "shooting.percent_dunks_of_fga"))
        if _gte(stats.trb, 10.0) and _gte(stats.blk_pct, 3.0):
            _append_match(matches, catalog, "C", "Rebounding-First Defensive Anchor", "rebounding plus block pressure", ("per_game.trb_per_game", "advanced.blk_percent"))

    return tuple(matches)


def primary_position_from_evidence(evidence: Any) -> str:
    season_pos = _clean_position(getattr(evidence, "season_info", {}).get("pos"))
    identity_pos = _clean_position(getattr(evidence, "identity", {}).get("pos"))
    if season_pos in _EXACT_POSITION_LISTINGS:
        return season_pos
    if season_pos in _POSITION_PAIR_BY_LISTING:
        return _POSITION_PAIR_BY_LISTING[season_pos][0]
    if identity_pos in _EXACT_POSITION_LISTINGS:
        return identity_pos
    if identity_pos in _POSITION_PAIR_BY_LISTING:
        return _POSITION_PAIR_BY_LISTING[identity_pos][0]
    return ""


@dataclass(frozen=True)
class _IdentityStats:
    pts: float | None
    ast: float | None
    trb: float | None
    x3pa: float | None
    x3p_pct: float | None
    fta: float | None
    mp: float | None
    usage: float | None
    ast_pct: float | None
    blk_pct: float | None
    rim_share: float | None
    dunk_share: float | None
    dunks: float | None

    @classmethod
    def from_evidence(cls, evidence: Any) -> "_IdentityStats":
        per_game = getattr(evidence, "per_game", {})
        advanced = getattr(evidence, "advanced", {})
        shooting = getattr(evidence, "shooting", {})
        return cls(
            pts=_number(per_game, "pts_per_game"),
            ast=_number(per_game, "ast_per_game"),
            trb=_number(per_game, "trb_per_game"),
            x3pa=_number(per_game, "x3pa_per_game"),
            x3p_pct=_optional_number(per_game, "x3p_percent"),
            fta=_number(per_game, "fta_per_game"),
            mp=_number(per_game, "mp_per_game"),
            usage=_number(advanced, "usg_percent"),
            ast_pct=_number(advanced, "ast_percent"),
            blk_pct=_number(advanced, "blk_percent"),
            rim_share=_number(shooting, "percent_fga_from_x0_3_range"),
            dunk_share=_number(shooting, "percent_dunks_of_fga"),
            dunks=_number(shooting, "num_of_dunks"),
        )


def _parse_position_file(position: str, path: Path) -> tuple[PositionalIdentityRole, ...]:
    roles: list[PositionalIdentityRole] = []
    current_category = ""
    current: dict[str, Any] | None = None
    active_detail_key = ""

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        category_match = _CATEGORY_RE.match(line)
        if category_match:
            current_category = category_match.group(2).strip()
            active_detail_key = ""
            continue
        role_match = _ROLE_RE.match(line)
        if role_match:
            if current is not None:
                roles.append(_role_from_current(position, current_category, current))
            current = {"index": int(role_match.group(1)), "name": role_match.group(2).strip(), "details": {}}
            active_detail_key = ""
            continue
        if current is None:
            continue
        detail_match = _DETAIL_RE.match(line)
        details = current["details"]
        if detail_match:
            active_detail_key = detail_match.group(1).strip().lower().replace(" ", "_").replace("/", "_")
            details[active_detail_key] = detail_match.group(2).strip()
        elif active_detail_key:
            existing = details.get(active_detail_key, "")
            details[active_detail_key] = f"{existing} {line}".strip()
    if current is not None:
        roles.append(_role_from_current(position, current_category, current))
    return tuple(roles)


def _role_from_current(position: str, category: str, current: dict[str, Any]) -> PositionalIdentityRole:
    return PositionalIdentityRole(
        position=position,
        index=int(current["index"]),
        name=str(current["name"]),
        category=category,
        details=dict(current.get("details") or {}),
    )


def _append_match(
    matches: list[PositionalIdentityMatch],
    catalog: PositionalIdentityCatalog,
    position: str,
    name_contains: str,
    reason: str,
    evidence_keys: tuple[str, ...],
) -> None:
    role = catalog.find_role(position, name_contains)
    if role is None:
        return
    if any(match.role_key == role.role_key for match in matches):
        return
    matches.append(
        PositionalIdentityMatch(
            role_key=role.role_key,
            position=role.position,
            role_name=role.name,
            reason=reason,
            evidence_keys=evidence_keys,
        )
    )


def _normalize_position(position: str) -> str:
    text = str(position or "").strip().upper()
    if text in _POSITION_ORDER:
        return text
    return ""


def _clean_position(value: object) -> str:
    return str(value or "").strip().upper().replace("–", "-").replace("—", "-")


def _norm_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _optional_number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key) if isinstance(mapping, dict) else None
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(mapping: dict[str, Any], key: str) -> float | None:
    return _optional_number(mapping, key)


def _gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


__all__ = [
    "PositionalIdentityCatalog",
    "PositionalIdentityMatch",
    "PositionalIdentityRole",
    "classify_positional_identities",
    "load_positional_identity_catalog",
    "primary_position_from_evidence",
]
