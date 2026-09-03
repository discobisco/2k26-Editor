"""Compare generated attributes against a creator-authored reference roster.

The player generation pool holds reference rosters captured from the editor that were
*not* built by this generator -- ``editor_capture_005`` (modern) and
``editor_capture_006`` (1983-84). They are independent ground truth for what a good
roster looks like, so the gap between what the generator produces for a player and what
the reference roster gives that same player is a direct quality measurement.

Run against both eras. A change that improves the modern roster while hurting 1983-84 is
an era leak, which is the failure mode most of the generator's rating errors share.

Usage::

    python player_generation_reference_comparison.py                    # both captures
    python player_generation_reference_comparison.py --snapshot editor_capture_005
    python player_generation_reference_comparison.py --out-dir outputs/exports
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import player_generator as pg
from player_generation_pool import POOL_SQLITE

#: Row keys carried on every captured row for identity, not a rated field.
_ROW_METADATA = frozenset(
    {"player_index", "player_label", "roster_slot", "team_index", "team_label", "team_slot"}
)

#: Minutes below this are noise -- a 40-minute season cannot support a rating comparison.
DEFAULT_MINUTES_FLOOR = 500.0

#: Reference captures and the season whose evidence reproduces those players. The
#: reference roster's own stats are simulated, so the season here is the real-world
#: season the generator draws evidence from, not the roster's internal season.
REFERENCE_SNAPSHOTS: dict[str, int] = {
    "editor_capture_005": 2026,
    "editor_capture_006": 1984,
}

POSITIONS = ("PG", "SG", "SF", "PF", "C")


@dataclass(frozen=True)
class PairedValue:
    player: str
    position: str
    minutes: float
    field: str
    field_key: str
    generated: float
    reference: float

    @property
    def delta(self) -> float:
        return self.generated - self.reference


def normalized_name(value: object) -> str:
    """Fold a roster label and a Basketball-Reference name onto the same key."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z ]", " ", text).lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", text)
    return " ".join(text.split())


def _snapshot_rows(connection: sqlite3.Connection, snapshot_id: str, row_type: str) -> dict[int, dict[str, Any]]:
    """Rows keyed by player_index.

    A roster may seat one player record on more than one team, which repeats the row
    verbatim; keying by index collapses those to the single player they describe.
    """
    rows: dict[int, dict[str, Any]] = {}
    for (payload,) in connection.execute(
        "SELECT row_json FROM pool_export_rows WHERE snapshot_id = ? AND row_type = ?",
        (snapshot_id, row_type),
    ):
        row = json.loads(payload)
        rows[int(row["player_index"])] = row
    return rows


def reference_players(snapshot_id: str, *, minutes_floor: float = DEFAULT_MINUTES_FLOOR) -> dict[str, dict[str, Any]]:
    """Reference roster players keyed by normalized name."""
    with sqlite3.connect(POOL_SQLITE) as connection:
        attributes = _snapshot_rows(connection, snapshot_id, "attributes")
        stats = _snapshot_rows(connection, snapshot_id, "stats")
    if not stats:
        raise LookupError(f"{snapshot_id} holds no captured stat rows")
    players: dict[str, dict[str, Any]] = {}
    for index, stat_row in stats.items():
        attribute_row = attributes.get(index)
        if attribute_row is None:
            continue
        try:
            minutes = float(stat_row.get("Minutes") or 0.0)
        except (TypeError, ValueError):
            minutes = 0.0
        if minutes < minutes_floor:
            continue
        players[normalized_name(stat_row.get("player_label"))] = {
            "label": stat_row.get("player_label"),
            "position": str(stat_row.get("primary_position") or "").strip(),
            "minutes": minutes,
            "attributes": attribute_row,
        }
    return players


#: Sections the reference roster captures and the generator rates.
COMPARED_SECTIONS = ("Attributes", "Tendencies")


def _attribute_column_by_field_key(field_index: dict[str, Any]) -> dict[str, str]:
    """Map the generator's ``Section/NAME`` keys onto captured ``Group / Name`` columns."""
    return {
        field_key: f"{entry.group} / {entry.display_name}"
        for field_key, entry in field_index.items()
        if str(entry.section) in COMPARED_SECTIONS
    }


def paired_values(
    snapshot_id: str,
    season: int,
    *,
    minutes_floor: float = DEFAULT_MINUTES_FLOOR,
    selected_league: str = "NBA",
) -> list[PairedValue]:
    reference = reference_players(snapshot_id, minutes_floor=minutes_floor)
    context = pg.season_context_index(season, selected_league=selected_league)
    field_index = context.field_index
    columns = _attribute_column_by_field_key(field_index)
    # Go through the index entry point. Calling generate_player_proposal directly
    # defaults league_player_rows to (), which silently drops every rule that ranks
    # against the season population -- 101 of the 103 bound tendency rules, and a
    # third of the attributes.
    free_throw_artifact = pg.load_free_throw_execution_artifact()

    paired: list[PairedValue] = []
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        name = normalized_name(evidence.identity.get("player"))
        entry = reference.get(name)
        if entry is None:
            continue
        proposal = pg.generate_player_proposal_from_index(
            context, player_id=player_id, team=team, free_throw_artifact=free_throw_artifact
        )
        for candidate in proposal.field_candidates:
            column = columns.get(candidate.field_key)
            if column is None:
                continue
            try:
                generated = float(candidate.display_value)
                referenced = float(entry["attributes"].get(column))
            except (TypeError, ValueError):
                continue
            paired.append(
                PairedValue(
                    player=str(entry["label"]),
                    position=entry["position"],
                    minutes=entry["minutes"],
                    field=column,
                    field_key=candidate.field_key,
                    generated=generated,
                    reference=referenced,
                )
            )
    return paired


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    count = len(left)
    if count < 3:
        return float("nan")
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    dev_left = sum((value - mean_left) ** 2 for value in left) ** 0.5
    dev_right = sum((value - mean_right) ** 2 for value in right) ** 0.5
    if dev_left == 0 or dev_right == 0:
        return float("nan")
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    return covariance / (dev_left * dev_right)


def field_summary(paired: Iterable[PairedValue]) -> list[dict[str, Any]]:
    grouped: dict[str, list[PairedValue]] = {}
    for value in paired:
        grouped.setdefault(value.field, []).append(value)

    summary: list[dict[str, Any]] = []
    for field, values in grouped.items():
        generated = [value.generated for value in values]
        referenced = [value.reference for value in values]
        deltas = [value.delta for value in values]
        row: dict[str, Any] = {
            "attribute": field,
            "n": len(values),
            "bias": round(statistics.mean(deltas), 2),
            "mae": round(statistics.mean(abs(delta) for delta in deltas), 2),
            "pearson_r": round(_pearson(generated, referenced), 3),
            "generated_median": statistics.median(generated),
            "reference_median": statistics.median(referenced),
            "generated_sd": round(statistics.pstdev(generated), 2),
            "reference_sd": round(statistics.pstdev(referenced), 2),
        }
        for position in POSITIONS:
            subset = [value.delta for value in values if value.position == position]
            row[f"bias_{position}"] = round(statistics.mean(subset), 1) if len(subset) >= 5 else ""
        summary.append(row)
    return sorted(summary, key=lambda row: -row["mae"])


def write_reports(snapshot_id: str, paired: Sequence[PairedValue], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"playergen_vs_{snapshot_id.replace('editor_capture_', 'capture')}.csv"
    rows_path = out_dir / f"playergen_vs_{snapshot_id.replace('editor_capture_', 'capture')}_rows.csv"

    summary = field_summary(paired)
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]) if summary else ["attribute"])
        writer.writeheader()
        writer.writerows(summary)

    with rows_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["player", "position", "minutes", "attribute", "generated", "reference", "delta"])
        for value in sorted(paired, key=lambda value: -abs(value.delta)):
            writer.writerow([
                value.player, value.position, int(value.minutes),
                value.field, value.generated, value.reference, round(value.delta, 1),
            ])
    return summary_path, rows_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", action="append", choices=sorted(REFERENCE_SNAPSHOTS), default=None)
    parser.add_argument("--minutes-floor", type=float, default=DEFAULT_MINUTES_FLOOR)
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/exports"))
    parser.add_argument("--top", type=int, default=12, help="worst-N fields to print")
    args = parser.parse_args(argv)

    snapshots = args.snapshot or sorted(REFERENCE_SNAPSHOTS)
    for snapshot_id in snapshots:
        season = REFERENCE_SNAPSHOTS[snapshot_id]
        paired = paired_values(snapshot_id, season, minutes_floor=args.minutes_floor)
        if not paired:
            print(f"{snapshot_id}: no players matched season {season}")
            continue
        players = len({value.player for value in paired})
        summary_path, rows_path = write_reports(snapshot_id, paired, args.out_dir)
        print(f"\n=== {snapshot_id} (evidence season {season}) ===")
        print(f"{players} players, {len(paired)} attribute pairs")
        print(f"{'attribute':38s} {'n':>4s} {'bias':>7s} {'MAE':>6s} {'r':>6s} {'gen~':>5s} {'ref~':>5s}")
        for row in field_summary(paired)[: args.top]:
            print(
                f"{row['attribute']:38s} {row['n']:4d} {row['bias']:+7.1f} {row['mae']:6.1f} "
                f"{row['pearson_r']:6.2f} {row['generated_median']:5.0f} {row['reference_median']:5.0f}"
            )
        print(f"wrote {summary_path}")
        print(f"wrote {rows_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
