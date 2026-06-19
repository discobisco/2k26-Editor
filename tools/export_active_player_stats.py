from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from nba2k_editor.models.data_model import EditorDataModel  # noqa: E402

TARGET = "NBA2K26.exe"
TEAM_LIMIT = 30
OUT_DIR = REPO_ROOT / "outputs"
CSV_PATH = OUT_DIR / "current_active_player_stats.csv"
JSON_PATH = OUT_DIR / "current_active_player_stats.json"
ATTRIBUTES_CSV_PATH = OUT_DIR / "current_active_player_attributes.csv"
ATTRIBUTES_JSON_PATH = OUT_DIR / "current_active_player_attributes.json"
SEASON_HIGHS_CSV_PATH = OUT_DIR / "current_active_player_season_highs.csv"
SEASON_HIGHS_JSON_PATH = OUT_DIR / "current_active_player_season_highs.json"
AWARDS_CSV_PATH = OUT_DIR / "current_active_player_awards.csv"
AWARDS_JSON_PATH = OUT_DIR / "current_active_player_awards.json"
TEAMS_CSV_PATH = OUT_DIR / "current_active_team_fields.csv"
TEAMS_JSON_PATH = OUT_DIR / "current_active_team_fields.json"
SUMMARY_PATH = OUT_DIR / "current_active_player_stats_summary.md"


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


def _norm_label(text: object) -> str:
    return " ".join(str(text or "").strip().split()).upper()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = EditorDataModel(target_executable=TARGET)
    if not model.attach():
        raise SystemExit(f"failed to attach: {model.last_status}")

    teams = model.scan_records("Teams", limit=TEAM_LIMIT)
    players = model.scan_records("Players")
    model.loaded_items["Teams"] = {team.display_label: team for team in teams}
    model.loaded_items["Players"] = {player.display_label: player for player in players}

    player_groups = {int(team.address): [] for team in teams}
    skipped_az = 0
    skipped_no_team = 0
    for player in players:
        if _norm_label(player.label) == "A Z":
            skipped_az += 1
            continue
        team_address = model._player_current_team_pointer(player)
        if team_address not in player_groups:
            skipped_no_team += 1
            continue
        player_groups[int(team_address)].append(player)

    grouped = model.grouped_fields("Players")
    season_id_entries = list(grouped.get("Stats", {}).get("Season IDs", ()))
    stat_id_entries = [entry for entry in season_id_entries if model.is_player_season_id_selector_entry(entry)]
    stat_detail_entries = [entry for entry in season_id_entries if model.is_player_selected_stat_detail_entry(entry)]
    if not stat_detail_entries:
        raise SystemExit("no selected stat detail fields found in Players / Stats / Season IDs")
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

    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    JSON_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with ATTRIBUTES_CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=attribute_fieldnames)
        writer.writeheader()
        writer.writerows(attribute_rows)

    ATTRIBUTES_JSON_PATH.write_text(json.dumps(attribute_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with SEASON_HIGHS_CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=season_high_fieldnames)
        writer.writeheader()
        writer.writerows(season_high_rows)

    SEASON_HIGHS_JSON_PATH.write_text(json.dumps(season_high_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with AWARDS_CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=award_fieldnames)
        writer.writeheader()
        writer.writerows(award_rows)

    AWARDS_JSON_PATH.write_text(json.dumps(award_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with TEAMS_CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=team_fieldnames)
        writer.writeheader()
        writer.writerows(team_rows)

    TEAMS_JSON_PATH.write_text(json.dumps(team_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Current active player stats export",
        "",
        f"Target: `{TARGET}`",
        f"Attach status: `{model.last_status}`",
        f"Teams scanned: {len(teams)} (limit {TEAM_LIMIT})",
        f"Players scanned: {len(players)}",
        f"Active roster rows exported: {len(rows)}",
        f"Ignored A Z players: {skipped_az}",
        f"Ignored players outside first {TEAM_LIMIT} team slots: {skipped_no_team}",
        f"CSV: `{CSV_PATH}`",
        f"JSON: `{JSON_PATH}`",
        f"Attributes CSV: `{ATTRIBUTES_CSV_PATH}`",
        f"Attributes JSON: `{ATTRIBUTES_JSON_PATH}`",
        f"Season highs CSV: `{SEASON_HIGHS_CSV_PATH}`",
        f"Season highs JSON: `{SEASON_HIGHS_JSON_PATH}`",
        f"Awards CSV: `{AWARDS_CSV_PATH}`",
        f"Awards JSON: `{AWARDS_JSON_PATH}`",
        f"Teams CSV: `{TEAMS_CSV_PATH}`",
        f"Teams JSON: `{TEAMS_JSON_PATH}`",
        "",
        "## Team counts",
    ]
    for team_slot, team in enumerate(teams):
        count = len(player_groups.get(int(team.address), ()))
        lines.append(f"- {team_slot:02d} {team.label}: {count}")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": model.last_status,
        "teams": len(teams),
        "players_scanned": len(players),
        "rows_exported": len(rows),
        "attribute_rows_exported": len(attribute_rows),
        "attribute_fields": len(attribute_entries),
        "season_high_rows_exported": len(season_high_rows),
        "season_high_fields": len(season_high_entries),
        "award_rows_exported": len(award_rows),
        "award_fields": len(award_entries),
        "team_rows_exported": len(team_rows),
        "team_fields": len(team_entries),
        "ignored_a_z": skipped_az,
        "ignored_outside_team_slots": skipped_no_team,
        "csv": str(CSV_PATH),
        "json": str(JSON_PATH),
        "attributes_csv": str(ATTRIBUTES_CSV_PATH),
        "attributes_json": str(ATTRIBUTES_JSON_PATH),
        "season_highs_csv": str(SEASON_HIGHS_CSV_PATH),
        "season_highs_json": str(SEASON_HIGHS_JSON_PATH),
        "awards_csv": str(AWARDS_CSV_PATH),
        "awards_json": str(AWARDS_JSON_PATH),
        "teams_csv": str(TEAMS_CSV_PATH),
        "teams_json": str(TEAMS_JSON_PATH),
        "summary": str(SUMMARY_PATH),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
