from __future__ import annotations

from .models import (
    FranchiseTeam,
    ImportedSnapshot,
    ImportedDataKind,
    ReasonLog,
    TeamDirection,
    TeamEvaluation,
)


def evaluate_team_at_stop(
    *,
    season: int,
    team: FranchiseTeam,
    snapshots: tuple[ImportedSnapshot, ...],
) -> TeamEvaluation:
    """Deterministic first-pass owner/GM evaluation.

    This is not a game simulator. It consumes imported 2K data and creates
    explainable owner/GM intent for the user/commissioner.
    """

    standings = _latest_payload(snapshots, ImportedDataKind.STANDINGS)
    team_standings = dict((standings or {}).get(team.team_id, {}))
    wins = int(team_standings.get("wins", 0) or 0)
    losses = int(team_standings.get("losses", 0) or 0)
    win_pct = wins / max(1, wins + losses)

    owner_pressure = max(0, team.owner.championship_expectations - team.owner.patience)
    gm_aggression = team.gm.aggression + team.gm.trade_frequency

    if win_pct >= 0.600:
        direction = TeamDirection.CONTEND
        action = "championship_push"
        owner_report = f"Owner is satisfied with {wins}-{losses} and expects contention."
        gm_report = "GM should look for upgrades that do not damage the long-term core."
        recommended = ("Explore veteran upgrade", "Protect core players", "Monitor luxury/spending approval")
    elif win_pct <= 0.350 and team.owner.rebuild_tolerance >= 45:
        direction = TeamDirection.REBUILD
        action = "rebuild_evaluation"
        owner_report = f"Owner can tolerate a rebuild at {wins}-{losses}."
        gm_report = "GM should value picks, prospects, and expiring contracts over short-term wins."
        recommended = ("Shop veterans", "Prioritize draft assets", "Open prospect minutes")
    elif win_pct <= 0.350:
        direction = TeamDirection.TANK
        action = "ownership_concern"
        owner_report = f"Owner is unhappy with {wins}-{losses} and low rebuild tolerance."
        gm_report = "GM is under pressure to change team direction quickly."
        recommended = ("Emergency owner meeting", "Evaluate GM job security", "Seek immediate roster correction")
    elif owner_pressure > 30 or gm_aggression > 130:
        direction = TeamDirection.EVALUATE
        action = "trade_market_scan"
        owner_report = "Owner pressure or GM aggression is high enough to request an extra evaluation."
        gm_report = "GM should scan for trade targets before the next major stop."
        recommended = ("Scan trade targets", "Identify expendable contracts", "Review positional weaknesses")
    else:
        direction = TeamDirection.EVALUATE
        action = "continue_evaluation"
        owner_report = f"Owner is monitoring a {wins}-{losses} team without forcing a direction."
        gm_report = "GM should keep evaluating roster fit and player development."
        recommended = ("Continue evaluation", "Import injuries/minutes at next stop")

    message = _reason_message(team.team_id, direction, wins, losses, recommended[0])
    logs = (
        ReasonLog(
            season=season,
            team_id=team.team_id,
            actor="owner",
            message=owner_report,
            action=action,
            evidence={"wins": wins, "losses": losses, "win_pct": round(win_pct, 3)},
        ),
        ReasonLog(
            season=season,
            team_id=team.team_id,
            actor="gm",
            message=message,
            action=action,
            evidence={"gm_aggression": team.gm.aggression, "trade_frequency": team.gm.trade_frequency},
        ),
    )
    return TeamEvaluation(team.team_id, direction, owner_report, gm_report, recommended, logs)


def _latest_payload(snapshots: tuple[ImportedSnapshot, ...], kind: ImportedDataKind) -> dict | None:
    for snapshot in reversed(snapshots):
        if snapshot.kind == kind:
            return snapshot.payload
    return None


def _reason_message(team_id: str, direction: TeamDirection, wins: int, losses: int, first_action: str) -> str:
    return f"GM evaluates {team_id} at {wins}-{losses}, classifies direction as {direction.value}, and recommends: {first_action}."
