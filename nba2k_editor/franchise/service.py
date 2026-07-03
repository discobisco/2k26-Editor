from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from typing import Any
from urllib import request

from nba2k_editor.models.franchise import (
    FranchiseDashboard,
    FranchiseLLMResult,
    FrontOfficeProfile,
    LeagueSimPlan,
    LiveFranchiseSnapshot,
    PlayerSnapshot,
    SimRequest,
    TeamSnapshot,
)
from nba2k_editor.franchise.store import FranchiseJsonStore

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "team_city": ("CITYNAME", "CITY NAME", "CITYSHORTNAME", "CITY SHORT NAME"),
    "team_name": ("TEAMNAME", "TEAM NAME"),
    "wins": ("WINS", "TEAMWINS", "WIN"),
    "losses": ("LOSSES", "TEAMLOSSES", "LOSS"),
    "conference_rank": ("CONFERENCERANK", "CONFERENCE RANK"),
    "division_rank": ("DIVISIONRANK", "DIVISION RANK"),
    "playoff_seed": ("PLAYOFFSEED", "PLAYOFF SEED", "SEED"),
    "payroll": ("PAYROLL", "TEAMPAYROLL", "SALARY"),
    "cap_room": ("CAPROOM", "CAP ROOM"),
    "first_name": ("FIRSTNAME", "FIRST NAME"),
    "last_name": ("LASTNAME", "LAST NAME"),
    "player_id": ("UNIQUEID", "UNIQUE ID", "PLAYERID", "PLAYER ID"),
    "overall": ("OVR", "OVERALL", "OVERALLRATING", "OVERALL RATING"),
    "potential": ("POTENTIAL", "POT"),
    "position": ("POSITION",),
    "age": ("AGE", "CUSTOMAGEATSETYEAR", "CUSTOM AGE AT SET YEAR"),
}

FRANCHISE_PANEL_TABS: tuple[str, ...] = (
    "League Office",
    "Front Office Inbox",
    "Sim Negotiation",
    "Trade Deadline Room",
    "Team Front Offices",
    "League Meetings",
    "Staff Decisions",
    "Scouting Combine",
    "Individual Workouts",
    "Expansion Draft",
    "Draft Room",
    "Free Agency",
    "Consequences",
    "Live Snapshot",
    "Blocked Writes",
)


def _identity(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _entry_lookup(model: Any, domain: str) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    grouped = model.grouped_fields(domain)
    for groups in grouped.values():
        for entries in groups.values():
            for entry in entries:
                for key in (
                    getattr(entry, "normalized_name", ""),
                    getattr(entry, "display_name", ""),
                    getattr(entry, "field", {}).get("normalized_name", ""),
                    getattr(entry, "field", {}).get("display_name", ""),
                ):
                    normalized = _identity(key)
                    if normalized and normalized not in lookup:
                        lookup[normalized] = entry
    return lookup


def _find_entry(lookup: dict[str, Any], aliases: Iterable[str]) -> Any | None:
    for alias in aliases:
        entry = lookup.get(_identity(alias))
        if entry is not None:
            return entry
    return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, "", "--"):
        return None
    return int(float(str(value).replace(",", "")))


def _field_identity(value: object) -> str:
    return str(value or "").strip().upper()


class FranchiseManagerService:
    """Fresh Franchise Manager service over existing editor data and an LLM front-office layer."""

    def __init__(
        self,
        editor_model: Any,
        *,
        store: FranchiseJsonStore | None = None,
        llm_client: Callable[[str], str] | None = None,
    ) -> None:
        self.editor_model = editor_model
        self.store = store or FranchiseJsonStore()
        self.llm_client = llm_client

    def build_dashboard(self, *, persist: bool = True) -> FranchiseDashboard:
        snapshot = self.import_live_snapshot()
        previous_state = self.store.load()
        prompt = self.build_llm_prompt(snapshot, previous_state=previous_state)
        llm_output = self._run_llm(prompt)
        llm_result = self._llm_result_from_output(llm_output)
        dashboard = FranchiseDashboard(
            snapshot=snapshot,
            llm_result=llm_result,
            metadata={"llm_prompt": prompt},
        )
        if persist:
            self.store.save_dashboard(dashboard)
        return dashboard

    def apply_trade_proposal(self, dashboard: FranchiseDashboard, index: int = 0) -> dict[str, int]:
        proposal = dashboard.llm_result.trade_proposals[index]
        steps = self._write_steps_for_trade_proposal(proposal)
        for _domain, index, _field_name, value, entry in steps:
            self.editor_model.write_entry_value(entry, index=index, value=value)
        return {"attempted": len(steps), "succeeded": len(steps)}

    def apply_signing_plan(self, dashboard: FranchiseDashboard, index: int = 0) -> dict[str, int]:
        return self.apply_roster_move_record(dashboard.llm_result.signing_plans[index])

    def apply_draft_action(self, dashboard: FranchiseDashboard, index: int = 0) -> dict[str, int]:
        return self.apply_roster_move_record(dashboard.llm_result.draft_actions[index])

    def apply_roster_move(self, dashboard: FranchiseDashboard, index: int = 0) -> dict[str, int]:
        return self.apply_roster_move_record(dashboard.llm_result.roster_moves[index])

    def preview_roster_move(self, dashboard: FranchiseDashboard, index: int = 0) -> tuple[str, ...]:
        return self.preview_roster_move_record(dashboard.llm_result.roster_moves[index])

    def preview_roster_move_record(self, move: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            f"{domain}[{index}].{field_name} = {value}"
            for domain, index, field_name, value, _entry in self._write_steps_for_roster_move(move)
        )

    def action_write_previews(self, dashboard: FranchiseDashboard) -> dict[str, tuple[str, ...]]:
        previews: dict[str, tuple[str, ...]] = {}
        for index, proposal in enumerate(dashboard.llm_result.trade_proposals):
            previews[f"Trade #{index}"] = self._blocked_preview_or_writes(lambda proposal=proposal: self._preview_trade_proposal(proposal))
        for index, plan in enumerate(dashboard.llm_result.signing_plans):
            previews[f"Signing #{index}"] = self._blocked_preview_or_writes(lambda plan=plan: self.preview_roster_move_record(plan))
        for index, action in enumerate(dashboard.llm_result.draft_actions):
            previews[f"Draft #{index}"] = self._blocked_preview_or_writes(lambda action=action: self.preview_roster_move_record(action))
        for index, move in enumerate(dashboard.llm_result.roster_moves):
            previews[f"Roster #{index}"] = self._blocked_preview_or_writes(lambda move=move: self.preview_roster_move_record(move))
        return previews

    def _blocked_preview_or_writes(self, build_preview: Callable[[], tuple[str, ...]]) -> tuple[str, ...]:
        try:
            return build_preview()
        except Exception as exc:
            return (f"BLOCKED: {exc}",)

    def _preview_trade_proposal(self, proposal: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            f"{domain}[{index}].{field_name} = {value}"
            for domain, index, field_name, value, _entry in self._write_steps_for_trade_proposal(proposal)
        )
    def _write_steps_for_trade_proposal(self, proposal: dict[str, Any]) -> tuple[tuple[str, int, str, int, Any], ...]:
        assets = tuple(proposal.get("outgoing_assets", ())) + tuple(proposal.get("incoming_assets", ()))
        moves = tuple(
            (asset, self._player_item_for_move(asset), self._team_item_for_move(asset))
            for asset in assets
            if isinstance(asset, dict)
        )
        team_slots = {
            int(team.index): [(entry, int(self.editor_model.read_entry_value(entry, index=int(team.index))["raw_value"] or 0)) for entry in self._team_slot_entries()]
            for team in self.editor_model.loaded_items.get("Teams", {}).values()
        }
        moved_addresses = {int(player.address) for _asset, player, _team in moves}
        simulated = {
            team_index: self._compact_slot_values(tuple(value for _entry, value in slots), moved_addresses)
            for team_index, slots in team_slots.items()
        }
        steps: list[tuple[str, int, str, int, Any]] = []
        for team_index, slots in team_slots.items():
            for offset, (entry, original_value) in enumerate(slots):
                value = simulated[team_index][offset]
                if value != original_value:
                    steps.append(("Teams", team_index, str(entry.normalized_name), value, entry))
        current_team_entry = self._player_current_team_entry()
        slot_entries = self._team_slot_entries()
        for asset, player, team in moves:
            team_index = int(team.index)
            slot_offset = self._target_slot_offset_for_simulated_values(simulated[team_index], asset)
            simulated[team_index][slot_offset] = int(player.address)
            entry = slot_entries[slot_offset]
            steps.append(("Teams", team_index, str(entry.normalized_name), int(player.address), entry))
            steps.append(("Players", int(player.index), str(current_team_entry.normalized_name), int(team.address), current_team_entry))
        return tuple(steps)

    def _compact_slot_values(self, values: tuple[int, ...], moved_addresses: set[int]) -> list[int]:
        remaining = [value for value in values if value not in moved_addresses]
        return [*remaining, *(0 for _ in range(len(values) - len(remaining)))]

    def _target_slot_offset_for_simulated_values(self, values: list[int], move: dict[str, Any]) -> int:
        requested = str(move.get("team_slot_field") or "").strip()
        if requested:
            wanted = _field_identity(requested)
            for offset, entry in enumerate(self._team_slot_entries()):
                if _field_identity(entry.normalized_name) != wanted:
                    continue
                if values[offset]:
                    raise ValueError(f"target team slot is occupied: {entry.normalized_name}")
                return offset
            raise KeyError(f"team roster slot field is missing: {requested}")
        for offset, value in enumerate(values):
            if value == 0:
                return offset
        raise ValueError("target team has no empty PLAYER slot after trade-package removals")

    def apply_roster_move_record(self, move: dict[str, Any]) -> dict[str, int]:
        steps = self._write_steps_for_roster_move(move)
        for _domain, index, _field_name, value, entry in steps:
            self.editor_model.write_entry_value(entry, index=index, value=value)
        return {"attempted": len(steps), "succeeded": len(steps)}

    def _write_steps_for_roster_move(self, move: dict[str, Any]) -> tuple[tuple[str, int, str, int, Any], ...]:
        player = self._player_item_for_move(move)
        team = self._team_item_for_move(move)
        slot_entry = self._target_team_slot_entry(team, move)
        steps = [
            ("Teams", index, str(entry.normalized_name), value, entry)
            for entry, index, value in self._source_slot_compaction_steps(player)
        ]
        steps.append(("Teams", int(team.index), str(slot_entry.normalized_name), int(player.address), slot_entry))
        current_team_entry = self._player_current_team_entry()
        steps.append(("Players", int(player.index), str(current_team_entry.normalized_name), int(team.address), current_team_entry))
        return tuple(steps)

    def import_live_snapshot(self) -> LiveFranchiseSnapshot:
        full_app_dataset = self._app_dataset_snapshot()
        team_items = tuple(self.editor_model.loaded_items.get("Teams", {}).values())
        team_lookup = _entry_lookup(self.editor_model, "Teams")
        player_lookup = _entry_lookup(self.editor_model, "Players")
        roster_rows = self._roster_slot_rows(team_items)
        team_indexes_with_players = self._team_indexes_for_roster_rows(roster_rows)
        teams = tuple(
            self._team_snapshot(item, team_lookup)
            for item in team_items
            if self._team_has_roster_players(item, team_indexes_with_players)
        )
        roster_players = self._roster_player_snapshots(roster_rows, player_lookup)
        return LiveFranchiseSnapshot(teams=teams, roster_players=roster_players, full_app_dataset=full_app_dataset)

    def _app_dataset_snapshot(self) -> dict[str, Any]:
        dataset_builder = getattr(self.editor_model, "app_dataset_snapshot", None)
        if callable(dataset_builder):
            snapshot = dataset_builder()
            return snapshot if isinstance(snapshot, dict) else {"value": snapshot}
        return {
            "domains": {
                str(domain): {"count": len(records), "records": [str(label) for label in records]}
                for domain, records in getattr(self.editor_model, "loaded_items", {}).items()
            },
            "source": "loaded_items fallback",
        }

    def build_llm_prompt(self, snapshot: LiveFranchiseSnapshot, *, previous_state: dict[str, Any] | None = None) -> str:
        payload = {
            "current_snapshot": snapshot.to_dict(),
            "previous_franchise_state": self._llm_context_from_state(previous_state or {}),
        }
        schema = {
            "panel_reports": {panel: "LLM-written panel text" for panel in FRANCHISE_PANEL_TABS},
            "front_offices": [{"team_id": "team_index_0", "role": "owner|gm|assistant_gm|cfo|coach|scout|trainer", "profile": {}}],
            "trade_proposals": [{"status": "proposed|blocked|manual_setup_required", "from_team_id": "team_index_0", "to_team_id": "team_index_1", "outgoing_assets": [{"player_id": "exact imported player_id", "team_id": "target team_id", "team_slot_field": "optional empty PLAYER# slot"}], "incoming_assets": [], "rationale": "model-generated transaction logic", "requires_user_approval": True, "write_path": "existing_editor_only"}],
            "signing_plans": [{"status": "target|blocked|manual_setup_required", "team_id": "target team_id", "player_id": "exact imported player_id", "player": "player/free-agent name if known", "team_slot_field": "optional empty PLAYER# slot", "rationale": "model-generated signing logic", "requires_user_approval": True, "write_path": "existing_editor_only"}],
            "draft_actions": [{"status": "target|trade_up|trade_down|blocked|manual_setup_required", "team_id": "target team_id", "player_id": "exact imported player_id/prospect id if known", "prospect": "prospect name if known", "team_slot_field": "optional empty PLAYER# slot", "rationale": "model-generated draft logic", "requires_user_approval": True, "write_path": "existing_editor_only"}],
            "roster_moves": [{"status": "proposed|blocked|manual_setup_required", "team_id": "target team_id", "move_type": "trade|sign|draft|waive|release|rotation|g_league|other", "player_id": "exact imported player_id", "player": "player name if known", "team_slot_field": "optional empty PLAYER# slot", "rationale": "model-generated roster logic", "requires_user_approval": True, "write_path": "existing_editor_only"}],
            "sim_plan": {"plan": {}, "team_requests": [{"team_id": "team_index_0", "request": {}}]},
            "trade_deadline": {},
            "offseason_phases": [],
            "league_meetings": [],
            "rule_votes": [],
            "staff_decisions": [],
            "scouting": {},
            "expansion_draft": {},
            "draft": {},
            "free_agency": {},
            "consequences": [],
        }
        return "\n".join(
            (
                "You are the NBA2K Editor Franchise Manager front-office model.",
                "NBA 2K remains the simulator. You create franchise life around the imported editor state.",
                "Baseline job right now: generate trades, player signings, draft actions, and roster moves around the imported 2K state.",
                "For any action that can move a player, include exact imported player_id, target team_id, and optional empty team_slot_field; vague player/team names are not enough to apply a live write.",
                "Do not remove broader league-office/offseason context; use it only to support transaction and draft decisions.",
                "Every panel, message, profile, vote, sim request, phase decision, and consequence must be generated by you from the JSON state.",
                "Do not use static templates, canned examples, or default text.",
                "Act as rival/self-interested executives, owners, staff, scouts, trainers, and league office actors, not as a user helper.",
                "Generate structured JSON only. No markdown outside the JSON object.",
                "Use these panel keys exactly:",
                json.dumps(list(FRANCHISE_PANEL_TABS), indent=2),
                "Return this JSON shape, filling it with model-generated franchise content:",
                json.dumps(schema, indent=2),
                "Do not claim a memory write happened. Real writes require explicit user action outside this generation step.",
                "CURRENT DATA:",
                json.dumps(payload, indent=2, sort_keys=True),
            )
        )

    def _llm_context_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "front_offices": state.get("front_offices", []),
            "trade_proposals": state.get("trade_proposals", [])[-20:],
            "signing_plans": state.get("signing_plans", [])[-20:],
            "draft_actions": state.get("draft_actions", [])[-20:],
            "roster_moves": state.get("roster_moves", [])[-20:],
            "sim_plans": state.get("sim_plans", [])[-3:],
            "trade_deadline_postures": state.get("trade_deadline_postures", [])[-3:],
            "league_meetings": state.get("league_meetings", [])[-3:],
            "rule_votes": state.get("rule_votes", [])[-10:],
            "staff_decisions": state.get("staff_decisions", [])[-10:],
            "consequences": state.get("consequences", [])[-20:],
            "draft_boards": state.get("draft_boards", [])[-3:],
            "free_agency_plans": state.get("free_agency_plans", [])[-3:],
        }

    def _run_llm(self, prompt: str) -> str:
        if self.llm_client is not None:
            return self.llm_client(prompt)
        endpoint = os.environ.get("NBA2K_FRANCHISE_LLM_ENDPOINT")
        api_key = os.environ.get("NBA2K_FRANCHISE_LLM_API_KEY")
        model = os.environ.get("NBA2K_FRANCHISE_LLM_MODEL")
        if not endpoint or not api_key or not model:
            return ""
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an NBA2K Franchise Manager model that returns only JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.9,
            }
        ).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])

    def _team_item_for_move(self, move: dict[str, Any]) -> Any:
        team_index = int(str(move["team_id"]).replace("team_index_", ""))
        for team in self.editor_model.loaded_items.get("Teams", {}).values():
            if int(team.index) == team_index:
                return team
        raise KeyError(f"team is not loaded: {move['team_id']}")

    def _player_item_for_move(self, move: dict[str, Any]) -> Any:
        requested = str(move.get("player_id") or move.get("player") or "")
        for player in self.editor_model.loaded_items.get("Players", {}).values():
            if requested == f"player_index_{int(player.index)}" or requested == str(player.index) or requested == str(player.label) or requested == str(player.display_label):
                return player
        unique_entry = _entry_lookup(self.editor_model, "Players").get("UNIQUEID")
        if unique_entry is not None:
            for player in self.editor_model.loaded_items.get("Players", {}).values():
                value = self.editor_model.read_entry_value(unique_entry, index=int(player.index))
                if requested in {str(value.get("raw_value")), str(value.get("display_value"))}:
                    return player
        snapshot = self.import_live_snapshot()
        for row in snapshot.roster_players:
            if requested == str(row.player_id):
                for player in self.editor_model.loaded_items.get("Players", {}).values():
                    if int(player.index) == int(row.index):
                        return player
        raise KeyError(f"player is not loaded: {requested}")

    def _team_slot_entries(self) -> tuple[Any, ...]:
        entries = []
        for entry in self.editor_model.grouped_fields("Teams")["Team Players"]["Team Players"]:
            name = _field_identity(entry.normalized_name)
            if not name.startswith("PLAYER"):
                continue
            suffix = name.replace("PLAYER", "", 1)
            if suffix.isdigit():
                entries.append((int(suffix), entry))
        return tuple(entry for _slot, entry in sorted(entries, key=lambda item: item[0]))

    def _team_slot_entry(self, normalized_name: str) -> Any:
        wanted = _field_identity(normalized_name)
        for entry in self._team_slot_entries():
            if _field_identity(entry.normalized_name) == wanted:
                return entry
        raise KeyError(f"team roster slot field is missing: {normalized_name}")

    def _target_team_slot_entry(self, team: Any, move: dict[str, Any]) -> Any:
        requested = str(move.get("team_slot_field") or "").strip()
        if requested:
            entry = self._team_slot_entry(requested)
            raw_value = int(self.editor_model.read_entry_value(entry, index=int(team.index))["raw_value"] or 0)
            if raw_value:
                raise ValueError(f"target team slot is occupied: {entry.normalized_name}")
            return entry
        for entry in self._team_slot_entries():
            raw_value = int(self.editor_model.read_entry_value(entry, index=int(team.index))["raw_value"] or 0)
            if raw_value == 0:
                return entry
        raise ValueError(f"target team has no empty PLAYER slot: {team.label}")

    def _player_current_team_entry(self) -> Any:
        for groups in self.editor_model.grouped_fields("Players").values():
            for entries in groups.values():
                for entry in entries:
                    if _field_identity(entry.normalized_name) == "CURRENTTEAM":
                        return entry
        raise KeyError("Players CURRENTTEAM field is missing")

    def _source_slot_compaction_steps(self, player: Any) -> tuple[tuple[Any, int, int], ...]:
        for team in self.editor_model.loaded_items.get("Teams", {}).values():
            slots = [(entry, int(self.editor_model.read_entry_value(entry, index=int(team.index))["raw_value"] or 0)) for entry in self._team_slot_entries()]
            for offset, (_entry, raw_value) in enumerate(slots):
                if raw_value != int(player.address):
                    continue
                steps: list[tuple[Any, int, int]] = []
                for current_index in range(offset, len(slots) - 1):
                    current_entry = slots[current_index][0]
                    next_value = slots[current_index + 1][1]
                    steps.append((current_entry, int(team.index), next_value))
                steps.append((slots[-1][0], int(team.index), 0))
                return tuple(steps)
        return ()

    def _llm_result_from_output(self, llm_output: str) -> FranchiseLLMResult:
        parsed = self._parse_json_output(llm_output)
        if parsed is None:
            return FranchiseLLMResult(panel_reports=self._panel_reports_from_section_output(llm_output), raw_output=llm_output)
        sim_plan = parsed.get("sim_plan", {}) if isinstance(parsed.get("sim_plan"), dict) else {}
        return FranchiseLLMResult(
            panel_reports=self._panel_reports_from_mapping(parsed.get("panel_reports", {})),
            front_offices=tuple(
                FrontOfficeProfile(
                    team_id=str(item.get("team_id") or ""),
                    role=str(item.get("role") or ""),
                    profile=dict(item.get("profile") or {}),
                )
                for item in parsed.get("front_offices", [])
                if isinstance(item, dict)
            ),
            trade_proposals=tuple(dict(item) for item in parsed.get("trade_proposals", []) if isinstance(item, dict)),
            signing_plans=tuple(dict(item) for item in parsed.get("signing_plans", []) if isinstance(item, dict)),
            draft_actions=tuple(dict(item) for item in parsed.get("draft_actions", []) if isinstance(item, dict)),
            roster_moves=tuple(dict(item) for item in parsed.get("roster_moves", []) if isinstance(item, dict)),
            sim_plan=LeagueSimPlan(
                plan=dict(sim_plan.get("plan") or {}),
                team_requests=tuple(
                    SimRequest(team_id=str(item.get("team_id") or ""), request=dict(item.get("request") or {}))
                    for item in sim_plan.get("team_requests", [])
                    if isinstance(item, dict)
                ),
            ),
            trade_deadline=dict(parsed.get("trade_deadline") or {}),
            offseason_phases=tuple(dict(item) for item in parsed.get("offseason_phases", []) if isinstance(item, dict)),
            league_meetings=tuple(dict(item) for item in parsed.get("league_meetings", []) if isinstance(item, dict)),
            rule_votes=tuple(dict(item) for item in parsed.get("rule_votes", []) if isinstance(item, dict)),
            staff_decisions=tuple(dict(item) for item in parsed.get("staff_decisions", []) if isinstance(item, dict)),
            scouting=dict(parsed.get("scouting") or {}),
            expansion_draft=dict(parsed.get("expansion_draft") or {}),
            draft=dict(parsed.get("draft") or {}),
            free_agency=dict(parsed.get("free_agency") or {}),
            consequences=tuple(dict(item) for item in parsed.get("consequences", []) if isinstance(item, dict)),
            raw_output=llm_output,
        )

    def _parse_json_output(self, llm_output: str) -> dict[str, Any] | None:
        text = llm_output.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _panel_reports_from_mapping(self, value: Any) -> dict[str, str]:
        reports = {panel: "" for panel in FRANCHISE_PANEL_TABS}
        if isinstance(value, dict):
            for panel in FRANCHISE_PANEL_TABS:
                reports[panel] = str(value.get(panel) or "")
        return reports

    def _panel_reports_from_section_output(self, llm_output: str) -> dict[str, str]:
        if not llm_output.strip():
            return {panel: "" for panel in FRANCHISE_PANEL_TABS}
        reports = {panel: "" for panel in FRANCHISE_PANEL_TABS}
        active_panel: str | None = None
        for line in llm_output.splitlines():
            stripped = line.strip().strip("#:")
            if stripped in reports:
                active_panel = stripped
                continue
            if active_panel is not None:
                reports[active_panel] = "\n".join((reports[active_panel], line)).strip()
        if any(reports.values()):
            return reports
        reports["League Office"] = llm_output.strip()
        return reports

    def _read_value(self, entry: Any | None, index: int) -> Any | None:
        if entry is None:
            return None
        value = self.editor_model.read_entry_value(entry, index=index)
        if isinstance(value, dict):
            if value.get("display_value") not in (None, ""):
                return value.get("display_value")
            return value.get("raw_value")
        return value

    def _team_snapshot(self, item: Any, lookup: dict[str, Any]) -> TeamSnapshot:
        city = self._read_value(_find_entry(lookup, _FIELD_ALIASES["team_city"]), item.index)
        name = self._read_value(_find_entry(lookup, _FIELD_ALIASES["team_name"]), item.index)
        return TeamSnapshot(
            team_id=f"team_index_{int(item.index)}",
            index=int(item.index),
            address=int(item.address),
            label=str(getattr(item, "display_label", item.label)),
            city=str(city).strip() if city not in (None, "") else None,
            name=str(name).strip() if name not in (None, "") else None,
            wins=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["wins"]), item.index)),
            losses=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["losses"]), item.index)),
            conference_rank=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["conference_rank"]), item.index)),
            division_rank=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["division_rank"]), item.index)),
            playoff_seed=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["playoff_seed"]), item.index)),
            payroll=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["payroll"]), item.index)),
            cap_room=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["cap_room"]), item.index)),
        )

    def _team_has_roster_players(self, team_item: Any, team_indexes: set[int]) -> bool:
        return int(team_item.index) in team_indexes

    def _roster_slot_rows(self, team_items: tuple[Any, ...]) -> tuple[tuple[Any, dict[str, Any]], ...]:
        return tuple(self.editor_model.player_roster_slot_items_for_team_items(team_items))

    def _team_indexes_for_roster_rows(self, roster_rows: tuple[tuple[Any, dict[str, Any]], ...]) -> set[int]:
        return {int(placement["team_index"]) for _player, placement in roster_rows}

    def _roster_player_snapshots(self, roster_rows: tuple[tuple[Any, dict[str, Any]], ...], lookup: dict[str, Any]) -> tuple[PlayerSnapshot, ...]:
        snapshots: list[PlayerSnapshot] = []
        seen: set[tuple[int, int | None]] = set()
        for player, placement in roster_rows:
            roster_slot = _coerce_int(placement.get("team_slot"))
            key = (int(player.index), roster_slot)
            if key in seen:
                continue
            seen.add(key)
            first_name = self._read_value(_find_entry(lookup, _FIELD_ALIASES["first_name"]), player.index)
            last_name = self._read_value(_find_entry(lookup, _FIELD_ALIASES["last_name"]), player.index)
            player_id_value = self._read_value(_find_entry(lookup, _FIELD_ALIASES["player_id"]), player.index)
            player_id = str(player_id_value).strip() if player_id_value not in (None, "") else f"player_index_{int(player.index)}"
            position = self._read_value(_find_entry(lookup, _FIELD_ALIASES["position"]), player.index)
            snapshots.append(
                PlayerSnapshot(
                    player_id=player_id,
                    index=int(player.index),
                    address=int(player.address),
                    label=str(getattr(player, "display_label", player.label)),
                    team_id=str(placement.get("team_label")) if placement.get("team_label") else None,
                    roster_slot=roster_slot,
                    roster_slot_field=str(placement.get("team_slot_field")) if placement.get("team_slot_field") else None,
                    first_name=str(first_name).strip() if first_name not in (None, "") else None,
                    last_name=str(last_name).strip() if last_name not in (None, "") else None,
                    overall=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["overall"]), player.index)),
                    potential=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["potential"]), player.index)),
                    position=str(position).strip() if position not in (None, "") else None,
                    age=_coerce_int(self._read_value(_find_entry(lookup, _FIELD_ALIASES["age"]), player.index)),
                )
            )
        return tuple(snapshots)
