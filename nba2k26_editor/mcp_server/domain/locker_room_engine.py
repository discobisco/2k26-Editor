from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..adapters.locker_room_profile_store import LockerRoomProfileStore
from ..adapters.live_roster_snapshot_adapter import LiveRosterSnapshotAdapter
from ..errors import ServiceError


EraKey = str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _clamp_trait(value: float) -> float:
    return max(0.0, min(100.0, value))


class LockerRoomEngine:
    def __init__(
        self,
        *,
        profile_store: LockerRoomProfileStore,
        live_snapshot_adapter: LiveRosterSnapshotAdapter,
        default_seed: int,
        era_modifiers_path: Path,
    ) -> None:
        self._store = profile_store
        self._live = live_snapshot_adapter
        self._default_seed = default_seed
        self._era_modifiers = self._load_era_modifiers(era_modifiers_path)
        self._impact_cache: dict[str, dict[str, Any]] = {}
        self._impact_cache_order: list[str] = []
        self._impact_cache_max = 512

    @staticmethod
    def _load_era_modifiers(path: Path) -> dict[str, dict[str, float]]:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                normalized: dict[str, dict[str, float]] = {}
                for key, value in payload.items():
                    if isinstance(value, dict):
                        normalized[str(key).lower()] = {
                            str(k): float(v) for k, v in value.items() if isinstance(v, (int, float))
                        }
                if normalized:
                    return normalized
        return {
            "1980s": {
                "loyalty_bias": 0.18,
                "media_sensitivity_mult": 0.82,
                "ego_bias": -0.06,
                "trade_demand_mult": 0.72,
                "toughness_bias": 0.14,
            },
            "1990s": {
                "loyalty_bias": 0.12,
                "media_sensitivity_mult": 0.78,
                "ego_bias": -0.03,
                "trade_demand_mult": 0.85,
                "toughness_bias": 0.18,
            },
            "2000s": {
                "loyalty_bias": 0.01,
                "media_sensitivity_mult": 0.93,
                "ego_bias": 0.08,
                "trade_demand_mult": 1.02,
                "toughness_bias": 0.06,
            },
            "modern": {
                "loyalty_bias": -0.09,
                "media_sensitivity_mult": 1.15,
                "ego_bias": 0.12,
                "trade_demand_mult": 1.18,
                "toughness_bias": -0.03,
            },
        }

    @staticmethod
    def _normalize_era(era: str) -> str:
        raw = str(era or "modern").strip().lower()
        if raw in {"1980s", "1990s", "2000s", "modern"}:
            return raw
        if raw in {"80s", "1980"}:
            return "1980s"
        if raw in {"90s", "1990"}:
            return "1990s"
        if raw in {"00s", "2000"}:
            return "2000s"
        return "modern"

    @staticmethod
    def _parse_record(record: str) -> tuple[int, int]:
        raw = str(record or "0-0").strip()
        if "-" not in raw:
            return (0, 0)
        left, right = raw.split("-", 1)
        try:
            return (max(0, int(left)), max(0, int(right)))
        except Exception:
            return (0, 0)

    def _rng(self, seed: int | None) -> random.Random:
        return random.Random(int(seed if seed is not None else self._default_seed))

    def _era_mod(self, era: EraKey) -> dict[str, float]:
        return self._era_modifiers.get(self._normalize_era(era), self._era_modifiers["modern"])

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _competition_weight(self, personality: dict[str, float]) -> float:
        return _clamp(float(personality.get("competitiveness", 50.0)) / 100.0)

    def _baseline_personality(self, *, player: dict[str, Any], era: str, rng: random.Random) -> dict[str, float]:
        age = self._safe_float(player.get("age"), default=26.0)
        overall = self._safe_float(player.get("overall"), default=74.0)
        potential = self._safe_float(player.get("potential"), default=min(99.0, overall + 6.0))
        usage = _clamp(self._safe_float(player.get("actual_usage_rate"), default=0.2))
        minutes = _clamp(self._safe_float(player.get("actual_minutes"), default=24.0) / 48.0)
        age_n = _clamp(age / 40.0)
        overall_n = _clamp((overall - 40.0) / 59.0)
        potential_n = _clamp((potential - 40.0) / 59.0)
        era_mod = self._era_mod(era)

        leadership = _clamp(0.35 * overall_n + 0.35 * age_n + 0.2 * minutes + 0.1 * rng.random())
        ego = _clamp(0.55 * overall_n + 0.3 * usage + 0.15 * rng.random() + float(era_mod.get("ego_bias", 0.0)))
        loyalty = _clamp(
            0.45 * (1.0 - usage)
            + 0.25 * age_n
            + 0.2 * (1.0 - ego)
            + 0.1 * rng.random()
            + float(era_mod.get("loyalty_bias", 0.0))
        )
        competitiveness = _clamp(0.4 * overall_n + 0.35 * potential_n + 0.2 * usage + 0.05 * rng.random())
        professionalism = _clamp(0.45 * age_n + 0.35 * (1.0 - ego) + 0.2 * overall_n)
        media_sensitivity = _clamp(
            (0.5 * usage + 0.35 * ego + 0.15 * (1.0 - age_n)) * float(era_mod.get("media_sensitivity_mult", 1.0))
        )
        mentorship = _clamp(0.6 * age_n + 0.2 * professionalism + 0.2 * (1.0 - ego))
        temperament = _clamp(
            0.6 * professionalism
            + 0.2 * competitiveness
            + 0.2 * (1.0 - media_sensitivity)
            + float(era_mod.get("toughness_bias", 0.0))
        )
        return {
            "leadership": round(_clamp_trait(leadership * 100.0), 4),
            "ego": round(_clamp_trait(ego * 100.0), 4),
            "loyalty": round(_clamp_trait(loyalty * 100.0), 4),
            "competitiveness": round(_clamp_trait(competitiveness * 100.0), 4),
            "professionalism": round(_clamp_trait(professionalism * 100.0), 4),
            "mediaSensitivity": round(_clamp_trait(media_sensitivity * 100.0), 4),
            "mentorship": round(_clamp_trait(mentorship * 100.0), 4),
            "temperament": round(_clamp_trait(temperament * 100.0), 4),
        }

    @staticmethod
    def _merge_personality(existing: dict[str, float], generated: dict[str, float], *, keep_ratio: float) -> dict[str, float]:
        merged: dict[str, float] = {}
        for key, new_value in generated.items():
            old_value = float(existing.get(key, new_value))
            value = (old_value * keep_ratio) + (new_value * (1.0 - keep_ratio))
            merged[key] = round(_clamp_trait(value), 4)
        return merged

    @staticmethod
    def _infer_archetype(personality: dict[str, float], *, rng: random.Random) -> str:
        ego = float(personality.get("ego", 50.0))
        leadership = float(personality.get("leadership", 50.0))
        loyalty = float(personality.get("loyalty", 50.0))
        competitiveness = float(personality.get("competitiveness", 50.0))
        professionalism = float(personality.get("professionalism", 50.0))
        media = float(personality.get("mediaSensitivity", 50.0))
        mentorship = float(personality.get("mentorship", 50.0))
        temperament = float(personality.get("temperament", 50.0))
        if ego >= 88 and professionalism <= 33 and temperament <= 32 and rng.random() <= 0.18:
            return "locker_room_cancer"
        if leadership >= 74 and professionalism >= 68:
            return "leader"
        if competitiveness >= 80 and ego >= 72:
            return "alpha_competitor"
        if ego >= 76 and media >= 70 and professionalism <= 58:
            return "diva"
        if mentorship >= 74 and professionalism >= 62:
            return "mentor"
        if loyalty >= 74 and ego <= 62:
            return "loyalist"
        if loyalty <= 40 and ego >= 62:
            return "mercenary"
        return "alpha_competitor" if competitiveness >= 65 else "loyalist"

    @staticmethod
    def _hierarchy_for_player(player: dict[str, Any]) -> str:
        overall = float(player.get("overall", 74.0))
        age = float(player.get("age", 25.0))
        if overall >= 88:
            return "star"
        if overall >= 80:
            return "starter"
        if age <= 22:
            return "rookie"
        return "role_player"

    @staticmethod
    def _default_expectation(player: dict[str, Any]) -> dict[str, Any]:
        mins = float(player.get("actual_minutes", 24.0))
        usage = _clamp(float(player.get("actual_usage_rate", 0.2)))
        salary = float(player.get("salary", 0.0))
        if salary >= 35_000_000:
            contract_status = "max"
        elif salary <= 8_000_000 and player.get("age", 25) <= 24:
            contract_status = "rookie"
        elif int(player.get("contract_years", 2)) <= 1:
            contract_status = "expiring"
        else:
            contract_status = "teamFriendly"
        return {
            "expectedMinutes": round(mins, 3),
            "expectedUsageRate": round(usage, 6),
            "contractStatus": contract_status,
        }

    def _state_template(self, *, team_id: str, season: str, era: str) -> dict[str, Any]:
        return {
            "team_id": team_id,
            "season": season,
            "era": self._normalize_era(era),
            "tick": 0,
            "last_updated_at": _utc_now_iso(),
            "last_live_sync_at": None,
            "stale_live_data": False,
            "recent_record": "0-0",
            "roster": [],
            "personalities": {},
            "role_expectations": {},
            "hierarchy": {},
            "captain_player_id": None,
            "conflicts": [],
            "chemistry_score": 0.5,
            "chemistry_breakdown": {},
            "morale_map": {},
            "average_morale": 0.5,
            "morale_trend": "stable",
            "mentor_boost_active": False,
            "conflict_risk": 0.0,
            "stress_factor": 0.0,
            "dynasty_finals_appearances_last_6": 0,
            "early_exit_streak": 0,
        }

    def _load_state(self, *, profile_id: str, team_id: str, season: str, era: str) -> dict[str, Any] | None:
        state = self._store.get_team_state(profile_id=profile_id, team_id=team_id, season=season, era=era)
        if isinstance(state, dict):
            return state
        return None

    def _save_state(self, *, profile_id: str, team_id: str, season: str, era: str, state: dict[str, Any]) -> dict[str, Any]:
        state["team_id"] = team_id
        state["season"] = season
        state["era"] = self._normalize_era(era)
        state["last_updated_at"] = _utc_now_iso()
        return self._store.upsert_team_state(
            profile_id=profile_id,
            team_id=team_id,
            season=season,
            era=era,
            state=state,
        )

    def _live_sync(self, *, profile_id: str, team_id: str, season: str, era: str, seed: int | None) -> dict[str, Any]:
        state = self._load_state(profile_id=profile_id, team_id=team_id, season=season, era=era)
        if not isinstance(state, dict):
            state = self._state_template(team_id=team_id, season=season, era=era)
        try:
            snapshot = self._live.load_team_snapshot(team_id=team_id, season=season)
            generated = self.generate_or_update_personalities_from_live_snapshot(
                state=state,
                snapshot=snapshot,
                era=era,
                mode="auto",
                seed=seed,
                manual_updates=[],
                events={},
            )
            generated["last_live_sync_at"] = _utc_now_iso()
            generated["stale_live_data"] = False
            return self._save_state(profile_id=profile_id, team_id=team_id, season=season, era=era, state=generated)
        except ServiceError as exc:
            if isinstance(state, dict) and state.get("roster"):
                state["stale_live_data"] = True
                return self._save_state(profile_id=profile_id, team_id=team_id, season=season, era=era, state=state)
            raise ServiceError(
                status_code=503,
                code="LIVE_PROFILE_BOOTSTRAP_REQUIRED",
                message="Live profile bootstrap is required and no cached profile snapshot exists.",
                details={"reason": exc.code, "team_id": team_id, "season": season, "era": self._normalize_era(era)},
            ) from exc

    def generate_or_update_personalities_from_live_snapshot(
        self,
        *,
        state: dict[str, Any],
        snapshot: dict[str, Any],
        era: str,
        mode: str,
        seed: int | None,
        manual_updates: list[dict[str, Any]],
        events: dict[str, int | float],
    ) -> dict[str, Any]:
        rng = self._rng(seed)
        roster = list(snapshot.get("roster", []))
        personalities = state.get("personalities", {})
        if not isinstance(personalities, dict):
            personalities = {}
        role_expectations = state.get("role_expectations", {})
        if not isinstance(role_expectations, dict):
            role_expectations = {}
        hierarchy = state.get("hierarchy", {})
        if not isinstance(hierarchy, dict):
            hierarchy = {}
        manual_map: dict[str, dict[str, Any]] = {}
        for item in manual_updates:
            pid = str(item.get("player_id"))
            if pid:
                manual_map[pid] = item

        for player in roster:
            pid = str(int(player.get("player_id", 0)))
            base = self._baseline_personality(player=player, era=era, rng=rng)
            existing = personalities.get(pid, {})
            if mode == "manual" and pid in manual_map:
                manual = manual_map[pid]
                trait_payload = manual.get("personality") or {}
                if isinstance(trait_payload, dict):
                    merged = {k: round(_clamp_trait(float(trait_payload.get(k, base[k]))), 4) for k in base}
                else:
                    merged = base
                archetype = str(manual.get("archetype") or self._infer_archetype(merged, rng=rng))
            else:
                old_traits = existing.get("personality", {})
                if isinstance(old_traits, dict) and old_traits:
                    merged = self._merge_personality(old_traits, base, keep_ratio=0.55)
                else:
                    merged = base
                archetype = self._infer_archetype(merged, rng=rng)
            personalities[pid] = {
                "player_id": int(player.get("player_id", 0)),
                "name": str(player.get("name", f"Player {pid}")),
                "archetype": archetype,
                "personality": merged,
            }
            if pid not in role_expectations:
                role_expectations[pid] = self._default_expectation(player)
            hierarchy[pid] = str(player.get("hierarchy_role") or self._hierarchy_for_player(player))

        state["roster"] = roster
        state["personalities"] = personalities
        state["role_expectations"] = role_expectations
        state["hierarchy"] = hierarchy
        if roster:
            captain = max(
                roster,
                key=lambda p: (
                    float(
                        personalities.get(str(int(p.get("player_id", 0))), {}).get("personality", {}).get("leadership", 50.0)
                    ),
                    float(p.get("overall", 70.0)),
                ),
            )
            state["captain_player_id"] = int(captain.get("player_id", 0))
        else:
            state["captain_player_id"] = None
        self.apply_seasonal_event_drift(state=state, events=events)
        return state

    def apply_seasonal_event_drift(self, *, state: dict[str, Any], events: dict[str, int | float]) -> None:
        championships = int(events.get("championships", 0) or 0)
        mvps = int(events.get("mvp_awards", 0) or 0)
        disputes = int(events.get("contract_disputes", 0) or 0)
        criticism = int(events.get("public_criticism", 0) or 0)
        personalities = state.get("personalities", {})
        if not isinstance(personalities, dict):
            return
        for payload in personalities.values():
            traits = payload.get("personality", {})
            if not isinstance(traits, dict):
                continue
            traits["leadership"] = round(_clamp_trait(float(traits.get("leadership", 50.0)) + (championships * 2.0)), 4)
            traits["professionalism"] = round(
                _clamp_trait(float(traits.get("professionalism", 50.0)) + (championships * 1.5) - (disputes * 1.7)),
                4,
            )
            traits["loyalty"] = round(
                _clamp_trait(float(traits.get("loyalty", 50.0)) + (championships * 1.2) - (disputes * 2.2)),
                4,
            )
            traits["ego"] = round(
                _clamp_trait(float(traits.get("ego", 50.0)) + (mvps * 2.5) + (disputes * 1.4) + (criticism * 0.6)),
                4,
            )
            traits["mediaSensitivity"] = round(
                _clamp_trait(float(traits.get("mediaSensitivity", 50.0)) + (criticism * 2.2)),
                4,
            )
            traits["temperament"] = round(
                _clamp_trait(float(traits.get("temperament", 50.0)) - (criticism * 1.1) - (disputes * 0.8)),
                4,
            )

    def _role_satisfaction_score(
        self,
        *,
        player: dict[str, Any],
        expectation: dict[str, Any],
        team_underperforming: bool,
    ) -> float:
        actual_minutes = self._safe_float(player.get("actual_minutes"), default=24.0)
        expected_minutes = max(1e-6, self._safe_float(expectation.get("expectedMinutes"), default=actual_minutes))
        minute_ratio = actual_minutes / expected_minutes
        minute_score = _clamp(minute_ratio, 0.0, 1.2)
        minute_score = _clamp(0.4 + (minute_score - 0.4) * 0.9)

        actual_usage = _clamp(self._safe_float(player.get("actual_usage_rate"), default=0.2))
        expected_usage = max(1e-6, _clamp(self._safe_float(expectation.get("expectedUsageRate"), default=actual_usage)))
        usage_ratio = _clamp(actual_usage / expected_usage, 0.0, 1.25)
        usage_score = _clamp(0.35 + (usage_ratio - 0.35) * 0.9)

        status = str(expectation.get("contractStatus", "teamFriendly"))
        contract_pressure = {
            "rookie": 0.10,
            "expiring": 0.22,
            "max": 0.24,
            "teamFriendly": 0.05,
        }.get(status, 0.12)
        underperf_penalty = 0.1 if team_underperforming else 0.0
        value = (minute_score * 0.45) + (usage_score * 0.35) + ((1.0 - contract_pressure) * 0.20) - underperf_penalty
        return _clamp(value)

    def _active_conflict_penalty(self, *, state: dict[str, Any], player_id: int | None = None) -> float:
        conflicts = state.get("conflicts", [])
        if not isinstance(conflicts, list):
            return 0.0
        total = 0.0
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            if player_id is not None:
                affected = conflict.get("affected_player_ids", [])
                if isinstance(affected, list) and player_id not in affected:
                    continue
            total += float(conflict.get("severity", 0.0)) * 0.08
        return _clamp(total, 0.0, 0.45)

    def calculate_team_chemistry(
        self,
        *,
        state: dict[str, Any],
        recent_record: str,
        team_underperforming: bool,
    ) -> dict[str, Any]:
        roster = state.get("roster", [])
        personalities = state.get("personalities", {})
        role_expectations = state.get("role_expectations", {})
        hierarchy = state.get("hierarchy", {})
        if not isinstance(roster, list) or not roster:
            chemistry_score = 0.5
            breakdown = {
                "averageProfessionalism": 0.5,
                "leadershipImpact": 0.5,
                "roleSatisfactionScore": 0.5,
                "mentorImpact": 0.5,
                "egoConflictPenalty": 0.0,
                "attributeBoostMultiplier": 1.0,
                "clutchMultiplier": 1.0,
                "injuryStressMultiplier": 1.0,
            }
            state["chemistry_score"] = chemistry_score
            state["chemistry_breakdown"] = breakdown
            return {"chemistry_score": chemistry_score, "breakdown": breakdown}

        professional_values: list[float] = []
        leadership_values: list[float] = []
        mentor_values: list[float] = []
        role_scores: list[float] = []
        high_ego_stars = 0

        for player in roster:
            pid = str(int(player.get("player_id", 0)))
            personality_payload = personalities.get(pid, {})
            personality = personality_payload.get("personality", {})
            professionalism = _clamp(float(personality.get("professionalism", 50.0)) / 100.0)
            leadership = _clamp(float(personality.get("leadership", 50.0)) / 100.0)
            mentorship = _clamp(float(personality.get("mentorship", 50.0)) / 100.0)
            ego = _clamp(float(personality.get("ego", 50.0)) / 100.0)
            professional_values.append(professionalism)
            hierarchy_role = str(hierarchy.get(pid, "role_player"))
            role_weight = {"star": 1.0, "starter": 0.85, "role_player": 0.65, "rookie": 0.45}.get(hierarchy_role, 0.6)
            leadership_values.append(leadership * role_weight)
            if int(player.get("age", 25)) <= 23:
                mentor_values.append(mentorship * 0.7)
            else:
                mentor_values.append(mentorship)
            expectation = role_expectations.get(pid, self._default_expectation(player))
            role_scores.append(
                self._role_satisfaction_score(
                    player=player,
                    expectation=expectation if isinstance(expectation, dict) else self._default_expectation(player),
                    team_underperforming=team_underperforming,
                )
            )
            if ego >= 0.75 and float(player.get("overall", 70.0)) >= 85.0:
                high_ego_stars += 1

        avg_prof = sum(professional_values) / max(1, len(professional_values))
        leadership_impact = sum(leadership_values) / max(1, len(leadership_values))
        role_satisfaction_score = sum(role_scores) / max(1, len(role_scores))
        mentor_impact = sum(mentor_values) / max(1, len(mentor_values))
        ego_conflict_penalty = 0.0
        if high_ego_stars >= 2:
            ego_conflict_penalty += min(0.35, (high_ego_stars - 1) * 0.08)
        ego_conflict_penalty += self._active_conflict_penalty(state=state)
        ego_conflict_penalty = _clamp(ego_conflict_penalty)
        chemistry_score = _clamp(
            (avg_prof * 0.25)
            + (leadership_impact * 0.20)
            + (role_satisfaction_score * 0.20)
            + (mentor_impact * 0.15)
            - (ego_conflict_penalty * 0.20)
        )
        attribute_multiplier = 1.05 if chemistry_score > 0.8 else 1.0
        clutch_multiplier = 0.95 if chemistry_score < 0.4 else 1.0
        injury_stress_multiplier = 1.12 if chemistry_score < 0.3 else 1.0

        breakdown = {
            "averageProfessionalism": round(avg_prof, 6),
            "leadershipImpact": round(leadership_impact, 6),
            "roleSatisfactionScore": round(role_satisfaction_score, 6),
            "mentorImpact": round(mentor_impact, 6),
            "egoConflictPenalty": round(ego_conflict_penalty, 6),
            "attributeBoostMultiplier": round(attribute_multiplier, 6),
            "clutchMultiplier": round(clutch_multiplier, 6),
            "injuryStressMultiplier": round(injury_stress_multiplier, 6),
        }
        state["recent_record"] = recent_record
        state["chemistry_score"] = round(chemistry_score, 6)
        state["chemistry_breakdown"] = breakdown
        state["mentor_boost_active"] = bool(mentor_impact >= 0.62)
        state["stress_factor"] = round(max(0.0, injury_stress_multiplier - 1.0), 6)
        return {"chemistry_score": chemistry_score, "breakdown": breakdown}

    def compute_trade_demand_probability(
        self,
        *,
        personality: dict[str, float],
        morale: float,
        conflict_penalty: float,
        era: str,
    ) -> float:
        ego = _clamp(float(personality.get("ego", 50.0)) / 100.0)
        loyalty = _clamp(float(personality.get("loyalty", 50.0)) / 100.0)
        media = _clamp(float(personality.get("mediaSensitivity", 50.0)) / 100.0)
        base = (ego * 0.38) + ((1.0 - loyalty) * 0.34) + (media * 0.18) + (conflict_penalty * 0.25) + ((1.0 - morale) * 0.26)
        era_mult = float(self._era_mod(era).get("trade_demand_mult", 1.0))
        return _clamp(base * era_mult)

    def evaluate_morale(
        self,
        *,
        state: dict[str, Any],
        team_win_pct: float,
        chemistry_score: float | None = None,
        team_underperforming: bool = False,
    ) -> dict[str, Any]:
        roster = state.get("roster", [])
        personalities = state.get("personalities", {})
        role_expectations = state.get("role_expectations", {})
        if chemistry_score is None:
            chemistry_score = float(state.get("chemistry_score", 0.5))
        chemistry_score = _clamp(float(chemistry_score))
        team_win_pct = _clamp(float(team_win_pct))
        per_player: list[dict[str, Any]] = []
        morale_values: list[float] = []
        era = str(state.get("era", "modern"))
        for player in roster:
            pid = str(int(player.get("player_id", 0)))
            payload = personalities.get(pid, {})
            personality = payload.get("personality", {})
            expectation = role_expectations.get(pid, self._default_expectation(player))
            if not isinstance(expectation, dict):
                expectation = self._default_expectation(player)
            role_satisfaction = self._role_satisfaction_score(
                player=player,
                expectation=expectation,
                team_underperforming=team_underperforming,
            )
            contract_status = str(expectation.get("contractStatus", "teamFriendly"))
            contract_security = {"rookie": 0.65, "expiring": 0.35, "max": 0.8, "teamFriendly": 0.75}.get(contract_status, 0.6)
            conflict_penalty = self._active_conflict_penalty(state=state, player_id=int(player.get("player_id", 0)))
            competitiveness_weight = self._competition_weight(personality)
            morale = _clamp(
                (team_win_pct * competitiveness_weight)
                + (role_satisfaction * 0.3)
                + (contract_security * 0.2)
                + (chemistry_score * 0.2)
                - conflict_penalty
            )
            trade_demand = self.compute_trade_demand_probability(
                personality=personality,
                morale=morale,
                conflict_penalty=conflict_penalty,
                era=era,
            )
            shot_consistency = _clamp(0.9 + (morale * 0.2), 0.8, 1.1)
            injury_multiplier = _clamp(1.12 - (morale * 0.22) + float(state.get("stress_factor", 0.0)), 0.85, 1.35)
            development_multiplier = _clamp(0.85 + (morale * 0.35), 0.75, 1.25)
            morale_values.append(morale)
            per_player.append(
                {
                    "player_id": int(player.get("player_id", 0)),
                    "morale": round(morale, 6),
                    "roleSatisfaction": round(role_satisfaction, 6),
                    "conflictPenalty": round(conflict_penalty, 6),
                    "contractSecurity": round(contract_security, 6),
                    "shotConsistencyMultiplier": round(shot_consistency, 6),
                    "injuryProbabilityMultiplier": round(injury_multiplier, 6),
                    "developmentRateMultiplier": round(development_multiplier, 6),
                    "tradeDemandProbability": round(trade_demand, 6),
                }
            )

        average_morale = sum(morale_values) / max(1, len(morale_values))
        previous = float(state.get("average_morale", average_morale))
        if average_morale >= previous + 0.02:
            trend = "up"
        elif average_morale <= previous - 0.02:
            trend = "down"
        else:
            trend = "stable"
        state["average_morale"] = round(average_morale, 6)
        state["morale_trend"] = trend
        state["morale_map"] = {str(item["player_id"]): item["morale"] for item in per_player}
        return {"players": per_player, "average_morale": average_morale, "morale_trend": trend}

    def _decay_conflicts(self, *, state: dict[str, Any]) -> list[dict[str, Any]]:
        active: list[dict[str, Any]] = []
        for item in state.get("conflicts", []):
            if not isinstance(item, dict):
                continue
            ticks = int(item.get("remaining_ticks", 0)) - 1
            severity = float(item.get("severity", 0.0)) * 0.9
            if ticks <= 0 or severity <= 0.08:
                continue
            item["remaining_ticks"] = ticks
            item["severity"] = round(_clamp(severity), 6)
            active.append(item)
        return active

    def _enqueue_conflict(
        self,
        *,
        queue: list[dict[str, Any]],
        conflict_type: str,
        severity: float,
        affected_player_ids: list[int],
        narrative_tag: str | None,
        tick: int,
    ) -> None:
        for existing in queue:
            if str(existing.get("type")) != conflict_type:
                continue
            existing["severity"] = round(_clamp(float(existing.get("severity", 0.0)) + (severity * 0.5)), 6)
            existing["remaining_ticks"] = max(int(existing.get("remaining_ticks", 0)), int(4 + round(severity * 5)))
            if narrative_tag:
                existing["narrative_tag"] = narrative_tag
            return
        queue.append(
            {
                "type": conflict_type,
                "severity": round(_clamp(severity), 6),
                "remaining_ticks": int(4 + round(severity * 5)),
                "affected_player_ids": sorted(set(int(v) for v in affected_player_ids)),
                "narrative_tag": narrative_tag,
                "created_tick": tick,
            }
        )

    def simulate_conflicts(
        self,
        *,
        state: dict[str, Any],
        trade_rumor_pressure: float,
        media_pressure: float,
    ) -> dict[str, Any]:
        roster = state.get("roster", [])
        personalities = state.get("personalities", {})
        decayed = self._decay_conflicts(state=state)
        tick = int(state.get("tick", 0))
        state["tick"] = tick + 1

        star_candidates: list[dict[str, Any]] = []
        rookies: list[dict[str, Any]] = []
        veterans: list[dict[str, Any]] = []
        for player in roster:
            pid = str(int(player.get("player_id", 0)))
            traits = personalities.get(pid, {}).get("personality", {})
            ego = float(traits.get("ego", 50.0))
            if ego >= 76 and float(player.get("overall", 70.0)) >= 84:
                star_candidates.append({"pid": int(player.get("player_id", 0)), "ego": ego})
            if int(player.get("age", 25)) <= 22:
                rookies.append(player)
            else:
                veterans.append(player)

        if len(star_candidates) >= 2:
            top = sorted(star_candidates, key=lambda x: x["ego"], reverse=True)[:2]
            severity = _clamp(((top[0]["ego"] + top[1]["ego"]) / 200.0) * 0.85)
            self._enqueue_conflict(
                queue=decayed,
                conflict_type="ego_clash",
                severity=severity,
                affected_player_ids=[top[0]["pid"], top[1]["pid"]],
                narrative_tag="practice_fight" if severity >= 0.7 else None,
                tick=tick,
            )

        if rookies and veterans:
            best_rookie = max(rookies, key=lambda p: float(p.get("actual_minutes", 0.0)))
            top_veteran = max(veterans, key=lambda p: float(p.get("actual_minutes", 0.0)))
            if float(best_rookie.get("actual_minutes", 0.0)) >= float(top_veteran.get("actual_minutes", 0.0)) + 4.0:
                severity = _clamp(
                    (float(best_rookie.get("actual_minutes", 0.0)) - float(top_veteran.get("actual_minutes", 0.0))) / 16.0
                )
                self._enqueue_conflict(
                    queue=decayed,
                    conflict_type="rookie_minutes",
                    severity=severity,
                    affected_player_ids=[int(best_rookie.get("player_id", 0)), int(top_veteran.get("player_id", 0))],
                    narrative_tag=None,
                    tick=tick,
                )

        rumor = _clamp(trade_rumor_pressure)
        if rumor >= 0.45:
            affected = [int(p.get("player_id", 0)) for p in roster[: min(4, len(roster))]]
            self._enqueue_conflict(
                queue=decayed,
                conflict_type="trade_rumor",
                severity=_clamp(rumor * 0.8),
                affected_player_ids=affected,
                narrative_tag="public_drama" if rumor >= 0.75 else None,
                tick=tick,
            )

        media = _clamp(media_pressure)
        if media >= 0.5:
            affected = [int(p.get("player_id", 0)) for p in roster[: min(5, len(roster))]]
            self._enqueue_conflict(
                queue=decayed,
                conflict_type="media_pressure",
                severity=_clamp(media * 0.75),
                affected_player_ids=affected,
                narrative_tag="public_drama" if media >= 0.7 else None,
                tick=tick,
            )

        state["conflicts"] = decayed
        risk = _clamp(sum(float(item.get("severity", 0.0)) for item in decayed) / max(1, len(decayed)))
        state["conflict_risk"] = round(risk, 6)
        morale_penalty = _clamp(sum(float(item.get("severity", 0.0)) * 0.08 for item in decayed), 0.0, 0.45)
        return {"events": decayed, "conflict_risk": risk, "morale_penalty": morale_penalty}

    def apply_playoff_pressure(self, *, state: dict[str, Any], seed: int | None) -> dict[str, Any]:
        roster = state.get("roster", [])
        personalities = state.get("personalities", {})
        rng = self._rng(seed)
        per_player: list[dict[str, Any]] = []
        for player in roster:
            pid = str(int(player.get("player_id", 0)))
            payload = personalities.get(pid, {})
            archetype = str(payload.get("archetype", "loyalist"))
            traits = payload.get("personality", {})
            professionalism = _clamp(float(traits.get("professionalism", 50.0)) / 100.0)
            temperament = _clamp(float(traits.get("temperament", 50.0)) / 100.0)
            competitiveness = _clamp(float(traits.get("competitiveness", 50.0)) / 100.0)
            composure = _clamp((temperament * 0.4) + (professionalism * 0.35) + (competitiveness * 0.25))
            clutch = 0.0
            usage_eff = 0.0
            volatility = 0.0
            if archetype == "leader":
                clutch += 0.05
            elif archetype == "alpha_competitor":
                usage_eff += 0.04
            elif archetype == "diva":
                volatility += 0.06 + (rng.random() * 0.03)
            if professionalism >= 0.72:
                volatility -= 0.03
            if composure <= 0.42:
                clutch -= 0.05
                usage_eff -= 0.03
            per_player.append(
                {
                    "player_id": int(player.get("player_id", 0)),
                    "clutchAdjustment": round(clutch, 6),
                    "usageEfficiencyAdjustment": round(usage_eff, 6),
                    "volatilityAdjustment": round(volatility, 6),
                    "composure": round(composure, 6),
                }
            )
        return {"players": per_player}

    def get_or_refresh_state(
        self,
        *,
        profile_id: str,
        team_id: str,
        season: str,
        era: str,
        seed: int | None,
        recent_record: str,
        team_underperforming: bool,
    ) -> dict[str, Any]:
        state = self._live_sync(profile_id=profile_id, team_id=team_id, season=season, era=era, seed=seed)
        cache_key = (
            f"{profile_id}|{team_id}|{season}|{self._normalize_era(era)}|{recent_record}|"
            f"{int(team_underperforming)}|{int(state.get('tick', 0))}|{len(state.get('roster', []))}"
        )
        cached = self._impact_cache.get(cache_key)
        if isinstance(cached, dict):
            state["chemistry_score"] = cached["chemistry_score"]
            state["chemistry_breakdown"] = cached["chemistry_breakdown"]
            state["average_morale"] = cached["average_morale"]
            state["morale_trend"] = cached["morale_trend"]
            state["morale_map"] = dict(cached["morale_map"])
        else:
            chemistry = self.calculate_team_chemistry(
                state=state,
                recent_record=recent_record,
                team_underperforming=team_underperforming,
            )
            wins, losses = self._parse_record(recent_record)
            games = wins + losses
            win_pct = 0.5 if games <= 0 else _clamp(wins / games)
            morale = self.evaluate_morale(
                state=state,
                team_win_pct=win_pct,
                chemistry_score=float(chemistry["chemistry_score"]),
                team_underperforming=team_underperforming,
            )
            self._impact_cache[cache_key] = {
                "chemistry_score": state.get("chemistry_score"),
                "chemistry_breakdown": dict(state.get("chemistry_breakdown", {})),
                "average_morale": state.get("average_morale"),
                "morale_trend": state.get("morale_trend"),
                "morale_map": dict(state.get("morale_map", {})),
            }
            self._impact_cache_order.append(cache_key)
            while len(self._impact_cache_order) > self._impact_cache_max:
                stale = self._impact_cache_order.pop(0)
                self._impact_cache.pop(stale, None)
        return self._save_state(profile_id=profile_id, team_id=team_id, season=season, era=era, state=state)

    def status(
        self,
        *,
        profile_id: str,
        team_id: str,
        season: str,
        era: str,
        seed: int | None,
    ) -> dict[str, Any]:
        state = self._live_sync(profile_id=profile_id, team_id=team_id, season=season, era=era, seed=seed)
        recent_record = str(state.get("recent_record", "0-0"))
        chemistry = self.calculate_team_chemistry(state=state, recent_record=recent_record, team_underperforming=False)
        wins, losses = self._parse_record(recent_record)
        games = wins + losses
        win_pct = 0.5 if games <= 0 else _clamp(wins / games)
        morale = self.evaluate_morale(state=state, team_win_pct=win_pct, chemistry_score=float(chemistry["chemistry_score"]))
        conflict_risk = _clamp(float(state.get("conflict_risk", 0.0)))
        mentor_boost = bool(state.get("mentor_boost_active", False))
        self._save_state(profile_id=profile_id, team_id=team_id, season=season, era=era, state=state)
        return {
            "profile_id": profile_id,
            "team_id": team_id,
            "season": season,
            "era": self._normalize_era(era),
            "chemistry_score": round(float(state.get("chemistry_score", 0.5)), 6),
            "morale_trend": str(state.get("morale_trend", "stable")),
            "conflict_risk": round(conflict_risk, 6),
            "mentor_boost_active": mentor_boost,
            "status": state,
            "average_morale": round(float(morale["average_morale"]), 6),
            "stale_live_data": bool(state.get("stale_live_data", False)),
        }
