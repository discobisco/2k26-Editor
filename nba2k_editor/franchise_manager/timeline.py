from __future__ import annotations

from .models import SeasonPhase, StopPoint, StopPriority


OPENING_NIGHT_MONTH_DAY = "11-01"
MIDSEASON_MONTH_DAY = "01-15"
TRADE_DEADLINE_MONTH_DAY = "02-15"
END_SEASON_MONTH_DAY = "04-15"
PLAYOFFS_MONTH_DAY = "04-20"
FINALS_MONTH_DAY = "06-15"
DRAFT_MONTH_DAY = "06-25"
FREE_AGENCY_MONTH_DAY = "07-01"
TRAINING_CAMP_MONTH_DAY = "10-01"


def season_start_year(season: int) -> int:
    if isinstance(season, bool) or not isinstance(season, int) or season < 1947:
        raise ValueError("season must be a season-ending year >= 1947")
    return season - 1


def season_label(season: int) -> str:
    start = season_start_year(season)
    return f"{start}-{str(season)[-2:]}"


def date_label_for_stop(season: int, month_day: str) -> str:
    start = season_start_year(season)
    month = int(month_day.split("-", 1)[0])
    year = start if month >= 10 else season
    return f"{year}-{month_day}"


def default_stop_points(season: int) -> tuple[StopPoint, ...]:
    """Stop points where the user should return from NBA 2K simulation.

    The manager does not simulate games. These stops only tell the user when to
    pause 2K, import data, and let franchise AI evaluate the league.
    """

    return (
        StopPoint(season, SeasonPhase.REGULAR_SEASON, date_label_for_stop(season, OPENING_NIGHT_MONTH_DAY), "Opening Night", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.REGULAR_SEASON, "after 10 games", "10 Game Evaluation", StopPriority.RECOMMENDED),
        StopPoint(season, SeasonPhase.REGULAR_SEASON, "after 20 games", "20 Game Evaluation", StopPriority.RECOMMENDED),
        StopPoint(season, SeasonPhase.REGULAR_SEASON, date_label_for_stop(season, MIDSEASON_MONTH_DAY), "Midseason Evaluation", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.REGULAR_SEASON, date_label_for_stop(season, TRADE_DEADLINE_MONTH_DAY), "Trade Deadline Evaluation", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.REGULAR_SEASON, date_label_for_stop(season, END_SEASON_MONTH_DAY), "End of Season Import", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.PLAYOFFS, date_label_for_stop(season, PLAYOFFS_MONTH_DAY), "Playoff Results Import", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.CHAMPIONSHIP, date_label_for_stop(season, FINALS_MONTH_DAY), "Finals Result Import", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.DRAFT, date_label_for_stop(season, DRAFT_MONTH_DAY), "Draft", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.FREE_AGENCY, date_label_for_stop(season, FREE_AGENCY_MONTH_DAY), "Free Agency", StopPriority.REQUIRED),
        StopPoint(season, SeasonPhase.TRAINING_CAMP, date_label_for_stop(season, TRAINING_CAMP_MONTH_DAY), "Training Camp", StopPriority.REQUIRED),
    )


def dynamic_stop_request(season: int, *, reason: str, priority: StopPriority, team_id: str | None = None, date_label: str = "user-defined") -> StopPoint:
    if not reason.strip():
        raise ValueError("dynamic stop reason is required")
    return StopPoint(
        season=season,
        phase=SeasonPhase.REGULAR_SEASON,
        date_label=date_label,
        reason=reason.strip(),
        priority=priority,
        team_id=team_id,
    )
