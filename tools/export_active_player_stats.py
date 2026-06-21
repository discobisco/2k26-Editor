from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from nba2k_editor.models.data_model import EditorDataModel  # noqa: E402
from nba2k_editor.models.schema import RecordListItem  # noqa: E402

from active_export_runs import active_export_paths, create_next_run_dir, parse_run_number  # noqa: E402

TARGET = "NBA2K26.exe"
TEAM_LIMIT = 30


def _display(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("display_value", ""))


def _raw_int(value: dict[str, Any] | None) -> int | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("raw_value")
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def main() -> int:
    model = EditorDataModel(target_executable=TARGET)
    if not model.attach():
        raise SystemExit(f"failed to attach: {model.last_status}")

    teams = model.scan_records("Teams", limit=TEAM_LIMIT)
    model.loaded_items["Teams"] = {team.display_label: team for team in teams}

    team_player_entries = sorted(
        (
            entry
            for entry in model.grouped_fields("Teams").get("Team Players", {}).get("Team Players", ())
            if str(entry.normalized_name).startswith("PLAYER")
        ),
        key=lambda entry: int(str(entry.normalized_name).replace("PLAYER", "")),
    )
    player_base = model.domain_base("Players")
    player_stride = model.domain_stride("Players")
    player_label_entries = model._label_entries("Players")
    player_groups: dict[int, list[RecordListItem]] = {int(team.address): [] for team in teams}
    for team in teams:
        for roster_slot, entry in enumerate(team_player_entries, start=1):
            player_pointer = _raw_int(model.read_entry_value(entry, index=team.index))
            if not player_pointer:
                continue
            player_index = (int(player_pointer) - player_base) // player_stride
            player_label = model._label_for_record_address("Players", player_index, int(player_pointer), player_label_entries)
            player_groups[int(team.address)].append(
                RecordListItem(domain="Players", index=int(player_index), address=int(player_pointer), label=str(player_label or f"Player {roster_slot}"))
            )
    players = [player for roster in player_groups.values() for player in roster]
    model.loaded_items["Players"] = {player.display_label: player for player in players}

    grouped = model.grouped_fields("Players")
    season_id_entries = list(grouped.get("Stats", {}).get("Season IDs", ()))
    stat_id_entries = [entry for entry in season_id_entries if model.is_player_season_id_selector_entry(entry)]
    stat_detail_entries = [entry for entry in season_id_entries if model.is_player_selected_stat_detail_entry(entry)]
    if not stat_detail_entries:
        raise SystemExit("no selected stat detail fields found in Players / Stats / Season IDs")
    position_entries = {
        str(entry.normalized_name).upper(): entry
        for section_groups in grouped.values()
        for group_entries in section_groups.values()
        for entry in group_entries
        if str(entry.normalized_name).upper() in {"POSITION", "SECONDARYPOSITION"}
    }
    attribute_entries = [entry for group_entries in grouped.get("Attributes", {}).values() for entry in group_entries]
    if not attribute_entries:
        raise SystemExit("no Players / Attributes fields found")
    season_high_entries = list(grouped.get("Stats", {}).get("Season High", ()))
    if not season_high_entries:
        raise SystemExit("no Players / Stats / Season High fields found")
    award_entries = list(grouped.get("Stats", {}).get("Awards", ()))
    if not award_entries:
        raise SystemExit("no Players / Stats / Awards fields found")

    selector = "Current Year Stat ID"
    rows: list[dict[str, Any]] = []
    attribute_rows: list[dict[str, Any]] = []
    season_high_rows: list[dict[str, Any]] = []
    award_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []
    team_entries = [entry for section_groups in model.grouped_fields("Teams").values() for group_entries in section_groups.values() for entry in group_entries]
    team_identity_fieldnames = ["team_slot", "team_index", "team_label"]
    identity_fieldnames = [
        "team_slot",
        "team_index",
        "team_label",
        "roster_slot",
        "player_index",
        "player_label",
    ]
    fieldnames = [
        *identity_fieldnames,
        "primary_position",
        "secondary_position",
        "current_year_stat_id",
    ] + [entry.display_name for entry in stat_detail_entries]
    attribute_fieldnames = [*identity_fieldnames, *[f"{entry.group} / {entry.display_name}" for entry in attribute_entries]]
    season_high_fieldnames = [*identity_fieldnames, *[entry.display_name for entry in season_high_entries]]
    award_fieldnames = [*identity_fieldnames, *[entry.display_name for entry in award_entries]]
    team_fieldnames = [*team_identity_fieldnames, *[f"{entry.section} / {entry.group} / {entry.display_name}" for entry in team_entries]]

    for team_slot, team in enumerate(teams):
        team_row: dict[str, Any] = {
            "team_slot": team_slot,
            "team_index": team.index,
            "team_label": team.label,
        }
        for entry in team_entries:
            column = f"{entry.section} / {entry.group} / {entry.display_name}"
            try:
                team_row[column] = _display(model.read_entry_value(entry, index=team.index))
            except Exception as exc:
                team_row[column] = f"ERR: {exc}"
        team_rows.append(team_row)

        roster = sorted(player_groups.get(int(team.address), ()), key=lambda item: int(item.index))
        for roster_slot, player in enumerate(roster, start=1):
            row: dict[str, Any] = {
                "team_slot": team_slot,
                "team_index": team.index,
                "team_label": team.label,
                "roster_slot": roster_slot,
                "player_index": player.index,
                "player_label": player.label,
            }
            for column, normalized_name in (("primary_position", "POSITION"), ("secondary_position", "SECONDARYPOSITION")):
                entry = position_entries.get(normalized_name)
                if entry is None:
                    row[column] = ""
                    continue
                try:
                    row[column] = _display(model.read_entry_value(entry, index=player.index))
                except Exception as exc:
                    row[column] = f"ERR: {exc}"
            stat_id = None
            for entry in stat_id_entries:
                if entry.display_name == selector or entry.normalized_name == "CURRENTYEARSTATID":
                    try:
                        stat_id = _raw_int(model.read_entry_value(entry, index=player.index))
                    except Exception:
                        stat_id = None
                    break
            row["current_year_stat_id"] = "" if stat_id is None else stat_id
            for entry in stat_detail_entries:
                try:
                    row[entry.display_name] = _display(model.read_entry_value(entry, index=player.index, stat_selector=selector))
                except Exception as exc:
                    row[entry.display_name] = f"ERR: {exc}"
            rows.append(row)

            attribute_row: dict[str, Any] = {
                "team_slot": team_slot,
                "team_index": team.index,
                "team_label": team.label,
                "roster_slot": roster_slot,
                "player_index": player.index,
                "player_label": player.label,
            }
            for entry in attribute_entries:
                column = f"{entry.group} / {entry.display_name}"
                try:
                    attribute_row[column] = _display(model.read_entry_value(entry, index=player.index))
                except Exception as exc:
                    attribute_row[column] = f"ERR: {exc}"
            attribute_rows.append(attribute_row)

            season_high_row: dict[str, Any] = {
                "team_slot": team_slot,
                "team_index": team.index,
                "team_label": team.label,
                "roster_slot": roster_slot,
                "player_index": player.index,
                "player_label": player.label,
            }
            for entry in season_high_entries:
                try:
                    season_high_row[entry.display_name] = _display(model.read_entry_value(entry, index=player.index))
                except Exception as exc:
                    season_high_row[entry.display_name] = f"ERR: {exc}"
            season_high_rows.append(season_high_row)

            award_row: dict[str, Any] = {
                "team_slot": team_slot,
                "team_index": team.index,
                "team_label": team.label,
                "roster_slot": roster_slot,
                "player_index": player.index,
                "player_label": player.label,
            }
            for entry in award_entries:
                try:
                    award_row[entry.display_name] = _display(model.read_entry_value(entry, index=player.index))
                except Exception as exc:
                    award_row[entry.display_name] = f"ERR: {exc}"
            award_rows.append(award_row)

    run_dir = create_next_run_dir(REPO_ROOT)
    paths = active_export_paths(run_dir)
    run_number = parse_run_number(run_dir)

    with paths["stats_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    paths["stats_json"].write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with paths["attributes_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=attribute_fieldnames)
        writer.writeheader()
        writer.writerows(attribute_rows)

    paths["attributes_json"].write_text(json.dumps(attribute_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with paths["season_highs_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=season_high_fieldnames)
        writer.writeheader()
        writer.writerows(season_high_rows)

    paths["season_highs_json"].write_text(json.dumps(season_high_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with paths["awards_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=award_fieldnames)
        writer.writeheader()
        writer.writerows(award_rows)

    paths["awards_json"].write_text(json.dumps(award_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with paths["teams_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=team_fieldnames)
        writer.writeheader()
        writer.writerows(team_rows)

    paths["teams_json"].write_text(json.dumps(team_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Current active player stats export",
        "",
        f"Run folder: `{run_dir}`",
        f"Run number: {run_number}",
        f"Target: `{TARGET}`",
        f"Attach status: `{model.last_status}`",
        f"Teams scanned: {len(teams)} (limit {TEAM_LIMIT})",
        f"Player discovery: Teams / Team Players / Player 1-15 pointers",
        f"Roster player pointers read: {len(teams) * len(team_player_entries)}",
        f"Rostered players found: {len(players)}",
        f"Active roster rows exported: {len(rows)}",
        f"CSV: `{paths['stats_csv']}`",
        f"JSON: `{paths['stats_json']}`",
        f"Attributes CSV: `{paths['attributes_csv']}`",
        f"Attributes JSON: `{paths['attributes_json']}`",
        f"Season highs CSV: `{paths['season_highs_csv']}`",
        f"Season highs JSON: `{paths['season_highs_json']}`",
        f"Awards CSV: `{paths['awards_csv']}`",
        f"Awards JSON: `{paths['awards_json']}`",
        f"Teams CSV: `{paths['teams_csv']}`",
        f"Teams JSON: `{paths['teams_json']}`",
        "",
        "## Team counts",
    ]
    for team_slot, team in enumerate(teams):
        count = len(player_groups.get(int(team.address), ()))
        lines.append(f"- {team_slot:02d} {team.label}: {count}")
    paths["summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "run_dir": str(run_dir),
        "run_number": run_number,
        "player_discovery": "team_player_pointers",
        "status": model.last_status,
        "teams": len(teams),
        "roster_player_pointers_read": len(teams) * len(team_player_entries),
        "players_scanned": len(players),
        "rostered_players_found": len(players),
        "rows_exported": len(rows),
        "attribute_rows_exported": len(attribute_rows),
        "attribute_fields": len(attribute_entries),
        "season_high_rows_exported": len(season_high_rows),
        "season_high_fields": len(season_high_entries),
        "award_rows_exported": len(award_rows),
        "award_fields": len(award_entries),
        "team_rows_exported": len(team_rows),
        "team_fields": len(team_entries),
        "csv": str(paths["stats_csv"]),
        "json": str(paths["stats_json"]),
        "attributes_csv": str(paths["attributes_csv"]),
        "attributes_json": str(paths["attributes_json"]),
        "season_highs_csv": str(paths["season_highs_csv"]),
        "season_highs_json": str(paths["season_highs_json"]),
        "awards_csv": str(paths["awards_csv"]),
        "awards_json": str(paths["awards_json"]),
        "teams_csv": str(paths["teams_csv"]),
        "teams_json": str(paths["teams_json"]),
        "summary": str(paths["summary"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
