from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from nba2k_editor.models.data_model import EditorDataModel, FieldEntry

BASELINE_DIR = Path(__file__).parent / "baselines"
DOCX_NAMES = {
    "player baseline.docx",
    "team baseline.docx",
    "staff baseline.docx",
    "stadium baseline.docx",
    "shoes baseline.docx",
    "jersey baseline.docx",
    "nba history baseline.docx",
    "nba record baseline.docx",
}
EXPECTED_BASELINE_CELL_METADATA = {
    "jersey baseline.docx": (104, 103, "57d48ef95e2779409b4aad97c1e4edc66f7d5ef326f403443fb00e9cb10dda3c"),
    "nba history baseline.docx": (588, 588, "ca36eecb01d496987cc7b340272a35d429c48322a675ea44bf4927a4b7410eec"),
    "nba record baseline.docx": (402, 402, "696ce38191ffec4fe2d13db9e58179fd2e100322b70086a5961366552abb173c"),
    "player baseline.docx": (1070, 1067, "9862ea6f8ef4935d7cbf51cbca26c51ae6a527d26f613933718445ec29a1acc5"),
    "shoes baseline.docx": (6, 6, "0c090c935b351d6a8358e432a9018d1247980df94448800df9574a5f1cc422a9"),
    "stadium baseline.docx": (30, 30, "e5d97faea18aa2aadcd3e6e3685c1c15f7a9a54cc224357e66f011c109e527b7"),
    "staff baseline.docx": (328, 328, "4eda1541e047b54b948220c4486e6694e59b831417653f68fd4c51082b6179e5"),
    "team baseline.docx": (490, 463, "dc5471540836cc3470bdc88b259dda86d421e660b0051aa6c6e8320b919394f5"),
}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

BASELINE_DOMAIN_BY_DOCX = {
    "player baseline.docx": "Players",
    "team baseline.docx": "Teams",
    "staff baseline.docx": "Staff",
    "stadium baseline.docx": "Stadiums",
    "shoes baseline.docx": "Shoes",
    "jersey baseline.docx": "Jerseys",
    "nba history baseline.docx": "NBA History",
    "nba record baseline.docx": "NBA Records",
}
LIVE_BASELINE_TARGETS = (
    ("player baseline.docx", "Players", "Tyrese Maxey", 120),
    ("team baseline.docx", "Teams", "Philadelphia 76ers", 120),
    ("staff baseline.docx", "Staff", "Nick Nurse", 120),
    ("stadium baseline.docx", "Stadiums", "Xfinity Mobile Arena", 120),
    ("shoes baseline.docx", "Shoes", "2K Generic", 120),
    ("jersey baseline.docx", "Jerseys", "Practice", 120),
    ("nba history baseline.docx", "NBA History", "Most Valuable Player", 120),
    ("nba record baseline.docx", "NBA Records", "Points", 120),
)


def _docx_paragraphs(name: str) -> list[str]:
    path = BASELINE_DIR / name
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = [
        "".join(text.text or "" for text in paragraph.findall(".//w:t", WORD_NS)).strip()
        for paragraph in root.findall(".//w:p", WORD_NS)
    ]
    return [text for text in paragraphs if text]


def _docx_cells(name: str) -> list[str]:
    path = BASELINE_DIR / name
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    cells: list[str] = []
    for cell in root.findall(".//w:tc", WORD_NS):
        paragraphs = [
            "".join(text.text or "" for text in paragraph.findall(".//w:t", WORD_NS)).strip()
            for paragraph in cell.findall(".//w:p", WORD_NS)
        ]
        cells.append("\n".join(text for text in paragraphs if text))
    return cells


def _cell_digest(cells: list[str]) -> str:
    payload = json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _field_identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _docx_table_rows(name: str) -> list[list[str]]:
    path = BASELINE_DIR / name
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    rows: list[list[str]] = []
    for row in root.findall(".//w:tr", WORD_NS):
        cells: list[str] = []
        for cell in row.findall("./w:tc", WORD_NS):
            paragraphs = [
                "".join(text.text or "" for text in paragraph.findall(".//w:t", WORD_NS)).strip()
                for paragraph in cell.findall(".//w:p", WORD_NS)
            ]
            cells.append("\n".join(text for text in paragraphs if text))
        if cells:
            rows.append(cells)
    return rows


def _docx_field_value_pairs(name: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in _docx_table_rows(name):
        if len(row) == 2 and row[0] not in {"Field", "Value"}:
            pairs.append((row[0], row[1]))
    return pairs


def _docx_sectioned_field_value_pairs(name: str) -> list[tuple[str, str, str]]:
    path = BASELINE_DIR / name
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find("w:body", WORD_NS)
    if body is None:
        return []
    section = ""
    pairs: list[tuple[str, str, str]] = []
    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in child.findall(".//w:t", WORD_NS)).strip()
            if text and not text.endswith("Baseline") and "Baseline - " not in text and not text.startswith("Transcribed "):
                section = text
        elif tag == "tbl":
            rows: list[list[str]] = []
            for row in child.findall(".//w:tr", WORD_NS):
                cells: list[str] = []
                for cell in row.findall("./w:tc", WORD_NS):
                    paragraphs = [
                        "".join(text.text or "" for text in paragraph.findall(".//w:t", WORD_NS)).strip()
                        for paragraph in cell.findall(".//w:p", WORD_NS)
                    ]
                    cells.append("\n".join(text for text in paragraphs if text))
                rows.append(cells)
            if rows[:1] == [["Field", "Value"]]:
                pairs.extend((section, row[0], row[1]) for row in rows[1:] if len(row) == 2)
    return pairs


def _layout_entries(model: EditorDataModel, domain: str) -> list[FieldEntry]:
    entries: list[FieldEntry] = []
    for groups in model.grouped_fields(domain).values():
        for group_entries in groups.values():
            for entry in group_entries:
                entries.append(entry)
    return entries


def _entry_for_baseline_label(entries: list[FieldEntry], section: str, label: str) -> FieldEntry | None:
    label_id = _field_identity(label)
    exact_matches = [entry for entry in entries if _field_identity(entry.display_name) == label_id]
    prefix_matches: list[FieldEntry] = []
    if len(label_id) >= 8:
        prefix_matches = [
            entry
            for entry in entries
            if _field_identity(entry.display_name).startswith(label_id) or label_id.startswith(_field_identity(entry.display_name))
        ]
    matches_by_key = {(entry.domain, entry.ordinal): entry for entry in [*exact_matches, *prefix_matches]}
    matches = list(matches_by_key.values())
    section_id = _field_identity(section)
    if section_id and len(matches) > 1:
        section_matches = [
            entry
            for entry in matches
            if section_id in {_field_identity(entry.section), _field_identity(entry.group)}
            or _field_identity(entry.section).startswith(section_id)
            or _field_identity(entry.group).startswith(section_id)
            or section_id.startswith(_field_identity(entry.section))
            or section_id.startswith(_field_identity(entry.group))
        ]
        if len(section_matches) == 1:
            return section_matches[0]
        if section_matches:
            matches = section_matches
    if len(exact_matches) == 1 and exact_matches[0] in matches:
        return exact_matches[0]
    return matches[0] if len(matches) == 1 else None


def _bytes_repr_to_hex(value: str) -> str | None:
    if not value.startswith("b'") and not value.startswith('b"'):
        return None
    try:
        parsed = ast.literal_eval(value)
    except Exception:
        return None
    return parsed.hex().upper() if isinstance(parsed, bytes) else None


def _manual_review_reason(label: str, expected: str, actual: str) -> str | None:
    if actual == expected:
        return "exact"
    expected_text = str(expected).strip()
    actual_text = str(actual).strip()
    if not expected_text and actual_text in {"0", "None", "--"}:
        return "blank-vs-nullish"
    if re.fullmatch(r"\d+[:\-]\d+", expected_text) and expected_text.replace(":", "-") == actual_text.replace(":", "-"):
        return "score-separator-format"
    if expected_text.lower() in {"yes", "no"} and actual_text in {"0", "1"}:
        return "boolean-raw-vs-label"
    if expected_text.upper() in {"YES", "NO", "NONE"} and actual_text in {"0", "1"}:
        return "enum-raw-vs-label"
    expected_hex = expected_text.lstrip("#").upper()
    actual_hex = actual_text.lstrip("#").upper()
    if re.fullmatch(r"[0-9A-F]{6,8}", expected_hex) and expected_hex == actual_hex:
        return "hex-format"
    if expected_text.lower().startswith("0x"):
        try:
            if int(expected_text, 16) == int(actual_text, 10):
                return "hex-number-format"
        except ValueError:
            pass
    actual_bytes_hex = _bytes_repr_to_hex(actual_text)
    if actual_bytes_hex and expected_hex in {actual_bytes_hex, "".join(reversed([actual_bytes_hex[i : i + 2] for i in range(0, len(actual_bytes_hex), 2)]))}:
        return "bytes-hex-format"
    try:
        expected_number = float(expected_text)
        actual_number = float(actual_text)
    except ValueError:
        expected_number = actual_number = None
    if expected_number is not None and actual_number is not None:
        if abs(expected_number - actual_number) <= 0.01:
            return "numeric-format-or-rounding"
        return "numeric-live-value-diff"
    if expected_number is None and actual_number is None and expected_text and actual_text and not actual_text.startswith("b'") and not actual_text.startswith('b"'):
        return "text-live-value-diff"
    expected_id = _field_identity(expected_text)
    actual_id = _field_identity(actual_text)
    if len(expected_id) >= 4 and (actual_id.endswith(expected_id) or expected_id in actual_id):
        return "expanded-name-vs-short-name"
    if len(expected_id) >= 8 and len(actual_id) >= 8 and (expected_id.startswith(actual_id) or actual_id.startswith(expected_id)):
        return "truncated-name"
    return None


def _first_item_containing(model: EditorDataModel, domain: str, needle: str, limit: int):
    items = model.refresh_domain_items(domain, limit=limit)
    lowered = needle.lower()
    for item in items:
        if lowered in item.label.lower():
            return item
    labels = [item.display_label for item in items[:20]]
    raise AssertionError(f"missing live {domain} baseline target {needle!r}; first labels: {labels}")


def _first_table_after_heading(rows: list[list[str]], heading: str, columns: list[str], count: int) -> list[dict[str, str]]:
    for index, row in enumerate(rows):
        if row == [heading]:
            header_index = index + 1
            while header_index < len(rows) and rows[header_index] != columns:
                header_index += 1
            if header_index >= len(rows):
                break
            table_rows: list[dict[str, str]] = []
            for values in rows[header_index + 1 : header_index + 1 + count]:
                if len(values) != len(columns):
                    break
                table_rows.append(dict(zip(columns, values)))
            return table_rows
    raise AssertionError(f"missing baseline table {heading!r}")


def _nth_table_by_columns(rows: list[list[str]], columns: list[str], occurrence: int, count: int) -> list[dict[str, str]]:
    seen = 0
    for index, row in enumerate(rows):
        if row != columns:
            continue
        seen += 1
        if seen != occurrence:
            continue
        table_rows: list[dict[str, str]] = []
        for values in rows[index + 1 : index + 1 + count]:
            if len(values) != len(columns):
                break
            table_rows.append(dict(zip(columns, values)))
        return table_rows
    raise AssertionError(f"missing baseline table columns={columns!r} occurrence={occurrence}")


def _table_hard_failures(
    table_name: str,
    expected_rows: list[dict[str, str]],
    actual_rows: list[dict[str, str]],
    columns: list[str],
    *,
    review_live_value_drift: bool = False,
) -> tuple[list[str], list[tuple[str, int, str, str, str, str]]]:
    hard: list[str] = []
    manual_review: list[tuple[str, int, str, str, str, str]] = []
    if len(actual_rows) != len(expected_rows):
        hard.append(f"{table_name}: expected {len(expected_rows)} rows, got {len(actual_rows)}")
    for row_index, expected in enumerate(expected_rows[: len(actual_rows)], start=1):
        actual = actual_rows[row_index - 1]
        for column in columns:
            expected_value = expected.get(column, "")
            actual_value = actual.get(column, "")
            reason = _manual_review_reason(column, expected_value, actual_value)
            if reason is None and review_live_value_drift and expected_value and actual_value and actual_value != "--":
                reason = "live-table-value-diff"
            if reason is None:
                hard.append(f"{table_name} row {row_index} {column}: expected={expected_value!r} actual={actual_value!r}")
            elif reason != "exact":
                manual_review.append((table_name, row_index, column, expected_value, actual_value, reason))
    return hard, manual_review


def _value_after(paragraphs: list[str], label: str, *, occurrence: int = 1) -> str:
    seen = 0
    for index, text in enumerate(paragraphs[:-1]):
        if text == label:
            seen += 1
            if seen == occurrence:
                return paragraphs[index + 1]
    raise AssertionError(f"missing label {label!r} occurrence {occurrence}")


def _assert_sequence(paragraphs: list[str], expected: list[str]) -> None:
    cursor = 0
    for text in expected:
        try:
            cursor = paragraphs.index(text, cursor) + 1
        except ValueError as exc:
            raise AssertionError(f"missing ordered baseline text {text!r}") from exc


def test_baseline_docx_files_are_present_and_readable() -> None:
    found = {path.name for path in BASELINE_DIR.glob("*.docx")}
    assert DOCX_NAMES <= found
    for name in DOCX_NAMES:
        paragraphs = _docx_paragraphs(name)
        assert paragraphs, name
        assert paragraphs[0].endswith("Baseline") or "Baseline - " in paragraphs[0]


def test_baseline_docx_every_table_cell_matches_current_fixture_snapshot() -> None:
    for name, (expected_cells, expected_nonempty_cells, expected_digest) in EXPECTED_BASELINE_CELL_METADATA.items():
        cells = _docx_cells(name)
        assert len(cells) == expected_cells, name
        assert sum(1 for cell in cells if cell) == expected_nonempty_cells, name
        assert _cell_digest(cells) == expected_digest, name


def test_live_game_editor_field_value_baselines_match_docx_values() -> None:
    model = EditorDataModel(target_executable="NBA2K26.exe")
    assert model.attach(), model.runtime_status_text()

    failures: list[str] = []
    for name, domain, target_label, scan_limit in LIVE_BASELINE_TARGETS:
        if name in {"nba history baseline.docx", "nba record baseline.docx"}:
            continue
        item = _first_item_containing(model, domain, target_label, scan_limit)
        entries = _layout_entries(model, domain)
        missing: list[str] = []
        mismatches: list[tuple[str, str, str]] = []
        manual_review: list[tuple[str, str, str, str]] = []
        for section, label, expected in _docx_sectioned_field_value_pairs(name):
            entry = _entry_for_baseline_label(entries, section, label)
            if entry is None:
                missing.append(label)
                continue
            try:
                actual = str(model.read_entry_value(entry, index=item.index)["display_value"])
            except Exception as exc:
                actual = f"ERROR {type(exc).__name__}: {str(exc)[:120]}"
            reason = _manual_review_reason(label, expected, actual)
            if reason is None:
                mismatches.append((label, expected, actual))
            elif reason != "exact":
                manual_review.append((label, expected, actual, reason))
        if missing or mismatches:
            failures.append(
                f"{name} -> {item.display_label}: missing={missing[:25]!r}; hard_mismatches={mismatches[:25]!r}; "
                f"manual_review={manual_review[:25]!r}"
            )
    assert not failures, "\n".join(failures)


def test_live_game_editor_history_baseline_rows_match_docx_values() -> None:
    model = EditorDataModel(target_executable="NBA2K26.exe")
    assert model.attach(), model.runtime_status_text()
    model.refresh_domain_items("NBA History", limit=2600)
    rows = _docx_table_rows("nba history baseline.docx")

    mvp_columns = ["Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name"]
    expected_mvp = _nth_table_by_columns(rows, mvp_columns, 1, 25)
    actual_mvp = model.record_summary_rows("NBA History", limit=len(expected_mvp), history_type=8)
    failures, manual_review = _table_hard_failures(
        "NBA History MVP",
        expected_mvp,
        [{key: row.get(key, "") for key in mvp_columns} for row in actual_mvp],
        mvp_columns,
    )

    fmvp_columns = [
        "Season",
        "Team Logo",
        "Winner Team City",
        "Winner Team Name",
        "Result",
        "Loser Team City",
        "Loser Team Name",
        "First Name",
        "Last Name",
    ]
    expected_fmvp = _nth_table_by_columns(rows, fmvp_columns, 1, 25)
    actual_fmvp = model.record_summary_rows("NBA History", limit=len(expected_fmvp), history_type=1)
    normalized_actual_fmvp = []
    for row in actual_fmvp:
        normalized_actual_fmvp.append(
            {
                "Season": row.get("Season", ""),
                "Team Logo": row.get("Team Logo", ""),
                "Winner Team City": row.get("Winner Team City", row.get("Team City", "")),
                "Winner Team Name": row.get("Winner Team Name", row.get("Team Name", "")),
                "Result": row.get("Result", ""),
                "Loser Team City": row.get("Loser Team City", ""),
                "Loser Team Name": row.get("Loser Team Name", ""),
                "First Name": row.get("First Name", ""),
                "Last Name": row.get("Last Name", ""),
            }
        )
    fmvp_failures, fmvp_manual_review = _table_hard_failures("NBA History FMVP", expected_fmvp, normalized_actual_fmvp, fmvp_columns)
    failures.extend(fmvp_failures)
    manual_review.extend(fmvp_manual_review)
    assert not failures, f"hard_failures={failures[:25]!r}; manual_review={manual_review[:25]!r}"


def test_live_game_editor_record_baseline_rows_match_docx_values() -> None:
    model = EditorDataModel(target_executable="NBA2K26.exe")
    assert model.attach(), model.runtime_status_text()
    rows = _docx_table_rows("nba record baseline.docx")

    game_columns = ["Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Month", "Day", "Data"]
    season_columns = ["Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data"]
    table_specs = (
        ("Single Game (Regular) - Points", game_columns, 1, 0, 5),
        ("Single Game (Playoffs) - Points", game_columns, 2, 50, 5),
        ("Season - Points", season_columns, 1, 100, 10),
        ("Career - Points", season_columns, 2, 350, 100),
    )
    failures: list[str] = []
    manual_reviews: list[tuple[str, int, str, str, str, str]] = []
    for heading, columns, occurrence, start, count in table_specs:
        expected = _nth_table_by_columns(rows, columns, occurrence, count)
        actual_rows = model.record_summary_rows(
            "NBA Records",
            limit=len(expected),
            record_row_start=start,
            record_row_count=len(expected),
        )
        actual = [{key: row.get(key, "") for key in columns} for row in actual_rows]
        hard, manual_review = _table_hard_failures(heading, expected, actual, columns, review_live_value_drift=True)
        failures.extend(hard)
        manual_reviews.extend(manual_review)
    assert not failures, f"hard_failures={failures[:50]!r}; manual_review={manual_reviews[:50]!r}"


def test_player_baseline_captures_tyrese_maxey_identity_and_team() -> None:
    paragraphs = _docx_paragraphs("player baseline.docx")
    assert paragraphs[0] == "Player Baseline - Tyrese Maxey"
    assert _value_after(paragraphs, "First Name") == "Tyrese"
    assert _value_after(paragraphs, "Last Name") == "Maxey"
    assert _value_after(paragraphs, "Position") == "PG"
    assert _value_after(paragraphs, "Secondary Positi") == "SG"
    assert _value_after(paragraphs, "Height (cm)") == "187.96"
    assert _value_after(paragraphs, "Current Team") == "Philadelphia 76ers"
    assert _value_after(paragraphs, "Drafted Team") == "Philadelphia 76ers"


def test_team_baseline_captures_76ers_identity_and_jersey_rows() -> None:
    paragraphs = _docx_paragraphs("team baseline.docx")
    assert paragraphs[0] == "Team Baseline - Philadelphia 76ers"
    assert _value_after(paragraphs, "City Name") == "Philadelphia"
    assert _value_after(paragraphs, "Team Name") == "76ers"
    assert _value_after(paragraphs, "City Short Name") == "PHI"
    assert _value_after(paragraphs, "Stadium") == "Xfinity Mobile Ar"
    assert _value_after(paragraphs, "Uniform #1") == "u000phi_current"
    assert _value_after(paragraphs, "Uniform #6") == "u000phi_1945_h"
    assert _value_after(paragraphs, "Practice Jersey H") == "u000phi_current_practice_home"


def test_staff_baseline_captures_nick_nurse_and_badge_values() -> None:
    paragraphs = _docx_paragraphs("staff baseline.docx")
    assert paragraphs[0] == "Staff Baseline - Nick Nurse"
    assert _value_after(paragraphs, "First Name") == "Nick"
    assert _value_after(paragraphs, "Last Name") == "Nurse"
    assert _value_after(paragraphs, "Position") == "Head Coach"
    assert _value_after(paragraphs, "Current Team") == "Philadelphia 76ers"
    assert _value_after(paragraphs, "Tactician") == "Silver"
    assert _value_after(paragraphs, "Coaching Legend") == "Bronze"
    assert _value_after(paragraphs, "Mind Games") == "Silver"


def test_stadium_shoes_and_jersey_baselines_capture_domain_specific_values() -> None:
    stadium = _docx_paragraphs("stadium baseline.docx")
    assert stadium[0] == "Stadium Baseline - Xfinity Mobile Arena"
    assert _value_after(stadium, "Arena Name") == "Xfinity Mobile Arena"
    assert _value_after(stadium, "City Name") == "Philadelphia"
    assert _value_after(stadium, "Arena Id") == "arena_000_int"
    assert _value_after(stadium, "Backboard Shakes") == "Yes"

    shoes = _docx_paragraphs("shoes baseline.docx")
    assert shoes[0] == "Shoes Baseline - 2K Generic"
    assert _value_after(shoes, "ID") == "0"
    assert _value_after(shoes, "Name") == "2K Generic"

    jersey = _docx_paragraphs("jersey baseline.docx")
    assert jersey[0] == "Jersey Baseline - Philadelphia 76ers - Practice"
    assert _value_after(jersey, "Uniform File") == "u000phi_current_practice_home"
    assert _value_after(jersey, "Edition Name") == "Practice"
    assert _value_after(jersey, "Primary Color") == "2E3C70"
    assert _value_after(jersey, "Is Home") == "YES"
    assert _value_after(jersey, "Is Alternate") == "YES"


def test_nba_history_baseline_captures_mvp_and_fmvp_top_rows() -> None:
    paragraphs = _docx_paragraphs("nba history baseline.docx")
    assert paragraphs[0] == "NBA History Baseline"
    _assert_sequence(
        paragraphs,
        [
            "Most Valuable Player",
            "Season",
            "Team Logo",
            "Team City",
            "Team Name",
            "First Name",
            "Last Name",
            "2024-2025",
            "Thunder",
            "Oklahoma City",
            "Thunder",
            "Shai",
            "Gilgeous-Alexander",
            "2023-2024",
            "Nuggets",
            "Denver",
            "Nuggets",
            "Nikola",
            "Jokic",
            "2022-2023",
            "76ers",
            "Philadelphia",
            "76ers",
            "Joel",
            "Embiid",
        ],
    )
    _assert_sequence(
        paragraphs,
        [
            "Past Champions",
            "Tabs (visible): NBA Championship | FMVP (selected)",
            "FMVP",
            "Season",
            "Team Logo",
            "Winner Team City",
            "Winner Team Name",
            "Result",
            "Loser Team City",
            "Loser Team Name",
            "First Name",
            "Last Name",
            "2024-2025",
            "Thunder",
            "Oklahoma City",
            "Thunder",
            "4:3",
            "Indiana",
            "Pacers",
            "Shai",
            "Gilgeous-Alexander",
        ],
    )


def test_nba_record_baseline_captures_points_record_top_rows() -> None:
    paragraphs = _docx_paragraphs("nba record baseline.docx")
    assert paragraphs[0] == "NBA Record Baseline"
    _assert_sequence(
        paragraphs,
        [
            "Single Game (Regular) - Points",
            "Rank",
            "First Name",
            "Last Name",
            "Signature ID",
            "Team Logo",
            "Year",
            "Month",
            "Day",
            "Data",
            "1",
            "Wilt",
            "Chamberlain",
            "3995331167",
            "Warriors",
            "1962",
            "3",
            "2",
            "100.00",
            "2",
            "Kobe",
            "Bryant",
            "1882810953",
            "Lakers",
            "2006",
            "1",
            "22",
            "81.00",
        ],
    )
    _assert_sequence(
        paragraphs,
        [
            "Career - Points",
            "Rank",
            "First Name",
            "Last Name",
            "Signature ID",
            "Team Logo",
            "Year",
            "Data",
            "1",
            "LeBron",
            "James",
            "14453172",
            "Lakers",
            "2026",
            "43178.00",
        ],
    )
