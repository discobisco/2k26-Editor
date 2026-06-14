from __future__ import annotations

import inspect
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from player_evidence import PlayerEvidence
from player_generator import (
    GeneratedPlayerProposal,
    SeasonPlayerContextIndex,
    authored_player_field_index,
    generate_player_proposal,
    generate_player_proposal_from_contract,
    generate_player_proposal_from_index,
    generate_player_proposals_for_contract,
    generate_player_proposals_from_index,
    season_context_index,
    selected_year_player_comparison_rows,
)
from player_rules import (
    ATTRIBUTE_FIELDS,
    PROFILE_FIELDS,
    TENDENCY_FIELDS,
)
from contracts import GeneratorInputContract, OutputTarget
from source_data import GeneratorSourceInventory
from workbook_sqlite import ensure_workbook_sqlite_database, iter_workbook_sqlite_sheet_rows, workbook_sqlite_sheet_names

OFFSETS_PLAYERS_PATH = Path(__file__).resolve().parents[1] / "nba2k_editor" / "core" / "Offsets" / "offsets_players.json"


def _evidence(**overrides: object) -> PlayerEvidence:
    base = PlayerEvidence(
        player_id="player01",
        season=2025,
        team="NYK",
        identity={
            "player": "Rule Test",
            "player_id": "player01",
            "pos": "G",
            "ht_in_in": 75,
            "wt": 195,
            "colleges": "Memphis",
            "from": 2021,
        },
        season_info={"player_id": "player01", "team": "NYK", "pos": "G", "experience": 4},
        per_game={
            "pts_per_game": 20.0,
            "trb_per_game": 5.0,
            "ast_per_game": 6.0,
            "stl_per_game": 1.4,
            "blk_per_game": 0.5,
            "x3p_percent": 0.390,
            "x3pa_per_game": 7.0,
            "ft_percent": 0.850,
            "fg_percent": 0.470,
        },
        per_100={"pts_per_100_poss": 31.0, "ast_per_100_poss": 9.0, "trb_per_100_poss": 7.0},
        advanced={"ts_percent": 0.600, "usg_percent": 27.0, "per": 20.0},
        shooting={"percent_fga_from_x0_3_range": 0.20, "percent_dunks_of_fga": 0.04, "num_of_dunks": 18},
        play_by_play={"pg_percent": 70, "sg_percent": 30},
        team_roster=(
            {"player_id": "player01", "team": "NYK", "season": 2025, "player": "Rule Test"},
            {"player_id": "player02", "team": "NYK", "season": 2025, "player": "Teammate"},
        ),
        team_stats_per_game={"abbreviation": "NYK", "pts_per_game": 117.0, "x3pa_per_game": 37.0},
        team_stats_per_100={"abbreviation": "NYK", "pts_per_100_poss": 119.0},
        team_summary={"abbreviation": "NYK", "o_rtg": 119.0, "d_rtg": 112.0, "pace": 99.0},
        opponent_stats_per_game={"abbreviation": "NYK", "opp_pts_per_game": 112.0},
        opponent_stats_per_100={"abbreviation": "NYK", "opp_pts_per_100_poss": 112.0},
        missing_sources=(),
    )
    return replace(base, **overrides)


class PlayerGeneratorProposalTests(unittest.TestCase):
    def _contract(self, season: int) -> GeneratorInputContract:
        return GeneratorInputContract(
            season=season,
            source_root=GeneratorSourceInventory.from_default().root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()

    def test_generated_player_proposal_lines_up_with_offsets_players_json(self) -> None:
        proposal = generate_player_proposal(_evidence())
        authored = authored_player_field_index(OFFSETS_PLAYERS_PATH)
        expected_keys = PROFILE_FIELDS | ATTRIBUTE_FIELDS | TENDENCY_FIELDS

        self.assertIsInstance(proposal, GeneratedPlayerProposal)
        self.assertEqual(proposal.player_id, "player01")
        self.assertEqual(proposal.season, 2025)
        self.assertEqual(proposal.team, "NYK")
        self.assertEqual({candidate.field_key for candidate in proposal.field_candidates}, expected_keys)
        self.assertEqual(proposal.warnings, ())

        for candidate in proposal.field_candidates:
            authored_field = authored[candidate.field_key]
            self.assertEqual(candidate.domain, "Players")
            self.assertEqual(candidate.section, authored_field.section)
            self.assertEqual(candidate.group, authored_field.group)
            self.assertEqual(candidate.normalized_name, authored_field.normalized_name)
            self.assertEqual(candidate.field_key, f"{candidate.section}/{candidate.normalized_name}")
            self.assertNotEqual(candidate.display_value, "")
            self.assertTrue(candidate.source_rule)
            self.assertTrue(candidate.evidence_keys)

    def test_proposal_candidates_match_main_editor_write_readback_contract_shape(self) -> None:
        proposal = generate_player_proposal(_evidence())
        authored = authored_player_field_index(OFFSETS_PLAYERS_PATH)
        writes_seen: list[tuple[str, str, str, str, object]] = []

        for candidate in proposal.field_candidates:
            field_entry = authored[candidate.field_key]
            # This is the shape the later apply bridge needs before calling the
            # existing player write/readback seam: FieldEntry + display value.
            writes_seen.append(
                (
                    candidate.domain,
                    field_entry.section,
                    field_entry.group,
                    field_entry.normalized_name,
                    candidate.display_value,
                )
            )

        self.assertIn(("Players", "Attributes", "Offense", "3POINT", proposal.by_field_key()["Attributes/3POINT"].display_value), writes_seen)
        self.assertIn(("Players", "Vitals", "ID", "FIRSTNAME", "Rule"), writes_seen)
        self.assertIn(("Players", "Tendencies", "Freelance", "TOUCHES", proposal.by_field_key()["Tendencies/TOUCHES"].display_value), writes_seen)

    def test_proposal_values_keep_editor_ranges(self) -> None:
        proposal = generate_player_proposal(_evidence())

        for candidate in proposal.field_candidates:
            if candidate.section == "Attributes":
                self.assertGreaterEqual(candidate.display_value, 25)
                self.assertLessEqual(candidate.display_value, 99)
            if candidate.section == "Tendencies":
                self.assertGreaterEqual(candidate.display_value, 0)
                self.assertLessEqual(candidate.display_value, 100)

    def test_contract_generation_compares_player_to_selected_year_population(self) -> None:
        contract = self._contract(2025)

        proposal = generate_player_proposal_from_contract(contract, player_id="brunsja01", team="NYK")

        self.assertEqual(proposal.season, 2025)
        self.assertEqual(proposal.team, "NYK")
        self.assertEqual(proposal.identity["player"], "Jalen Brunson")
        self.assertGreaterEqual(proposal.by_field_key()["Attributes/3POINT"].display_value, 25)
        self.assertLessEqual(proposal.by_field_key()["Attributes/3POINT"].display_value, 99)

    def test_batch_generation_reuses_selected_year_context_for_team_subset(self) -> None:
        batch = generate_player_proposals_for_contract(self._contract(2025), team_filter="NYK")
        by_key = batch.by_player_team()

        self.assertEqual(batch.season, 2025)
        self.assertEqual(batch.failures, ())
        self.assertIn(("brunsja01", "NYK"), by_key)
        self.assertGreaterEqual(len(batch.proposals), 15)
        self.assertTrue(all(proposal.season == 2025 and proposal.team == "NYK" for proposal in batch.proposals))
        self.assertGreater(len(by_key[("brunsja01", "NYK")].field_candidates), 100)

    def test_multi_team_players_generate_once_on_first_listed_roster_with_aggregate_stats(self) -> None:
        context = season_context_index(self._contract(2025))

        self.assertIn(("ANDERKY01", "GSW"), context.evidence_by_key)
        self.assertNotIn(("ANDERKY01", "2TM"), context.evidence_by_key)
        self.assertNotIn(("ANDERKY01", "MIA"), context.evidence_by_key)
        evidence = context.evidence_for(player_id="anderky01", team="GSW")

        self.assertEqual(evidence.team, "GSW")
        self.assertEqual(evidence.season_info["team"], "GSW")
        self.assertEqual(evidence.per_game["team"], "GSW")
        self.assertEqual(evidence.per_game["source_team"], "2TM")
        self.assertEqual(evidence.per_game["pts_per_game"], 5.9)
        shares = evidence.per_game["multi_team_stat_shares"]
        self.assertEqual(tuple(share["team"] for share in shares), ("GSW", "MIA"))
        self.assertAlmostEqual(sum(float(share["stat_share"]) for share in shares), 1.0, places=5)
        self.assertIn(("anderky01", "GSW"), generate_player_proposals_for_contract(self._contract(2025), team_filter="GSW").by_player_team())
        self.assertNotIn(("anderky01", "MIA"), generate_player_proposals_for_contract(self._contract(2025), team_filter="MIA").by_player_team())

    def test_1947_full_season_ignores_draft_only_players_without_player_evidence(self) -> None:
        context = season_context_index(self._contract(1947))
        batch = generate_player_proposals_from_index(context)

        self.assertNotIn(("ALAMOBO01", "PIT"), context.evidence_by_key)
        self.assertEqual(batch.failures, ())
        self.assertGreater(len(batch.proposals), 150)

    def test_season_context_index_is_backend_cached_and_complete(self) -> None:
        contract = self._contract(2025)

        context = season_context_index(contract)
        same_context = season_context_index(contract)

        self.assertIsInstance(context, SeasonPlayerContextIndex)
        self.assertIs(context, same_context)
        self.assertIs(context.field_index["Attributes/3POINT"], same_context.field_index["Attributes/3POINT"])
        self.assertGreater(len(context.comparison_rows), 500)
        self.assertGreater(len(context.evidence_by_key), 500)
        self.assertIn(("BRUNSJA01", "NYK"), context.evidence_by_key)
        self.assertEqual(context.evidence_for(player_id="brunsja01", team="NYK").identity["player"], "Jalen Brunson")
        self.assertEqual(context.comparison_row_for(player_id="brunsja01", team="NYK")["team_summaries.o_rtg"], 118.5)

    def test_indexed_generation_matches_contract_generation_without_rebuilding_context(self) -> None:
        contract = self._contract(2025)
        context = season_context_index(contract)

        from_contract = generate_player_proposal_from_contract(contract, player_id="brunsja01", team="NYK")
        from_index = generate_player_proposal_from_index(context, player_id="brunsja01", team="NYK")
        batch = generate_player_proposals_from_index(context, team_filter="NYK")

        self.assertEqual(from_index.by_field_key(), from_contract.by_field_key())
        self.assertIn(("brunsja01", "NYK"), batch.by_player_team())
        self.assertEqual(batch.by_player_team()[("brunsja01", "NYK")].by_field_key(), from_index.by_field_key())

    def test_player_generator_screen_state_does_not_store_backend_context(self) -> None:
        import nba2k_editor.ui.player_generator_screen as screen

        state_fields = set(screen.PlayerGeneratorScreenState.__dataclass_fields__)

        self.assertNotIn("generator", state_fields)
        self.assertNotIn("context", state_fields)
        self.assertNotIn("season_context", state_fields)
        self.assertNotIn("season_context_index", state_fields)
        self.assertFalse(hasattr(screen.PlayerGeneratorScreenState(), "generator"))
        self.assertFalse(hasattr(screen.PlayerGeneratorScreenState(), "season_context_index"))

    def test_selected_year_comparison_rows_include_player_and_team_context(self) -> None:
        rows = selected_year_player_comparison_rows(self._contract(2025))
        row = next(row for row in rows if row["player_id"] == "brunsja01" and row["team"] == "NYK")

        self.assertEqual(row["season"], 2025)
        self.assertEqual(row["pts_per_game"], 26.0)
        self.assertEqual(row["pts_per_100_poss"], 36.4)
        self.assertEqual(row["usg_percent"], 29.5)
        self.assertEqual(row["percent_dunks_of_fga"], 0)
        self.assertEqual(row["pg_percent"], 100)
        self.assertEqual(row["team_summaries.o_rtg"], 118.5)
        self.assertEqual(row["team_summaries.pace"], 96.7)
        self.assertEqual(row["opponent_stats_per_game.opp_pts_per_game"], 111.7)

    def test_actual_player_comparison_row_keeps_every_applicable_source_column(self) -> None:
        contract = self._contract(2025)
        rows = selected_year_player_comparison_rows(contract)
        row = next(row for row in rows if row["player_id"] == "brunsja01" and row["team"] == "NYK")
        database_path = ensure_workbook_sqlite_database(contract.source_root)

        missing: list[str] = []
        for sheet in workbook_sqlite_sheet_names(database_path):
            prefix = sheet.lower().replace(" ", "_")
            for source_row in iter_workbook_sqlite_sheet_rows(database_path, sheet):
                if source_row.get("season") is not None and source_row.get("season") != 2025:
                    continue
                player_id = str(source_row.get("player_id") or "").strip()
                team = str(source_row.get("team") or source_row.get("tm") or "").strip()
                abbreviation = str(source_row.get("abbreviation") or "").strip()
                applies_to_brunson = player_id == "brunsja01" and (not team or team == "NYK")
                applies_to_knicks = not player_id and abbreviation == "NYK"
                if not applies_to_brunson and not applies_to_knicks:
                    continue
                for column, value in source_row.items():
                    if value is None:
                        continue
                    key = f"{prefix}.{column}"
                    if key not in row:
                        missing.append(key)

        self.assertEqual(missing, [])

    def test_proposal_contains_no_live_memory_address_or_direct_write_action(self) -> None:
        proposal = generate_player_proposal(_evidence())

        self.assertFalse(hasattr(proposal, "address"))
        self.assertFalse(hasattr(proposal, "record_addr"))
        for candidate in proposal.field_candidates:
            self.assertFalse(hasattr(candidate, "address"))
            self.assertFalse(hasattr(candidate, "record_addr"))

        import player_generator

        source = inspect.getsource(player_generator)
        for banned in ("GameMemory", "write_value", "write_entry_value", "write_and_readback", "subprocess", "clipboard"):
            self.assertNotIn(banned, source)

    def test_generator_runtime_uses_sqlite_database_not_workbook_reader(self) -> None:
        import player_evidence
        import player_generator
        import roster_evidence

        context = season_context_index(self._contract(2025))

        self.assertEqual(context.source_database_path.name, "NBA_DATA_Master.sqlite")
        self.assertTrue(context.source_database_path.is_file())
        for module in (player_evidence, player_generator, roster_evidence):
            module_source = inspect.getsource(module)
            self.assertNotIn("from workbook_reader", module_source)
            self.assertNotIn("NBA DATA Master.xlsx", module_source)


if __name__ == "__main__":
    unittest.main()
