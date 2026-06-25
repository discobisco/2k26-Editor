from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import FranchiseTeam, ImportedDataKind, ImportedSnapshot


@dataclass(frozen=True)
class TeamRecord:
    wins: int = 0
    losses: int = 0
    expected_wins: int | None = None
    expected_losses: int | None = None
    market_pressure: int = 50

    @property
    def games_played(self) -> int:
        return self.wins + self.losses

    @property
    def win_pct(self) -> float:
        return self.wins / max(1, self.games_played)

    @property
    def expected_win_pct(self) -> float:
        if self.expected_wins is None:
            return self.win_pct
        expected_games = (self.expected_wins or 0) + (self.expected_losses or max(0, self.games_played - self.expected_wins))
        return self.expected_wins / max(1, expected_games)


@dataclass(frozen=True)
class FranchisePlayer:
    player_id: str
    team_id: str
    name: str = ""
    age: float | None = None
    overall: float | None = None
    potential: float | None = None
    minutes: float | None = None
    morale: float | None = None
    development: float | None = None
    position: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerContract:
    player_id: str
    team_id: str
    salary: int = 0
    years_remaining: int = 0
    expiring: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DraftPickAsset:
    team_id: str
    year: int
    round: int = 1
    protection: str = ""
    incoming_from: str = ""
    outgoing_to: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InjuryStatus:
    player_id: str
    team_id: str
    severity: int = 0
    games_remaining: int = 0
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapSheet:
    payroll: int = 0
    salary_cap: int = 0
    luxury_tax_line: int = 0
    cap_space: int = 0
    luxury_tax_overage: int = 0
    expiring_salary: int = 0

    @property
    def is_tax_team(self) -> bool:
        return self.luxury_tax_line > 0 and self.payroll > self.luxury_tax_line


@dataclass(frozen=True)
class RosterProfile:
    players: tuple[FranchisePlayer, ...] = ()
    average_age: float = 0.0
    star_quality: float = 0.0
    top_two_quality: float = 0.0
    average_morale: float = 50.0
    development_score: float = 0.0
    young_core_count: int = 0
    veteran_core_count: int = 0


@dataclass(frozen=True)
class InjurySummary:
    active_count: int = 0
    total_severity: int = 0
    rotation_games_lost: int = 0
    descriptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DraftAssetSummary:
    future_firsts: int = 0
    protected_firsts: int = 0
    second_rounders: int = 0
    outgoing_firsts: int = 0
    pick_value: float = 0.0


@dataclass(frozen=True)
class RecentTransactionSummary:
    count: int = 0
    descriptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class TeamContext:
    season: int
    team: FranchiseTeam
    record: TeamRecord
    roster: RosterProfile
    cap: CapSheet
    draft_assets: DraftAssetSummary
    injuries: InjurySummary
    recent_transactions: RecentTransactionSummary
    contracts: tuple[PlayerContract, ...] = ()
    draft_picks: tuple[DraftPickAsset, ...] = ()
    injury_statuses: tuple[InjuryStatus, ...] = ()


def build_team_context(*, season: int, team: FranchiseTeam, snapshots: tuple[ImportedSnapshot, ...]) -> TeamContext:
    standings = _latest_payload(snapshots, ImportedDataKind.STANDINGS)
    team_stats = _latest_payload(snapshots, ImportedDataKind.TEAM_STATS)
    player_stats = _latest_payload(snapshots, ImportedDataKind.PLAYER_STATS)
    injuries_payload = _latest_payload(snapshots, ImportedDataKind.INJURIES)
    contracts_payload = _latest_payload(snapshots, ImportedDataKind.CONTRACTS)
    trades_payload = _latest_payload(snapshots, ImportedDataKind.TRADES)

    record = _team_record(team.team_id, standings or {}, team_stats or {})
    players = tuple(_team_players(team.team_id, player_stats or {}))
    contracts = tuple(_team_contracts(team.team_id, contracts_payload or {}))
    draft_picks = tuple(_team_draft_picks(team.team_id, contracts_payload or {}))
    injuries = tuple(_team_injuries(team.team_id, injuries_payload or {}))
    transactions = tuple(_team_transactions(team.team_id, trades_payload or {}))
    return TeamContext(
        season=season,
        team=team,
        record=record,
        roster=_roster_profile(players),
        cap=_cap_sheet(contracts_payload or {}, contracts),
        draft_assets=_draft_asset_summary(draft_picks),
        injuries=_injury_summary(injuries),
        recent_transactions=RecentTransactionSummary(len(transactions), tuple(transactions[-5:])),
        contracts=contracts,
        draft_picks=draft_picks,
        injury_statuses=injuries,
    )


def latest_payload(snapshots: tuple[ImportedSnapshot, ...], kind: ImportedDataKind) -> dict | None:
    return _latest_payload(snapshots, kind)


def _latest_payload(snapshots: tuple[ImportedSnapshot, ...], kind: ImportedDataKind) -> dict | None:
    for snapshot in reversed(snapshots):
        if snapshot.kind == kind:
            return snapshot.payload
    return None


def _team_record(team_id: str, standings: dict[str, Any], team_stats: dict[str, Any]) -> TeamRecord:
    row = _team_mapping(team_id, standings)
    wins = _int_from(row, "wins", "W", default=0)
    losses = _int_from(row, "losses", "L", default=0)
    expected_wins = _optional_int_from(row, "expected_wins", "xwins", "pythagorean_wins")
    expected_losses = _optional_int_from(row, "expected_losses", "xlosses", "pythagorean_losses")
    if expected_wins is None:
        expected_wins, expected_losses = _pythagorean_expected_record(team_id, team_stats, wins + losses)
    market_pressure = _bounded_int(_number_from(row, "market_pressure", "fan_pressure", default=50), 0, 100)
    return TeamRecord(wins=wins, losses=losses, expected_wins=expected_wins, expected_losses=expected_losses, market_pressure=market_pressure)


def _team_players(team_id: str, payload: dict[str, Any]) -> Iterable[FranchisePlayer]:
    for row in _rows_from_payload(payload, "players"):
        row_team = str(row.get("team_id") or row.get("team") or row.get("CURRENTTEAM") or "").strip()
        if row_team and row_team != team_id:
            continue
        player_id = str(row.get("player_id") or row.get("id") or row.get("name") or "").strip()
        if not player_id:
            continue
        yield FranchisePlayer(
            player_id=player_id,
            team_id=row_team or team_id,
            name=str(row.get("name") or row.get("player") or player_id),
            age=_optional_number_from(row, "age", "AGE"),
            overall=_optional_number_from(row, "overall", "ovr", "OVERALL", "rating"),
            potential=_optional_number_from(row, "potential", "pot", "POTENTIAL"),
            minutes=_optional_number_from(row, "minutes", "mpg", "MINUTES", "minutes_per_game"),
            morale=_optional_number_from(row, "morale", "MORALE"),
            development=_optional_number_from(row, "development", "development_score", "progression"),
            position=str(row.get("position") or row.get("pos") or ""),
            raw=dict(row),
        )


def _team_contracts(team_id: str, payload: dict[str, Any]) -> Iterable[PlayerContract]:
    for row in _rows_from_payload(payload, "contracts"):
        row_team = str(row.get("team_id") or row.get("team") or "").strip()
        if row_team and row_team != team_id:
            continue
        player_id = str(row.get("player_id") or row.get("id") or row.get("name") or "").strip()
        if not player_id:
            continue
        salary = _int_from(row, "salary", "current_salary", "amount", default=0)
        years = _int_from(row, "years_remaining", "years", default=0)
        expiring = bool(row.get("expiring")) or years == 1
        yield PlayerContract(player_id, row_team or team_id, salary, years, expiring, dict(row))


def _team_draft_picks(team_id: str, payload: dict[str, Any]) -> Iterable[DraftPickAsset]:
    for row in _rows_from_payload(payload, "draft_picks"):
        owner = str(row.get("team_id") or row.get("owner_team") or row.get("team") or "").strip()
        outgoing_to = str(row.get("outgoing_to") or "").strip()
        if owner and owner != team_id:
            continue
        if outgoing_to and owner == team_id:
            # Pick is owned now but already owed elsewhere; keep it as outgoing risk evidence.
            pass
        yield DraftPickAsset(
            team_id=owner or team_id,
            year=_int_from(row, "year", "season", default=0),
            round=_int_from(row, "round", "draft_round", default=1),
            protection=str(row.get("protection") or row.get("protections") or ""),
            incoming_from=str(row.get("incoming_from") or row.get("from_team") or ""),
            outgoing_to=outgoing_to,
            raw=dict(row),
        )


def _team_injuries(team_id: str, payload: dict[str, Any]) -> Iterable[InjuryStatus]:
    for row in _rows_from_payload(payload, "injuries"):
        row_team = str(row.get("team_id") or row.get("team") or "").strip()
        if row_team and row_team != team_id:
            continue
        player_id = str(row.get("player_id") or row.get("id") or row.get("name") or "").strip()
        if not player_id:
            continue
        yield InjuryStatus(
            player_id=player_id,
            team_id=row_team or team_id,
            severity=_bounded_int(_number_from(row, "severity", "injury_severity", default=0), 0, 100),
            games_remaining=_int_from(row, "games_remaining", "games_out", default=0),
            description=str(row.get("description") or row.get("injury") or ""),
            raw=dict(row),
        )


def _team_transactions(team_id: str, payload: dict[str, Any]) -> Iterable[str]:
    for row in _rows_from_payload(payload, "transactions"):
        row_team = str(row.get("team_id") or row.get("team") or "").strip()
        teams = {str(value).strip() for value in row.get("teams", ())} if isinstance(row.get("teams"), (list, tuple, set)) else set()
        if row_team and row_team != team_id and team_id not in teams:
            continue
        text = str(row.get("description") or row.get("message") or row.get("type") or "transaction").strip()
        if text:
            yield text


def _roster_profile(players: tuple[FranchisePlayer, ...]) -> RosterProfile:
    ages = [player.age for player in players if player.age is not None]
    ratings = sorted((player.overall for player in players if player.overall is not None), reverse=True)
    morale = [player.morale for player in players if player.morale is not None]
    development = [player.development for player in players if player.development is not None]
    young_core = sum(1 for player in players if (player.age or 99) <= 24 and (player.potential or player.overall or 0) >= 78)
    veteran_core = sum(1 for player in players if (player.age or 0) >= 31 and (player.overall or 0) >= 78)
    return RosterProfile(
        players=players,
        average_age=round(sum(ages) / max(1, len(ages)), 2) if ages else 0.0,
        star_quality=round(ratings[0], 2) if ratings else 0.0,
        top_two_quality=round(sum(ratings[:2]) / max(1, min(2, len(ratings))), 2) if ratings else 0.0,
        average_morale=round(sum(morale) / max(1, len(morale)), 2) if morale else 50.0,
        development_score=round(sum(development), 2) if development else 0.0,
        young_core_count=young_core,
        veteran_core_count=veteran_core,
    )


def _cap_sheet(payload: dict[str, Any], contracts: tuple[PlayerContract, ...]) -> CapSheet:
    payroll = sum(contract.salary for contract in contracts)
    if not payroll:
        payroll = _int_from(payload, "payroll", "team_payroll", default=0)
    salary_cap = _int_from(payload, "salary_cap", "cap", default=0)
    luxury_tax_line = _int_from(payload, "luxury_tax_line", "tax_line", "luxury_tax", default=0)
    expiring_salary = sum(contract.salary for contract in contracts if contract.expiring)
    return CapSheet(
        payroll=payroll,
        salary_cap=salary_cap,
        luxury_tax_line=luxury_tax_line,
        cap_space=salary_cap - payroll if salary_cap else 0,
        luxury_tax_overage=max(0, payroll - luxury_tax_line) if luxury_tax_line else 0,
        expiring_salary=expiring_salary,
    )


def _draft_asset_summary(picks: tuple[DraftPickAsset, ...]) -> DraftAssetSummary:
    future_firsts = sum(1 for pick in picks if pick.round == 1 and not pick.outgoing_to)
    protected = sum(1 for pick in picks if pick.round == 1 and pick.protection and not pick.outgoing_to)
    seconds = sum(1 for pick in picks if pick.round == 2 and not pick.outgoing_to)
    outgoing = sum(1 for pick in picks if pick.round == 1 and pick.outgoing_to)
    pick_value = future_firsts * 10 + protected * 3 + seconds * 2 - outgoing * 8
    return DraftAssetSummary(future_firsts, protected, seconds, outgoing, float(pick_value))


def _injury_summary(injuries: tuple[InjuryStatus, ...]) -> InjurySummary:
    active = tuple(injury for injury in injuries if injury.severity > 0 or injury.games_remaining > 0)
    return InjurySummary(
        active_count=len(active),
        total_severity=sum(injury.severity for injury in active),
        rotation_games_lost=sum(injury.games_remaining for injury in active),
        descriptions=tuple(injury.description for injury in active if injury.description),
    )


def _pythagorean_expected_record(team_id: str, team_stats: dict[str, Any], games: int) -> tuple[int | None, int | None]:
    row = _team_mapping(team_id, team_stats)
    points = _optional_number_from(row, "points", "POINTS")
    allowed = _optional_number_from(row, "points_allowed", "PA")
    if points is None or allowed is None or points <= 0 or allowed <= 0 or games <= 0:
        return None, None
    pct = (points**14) / max(1.0, points**14 + allowed**14)
    wins = int(round(pct * games))
    return wins, max(0, games - wins)


def _team_mapping(team_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get(team_id)
    if isinstance(value, dict):
        return dict(value)
    for row in _rows_from_payload(payload, "teams"):
        row_team = str(row.get("team_id") or row.get("team") or row.get("label") or "").strip()
        if row_team == team_id:
            return dict(row)
    return {}


def _rows_from_payload(payload: dict[str, Any], key: str) -> Iterable[dict[str, Any]]:
    value = payload.get(key)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield dict(item)
        return
    if isinstance(value, dict):
        for item_key, item in value.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("player_id" if key == "players" else "team_id", item_key)
                yield row
        return
    if key not in payload:
        for item_key, item in payload.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("team_id", item_key)
                yield row


def _int_from(mapping: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = _number_from(mapping, *keys, default=default)
    return int(round(value))


def _optional_int_from(mapping: dict[str, Any], *keys: str) -> int | None:
    value = _optional_number_from(mapping, *keys)
    return None if value is None else int(round(value))


def _optional_number_from(mapping: dict[str, Any], *keys: str) -> float | None:
    normalized = {_normalize(key): value for key, value in mapping.items()}
    for key in keys:
        value = normalized.get(_normalize(key))
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return None


def _number_from(mapping: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    value = _optional_number_from(mapping, *keys)
    return default if value is None else value


def _bounded_int(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def _normalize(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())
