from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nba2k_editor.franchise.service import FRANCHISE_PANEL_TABS, FranchiseManagerService


@dataclass(frozen=True)
class FranchiseDisplayState:
    status: str
    panel_texts: dict[str, str]
    dashboard: Any | None = None


def empty_franchise_display_state(status: str = "Franchise Manager has not imported current editor data yet.") -> FranchiseDisplayState:
    return FranchiseDisplayState(
        status=status,
        panel_texts={panel: "" for panel in FRANCHISE_PANEL_TABS},
        dashboard=None,
    )


def build_franchise_dashboard_state(editor_model: Any) -> FranchiseDisplayState:
    service = FranchiseManagerService(editor_model)
    dashboard = service.build_dashboard()
    return state_from_dashboard(dashboard, action_preview_text=_action_preview_text(service.action_write_previews(dashboard)))


def apply_first_trade_proposal(editor_model: Any, state: FranchiseDisplayState, *, index: int = 0) -> FranchiseDisplayState:
    dashboard = _dashboard_or_raise(state)
    result = FranchiseManagerService(editor_model).apply_trade_proposal(dashboard, index=index)
    return _state_with_status(state, f"Applied trade proposal #{index} through existing editor write path: {result['succeeded']} writes succeeded.")


def apply_first_signing_plan(editor_model: Any, state: FranchiseDisplayState, *, index: int = 0) -> FranchiseDisplayState:
    dashboard = _dashboard_or_raise(state)
    result = FranchiseManagerService(editor_model).apply_signing_plan(dashboard, index=index)
    return _state_with_status(state, f"Applied signing plan #{index} through existing editor write path: {result['succeeded']} writes succeeded.")


def apply_first_draft_action(editor_model: Any, state: FranchiseDisplayState, *, index: int = 0) -> FranchiseDisplayState:
    dashboard = _dashboard_or_raise(state)
    result = FranchiseManagerService(editor_model).apply_draft_action(dashboard, index=index)
    return _state_with_status(state, f"Applied draft action #{index} through existing editor write path: {result['succeeded']} writes succeeded.")


def apply_first_roster_move(editor_model: Any, state: FranchiseDisplayState, *, index: int = 0) -> FranchiseDisplayState:
    dashboard = _dashboard_or_raise(state)
    result = FranchiseManagerService(editor_model).apply_roster_move(dashboard, index=index)
    return _state_with_status(state, f"Applied roster move #{index} through existing editor write path: {result['succeeded']} writes succeeded.")


def _dashboard_or_raise(state: FranchiseDisplayState) -> Any:
    if state.dashboard is None:
        raise RuntimeError("import current editor data before applying franchise actions")
    return state.dashboard


def _state_with_status(state: FranchiseDisplayState, status: str) -> FranchiseDisplayState:
    return FranchiseDisplayState(status=status, panel_texts=dict(state.panel_texts), dashboard=state.dashboard)


def _action_preview_text(previews: dict[str, tuple[str, ...]]) -> str:
    lines: list[str] = []
    for action, writes in previews.items():
        if not writes:
            continue
        lines.append(f"{action} proposed editor writes:")
        lines.extend(f"  {write}" for write in writes)
    return "\n".join(lines)


def state_from_dashboard(dashboard: Any, *, action_preview_text: str = "") -> FranchiseDisplayState:
    panel_texts = {panel: dashboard.panel_reports.get(panel, "") for panel in FRANCHISE_PANEL_TABS}
    if action_preview_text:
        existing = panel_texts.get("Blocked Writes", "")
        panel_texts["Blocked Writes"] = "\n\n".join(part for part in (existing, action_preview_text) if part)
    loaded_domains = sum(1 for domain in dashboard.snapshot.full_app_dataset.get("domains", {}).values() if int(domain.get("count") or 0) > 0)
    return FranchiseDisplayState(
        status=(
            f"Loaded full app dataset across {loaded_domains} domains; "
            f"franchise action layer found {len(dashboard.snapshot.teams)} roster teams and "
            f"{len(dashboard.snapshot.roster_players)} roster players."
        ),
        panel_texts=panel_texts,
        dashboard=dashboard,
    )
