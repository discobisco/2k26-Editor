from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from nba2k_editor.franchise.models import FantasyDraftStoredPick, FranchiseRecord


@dataclass(frozen=True)
class DraftPoolPlayer:
    player_label: str
    player_index: int
    source_team_index: int
    source_team_label: str
    source_slot: int
    source_slot_field: str
    draft_facts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DraftPosition:
    pick_number: int
    round_number: int
    team_index: int
    team_label: str


@dataclass(frozen=True)
class DraftPick:
    player_label: str
    player_index: int
    pick_number: int
    round_number: int
    team_index: int
    team_label: str


@dataclass(frozen=True)
class FantasyDraftBoard:
    mode: str
    source: str
    user_team_index: int
    current_position: DraftPosition
    pool_count: int
    available_count: int
    available_players: tuple[DraftPoolPlayer, ...]


def _base_team_items(model: Any, team_count: int) -> tuple[Any, ...]:
    teams = tuple(getattr(model, "loaded_items", {}).get("Teams", {}).values())
    return tuple(team for team in teams if 0 <= int(getattr(team, "index")) < team_count)


def team_labels_from_model(model: Any, *, team_count: int = 30) -> dict[int, str]:
    return {int(getattr(team, "index")): str(getattr(team, "label", f"Team {int(getattr(team, 'index'))}")) for team in _base_team_items(model, team_count)}


def _player_is_active(value: dict[str, Any]) -> bool:
    raw = value.get("raw_value")
    display = str(value.get("display_value") or "").strip().casefold()
    return raw in {1, True} or display == "yes"


def _is_a_z_placeholder(player: Any) -> bool:
    return " ".join(str(getattr(player, "label", "")).split()).casefold() == "a z"


_DRAFT_FACT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overall", ("OVERALL", "OVR", "OVERALLRATING")),
    ("potential", ("POTENTIAL",)),
    ("position", ("POSITION",)),
    ("height", ("HEIGHT",)),
    ("weight", ("WEIGHT",)),
    ("birth_year", ("BIRTHYEAR",)),
)


def _read_draft_fact(model: Any, player_index: int, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        entry = model._field_by_normalized_name("Players", name)
        if entry is None:
            continue
        value = model.read_entry_value(entry, index=player_index)
        display = str(value.get("display_value") or "").strip()
        if display:
            return display
        raw = value.get("raw_value")
        if raw is not None:
            return str(raw)
    return ""


def _draft_facts_for_player(model: Any, player_index: int) -> tuple[tuple[str, str], ...]:
    facts: list[tuple[str, str]] = []
    for key, candidates in _DRAFT_FACT_FIELDS:
        value = _read_draft_fact(model, player_index, candidates)
        if value:
            facts.append((key, value))
    return tuple(facts)


def build_active_player_draft_pool(model: Any, *, team_count: int = 30) -> tuple[DraftPoolPlayer, ...]:
    active_entry = model._field_by_normalized_name("Players", "ISACTIVE")
    if active_entry is None:
        raise KeyError("Players/ISACTIVE offset is not loaded")
    players: list[DraftPoolPlayer] = []
    for player in getattr(model, "loaded_items", {}).get("Players", {}).values():
        if _is_a_z_placeholder(player):
            continue
        player_index = int(getattr(player, "index"))
        value = model.read_entry_value(active_entry, index=player_index)
        if not _player_is_active(value):
            continue
        players.append(
            DraftPoolPlayer(
                player_label=str(getattr(player, "display_label", getattr(player, "label", ""))),
                player_index=player_index,
                source_team_index=-1,
                source_team_label="Is Active",
                source_slot=0,
                source_slot_field="ISACTIVE",
                draft_facts=_draft_facts_for_player(model, player_index),
            )
        )
    return tuple(players)


def league_team_indexes(record: FranchiseRecord) -> tuple[int, ...]:
    return tuple(sorted(int(team.team_index) for team in record.team_options))


def draft_position(
    pick_number: int,
    *,
    team_count: int = 30,
    user_team_index: int = 0,
    team_labels: dict[int, str] | None = None,
    team_order: Iterable[int] | None = None,
) -> DraftPosition:
    order = tuple(int(index) for index in team_order) if team_order is not None else tuple(range(int(team_count)))
    if not order:
        raise ValueError("league must include at least one team")
    zero_based_pick = max(0, int(pick_number) - 1)
    round_number = zero_based_pick // len(order) + 1
    round_pick_index = zero_based_pick % len(order)
    if round_number % 2 == 0:
        round_pick_index = len(order) - 1 - round_pick_index
    team_index = order[round_pick_index]
    labels = team_labels or {}
    return DraftPosition(int(pick_number), round_number, team_index, labels.get(team_index, f"Team {team_index}"))


def available_players(pool: Iterable[DraftPoolPlayer], drafted_picks: Iterable[DraftPick | FantasyDraftStoredPick]) -> tuple[DraftPoolPlayer, ...]:
    drafted = {int(pick.player_index) for pick in drafted_picks}
    return tuple(player for player in pool if player.player_index not in drafted)


def find_available_player(pool: Iterable[DraftPoolPlayer], drafted_picks: Iterable[DraftPick | FantasyDraftStoredPick], query: str) -> DraftPoolPlayer | None:
    available = available_players(pool, drafted_picks)
    query_text = str(query).casefold()
    for player in available:
        if query_text in player.player_label.casefold():
            return player
    return None


def find_available_player_by_index(pool: Iterable[DraftPoolPlayer], drafted_picks: Iterable[DraftPick | FantasyDraftStoredPick], player_index: int) -> DraftPoolPlayer | None:
    for player in available_players(pool, drafted_picks):
        if player.player_index == int(player_index):
            return player
    return None


def make_pick(player: DraftPoolPlayer, *, position: DraftPosition) -> DraftPick:
    return DraftPick(
        player_label=player.player_label,
        player_index=player.player_index,
        pick_number=position.pick_number,
        round_number=position.round_number,
        team_index=position.team_index,
        team_label=position.team_label,
    )


def stored_pick_from_player(
    player: DraftPoolPlayer,
    *,
    position: DraftPosition,
    picked_by: str,
) -> FantasyDraftStoredPick:
    return FantasyDraftStoredPick(
        pick_number=position.pick_number,
        round_number=position.round_number,
        team_index=position.team_index,
        team_label=position.team_label,
        player_index=player.player_index,
        player_label=player.player_label,
        source_team_index=player.source_team_index,
        source_slot=player.source_slot,
        source_slot_field=player.source_slot_field,
        picked_by=picked_by,
    )


def draft_turn_owner(position: DraftPosition, record: FranchiseRecord) -> str:
    if int(position.team_index) == int(record.setup.user_team_index):
        return "user"
    return "manual"


def build_fantasy_draft_board(
    model: Any,
    *,
    user_team_index: int = 0,
    team_count: int = 30,
    current_pick_number: int = 1,
    drafted_picks: Iterable[DraftPick | FantasyDraftStoredPick] = (),
) -> FantasyDraftBoard:
    labels = team_labels_from_model(model, team_count=team_count)
    position = draft_position(current_pick_number, team_count=team_count, user_team_index=user_team_index, team_labels=labels)
    pool = build_active_player_draft_pool(model, team_count=team_count)
    available = available_players(pool, drafted_picks)
    return FantasyDraftBoard(
        mode="read_only_fantasy_draft",
        source="Players/ISACTIVE active player offset",
        user_team_index=int(user_team_index),
        current_position=position,
        pool_count=len(pool),
        available_count=len(available),
        available_players=available,
    )


def build_fantasy_draft_markdown(
    model: Any,
    *,
    user_team_index: int = 0,
    team_count: int = 30,
    current_pick_number: int = 1,
    drafted_picks: Iterable[DraftPick | FantasyDraftStoredPick] = (),
) -> str:
    picks = tuple(drafted_picks)
    board = build_fantasy_draft_board(
        model,
        user_team_index=user_team_index,
        team_count=team_count,
        current_pick_number=current_pick_number,
        drafted_picks=picks,
    )
    lines = [
        "# Franchise Manager Fantasy Draft Room",
        f"Draft pool source: {board.source}",
        "Pool uses Players/ISACTIVE from the in-game draft page.",
        f"User team: Team {board.user_team_index}",
        f"Current pick: {board.current_position.pick_number}",
        f"On clock: Team {board.current_position.team_index} {board.current_position.team_label}",
        f"Pool count: {board.pool_count}",
        f"Available now: {board.available_count}",
        "",
        "## Drafted Picks",
    ]
    if not picks:
        lines.append("None")
    for pick in picks:
        lines.append(f"Pick {pick.pick_number} R{pick.round_number} Team {pick.team_index} {pick.team_label}: {pick.player_label}")
    lines.append("")
    lines.append("## Available Players")
    if not board.available_players:
        lines.append("None")
    for player in board.available_players[:25]:
        lines.append(f"{player.player_label} from Team {player.source_team_index} {player.source_slot_field}")
    return "\n".join(lines)
