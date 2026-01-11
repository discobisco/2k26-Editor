"""Persona management for AI assistant.

Provides helpers to ensure default team personas, retrieve persona text for a
selection, and merge profile changes into the app settings.
"""
from __future__ import annotations

from typing import Any, Iterable

TeamEntry = str | int | tuple[Any, ...] | dict[str, Any]


def ensure_default_profiles(settings: dict[str, Any], team_names: Iterable[TeamEntry], active_count: int = 12) -> dict[str, Any]:
    """Ensure the settings dict contains a `profiles` section with defaults.

    team_names is an iterable where the index corresponds to team ID. The
    function will create up to len(team_names) team profiles but only enable the
    first `active_count` teams by default.
    """
    profiles = settings.get("profiles") or {}
    base = profiles.get("base", "You are an experienced NBA general manager focused on building a competitive roster. Prioritize win-now trades while balancing future cap and development. Keep replies concise and actionable.")
    team_profiles = profiles.get("team_profiles") or []

    entries = list(team_names)
    # Normalize entries into (id, name) pairs. Supported inputs:
    # - iterable of names (strings) -> id = index
    # - iterable of (id, name) tuples -> uses provided id
    # - iterable of dicts with 'id' and 'name' keys
    normalized: list[tuple[int, str]] = []
    for i, entry in enumerate(entries):
        if isinstance(entry, tuple) and len(entry) >= 2:
            tid, name = int(entry[0]), str(entry[1])
        elif isinstance(entry, dict) and "id" in entry and "name" in entry:
            tid, name = int(entry["id"]), str(entry["name"])
        elif isinstance(entry, int):
            tid, name = int(entry), f"Team {int(entry)}"
        else:
            tid, name = i, str(entry) or f"Team {i}"
        normalized.append((tid, name))

    max_teams = max(0, min(len(normalized), 36))
    new_team_profiles: list[dict[str, Any]] = []
    for idx in range(max_teams):
        tid, name = normalized[idx]
        persona = f"You are the General Manager of {name} (team id: {tid}).\nYour constraints and priorities: act as the GM for roster decisions, be concise, and justify trade or signing decisions."
        enabled = idx < int(active_count)
        # Default constraints: budget in millions (None = unspecified), priority, rebuild years, playstyle
        constraints = {
            "budget_m": None,
            "priority": "win-now",
            "rebuild_years": 2,
            "playstyle": "balanced",
        }
        new_team_profiles.append({"id": int(tid), "name": name, "enabled": enabled, "persona": persona, "constraints": constraints})

    profiles = {
        "base": base,
        "active_count": int(active_count),
        "team_profiles": new_team_profiles,
    }
    settings["profiles"] = profiles
    return settings


def get_persona_text(settings: dict[str, Any], selection: str | None, include_constraints: bool = True) -> str:
    """Return persona text for the given selection.

    selection values:
      - None or 'none' -> ''
      - 'base' -> base persona
      - 'team:<id>' -> persona for that team id if found and enabled, otherwise ''

    When include_constraints is True, constraints (budget, priority, etc.) are
    appended to the persona text to help shape the model's decisions.
    """
    if not selection:
        return ""
    sel = str(selection).strip().lower()
    profiles = settings.get("profiles") or {}
    if sel in ("none", "", "0"):
        return ""
    if sel == "base":
        return str(profiles.get("base", "") or "")
    if sel.startswith("team:"):
        try:
            tid = int(sel.split(":", 1)[1])
        except Exception:
            return ""
        teams = profiles.get("team_profiles") or []
        for t in teams:
            if int(t.get("id", -1)) == tid and t.get("enabled"):
                persona = str(t.get("persona", "") or "")
                if include_constraints:
                    constr = t.get("constraints") or {}
                    cparts: list[str] = []
                    budget = constr.get("budget_m")
                    if budget:
                        cparts.append(f"Budget: ${budget}M")
                    priority = constr.get("priority")
                    if priority:
                        cparts.append(f"Priority: {priority}")
                    rebuild = constr.get("rebuild_years")
                    if rebuild is not None:
                        cparts.append(f"Rebuild target: {rebuild} years")
                    play = constr.get("playstyle")
                    if play:
                        cparts.append(f"Playstyle: {play}")
                    if cparts:
                        persona = persona + "\n\nConstraints:\n- " + "\n- ".join(cparts)
                return persona
        return ""
    # allow numeric selections like '12' -> team:12
    try:
        maybe = int(sel)
        teams = profiles.get("team_profiles") or []
        for t in teams:
            if int(t.get("id", -1)) == maybe and t.get("enabled"):
                persona = str(t.get("persona", "") or "")
                if include_constraints:
                    constr = t.get("constraints") or {}
                    cparts: list[str] = []
                    budget = constr.get("budget_m")
                    if budget:
                        cparts.append(f"Budget: ${budget}M")
                    priority = constr.get("priority")
                    if priority:
                        cparts.append(f"Priority: {priority}")
                    rebuild = constr.get("rebuild_years")
                    if rebuild is not None:
                        cparts.append(f"Rebuild target: {rebuild} years")
                    play = constr.get("playstyle")
                    if play:
                        cparts.append(f"Playstyle: {play}")
                    if cparts:
                        persona = persona + "\n\nConstraints:\n- " + "\n- ".join(cparts)
                return persona
    except Exception:
        pass
    return ""


def export_profiles(settings: dict[str, Any], path: str) -> None:
    """Export the `profiles` section to a JSON file at `path`."""
    import json

    profiles = settings.get("profiles") or {}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profiles, fh, indent=2)


def import_profiles(settings: dict[str, Any], path: str) -> dict[str, Any]:
    """Import profiles JSON from `path` and merge into settings."""
    import json

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise RuntimeError("Invalid profiles file: root must be an object/dict.")
    settings["profiles"] = data
    return settings


__all__ = [
    "ensure_default_profiles",
    "get_persona_text",
    "export_profiles",
    "import_profiles",
]
