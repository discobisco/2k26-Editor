from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.models.schema import FieldEntry
from player_generator import GeneratedPlayerProposal, authored_player_field_index


@dataclass(frozen=True)
class GamePortFieldResult:
    field_key: str
    section: str
    group: str
    normalized_name: str
    display_name: str
    attempted_value: int | str
    readback_value: Any
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class GamePortResult:
    player_index: int
    attempted: int
    succeeded: int
    failed: int
    fields: tuple[GamePortFieldResult, ...]

    @property
    def ok(self) -> bool:
        return self.failed == 0


@dataclass(frozen=True)
class GamePortBatchResult:
    player_results: tuple[GamePortResult, ...]
    generated_count: int
    target_count: int

    @property
    def attempted(self) -> int:
        return sum(result.attempted for result in self.player_results)

    @property
    def succeeded(self) -> int:
        return sum(result.succeeded for result in self.player_results)

    @property
    def failed(self) -> int:
        return sum(result.failed for result in self.player_results)

    @property
    def applied_players(self) -> int:
        return len(self.player_results)

    @property
    def unapplied_generated(self) -> int:
        return max(0, self.generated_count - self.applied_players)

    @property
    def unused_targets(self) -> int:
        return max(0, self.target_count - self.applied_players)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.unapplied_generated == 0


def apply_generated_player_proposal_to_game(
    model: Any,
    proposal: GeneratedPlayerProposal,
    *,
    player_index: int,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
) -> GamePortResult:
    return apply_generated_rows_to_game(
        model,
        proposal.field_candidates,
        player_index=player_index,
        field_index=field_index,
        offsets_path=offsets_path,
        stop_on_error=stop_on_error,
    )


def apply_generated_players_to_game(
    model: Any,
    generated_players: Iterable[Any],
    *,
    player_indices: Iterable[int],
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
) -> GamePortBatchResult:
    generated_tuple = tuple(generated_players)
    index_tuple = tuple(int(index) for index in player_indices)
    player_results: list[GamePortResult] = []
    for generated, player_index in zip(generated_tuple, index_tuple):
        player_results.append(
            apply_generated_rows_to_game(
                model,
                _generated_rows(generated),
                player_index=player_index,
                field_index=field_index,
                offsets_path=offsets_path,
                stop_on_error=stop_on_error,
            )
        )
    return GamePortBatchResult(
        player_results=tuple(player_results),
        generated_count=len(generated_tuple),
        target_count=len(index_tuple),
    )


def apply_generated_rows_to_game(
    model: Any,
    rows: Iterable[Any],
    *,
    player_index: int,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
) -> GamePortResult:
    if player_index < 0:
        raise ValueError("player_index must be >= 0")
    authored = field_index if field_index is not None else authored_player_field_index(offsets_path)
    results: list[GamePortFieldResult] = []
    for row in rows:
        field_key = str(getattr(row, "field_key", "")).strip()
        attempted_value = _row_value(row)
        try:
            entry = authored[field_key]
            readback = model.write_entry_value(entry, index=player_index, value=attempted_value)
            results.append(
                GamePortFieldResult(
                    field_key=field_key,
                    section=entry.section,
                    group=entry.group,
                    normalized_name=entry.normalized_name,
                    display_name=entry.display_name,
                    attempted_value=attempted_value,
                    readback_value=readback.get("display_value") if isinstance(readback, dict) else readback,
                    ok=True,
                )
            )
        except Exception as exc:
            fallback_entry = authored.get(field_key)
            results.append(
                GamePortFieldResult(
                    field_key=field_key,
                    section=fallback_entry.section if fallback_entry is not None else str(getattr(row, "section", "")),
                    group=fallback_entry.group if fallback_entry is not None else str(getattr(row, "group", "")),
                    normalized_name=fallback_entry.normalized_name if fallback_entry is not None else _field_key_name(field_key),
                    display_name=fallback_entry.display_name if fallback_entry is not None else str(getattr(row, "field", field_key)),
                    attempted_value=attempted_value,
                    readback_value=None,
                    ok=False,
                    error=str(exc),
                )
            )
            if stop_on_error:
                break
    succeeded = sum(1 for result in results if result.ok)
    failed = len(results) - succeeded
    return GamePortResult(
        player_index=player_index,
        attempted=len(results),
        succeeded=succeeded,
        failed=failed,
        fields=tuple(results),
    )


def _row_value(row: Any) -> int | str:
    if hasattr(row, "display_value"):
        return getattr(row, "display_value")
    if hasattr(row, "value"):
        return getattr(row, "value")
    raise AttributeError("generated row is missing display_value/value")


def _generated_rows(generated: Any) -> Iterable[Any]:
    if hasattr(generated, "field_candidates"):
        return getattr(generated, "field_candidates")
    if hasattr(generated, "rows"):
        return getattr(generated, "rows")
    raise AttributeError("generated player is missing field_candidates/rows")


def _field_key_name(field_key: str) -> str:
    return field_key.split("/", 1)[-1] if "/" in field_key else field_key


__all__ = [
    "GamePortBatchResult",
    "GamePortFieldResult",
    "GamePortResult",
    "apply_generated_player_proposal_to_game",
    "apply_generated_players_to_game",
    "apply_generated_rows_to_game",
]
