from __future__ import annotations

from pathlib import Path

from nba2k_editor.mcp_server.adapters.locker_room_profile_store import LockerRoomProfileStore
from nba2k_editor.mcp_server.domain.locker_room_engine import LockerRoomEngine


class _LiveStub:
    def __init__(self, roster):
        self._roster = roster

    def load_team_snapshot(self, *, team_id: str, season: str):
        return {
            "team_id": team_id,
            "season": season,
            "roster": list(self._roster),
            "live": True,
        }


def _engine(tmp_path, roster):
    store = LockerRoomProfileStore(root_dir=tmp_path)
    return LockerRoomEngine(
        profile_store=store,
        live_snapshot_adapter=_LiveStub(roster),  # type: ignore[arg-type]
        default_seed=42,
        era_modifiers_path=Path(__file__).resolve().parents[2] / "data" / "ai" / "locker_room_era_modifiers.json",
    )


def _roster():
    return [
        {
            "player_id": 1,
            "name": "Alpha Star",
            "team": "LAL",
            "age": 29,
            "overall": 92,
            "potential": 94,
            "actual_minutes": 37,
            "actual_usage_rate": 0.35,
        },
        {
            "player_id": 2,
            "name": "Co-Star",
            "team": "LAL",
            "age": 27,
            "overall": 89,
            "potential": 90,
            "actual_minutes": 35,
            "actual_usage_rate": 0.3,
        },
        {
            "player_id": 3,
            "name": "Rookie",
            "team": "LAL",
            "age": 20,
            "overall": 75,
            "potential": 88,
            "actual_minutes": 18,
            "actual_usage_rate": 0.17,
        },
    ]


def test_locker_room_generation_is_seed_deterministic(tmp_path):
    engine = _engine(tmp_path, _roster())
    one = engine.get_or_refresh_state(
        profile_id="deterministic",
        team_id="LAL_1998",
        season="1998-99",
        era="1990s",
        seed=77,
        recent_record="6-4",
        team_underperforming=False,
    )
    two = engine.get_or_refresh_state(
        profile_id="deterministic",
        team_id="LAL_1998",
        season="1998-99",
        era="1990s",
        seed=77,
        recent_record="6-4",
        team_underperforming=False,
    )
    assert one["personalities"] == two["personalities"]


def test_chemistry_bounds_and_effect_markers(tmp_path):
    engine = _engine(tmp_path, _roster())
    state = engine.get_or_refresh_state(
        profile_id="chem",
        team_id="LAL_1998",
        season="1998-99",
        era="1990s",
        seed=12,
        recent_record="8-2",
        team_underperforming=False,
    )
    chemistry = engine.calculate_team_chemistry(state=state, recent_record="8-2", team_underperforming=False)
    assert 0.0 <= chemistry["chemistry_score"] <= 1.0
    breakdown = chemistry["breakdown"]
    assert breakdown["attributeBoostMultiplier"] in {1.0, 1.05}
    assert breakdown["clutchMultiplier"] in {1.0, 0.95}
    assert breakdown["injuryStressMultiplier"] in {1.0, 1.12}


def test_morale_formula_outputs_are_bounded(tmp_path):
    engine = _engine(tmp_path, _roster())
    state = engine.get_or_refresh_state(
        profile_id="morale",
        team_id="LAL_1998",
        season="1998-99",
        era="1990s",
        seed=23,
        recent_record="5-5",
        team_underperforming=True,
    )
    morale = engine.evaluate_morale(state=state, team_win_pct=0.5, chemistry_score=state["chemistry_score"], team_underperforming=True)
    assert 0.0 <= morale["average_morale"] <= 1.0
    assert all(0.0 <= row["morale"] <= 1.0 for row in morale["players"])


def test_conflict_queue_decays_and_escalates(tmp_path):
    engine = _engine(tmp_path, _roster())
    state = engine.get_or_refresh_state(
        profile_id="conflicts",
        team_id="LAL_1998",
        season="1998-99",
        era="1990s",
        seed=5,
        recent_record="4-6",
        team_underperforming=True,
    )
    first = engine.simulate_conflicts(state=state, trade_rumor_pressure=0.8, media_pressure=0.8)
    second = engine.simulate_conflicts(state=state, trade_rumor_pressure=0.8, media_pressure=0.8)
    assert first["events"]
    assert second["events"]
    assert second["conflict_risk"] >= 0.0
    for _ in range(10):
        engine.simulate_conflicts(state=state, trade_rumor_pressure=0.0, media_pressure=0.0)
    assert len(state["conflicts"]) <= len(second["events"])


def test_era_modifiers_shift_trade_demand(tmp_path):
    engine = _engine(tmp_path, _roster())
    personality = {
        "ego": 78.0,
        "loyalty": 35.0,
        "mediaSensitivity": 66.0,
        "competitiveness": 82.0,
        "professionalism": 52.0,
        "leadership": 48.0,
        "mentorship": 45.0,
        "temperament": 40.0,
    }
    modern = engine.compute_trade_demand_probability(
        personality=personality,
        morale=0.35,
        conflict_penalty=0.2,
        era="modern",
    )
    eighties = engine.compute_trade_demand_probability(
        personality=personality,
        morale=0.35,
        conflict_penalty=0.2,
        era="1980s",
    )
    assert modern > eighties

