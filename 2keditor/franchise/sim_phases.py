from __future__ import annotations

from dataclasses import dataclass

from nba2k_editor.franchise.models import LEAGUE_MODE_COLLEGE, LEAGUE_MODE_NBA, normalize_league_mode


STATUS_READY = "ready"
STATUS_WAITING_FOR_GAME_ADVANCE = "waiting_for_game_advance"


@dataclass(frozen=True)
class FranchisePhase:
    key: str
    label: str


FRANCHISE_PHASES = (
    FranchisePhase("season", "Season"),
    FranchisePhase("playoffs", "Playoffs"),
    FranchisePhase("player_retirements", "Player Retirements"),
    FranchisePhase("staff_retirements", "Staff Retirements"),
    FranchisePhase("hall_of_fame_inductees", "Hall of Fame Inductees"),
    FranchisePhase("league_meetings", "League Meetings"),
    FranchisePhase("staff_signing", "Staff Signing"),
    FranchisePhase("draft_lottery", "Draft Lottery"),
    FranchisePhase("draft_combine", "Draft Combine"),
    FranchisePhase("pre_draft_workouts", "Pre-Draft Workouts"),
    FranchisePhase("expansion_draft", "Expansion Draft"),
    FranchisePhase("nba_draft", "NBA Draft"),
    FranchisePhase("rookie_signing", "Rookie Signing"),
    FranchisePhase("team_player_options", "Team/Player Options"),
    FranchisePhase("qualifying_offers", "Qualifying Offers"),
    FranchisePhase("free_agency", "Free Agency"),
    FranchisePhase("player_progression", "Player Progression"),
    FranchisePhase("nba_summer_league", "NBA Summer League"),
    FranchisePhase("fiba_friendlies", "FIBA Friendlies"),
    FranchisePhase("all_star_city_selection", "All-Star City Selection"),
    FranchisePhase("2k_hoops_summit", "2K Hoops Summit"),
    FranchisePhase("advance_to_next_season", "Advance to Next Season"),
)

COLLEGE_PHASES = (
    FranchisePhase("preseason", "Preseason"),
    FranchisePhase("regular_season", "Regular Season"),
    FranchisePhase("postseason", "Postseason"),
    FranchisePhase("roster_departures", "Roster Departures"),
    FranchisePhase("player_transfers", "Player Transfers"),
    FranchisePhase("recruiting", "Recruiting"),
    FranchisePhase("player_development", "Player Development"),
    FranchisePhase("advance_to_next_season", "Advance to Next Season"),
)


def initial_phase(league_mode: str = LEAGUE_MODE_NBA) -> str:
    return "preseason" if normalize_league_mode(league_mode) == LEAGUE_MODE_COLLEGE else "season"


def franchise_phase_sequence(
    *,
    expansion_draft_required: bool,
    league_mode: str = LEAGUE_MODE_NBA,
) -> tuple[FranchisePhase, ...]:
    mode = normalize_league_mode(league_mode)
    if mode == LEAGUE_MODE_COLLEGE:
        if expansion_draft_required:
            raise ValueError("College mode does not use the NBA Expansion Draft phase.")
        return COLLEGE_PHASES
    if expansion_draft_required:
        return FRANCHISE_PHASES
    return tuple(phase for phase in FRANCHISE_PHASES if phase.key != "expansion_draft")


def phase_label(phase_key: str, *, league_mode: str = LEAGUE_MODE_NBA) -> str:
    mode = normalize_league_mode(league_mode)
    phases = COLLEGE_PHASES if mode == LEAGUE_MODE_COLLEGE else FRANCHISE_PHASES
    phase_by_key = {phase.key: phase for phase in phases}
    try:
        return phase_by_key[str(phase_key)].label
    except KeyError as exc:
        raise ValueError(f"unknown {mode} phase: {phase_key}") from exc


def next_franchise_phase(
    current_phase: str,
    *,
    expansion_draft_required: bool,
    league_mode: str = LEAGUE_MODE_NBA,
) -> tuple[str, int]:
    sequence = franchise_phase_sequence(
        expansion_draft_required=expansion_draft_required,
        league_mode=league_mode,
    )
    keys = tuple(phase.key for phase in sequence)
    try:
        index = keys.index(str(current_phase))
    except ValueError as exc:
        raise ValueError(f"phase {current_phase!r} is not active in this franchise cycle") from exc
    if index + 1 < len(keys):
        return keys[index + 1], 0
    return initial_phase(league_mode), 1


def game_advance_instruction(
    next_phase: str,
    *,
    next_sim_year: int,
    league_mode: str = LEAGUE_MODE_NBA,
) -> str:
    return (
        f"Progress NBA 2K to {phase_label(next_phase, league_mode=league_mode)} for true sim year {int(next_sim_year)}, "
        "then select that observed phase and click Sync and Resume."
    )
