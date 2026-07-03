from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nba2k_editor.ui.franchise_screen import FRANCHISE_PANEL_TABS
from nba2k_editor.franchise.service import FranchiseManagerService
from nba2k_editor.franchise.store import FranchiseJsonStore
from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui import qt_app
from nba2k_editor.ui.qt_app import QtEditorApp
from tests.test_qt_editor_players_screen import PlayerScreenModel


def field(domain: str, name: str, display: str | None = None) -> FieldEntry:
    return FieldEntry(domain=domain, section="Vitals", group="Vitals", ordinal=0, field={"normalized_name": name, "display_name": display or name})


class FakeFranchiseModel:
    def __init__(self) -> None:
        self.team = RecordListItem(domain="Teams", index=0, address=1000, label="Philadelphia 76ers")
        self.empty_team = RecordListItem(domain="Teams", index=1, address=2000, label="Empty Team")
        self.player = RecordListItem(domain="Players", index=7, address=7000, label="Tyrese Maxey")
        self.second_player = RecordListItem(domain="Players", index=8, address=8000, label="Joel Embiid")
        self.third_player = RecordListItem(domain="Players", index=9, address=9000, label="Nikola Jokic")
        self.fourth_player = RecordListItem(domain="Players", index=10, address=9100, label="Jamal Murray")
        self.loaded_items = {
            "Teams": {self.team.display_label: self.team, self.empty_team.display_label: self.empty_team},
            "Players": {
                self.player.display_label: self.player,
                self.second_player.display_label: self.second_player,
                self.third_player.display_label: self.third_player,
                self.fourth_player.display_label: self.fourth_player,
            },
        }
        self.roster_slot_calls = 0
        self.dataset_calls = 0
        self.write_calls: list[tuple[str, int, Any]] = []
        self.team_fields = {
            "CITYNAME": field("Teams", "CITYNAME", "City Name"),
            "TEAMNAME": field("Teams", "TEAMNAME", "Team Name"),
            "WINS": field("Teams", "WINS"),
            "LOSSES": field("Teams", "LOSSES"),
            "PLAYER1": FieldEntry(domain="Teams", section="Team Players", group="Team Players", ordinal=1, field={"normalized_name": "PLAYER1", "display_name": "PLAYER1"}),
            "PLAYER2": FieldEntry(domain="Teams", section="Team Players", group="Team Players", ordinal=2, field={"normalized_name": "PLAYER2", "display_name": "PLAYER2"}),
        }
        self.player_fields = {
            "FIRSTNAME": field("Players", "FIRSTNAME", "First Name"),
            "LASTNAME": field("Players", "LASTNAME", "Last Name"),
            "UNIQUEID": field("Players", "UNIQUEID", "Unique ID"),
            "OVR": field("Players", "OVR"),
            "POTENTIAL": field("Players", "POTENTIAL"),
            "POSITION": field("Players", "POSITION"),
            "CURRENTTEAM": field("Players", "CURRENTTEAM"),
        }
        self.values = {
            ("Teams", 0, "CITYNAME"): {"display_value": "Philadelphia", "raw_value": "Philadelphia"},
            ("Teams", 0, "TEAMNAME"): {"display_value": "76ers", "raw_value": "76ers"},
            ("Teams", 0, "WINS"): {"display_value": "22", "raw_value": 22},
            ("Teams", 0, "LOSSES"): {"display_value": "10", "raw_value": 10},
            ("Players", 7, "FIRSTNAME"): {"display_value": "Tyrese", "raw_value": "Tyrese"},
            ("Players", 7, "LASTNAME"): {"display_value": "Maxey", "raw_value": "Maxey"},
            ("Players", 7, "UNIQUEID"): {"display_value": "203999", "raw_value": 203999},
            ("Players", 7, "OVR"): {"display_value": "88", "raw_value": 88},
            ("Players", 7, "POTENTIAL"): {"display_value": "91", "raw_value": 91},
            ("Players", 7, "POSITION"): {"display_value": "PG", "raw_value": "PG"},
            ("Players", 7, "CURRENTTEAM"): {"display_value": "Philadelphia 76ers", "raw_value": 1000},
            ("Players", 8, "FIRSTNAME"): {"display_value": "Joel", "raw_value": "Joel"},
            ("Players", 8, "LASTNAME"): {"display_value": "Embiid", "raw_value": "Embiid"},
            ("Players", 8, "UNIQUEID"): {"display_value": "203954", "raw_value": 203954},
            ("Players", 8, "OVR"): {"display_value": "95", "raw_value": 95},
            ("Players", 8, "POTENTIAL"): {"display_value": "95", "raw_value": 95},
            ("Players", 8, "POSITION"): {"display_value": "C", "raw_value": "C"},
            ("Players", 8, "CURRENTTEAM"): {"display_value": "Philadelphia 76ers", "raw_value": 1000},
            ("Players", 9, "FIRSTNAME"): {"display_value": "Nikola", "raw_value": "Nikola"},
            ("Players", 9, "LASTNAME"): {"display_value": "Jokic", "raw_value": "Jokic"},
            ("Players", 9, "UNIQUEID"): {"display_value": "204001", "raw_value": 204001},
            ("Players", 9, "OVR"): {"display_value": "97", "raw_value": 97},
            ("Players", 9, "POTENTIAL"): {"display_value": "97", "raw_value": 97},
            ("Players", 9, "POSITION"): {"display_value": "C", "raw_value": "C"},
            ("Players", 9, "CURRENTTEAM"): {"display_value": "Empty Team", "raw_value": 2000},
            ("Players", 10, "FIRSTNAME"): {"display_value": "Jamal", "raw_value": "Jamal"},
            ("Players", 10, "LASTNAME"): {"display_value": "Murray", "raw_value": "Murray"},
            ("Players", 10, "UNIQUEID"): {"display_value": "2039999", "raw_value": 2039999},
            ("Players", 10, "OVR"): {"display_value": "88", "raw_value": 88},
            ("Players", 10, "POTENTIAL"): {"display_value": "88", "raw_value": 88},
            ("Players", 10, "POSITION"): {"display_value": "PG", "raw_value": "PG"},
            ("Players", 10, "CURRENTTEAM"): {"display_value": "Empty Team", "raw_value": 2000},
        }
        self.team_slot_values = {
            (0, "PLAYER1"): self.player.address,
            (0, "PLAYER2"): self.second_player.address,
            (1, "PLAYER1"): 0,
            (1, "PLAYER2"): 0,
        }

    def grouped_fields(self, domain: str) -> dict[str, dict[str, list[FieldEntry]]]:
        if domain == "Teams":
            return {
                "Vitals": {"Vitals": [self.team_fields["CITYNAME"], self.team_fields["TEAMNAME"], self.team_fields["WINS"], self.team_fields["LOSSES"]]},
                "Team Players": {"Team Players": [self.team_fields["PLAYER1"], self.team_fields["PLAYER2"]]},
            }
        if domain == "Players":
            return {"Vitals": {"Vitals": list(self.player_fields.values())}}
        return {}

    def read_entry_value(self, entry: FieldEntry, *, index: int, **_kwargs: Any) -> dict[str, Any]:
        if entry.domain == "Teams" and entry.normalized_name.startswith("PLAYER"):
            raw_value = self.team_slot_values[(index, entry.normalized_name)]
            return {"display_value": raw_value, "raw_value": raw_value}
        return self.values[(entry.domain, index, entry.normalized_name)]

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, **_kwargs: Any) -> None:
        self.write_calls.append((entry.normalized_name, index, value))
        if entry.domain == "Teams" and entry.normalized_name.startswith("PLAYER"):
            self.team_slot_values[(index, entry.normalized_name)] = int(value)

    def player_roster_slot_items_for_team_items(self, team_items: tuple[RecordListItem, ...]) -> list[tuple[RecordListItem, dict[str, Any]]]:
        self.roster_slot_calls += 1
        assert tuple(team_items) == (self.team, self.empty_team)
        return [
            (self.player, {"team_index": 0, "team_label": self.team.label, "team_slot": 1, "team_slot_field": "PLAYER1"}),
            (self.second_player, {"team_index": 0, "team_label": self.team.label, "team_slot": 2, "team_slot_field": "PLAYER2"}),
        ]

    def runtime_status_text(self) -> str:
        return "fake runtime"

    def app_dataset_snapshot(self) -> dict[str, Any]:
        self.dataset_calls += 1
        return {
            "target_executable": "fake.exe",
            "runtime_status": self.runtime_status_text(),
            "domains": {
                "Teams": {"count": len(self.loaded_items["Teams"]), "records": [{"label": item.label} for item in self.loaded_items["Teams"].values()]},
                "Players": {"count": len(self.loaded_items["Players"]), "records": [{"label": item.label} for item in self.loaded_items["Players"].values()]},
                "Staff": {"count": 0, "records": []},
            },
        }


def fake_llm(prompt: str) -> str:
    assert "Tyrese Maxey" in prompt
    assert "Philadelphia" in prompt
    assert "front_offices" in prompt
    assert "full_app_dataset" in prompt
    assert "Staff" in prompt
    assert "trade_proposals" in prompt
    assert "signing_plans" in prompt
    assert "draft_actions" in prompt
    assert "roster_moves" in prompt
    assert "offseason_phases" in prompt
    assert "consequences" in prompt
    return json.dumps(
        {
            "panel_reports": {
                "League Office": "LLM league read: Philadelphia has one imported roster-slot player.",
                "Front Office Inbox": "LLM inbox: Tyrese Maxey is the visible roster anchor.",
                "Sim Negotiation": "LLM sim read: 22-10 record supports a longer window if the user chooses it.",
            },
            "front_offices": [
                {"team_id": "team_index_0", "role": "owner", "profile": {"pressure": "high-market expectation"}},
                {"team_id": "team_index_0", "role": "gm", "profile": {"posture": "contender watch"}},
            ],
            "trade_proposals": [
                {"status": "proposed", "from_team_id": "team_index_0", "to_team_id": "team_index_1", "outgoing_assets": [{"player_id": "203999", "team_id": "team_index_1"}], "incoming_assets": [], "rationale": "LLM trade baseline", "requires_user_approval": True, "write_path": "existing_editor_only"}
            ],
            "signing_plans": [
                {"status": "target", "team_id": "team_index_1", "player_id": "203999", "player": "Tyrese Maxey", "rationale": "LLM signing baseline", "requires_user_approval": True, "write_path": "existing_editor_only"}
            ],
            "draft_actions": [
                {"status": "target", "team_id": "team_index_1", "player_id": "203999", "prospect": "Tyrese Maxey", "rationale": "LLM draft baseline", "requires_user_approval": True, "write_path": "existing_editor_only"}
            ],
            "roster_moves": [
                {"status": "proposed", "team_id": "team_index_1", "move_type": "rotation", "player_id": "203999", "player": "Tyrese Maxey", "rationale": "LLM roster baseline", "requires_user_approval": True, "write_path": "existing_editor_only"}
            ],
            "sim_plan": {
                "plan": {"recommended_window": "LLM supplied"},
                "team_requests": [{"team_id": "team_index_0", "request": {"urgency": "LLM supplied"}}],
            },
            "trade_deadline": {"team_index_0": "LLM posture"},
            "offseason_phases": [{"phase": "League Meetings", "source": "LLM"}],
            "league_meetings": [{"item": "LLM vote item"}],
            "rule_votes": [{"proposal": "LLM proposal"}],
            "staff_decisions": [{"team_id": "team_index_0", "decision": "LLM staff read"}],
            "scouting": {"combine": "LLM scouting read"},
            "expansion_draft": {"status": "LLM expansion read"},
            "draft": {"board": "LLM draft read"},
            "free_agency": {"plan": "LLM free agency read"},
            "consequences": [{"decision": "LLM consequence"}],
        }
    )


class FranchiseCommandCenterTests(unittest.TestCase):
    def test_service_imports_loaded_team_and_roster_slot_players_without_writes(self) -> None:
        model = FakeFranchiseModel()
        with tempfile.TemporaryDirectory() as tmp:
            service = FranchiseManagerService(model, store=FranchiseJsonStore(Path(tmp) / "state.json"), llm_client=fake_llm)
            dashboard = service.build_dashboard()

        self.assertEqual(1, model.roster_slot_calls)
        self.assertEqual(1, model.dataset_calls)
        self.assertEqual([], model.write_calls)
        self.assertEqual(1, len(dashboard.snapshot.teams))
        self.assertEqual(4, dashboard.snapshot.full_app_dataset["domains"]["Players"]["count"])
        self.assertIn("Staff", dashboard.snapshot.full_app_dataset["domains"])
        self.assertEqual("Philadelphia 76ers", dashboard.snapshot.teams[0].display_name)
        self.assertNotIn("Empty Team", [team.display_name for team in dashboard.snapshot.teams])
        self.assertEqual("Tyrese Maxey", dashboard.snapshot.roster_players[0].display_name)
        self.assertEqual("203999", dashboard.snapshot.roster_players[0].player_id)
        self.assertNotIn("missing_data", dashboard.snapshot.to_dict())
        self.assertIn("LLM league read", dashboard.panel_reports["League Office"])
        self.assertIn("LLM inbox", dashboard.panel_reports["Front Office Inbox"])
        self.assertEqual("owner", dashboard.llm_result.front_offices[0].role)
        self.assertEqual("LLM trade baseline", dashboard.llm_result.trade_proposals[0]["rationale"])
        self.assertEqual("LLM signing baseline", dashboard.llm_result.signing_plans[0]["rationale"])
        self.assertEqual("LLM draft baseline", dashboard.llm_result.draft_actions[0]["rationale"])
        self.assertEqual("LLM roster baseline", dashboard.llm_result.roster_moves[0]["rationale"])
        self.assertEqual("LLM supplied", dashboard.llm_result.sim_plan.plan["recommended_window"])
        self.assertEqual("LLM consequence", dashboard.llm_result.consequences[0]["decision"])

    def test_explicit_roster_move_apply_uses_existing_write_path(self) -> None:
        model = FakeFranchiseModel()
        with tempfile.TemporaryDirectory() as tmp:
            service = FranchiseManagerService(model, store=FranchiseJsonStore(Path(tmp) / "state.json"), llm_client=fake_llm)
            dashboard = service.build_dashboard()

        result = service.apply_roster_move(dashboard)

        self.assertEqual({"attempted": 4, "succeeded": 4}, result)
        self.assertEqual(
            [("PLAYER1", 0, model.second_player.address), ("PLAYER2", 0, 0), ("PLAYER1", 1, model.player.address), ("CURRENTTEAM", model.player.index, model.empty_team.address)],
            model.write_calls,
        )

    def test_write_preview_lists_exact_slot_writes_without_applying(self) -> None:
        model = FakeFranchiseModel()
        service = FranchiseManagerService(model, llm_client=fake_llm)
        dashboard = service.build_dashboard(persist=False)

        preview = service.preview_roster_move(dashboard)
        previews = service.action_write_previews(dashboard)

        self.assertEqual(
            (
                "Teams[0].PLAYER1 = 8000",
                "Teams[0].PLAYER2 = 0",
                "Teams[1].PLAYER1 = 7000",
                "Players[7].CURRENTTEAM = 2000",
            ),
            preview,
        )
        self.assertEqual(preview, previews["Roster #0"])
        self.assertIn("Trade #0", previews)
        self.assertEqual([], model.write_calls)

    def test_target_full_blocks_before_writes(self) -> None:
        model = FakeFranchiseModel()
        model.team_slot_values[(1, "PLAYER1")] = 9000
        model.team_slot_values[(1, "PLAYER2")] = 9001
        service = FranchiseManagerService(model, llm_client=fake_llm)
        dashboard = service.build_dashboard(persist=False)

        with self.assertRaises(ValueError):
            service.preview_roster_move(dashboard)
        with self.assertRaises(ValueError):
            service.apply_roster_move(dashboard)
        self.assertEqual([], model.write_calls)

    def test_trade_preflights_all_assets_before_writes(self) -> None:
        def invalid_trade_llm(prompt: str) -> str:
            payload = json.loads(fake_llm(prompt))
            payload["trade_proposals"][0]["outgoing_assets"].append({"player_id": "203999", "team_id": "team_index_99"})
            return json.dumps(payload)

        model = FakeFranchiseModel()
        service = FranchiseManagerService(model, llm_client=invalid_trade_llm)
        dashboard = service.build_dashboard(persist=False)

        with self.assertRaises(KeyError):
            service.apply_trade_proposal(dashboard)
        self.assertEqual([], model.write_calls)

    def test_player_for_player_trade_uses_package_opened_slots(self) -> None:
        def swap_llm(prompt: str) -> str:
            payload = json.loads(fake_llm(prompt))
            payload["trade_proposals"] = [
                {
                    "status": "proposed",
                    "from_team_id": "team_index_0",
                    "to_team_id": "team_index_1",
                    "outgoing_assets": [{"player_id": "203999", "team_id": "team_index_1"}],
                    "incoming_assets": [{"player_id": "204001", "team_id": "team_index_0"}],
                    "rationale": "LLM player swap",
                    "requires_user_approval": True,
                    "write_path": "existing_editor_only",
                }
            ]
            return json.dumps(payload)

        model = FakeFranchiseModel()
        model.team_slot_values[(1, "PLAYER1")] = model.third_player.address
        model.team_slot_values[(1, "PLAYER2")] = model.fourth_player.address
        service = FranchiseManagerService(model, llm_client=swap_llm)
        dashboard = service.build_dashboard(persist=False)

        preview = service.action_write_previews(dashboard)["Trade #0"]
        result = service.apply_trade_proposal(dashboard)

        self.assertEqual(
            (
                "Teams[0].PLAYER1 = 8000",
                "Teams[0].PLAYER2 = 0",
                "Teams[1].PLAYER1 = 9100",
                "Teams[1].PLAYER2 = 0",
                "Teams[1].PLAYER2 = 7000",
                "Players[7].CURRENTTEAM = 2000",
                "Teams[0].PLAYER2 = 9000",
                "Players[9].CURRENTTEAM = 1000",
            ),
            preview,
        )
        self.assertEqual({"attempted": 8, "succeeded": 8}, result)
        self.assertEqual(
            [
                ("PLAYER1", 0, model.second_player.address),
                ("PLAYER2", 0, 0),
                ("PLAYER1", 1, model.fourth_player.address),
                ("PLAYER2", 1, 0),
                ("PLAYER2", 1, model.player.address),
                ("CURRENTTEAM", model.player.index, model.empty_team.address),
                ("PLAYER2", 0, model.third_player.address),
                ("CURRENTTEAM", model.third_player.index, model.team.address),
            ],
            model.write_calls,
        )

    def test_full_franchise_panel_suite_is_available(self) -> None:
        expected = (
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
        self.assertEqual(expected, FRANCHISE_PANEL_TABS)
        self.assertNotIn("Missing Data / Offset Hunt", FRANCHISE_PANEL_TABS)

    def test_display_state_persists_llm_output_and_no_canned_messages(self) -> None:
        model = FakeFranchiseModel()
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "state.json"
            service = FranchiseManagerService(model, store=FranchiseJsonStore(store_path), llm_client=fake_llm)
            dashboard = service.build_dashboard()
            saved = store_path.read_text(encoding="utf-8")

        combined = "\n".join(dashboard.panel_reports.values()) + saved
        self.assertIn("LLM league read", combined)
        self.assertIn("Philadelphia", saved)
        self.assertIn("front_offices", saved)
        self.assertIn("trade_proposals", saved)
        self.assertIn("signing_plans", saved)
        self.assertIn("draft_actions", saved)
        self.assertIn("roster_moves", saved)
        self.assertIn("sim_plans", saved)
        self.assertIn("league_meetings", saved)
        self.assertIn("consequences", saved)
        self.assertNotIn("missing_data", saved)
        self.assertNotIn("No trade executes automatically", combined)
        self.assertNotIn("staged here", combined)
        self.assertNotIn("ownership is losing patience", combined)
        self.assertNotIn("manual confirmation needed", combined.lower())

    def test_ui_registers_fresh_franchise_manager_screen(self) -> None:
        self.assertIn(qt_app.FRANCHISE_MANAGER_SCREEN, qt_app.NAV_ORDER)
        self.assertIn(qt_app.FRANCHISE_MANAGER_SCREEN, qt_app.APP_SCREENS)
        app = QtEditorApp(PlayerScreenModel())  # type: ignore[arg-type]
        app.franchise_state = SimpleNamespace(
            status="ready",
            panel_texts={panel: f"{panel} report" for panel in FRANCHISE_PANEL_TABS},
        )
        app._sync_franchise_manager_status()
        rendered = app.franchise_text.toPlainText()
        self.assertIn("ready", rendered)
        for panel in FRANCHISE_PANEL_TABS:
            self.assertIn(f"## {panel}", rendered)
        self.assertTrue(hasattr(QtEditorApp, "_refresh_franchise_manager"))


if __name__ == "__main__":
    unittest.main()
