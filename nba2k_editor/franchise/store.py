from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nba2k_editor.models.franchise import FranchiseDashboard, FranchiseLLMResult, LiveFranchiseSnapshot


DEFAULT_FRANCHISE_STATE_PATH = Path("outputs") / "franchise" / "franchise_state.json"


class FranchiseJsonStore:
    """Project-local persistence for franchise records, separate from live memory."""

    def __init__(self, path: str | Path = DEFAULT_FRANCHISE_STATE_PATH) -> None:
        self.path = Path(path)

    def save_dashboard(self, dashboard: FranchiseDashboard) -> None:
        state = self.load()
        runs = list(state.get("runs", []))
        run_id = len(runs) + 1
        dashboard_record = dashboard.to_dict()
        dashboard_record["run_id"] = run_id
        runs.append(dashboard_record)
        state.update(
            {
                "schema": "nba2k_editor.franchise.v1",
                "latest_run_id": run_id,
                "latest_dashboard": dashboard_record,
                "runs": runs,
                "snapshots": [*state.get("snapshots", []), self._snapshot_record(run_id, dashboard.snapshot)],
                "front_offices": [*state.get("front_offices", []), *dashboard.llm_result.to_dict().get("front_offices", [])],
                "trade_proposals": [*state.get("trade_proposals", []), *dashboard.llm_result.trade_proposals],
                "signing_plans": [*state.get("signing_plans", []), *dashboard.llm_result.signing_plans],
                "draft_actions": [*state.get("draft_actions", []), *dashboard.llm_result.draft_actions],
                "roster_moves": [*state.get("roster_moves", []), *dashboard.llm_result.roster_moves],
                "sim_plans": [*state.get("sim_plans", []), dashboard.llm_result.sim_plan.to_dict()],
                "trade_deadline_postures": [*state.get("trade_deadline_postures", []), dashboard.llm_result.trade_deadline],
                "league_meetings": [*state.get("league_meetings", []), *dashboard.llm_result.league_meetings],
                "rule_votes": [*state.get("rule_votes", []), *dashboard.llm_result.rule_votes],
                "staff_decisions": [*state.get("staff_decisions", []), *dashboard.llm_result.staff_decisions],
                "scouting_records": [*state.get("scouting_records", []), dashboard.llm_result.scouting],
                "expansion_drafts": [*state.get("expansion_drafts", []), dashboard.llm_result.expansion_draft],
                "draft_boards": [*state.get("draft_boards", []), dashboard.llm_result.draft],
                "free_agency_plans": [*state.get("free_agency_plans", []), dashboard.llm_result.free_agency],
                "consequences": [*state.get("consequences", []), *dashboard.llm_result.consequences],
                "llm_outputs": [*state.get("llm_outputs", []), self._llm_record(run_id, dashboard.llm_result)],
            }
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot_record(self, run_id: int, snapshot: LiveFranchiseSnapshot) -> dict[str, Any]:
        return {"run_id": run_id, **snapshot.to_dict()}

    def _llm_record(self, run_id: int, result: FranchiseLLMResult) -> dict[str, Any]:
        return {"run_id": run_id, **result.to_dict()}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))
