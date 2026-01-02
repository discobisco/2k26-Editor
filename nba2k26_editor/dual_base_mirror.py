"""Extension that mirrors player/team writes to a secondary base table."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

import tkinter as tk
from tkinter import messagebox

from nba2k26_editor.core import offsets as offsets_mod
from nba2k26_editor.core.config import (
    ACCENT_BG,
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    CONFIG_DIR,
    PANEL_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from nba2k26_editor.core.extensions import register_player_panel_extension
from nba2k26_editor.memory.game_memory import GameMemory

_LOG = logging.getLogger("nba2k26.dualbase")
CONFIG_PATH = CONFIG_DIR / "dual_base_mirror.json"


def _format_addr(value: int | None) -> str:
    return f"0x{int(value):X}" if value else ""


def _parse_addr(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None
    return int(raw, 0)


def _to_int_addr(value: object) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float, bool)):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(text, 0)
            except Exception:
                return int(float(text))
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except Exception:
            return int(float(text))
    except Exception:
        return None


def _candidate_addresses(report: object, key: str) -> list[int]:
    if not isinstance(report, dict):
        return []
    raw_list = report.get(key) or []
    candidates: list[int] = []
    for entry in raw_list:
        addr_val = None
        if isinstance(entry, dict):
            addr_val = entry.get("address")
        elif isinstance(entry, (int, str)):
            addr_val = entry
        parsed = _to_int_addr(addr_val)
        if parsed is not None:
            candidates.append(parsed)
    return candidates


class DualBaseMirror:
    """Tracks primary/secondary bases and computes mirror destinations."""

    def __init__(self, model) -> None:
        self.model = model
        self.mem = model.mem
        self.player_primary: int | None = None
        self.team_primary: int | None = None
        self.player_alts: list[int] = []
        self.team_alts: list[int] = []
        self.enabled: bool = False
        self._sync_stride_limits()

    def _sync_stride_limits(self) -> None:
        self.player_stride = int(getattr(offsets_mod, "PLAYER_STRIDE", 0) or 0)
        self.team_stride = int(
            getattr(offsets_mod, "TEAM_RECORD_SIZE", 0)
            or getattr(offsets_mod, "TEAM_STRIDE", 0)
            or 0
        )
        self.max_players = int(getattr(offsets_mod, "MAX_PLAYERS", 0) or 0)
        self.max_teams = int(getattr(offsets_mod, "MAX_TEAMS_SCAN", 0) or 0)

    def load_config(self, path: Path = CONFIG_PATH) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            _LOG.debug("Failed to load dual-base config: %s", exc)
            return
        self.enabled = bool(data.get("enabled"))
        player_alt = data.get("player_alt_base")
        team_alt = data.get("team_alt_base")
        self.player_alts = [int(player_alt)] if isinstance(player_alt, int) and player_alt > 0 else []
        self.team_alts = [int(team_alt)] if isinstance(team_alt, int) and team_alt > 0 else []

    def save_config(self, path: Path = CONFIG_PATH) -> None:
        payload = {
            "enabled": bool(self.enabled),
            "player_alt_base": self.player_alts[0] if self.player_alts else None,
            "team_alt_base": self.team_alts[0] if self.team_alts else None,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            _LOG.debug("Failed to persist dual-base config: %s", exc)

    def update_primary_from_model(self) -> None:
        """Refresh cached primary bases from the live process."""
        self._sync_stride_limits()
        try:
            self.player_primary = self.model._resolve_player_base_ptr()
        except Exception:
            self.player_primary = None
        try:
            self.team_primary = self.model._resolve_team_base_ptr()
        except Exception:
            self.team_primary = None

    def configure(
        self,
        *,
        enabled: bool,
        player_alt: int | None = None,
        team_alt: int | None = None,
    ) -> None:
        self.player_alts = [player_alt] if player_alt else []
        self.team_alts = [team_alt] if team_alt else []
        self.enabled = enabled and bool(self.player_alts or self.team_alts)

    def _mirror_for_table(
        self,
        addr: int,
        primary: int | None,
        stride: int,
        limit: int,
        targets: Iterable[int],
    ) -> list[int]:
        if not self.enabled or primary is None or stride <= 0:
            return []
        rel = addr - primary
        if rel < 0:
            return []
        if limit > 0 and rel >= stride * limit:
            return []
        if rel % stride >= stride:
            return []
        return [base + rel for base in targets]

    def mirror_addresses(self, addr: int, length: int) -> list[int]:
        """Return alternate addresses that should mirror the given write."""
        del length  # length not needed for now; kept for future-proofing
        mirrors: list[int] = []
        mirrors.extend(
            self._mirror_for_table(
                addr,
                self.player_primary,
                self.player_stride,
                self.max_players,
                self.player_alts,
            )
        )
        mirrors.extend(
            self._mirror_for_table(
                addr,
                self.team_primary,
                self.team_stride,
                self.max_teams,
                self.team_alts,
            )
        )
        return list(dict.fromkeys(mirrors))  # preserve order, drop duplicates


def _patch_game_memory() -> None:
    if getattr(GameMemory, "_dual_base_patched", False):
        return
    original_write_bytes = GameMemory.write_bytes

    def _write_bytes_with_mirror(self: GameMemory, addr: int, data: bytes) -> None:
        result = original_write_bytes(self, addr, data)
        mirror = getattr(self, "_dual_base_mirror", None)
        if mirror:
            try:
                for mirror_addr in mirror.mirror_addresses(addr, len(data)):
                    original_write_bytes(self, mirror_addr, data)
            except Exception as exc:  # pragma: no cover - defensive
                _LOG.debug("Mirror write failed: %s", exc)
        return result

    GameMemory.write_bytes = _write_bytes_with_mirror  # type: ignore[assignment]
    GameMemory._dual_base_patched = True


def _ensure_mirror(app) -> DualBaseMirror | None:
    model = getattr(app, "model", None)
    if model is None:
        return None
    mem = getattr(model, "mem", None)
    if mem is None:
        return None
    mirror = getattr(mem, "_dual_base_mirror", None)
    if not isinstance(mirror, DualBaseMirror):
        mirror = DualBaseMirror(model)
        mirror.load_config()
        setattr(mem, "_dual_base_mirror", mirror)
    mirror.update_primary_from_model()
    _maybe_seed_from_scan(app, mirror)
    return mirror


def _maybe_seed_from_scan(app, mirror: DualBaseMirror) -> None:
    """Auto-fill mirror bases from the latest dynamic scan if available."""
    report = getattr(app, "last_dynamic_base_report", None)
    overrides = getattr(app, "last_dynamic_base_overrides", None)
    mem = getattr(getattr(app, "model", None), "mem", None)
    if mem:
        report = report or getattr(mem, "last_dynamic_base_report", None)
        overrides = overrides or getattr(mem, "last_dynamic_base_overrides", None)
    new_player_alt = mirror.player_alts[0] if mirror.player_alts else None
    new_team_alt = mirror.team_alts[0] if mirror.team_alts else None
    # Use explicit overrides from the scan first
    if isinstance(overrides, dict):
        p_override = _to_int_addr(overrides.get("Player"))
        t_override = _to_int_addr(overrides.get("Team"))
        if p_override and p_override != mirror.player_primary and not new_player_alt:
            new_player_alt = p_override
        if t_override and t_override != mirror.team_primary and not new_team_alt:
            new_team_alt = t_override
    # Fall back to the top alternate candidate from the scan report
    player_candidates = _candidate_addresses(report, "player_candidates")
    team_candidates = _candidate_addresses(report, "team_candidates")
    for cand in player_candidates:
        if cand and cand != mirror.player_primary and not new_player_alt:
            new_player_alt = cand
            break
    for cand in team_candidates:
        if cand and cand != mirror.team_primary and not new_team_alt:
            new_team_alt = cand
            break
    # Only update if we found something new
    if new_player_alt or new_team_alt:
        mirror.configure(
            enabled=mirror.enabled or bool(new_player_alt or new_team_alt),
            player_alt=new_player_alt,
            team_alt=new_team_alt,
        )
        mirror.save_config()


def _status_text(mirror: DualBaseMirror) -> str:
    parts: list[str] = []
    if mirror.player_primary or mirror.team_primary:
        parts.append(
            f"Primary P:{_format_addr(mirror.player_primary) or '?'} "
            f"T:{_format_addr(mirror.team_primary) or '?'}"
        )
    if mirror.player_alts or mirror.team_alts:
        parts.append(
            f"Mirror P:{_format_addr(mirror.player_alts[0] if mirror.player_alts else None) or '-'} "
            f"T:{_format_addr(mirror.team_alts[0] if mirror.team_alts else None) or '-'}"
        )
    if not parts:
        parts.append("Provide mirror bases to enable syncing.")
    elif mirror.enabled:
        parts.append("Mirror writes enabled.")
    else:
        parts.append("Mirror disabled.")
    if mirror.enabled and not (mirror.player_primary or mirror.team_primary):
        parts.append("Open NBA2K to resolve primary bases.")
    return " | ".join(parts)


def _build_panel(app, ctx) -> None:
    parent = ctx.get("panel_parent")
    if parent is None:
        return
    mirror = _ensure_mirror(app)
    if mirror is None:
        return

    frame = tk.LabelFrame(
        parent,
        text="Dual-base mirror",
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
        bd=1,
        highlightthickness=0,
    )
    frame.pack(fill=tk.X, padx=20, pady=(10, 4))

    player_var = tk.StringVar(
        value=_format_addr(mirror.player_alts[0]) if mirror.player_alts else ""
    )
    team_var = tk.StringVar(
        value=_format_addr(mirror.team_alts[0]) if mirror.team_alts else ""
    )
    enabled_var = tk.BooleanVar(value=mirror.enabled)
    status_var = tk.StringVar(value=_status_text(mirror))

    def _apply_settings() -> None:
        try:
            p_alt = _parse_addr(player_var.get())
        except Exception:
            messagebox.showerror("Dual-base mirror", "Invalid player base. Use hex (0x) or decimal.")
            return
        try:
            t_alt = _parse_addr(team_var.get())
        except Exception:
            messagebox.showerror("Dual-base mirror", "Invalid team base. Use hex (0x) or decimal.")
            return
        mirror.configure(enabled=enabled_var.get(), player_alt=p_alt, team_alt=t_alt)
        mirror.update_primary_from_model()
        mirror.save_config()
        status_var.set(_status_text(mirror))

    def _refresh_primary() -> None:
        mirror.update_primary_from_model()
        status_var.set(_status_text(mirror))

    row = tk.Frame(frame, bg=PANEL_BG)
    row.pack(fill=tk.X, pady=2)
    tk.Label(row, text="Player mirror base", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(row=0, column=0, sticky="w")
    tk.Entry(row, textvariable=player_var, width=16, bg=PANEL_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY).grid(
        row=0, column=1, padx=(6, 12), pady=2
    )
    tk.Label(row, text="Team mirror base", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(row=1, column=0, sticky="w")
    tk.Entry(row, textvariable=team_var, width=16, bg=PANEL_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY).grid(
        row=1, column=1, padx=(6, 12), pady=2
    )
    tk.Checkbutton(
        row,
        text="Mirror writes to both tables",
        variable=enabled_var,
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
        activebackground=PANEL_BG,
        activeforeground=TEXT_PRIMARY,
        selectcolor=ACCENT_BG,
    ).grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="w")
    row.columnconfigure(3, weight=1)

    btns = tk.Frame(frame, bg=PANEL_BG)
    btns.pack(fill=tk.X, pady=(4, 0))
    tk.Button(
        btns,
        text="Apply mirror",
        command=_apply_settings,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=8,
    ).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(
        btns,
        text="Refresh primaries",
        command=_refresh_primary,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=8,
    ).pack(side=tk.LEFT)
    tk.Label(frame, textvariable=status_var, bg=PANEL_BG, fg=TEXT_SECONDARY, wraplength=380, justify="left").pack(
        anchor="w", pady=(4, 2)
    )


_patch_game_memory()
register_player_panel_extension(_build_panel, prepend=True)

__all__ = ["DualBaseMirror"]
