from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = REPO_ROOT / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget  # noqa: E402
from game_port import _generated_player_name_matches, _identity, apply_generated_player_proposal_to_game, import_generated_players_to_game, player_team_slot_indices_for_generated, validate_generated_player_names_match_offsets  # noqa: E402
from player_generator import generate_player_proposal_from_index, generate_player_proposals_from_index, season_context_index  # noqa: E402
from player_rules import _split_player_name  # noqa: E402
from source_data import GeneratorSourceInventory  # noqa: E402
from nba2k_editor.core.field_io import _display_to_raw_value, _raw_to_display_value  # noqa: E402
from nba2k_editor.models.data_model import EditorDataModel  # noqa: E402


class RecordingModel:
    def __init__(self) -> None:
        self.writes: list[tuple[int, str, str, str, object]] = []

    def write_entry_value(self, entry, *, index: int, value: object):
        self.writes.append((index, entry.section, entry.group, entry.normalized_name, value))
        return {"display_value": value}


class FastRecordingModel(RecordingModel):
    def __init__(self) -> None:
        super().__init__()
        self.fast_writes: list[tuple[int, str, str, str, object]] = []

    def write_entry_value_no_readback(self, entry, *, index: int, value: object):
        self.fast_writes.append((index, entry.section, entry.group, entry.normalized_name, value))


class LoadedRosterModel(RecordingModel):
    def __init__(self, teams: tuple[SimpleNamespace, ...], players: tuple[SimpleNamespace, ...]) -> None:
        super().__init__()
        self.loaded_items = {
            "Teams": {team.display_label: team for team in teams},
            "Players": {f"Player {player.index}": player for player in players},
        }


def _team(index: int, city: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        address=1000 + index,
        label=f"{city} {name}",
        display_label=f"{city} {name}",
        values={"CITYNAME": city, "TEAMNAME": name},
    )


def _player(index: int, team: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(index=index, team_address=team.address)


class PlayerGeneratorGamePortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = GeneratorSourceInventory.from_default().root

    def test_import_generated_players_to_game_requires_overwrite_contract(self) -> None:
        model = RecordingModel()
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()

        with self.assertRaisesRegex(ValueError, "overwrite_current_roster"):
            import_generated_players_to_game(model, contract, team_filter="GSW", player_indices=range(30))

        self.assertEqual([], model.writes)

    def test_import_generated_players_to_game_writes_generated_rows_through_model(self) -> None:
        model = RecordingModel()
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.OVERWRITE_CURRENT_ROSTER,
            roster_label="test live roster",
        ).validate()

        result = import_generated_players_to_game(model, contract, team_filter="GSW", player_indices=range(30))

        self.assertTrue(result.ok)
        self.assertEqual(2025, result.season)
        self.assertEqual("test live roster", result.roster_label)
        self.assertGreater(result.apply_result.generated_count, 0)
        self.assertGreater(result.apply_result.attempted, 0)
        self.assertEqual(result.apply_result.attempted, len(model.writes))
        self.assertIn("FIRSTNAME", {write[3] for write in model.writes})
        self.assertIn("3POINT", {write[3] for write in model.writes})
        self.assertTrue(any(write[3] == "UNDERBASKET" and write[4] in {"Cold", "Neutral", "Hot"} for write in model.writes))

    def test_import_generated_players_to_game_uses_no_readback_writer_when_available(self) -> None:
        model = FastRecordingModel()
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.OVERWRITE_CURRENT_ROSTER,
            roster_label="test live roster",
        ).validate()

        result = import_generated_players_to_game(model, contract, team_filter="GSW", player_indices=range(30))

        self.assertTrue(result.ok)
        self.assertGreater(result.apply_result.attempted, 0)
        self.assertEqual([], model.writes)
        self.assertEqual(result.apply_result.attempted, len(model.fast_writes))
        self.assertIn("FIRSTNAME", {write[3] for write in model.fast_writes})

    def test_import_generated_players_to_game_can_match_existing_loaded_player_names(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.OVERWRITE_CURRENT_ROSTER,
            roster_label="test live roster",
        ).validate()
        context = season_context_index(contract)
        batch = generate_player_proposals_from_index(context, team_filter="GSW")
        loaded_players = {
            f"[{100 + index}] {proposal.identity['player']}": SimpleNamespace(index=100 + index, label=str(proposal.identity["player"]))
            for index, proposal in enumerate(batch.proposals)
        }
        model = RecordingModel()
        setattr(model, "loaded_items", {"Players": loaded_players})

        result = import_generated_players_to_game(model, contract, team_filter="GSW", match_existing_player_names=True)

        self.assertTrue(result.ok)
        self.assertGreater(result.apply_result.applied_players, 0)
        self.assertEqual(100, model.writes[0][0])
        self.assertEqual({100 + index for index in range(result.apply_result.applied_players)}, {write[0] for write in model.writes})
        written_sections = {section for _index, section, _group, _name, _value in model.writes}
        self.assertLessEqual(written_sections, {"Attributes", "Tendencies"})
        self.assertIn("Attributes", written_sections)
        self.assertIn("Tendencies", written_sections)
        self.assertNotIn("Contract", written_sections)
        self.assertNotIn("Vitals", written_sections)

    def test_generated_name_matching_uses_2k_plain_ascii_names(self) -> None:
        self.assertEqual(_identity("Luka Doncic"), _identity("Luka Dončić"))
        self.assertEqual(_identity("Bogdan Bogdanovic"), _identity("Bogdan Bogdanović"))
        self.assertEqual(_identity("Moussa Diabate"), _identity("Moussa Diabaté"))
        self.assertEqual(_identity("Egor Demin"), _identity("Egor Dёmin"))
        self.assertEqual(_identity("Luka Doncic"), _identity("Luka DonÄ\x8diÄ‡"))
        self.assertEqual(_identity("Bogdan Bogdanovic"), _identity("Bogdan BogdanoviÄ‡"))
        self.assertEqual(_identity("Moussa Diabate"), _identity("Moussa DiabatÃ©"))

    def test_generated_name_matching_accepts_loaded_2k_name_variants_without_skipping(self) -> None:
        generated_names = (
            "Adama-Alpha Bal",
            "Mo Bamba",
            "Bogdan Bogdanović",
            "Bub Carrington",
            "Nic Claxton",
            "Walter Clayton",
            "Egor Dёmin",
            "Moussa Diabaté",
            "Rob Dillingham",
            "Luka Dončić",
        )
        loaded_names = (
            "Adama Bal",
            "Mohamed Bamba",
            "Bogdan Bogdanovic",
            "Bub Carrington",
            "Nicolas Claxton",
            "Walter Clayton Jr.",
            "Egor Demin",
            "Moussa Diabate",
            "Robert Dillingham",
            "Luka Doncic",
        )
        generated = tuple(SimpleNamespace(identity={"player": name}, player_id=name) for name in generated_names)
        loaded_players = {
            f"slot {index}": SimpleNamespace(index=index, label=name)
            for index, name in enumerate(loaded_names, start=200)
        }
        model = SimpleNamespace(loaded_items={"Players": loaded_players})

        matches = _generated_player_name_matches(model, generated)

        self.assertEqual(tuple(range(200, 210)), tuple(index for _proposal, index in matches))

    def test_generated_name_matching_does_not_drop_duplicate_loaded_names_like_stephen_curry(self) -> None:
        generated = (SimpleNamespace(identity={"player": "Stephen Curry"}, player_id="curryst01"),)
        model = SimpleNamespace(
            loaded_items={
                "Players": {
                    "slot 30": SimpleNamespace(index=30, label="Stephen Curry II"),
                    "slot 900": SimpleNamespace(index=900, label="Stephen Curry"),
                }
            }
        )

        matches = _generated_player_name_matches(model, generated)

        self.assertEqual((30,), tuple(index for _proposal, index in matches))

    def test_generated_name_matching_accepts_alex_sarr_loaded_as_alexandre_sarr(self) -> None:
        generated = (SimpleNamespace(identity={"player": "Alex Sarr"}, player_id="sarral01"),)
        model = SimpleNamespace(loaded_items={"Players": {"slot 33": SimpleNamespace(index=33, label="Alexandre Sarr")}})

        matches = _generated_player_name_matches(model, generated)

        self.assertEqual((33,), tuple(index for _proposal, index in matches))

    def test_generated_name_matching_accepts_bub_carrington_loaded_as_carlton_carrington(self) -> None:
        generated = (SimpleNamespace(identity={"player": "Bub Carrington"}, player_id="carrica01"),)
        model = SimpleNamespace(loaded_items={"Players": {"slot 34": SimpleNamespace(index=34, label="Carlton Carrington")}})

        matches = _generated_player_name_matches(model, generated)

        self.assertEqual((34,), tuple(index for _proposal, index in matches))

    def test_generated_name_matching_accepts_current_2k_name_variants(self) -> None:
        generated = (
            SimpleNamespace(identity={"player": "Svi Mykhailiuk"}, player_id="mykhasv01"),
            SimpleNamespace(identity={"player": "Jonas ValanÄ\x8diÅ«nas"}, player_id="valanjo01"),
            SimpleNamespace(identity={"player": "Bones Hyland"}, player_id="hylanbo01"),
        )
        model = SimpleNamespace(
            loaded_items={
                "Players": {
                    "slot 41": SimpleNamespace(index=41, label="Sviatoslav Mykhailiuk"),
                    "slot 42": SimpleNamespace(index=42, label="Jonas Valanciunas"),
                    "slot 43": SimpleNamespace(index=43, label="Nah'Shon Hyland"),
                }
            }
        )

        matches = _generated_player_name_matches(model, generated)

        self.assertEqual((41, 42, 43), tuple(index for _proposal, index in matches))

    def test_generated_profile_names_are_ascii_for_2k_import(self) -> None:
        self.assertEqual(("Luka", "Doncic"), _split_player_name("Luka Dončić"))
        self.assertEqual(("Egor", "Demin"), _split_player_name("Egor Dёmin"))

    def test_multi_team_player_uses_game_split_team_context_not_primary_team_only(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)

        evidence = context.evidence_for(player_id="WIGGIAN01", team="GSW")

        shares = {share["team"]: share["stat_share"] for share in evidence.source_context["multi_team_stat_shares"]}
        self.assertAlmostEqual(43 / 60, shares["GSW"], places=6)
        self.assertAlmostEqual(17 / 60, shares["MIA"], places=6)
        self.assertEqual("2TM", evidence.totals["source_team"])
        self.assertEqual(60, evidence.totals["g"])
        expected_team_pts = ((113.8 * 43) + (110.6 * 17)) / 60
        self.assertAlmostEqual(expected_team_pts, evidence.team_stats_per_game["pts_per_game"], places=4)
        self.assertAlmostEqual(expected_team_pts, evidence.source_context["team_stats_per_game.pts_per_game"], places=4)
        self.assertNotAlmostEqual(113.8, evidence.team_stats_per_game["pts_per_game"], places=4)

    def test_generated_player_names_match_active_2k26_offset_names(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        proposal = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")

        validate_generated_player_names_match_offsets((proposal,), field_index=context.field_index)
        inactive = []
        for candidate in proposal.field_candidates:
            entry = context.field_index[candidate.field_key]
            version_keys = tuple((entry.field.get("versions") or {}).keys())
            if not any("2K26" in str(version_key).split(",") for version_key in version_keys):
                inactive.append(candidate.field_key)

        self.assertEqual([], inactive)
        self.assertNotIn("Vitals/HEIGHT", proposal.by_field_key())
        self.assertIn("Tendencies/SHOT", proposal.by_field_key())
        self.assertIsInstance(proposal.by_field_key()["Tendencies/SHOT"].display_value, int)
        shot_entry = context.field_index["Tendencies/SHOT"]
        shot_payload = shot_entry.field["versions"]["2K26"]
        self.assertEqual(1047, shot_payload["address"])
        self.assertEqual("0x417", shot_payload["hex"])
        self.assertEqual(0, shot_payload["startBit"])
        self.assertEqual(7, shot_payload["length"])
        self.assertEqual("Integer", shot_payload["type"])
        self.assertNotIn("Attributes/ACCELERATION", proposal.by_field_key())

    def test_generated_profile_birth_fields_encode_current_age_in_birth_year_slot_without_custom_age(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        proposal = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")
        fields = proposal.by_field_key()

        self.assertEqual(14, fields["Vitals/BIRTHDAY"].display_value)
        self.assertEqual(3, fields["Vitals/BIRTHMONTH"].display_value)
        self.assertEqual(1936, fields["Vitals/BIRTHYEAR"].display_value)
        self.assertEqual("profile_birth_year_current_age_value_v1", fields["Vitals/BIRTHYEAR"].source_rule)
        self.assertNotIn("Vitals/CUSTOMAGEATSETYEAR", fields)
        self.assertEqual(183, fields["Vitals/WINGSPANCM"].display_value)
        self.assertEqual("profile_wingspan_metric_height_minus_two_v1", fields["Vitals/WINGSPANCM"].source_rule)

        model = RecordingModel()
        result = apply_generated_player_proposal_to_game(model, proposal, player_index=0, field_index=context.field_index)
        self.assertTrue(result.ok)
        writes_by_name = {write[3]: write[4] for write in model.writes}
        self.assertEqual(1936, writes_by_name["BIRTHYEAR"])
        self.assertNotIn("CUSTOMAGEATSETYEAR", writes_by_name)

    def test_1947_birth_year_slot_uses_age_on_october_1946(self) -> None:
        contract = GeneratorInputContract(
            season=1947,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)

        miasek = generate_player_proposal_from_index(context, player_id="miasest01", team="DTF").by_field_key()
        self.assertEqual(19, miasek["Vitals/BIRTHDAY"].display_value)
        self.assertEqual(9, miasek["Vitals/BIRTHMONTH"].display_value)
        self.assertEqual(1923, miasek["Vitals/BIRTHYEAR"].display_value)
        self.assertNotIn("Vitals/CUSTOMAGEATSETYEAR", miasek)

        feerick = generate_player_proposal_from_index(context, player_id="feeribo01", team="WSC").by_field_key()
        self.assertEqual(2, feerick["Vitals/BIRTHDAY"].display_value)
        self.assertEqual(1, feerick["Vitals/BIRTHMONTH"].display_value)
        self.assertEqual(1926, feerick["Vitals/BIRTHYEAR"].display_value)
        self.assertNotIn("Vitals/CUSTOMAGEATSETYEAR", feerick)

    def test_generated_player_play_types_use_2k26_dropdown_labels(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        curry = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")
        jokic = generate_player_proposal_from_index(context, player_id="jokicni01", team="DEN")
        gobert = generate_player_proposal_from_index(context, player_id="goberru01", team="MIN")

        play_fields = ("Vitals/PLAYTYPE1", "Vitals/PLAYTYPE2", "Vitals/PLAYTYPE3", "Vitals/PLAYTYPE4")
        play_options = set(context.field_index["Vitals/PLAYTYPE1"].field["versions"]["2K26"]["dropdown"])
        self.assertEqual(
            ("P&R Ball Handler", "3 PT", "None", "None"),
            tuple(curry.by_field_key()[field].display_value for field in play_fields),
        )
        self.assertEqual(
            ("3 PT", "Handoff Passer", "Post Up High", "P&R Roll Man"),
            tuple(jokic.by_field_key()[field].display_value for field in play_fields),
        )
        self.assertEqual(
            ("P&R Roll Man", "Cutter", "Post Up Low", "None"),
            tuple(gobert.by_field_key()[field].display_value for field in play_fields),
        )
        for proposal in (curry, jokic, gobert):
            for field in play_fields:
                candidate = proposal.by_field_key()[field]
                self.assertIn(candidate.display_value, play_options)
                self.assertEqual("profile_player_play_types_v1", candidate.source_rule)
                self.assertNotIn("positional", " ".join(candidate.evidence_keys).lower())

    def test_generated_player_play_types_cover_position_archetype_breakdowns(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        play_fields = ("Vitals/PLAYTYPE1", "Vitals/PLAYTYPE2", "Vitals/PLAYTYPE3", "Vitals/PLAYTYPE4")
        cases = {
            "high-volume scoring PG": ("curryst01", "GSW", {"P&R Ball Handler", "3 PT"}),
            "high-volume spot-up SG": ("hieldbu01", "GSW", {"3 PT", "Handoff Receiver"}),
            "playmaking wing": ("butleji01", "GSW", {"P&R Ball Handler", "P&R Wing", "Handoff Passer"}),
            "playmaking forward": ("greendr01", "GSW", {"P&R Wing", "Handoff Passer"}),
            "rim-running center": ("goberru01", "MIN", {"P&R Roll Man", "Cutter"}),
        }
        for case_name, (player_id, team, required_plays) in cases.items():
            proposal = generate_player_proposal_from_index(context, player_id=player_id, team=team)
            self.assertTrue(all("role_key" not in key for key in proposal.identity))
            play_values = set(proposal.by_field_key()[field].display_value for field in play_fields)
            self.assertTrue(required_plays.issubset(play_values), (case_name, play_values))

    def test_generated_low_role_players_leave_unused_play_types_as_none(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        spencer = generate_player_proposal_from_index(context, player_id="spencpa01", team="GSW")
        post = generate_player_proposal_from_index(context, player_id="postqu01", team="GSW")
        norris = generate_player_proposal_from_index(context, player_id="norrimi01", team="BOS")

        play_fields = ("Vitals/PLAYTYPE1", "Vitals/PLAYTYPE2", "Vitals/PLAYTYPE3", "Vitals/PLAYTYPE4")
        self.assertEqual(
            ("P&R Ball Handler", "None", "None", "None"),
            tuple(spencer.by_field_key()[field].display_value for field in play_fields),
        )
        self.assertEqual(
            ("3 PT", "None", "None", "None"),
            tuple(post.by_field_key()[field].display_value for field in play_fields),
        )
        self.assertEqual(
            ("Cutter", "None", "None", "None"),
            tuple(norris.by_field_key()[field].display_value for field in play_fields),
        )
        for proposal in (spencer, post, norris):
            self.assertNotEqual("None", proposal.by_field_key()["Vitals/PLAYTYPE1"].display_value)

    def test_generated_speed_with_ball_is_capped_by_speed(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        proposal = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")
        fields = proposal.by_field_key()

        self.assertLessEqual(fields["Attributes/SPEEDWITHBALL"].display_value, fields["Attributes/SPEED"].display_value)
        self.assertEqual("attribute_speedwithball_v1", fields["Attributes/SPEEDWITHBALL"].source_rule)
        self.assertIn("per_game.ast_per_game", fields["Attributes/SPEEDWITHBALL"].evidence_keys)
        self.assertIn("team_summary.pace", fields["Attributes/SPEEDWITHBALL"].evidence_keys)

    def test_generated_hot_zones_use_dropdown_labels_and_model_exposes_options(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        proposal = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")
        fields = proposal.by_field_key()

        self.assertIn(fields["Tendencies/UNDERBASKET"].display_value, {"Cold", "Neutral", "Hot"})
        self.assertIn(fields["Tendencies/3CENTER"].display_value, {"Cold", "Neutral", "Hot"})

        model = EditorDataModel(target_executable="NBA2K26.exe")
        entry = context.field_index["Tendencies/UNDERBASKET"]
        payload = model._field_version_payload(entry.field)
        self.assertEqual(["Cold", "Neutral", "Hot"], model.field_options(entry))
        self.assertEqual("Hot", _raw_to_display_value(entry.section, entry.field, payload, 2))
        self.assertEqual(2, _display_to_raw_value(entry.section, entry.field, payload, "Hot"))

    def test_team_slot_routing_matches_city_then_name_for_two_team_cities(self) -> None:
        clippers = _team(0, "Los Angeles", "Clippers")
        lakers = _team(1, "Los Angeles", "Lakers")
        model = LoadedRosterModel(
            teams=(clippers, lakers),
            players=(_player(10, clippers), _player(11, lakers)),
        )
        generated = (
            SimpleNamespace(team="LAL", identity={"team": "LAL", "team_name": "Los Angeles Lakers"}, field_candidates=()),
            SimpleNamespace(team="LAC", identity={"team": "LAC", "team_name": "Los Angeles Clippers"}, field_candidates=()),
        )

        self.assertEqual((11, 10), player_team_slot_indices_for_generated(model, generated))

    def test_team_slot_routing_ignores_teams_after_base_30_for_historical_city_match(self) -> None:
        sixers = _team(0, "Philadelphia", "76ers")
        pistons = _team(1, "Detroit", "Pistons")
        filler_teams = tuple(_team(index, f"City {index}", f"Team {index}") for index in range(2, 30))
        all_time_pistons = _team(30, "Detroit", "All-Time Pistons")
        model = LoadedRosterModel(
            teams=(sixers, pistons, *filler_teams, all_time_pistons),
            players=(_player(700, sixers), _player(701, pistons), _player(702, all_time_pistons)),
        )
        generated = (
            SimpleNamespace(team="DTF", identity={"team": "DTF", "team_name": "Detroit Falcons", "team_abbrev": "DTF"}, field_candidates=()),
        )

        self.assertEqual((701,), player_team_slot_indices_for_generated(model, generated))

    def test_team_slot_routing_uses_current_team_slots_not_global_player_order(self) -> None:
        atlanta = _team(0, "Atlanta", "Hawks")
        boston = _team(1, "Boston", "Celtics")
        chicago = _team(2, "Chicago", "Bulls")
        model = LoadedRosterModel(
            teams=(atlanta, boston, chicago),
            players=(
                _player(30, boston),
                _player(31, atlanta),
                _player(32, chicago),
                _player(33, atlanta),
            ),
        )
        generated = (
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=()),
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=()),
            SimpleNamespace(team="CHI", identity={"team": "CHI", "team_name": "Chicago Bulls"}, field_candidates=()),
        )

        self.assertEqual((31, 33, 32), player_team_slot_indices_for_generated(model, generated))

    def test_team_slot_routing_skips_city_name_matched_team_during_fallback(self) -> None:
        team_zero = _team(0, "City Zero", "Zeroes")
        knicks = _team(1, "New York", "Knicks")
        team_two = _team(2, "City Two", "Twos")
        model = LoadedRosterModel(
            teams=(team_zero, knicks, team_two),
            players=(_player(20, team_zero), _player(21, knicks), _player(22, team_two)),
        )
        generated = (
            SimpleNamespace(team="NYK", identity={"team": "NYK", "team_name": "New York Knicks"}, field_candidates=()),
            SimpleNamespace(team="NO_MATCH", identity={"team": "NO_MATCH", "team_name": "No Match"}, field_candidates=()),
        )

        self.assertEqual((21, 20), player_team_slot_indices_for_generated(model, generated))

    def test_team_slot_routing_does_not_skip_when_primary_team_slots_are_short(self) -> None:
        hawks = _team(0, "Atlanta", "Hawks")
        knicks = _team(1, "New York", "Knicks")
        sonics = _team(2, "Seattle", "SuperSonics")
        model = LoadedRosterModel(
            teams=(hawks, knicks, sonics),
            players=(
                *(SimpleNamespace(index=index, team_address=hawks.address) for index in range(14)),
                _player(50, knicks),
                _player(100, sonics),
                _player(101, sonics),
            ),
        )
        hawks_imports = tuple(
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=())
            for _index in range(16)
        )
        knicks_import = SimpleNamespace(team="NYK", identity={"team": "NYK", "team_name": "New York Knicks"}, field_candidates=())

        self.assertEqual((*range(14), 100, 101, 50), player_team_slot_indices_for_generated(model, (*hawks_imports, knicks_import)))

    def test_team_slot_routing_spills_players_after_15_to_unused_team_not_assigned_team(self) -> None:
        hawks = _team(0, "Atlanta", "Hawks")
        knicks = _team(1, "New York", "Knicks")
        sonics = _team(2, "Seattle", "SuperSonics")
        model = LoadedRosterModel(
            teams=(hawks, knicks, sonics),
            players=(
                *(SimpleNamespace(index=index, team_address=hawks.address) for index in range(17)),
                _player(50, knicks),
                _player(100, sonics),
                _player(101, sonics),
            ),
        )
        hawks_imports = tuple(
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=())
            for _index in range(17)
        )
        knicks_import = SimpleNamespace(team="NYK", identity={"team": "NYK", "team_name": "New York Knicks"}, field_candidates=())

        self.assertEqual((*range(15), 100, 101, 50), player_team_slot_indices_for_generated(model, (*hawks_imports, knicks_import)))

    def test_multi_team_overflow_uses_underfilled_alternate_team_before_spillover(self) -> None:
        hawks = _team(0, "Atlanta", "Hawks")
        knicks = _team(1, "New York", "Knicks")
        sonics = _team(2, "Seattle", "SuperSonics")
        model = LoadedRosterModel(
            teams=(hawks, knicks, sonics),
            players=(
                *(SimpleNamespace(index=index, team_address=hawks.address) for index in range(17)),
                _player(50, knicks),
                _player(51, knicks),
                _player(100, sonics),
                _player(101, sonics),
            ),
        )
        hawks_imports_before_xtm = tuple(
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=())
            for _index in range(14)
        )
        hawks_imports_after_xtm = tuple(
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=())
            for _index in range(2)
        )
        xtm_hawk = SimpleNamespace(
            team="ATL",
            identity={
                "team": "ATL",
                "team_name": "Atlanta Hawks",
                "multi_team_stat_shares": (
                    {"team": "ATL", "games": 40, "minutes": 900, "stat_share": 0.75},
                    {"team": "NYK", "games": 10, "minutes": 300, "stat_share": 0.25},
                ),
            },
            field_candidates=(),
        )
        knicks_import = SimpleNamespace(team="NYK", identity={"team": "NYK", "team_name": "New York Knicks"}, field_candidates=())

        self.assertEqual(
            (*range(14), 50, 14, 100, 51),
            player_team_slot_indices_for_generated(
                model,
                (*hawks_imports_before_xtm, xtm_hawk, *hawks_imports_after_xtm, knicks_import),
            ),
        )

    def test_all_base_teams_assigned_spills_after_15_to_overflow_teams_not_more_hawks(self) -> None:
        base_teams = (_team(0, "Atlanta", "Hawks"),) + tuple(_team(index, f"City {index}", f"Team {index}") for index in range(1, 30))
        overflow = _team(30, "Overflow", "Roster")
        model = LoadedRosterModel(
            teams=(*base_teams, overflow),
            players=(
                *(SimpleNamespace(index=index, team_address=base_teams[0].address) for index in range(20)),
                *(SimpleNamespace(index=team.index * 100, team_address=team.address) for team in base_teams[1:]),
                _player(3000, overflow),
                _player(3001, overflow),
            ),
        )
        atl_imports = tuple(
            SimpleNamespace(team="ATL", identity={"team": "ATL", "team_name": "Atlanta Hawks"}, field_candidates=())
            for _index in range(17)
        )
        other_base_imports = tuple(
            SimpleNamespace(team=f"T{index:02d}", identity={"team": f"T{index:02d}", "team_name": base_teams[index].display_label}, field_candidates=())
            for index in range(1, 30)
        )

        indices = player_team_slot_indices_for_generated(model, (*atl_imports, *other_base_imports))

        self.assertEqual((*range(15), 3000, 3001), indices[:17])

    def test_name_validator_rejects_generated_fields_not_in_offsets(self) -> None:
        generated = SimpleNamespace(
            identity={"player": "Bad Name"},
            field_candidates=(
                SimpleNamespace(
                    field_key="Attributes/OLDNAME",
                    section="Attributes",
                    group="Offense",
                    normalized_name="OLDNAME",
                    display_name="Old Name",
                    display_value=50,
                ),
            ),
        )

        with self.assertRaisesRegex(KeyError, "not in offsets_players.json"):
            validate_generated_player_names_match_offsets((generated,))


if __name__ == "__main__":
    unittest.main()
