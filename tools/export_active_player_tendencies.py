from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from nba2k_editor.models.data_model import EditorDataModel  # noqa: E402

from active_export_runs import active_export_paths, latest_run_dir, parse_run_number  # noqa: E402

TARGET = "NBA2K26.exe"


def _display(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("display_value", ""))


def _active_player_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing active attributes source: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    run_dir = latest_run_dir(REPO_ROOT)
    paths = active_export_paths(run_dir)
    run_number = parse_run_number(run_dir)
    source_rows = _active_player_rows(paths["attributes_csv"])
    model = EditorDataModel(target_executable=TARGET)
    if not model.attach():
        raise SystemExit(f"failed to attach: {model.last_status}")

    grouped = model.grouped_fields("Players")
    tendency_entries = [entry for group_entries in grouped.get("Tendencies", {}).values() for entry in group_entries]
    if not tendency_entries:
        raise SystemExit("no Players / Tendencies fields found")

    identity_fieldnames = [
        "team_slot",
        "team_index",
        "team_label",
        "roster_slot",
        "player_index",
        "player_label",
    ]
    fieldnames = [*identity_fieldnames, *[f"{entry.group} / {entry.display_name}" for entry in tendency_entries]]
    rows: list[dict[str, Any]] = []

    for source in source_rows:
        player_index = int(source["player_index"])
        row: dict[str, Any] = {key: source.get(key, "") for key in identity_fieldnames}
        for entry in tendency_entries:
            column = f"{entry.group} / {entry.display_name}"
            try:
                row[column] = _display(model.read_entry_value(entry, index=player_index))
            except Exception as exc:
                row[column] = f"ERR: {exc}"
        rows.append(row)

    with paths["tendencies_csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    paths["tendencies_json"].write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Current active player tendencies export",
        "",
        f"Run folder: `{run_dir}`",
        f"Run number: {run_number}",
        f"Target: `{TARGET}`",
        f"Attach status: `{model.last_status}`",
        f"Source active attributes rows: {len(source_rows)}",
        f"Active roster tendency rows exported: {len(rows)}",
        f"Tendency fields: {len(tendency_entries)}",
        f"CSV: `{paths['tendencies_csv']}`",
        f"JSON: `{paths['tendencies_json']}`",
    ]
    paths["tendencies_summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "run_dir": str(run_dir),
        "run_number": run_number,
        "status": model.last_status,
        "source_active_attribute_rows": len(source_rows),
        "rows_exported": len(rows),
        "tendency_fields": len(tendency_entries),
        "csv": str(paths["tendencies_csv"]),
        "json": str(paths["tendencies_json"]),
        "summary": str(paths["tendencies_summary"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
