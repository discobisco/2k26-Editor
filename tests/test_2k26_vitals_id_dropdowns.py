from __future__ import annotations

from typing import Any, cast

from nba2k_editor.core.field_io import _display_to_raw_value, _raw_to_display_value
from nba2k_editor.core.offsets import get_editor_layout_for_super
from nba2k_editor.models.data_model import EditorDataModel


EXPECTED_COUNTS = {
    "FACEID": 1786,
    "HEADSHOTID": 1199,
    "PORTRAITID": 2909,
    "AUDIOSIGNATUREID": 627,
}


def _id_payloads() -> dict[str, dict[str, Any]]:
    layout = cast(dict[str, Any], get_editor_layout_for_super("Players"))
    entries = cast(list[dict[str, Any]], layout["Vitals"]["ID"])
    return {
        str(entry["normalized_name"]): entry["versions"]["2K26"]
        for entry in entries
        if str(entry.get("normalized_name")) in EXPECTED_COUNTS
    }


def test_2k26_combined_roster_vitals_id_dropdowns_are_loaded() -> None:
    payloads = _id_payloads()

    assert set(payloads) == set(EXPECTED_COUNTS)
    for field_name, expected_count in EXPECTED_COUNTS.items():
        payload = payloads[field_name]
        options = cast(list[str], payload["dropdown"])
        assert payload["id_prefixed_dropdown"] is True
        assert len(options) == expected_count
        assert len(options) == len(set(options))
        assert all(not option.startswith("[0]") and not option.startswith("[-1]") for option in options)


def test_2k26_vitals_id_dropdowns_keep_same_name_new_ids_and_shared_ids() -> None:
    face_options = cast(list[str], _id_payloads()["FACEID"]["dropdown"])

    assert "[4642] Kareem Abdul-Jabbar" in face_options
    assert "[4643] Kareem Abdul-Jabbar" in face_options
    assert "[1643] Jeff Ayres" in face_options
    assert "[1643] Jeff Pendergraph" in face_options


def test_2k26_vitals_id_dropdowns_include_the_1983_84_roster_mappings() -> None:
    payloads = _id_payloads()

    assert "[8786] John Bagley" in payloads["FACEID"]["dropdown"]
    assert "[17475] Bobby C. Jones" in payloads["HEADSHOTID"]["dropdown"]
    assert "[20146] Kareem Abdul-Jabbar" in payloads["PORTRAITID"]["dropdown"]
    assert "[2289727391] Magic Johnson" in payloads["AUDIOSIGNATUREID"]["dropdown"]


def test_2k26_vitals_id_dropdowns_include_the_222326_roster_capture() -> None:
    payloads = _id_payloads()

    assert "[8703] Michael Adams" in payloads["FACEID"]["dropdown"]
    assert "[17604] Michael Jordan" in payloads["HEADSHOTID"]["dropdown"]
    assert "[20573] Alaa Abdelnaby" in payloads["PORTRAITID"]["dropdown"]
    assert "[3584566456] Isiah Thomas" in payloads["AUDIOSIGNATUREID"]["dropdown"]


def test_2k26_vitals_id_dropdowns_include_the_223023_roster_capture() -> None:
    payloads = _id_payloads()

    assert "[1899] Jeff Adrien" in payloads["FACEID"]["dropdown"]
    assert "[17646] Kobe Bryant" in payloads["HEADSHOTID"]["dropdown"]
    assert "[30336] Jeff Adrien" in payloads["PORTRAITID"]["dropdown"]
    assert "[3746983088] LeBron James" in payloads["AUDIOSIGNATUREID"]["dropdown"]
    assert "[15426] Nene" in payloads["HEADSHOTID"]["dropdown"]


def test_id_prefixed_dropdown_reads_and_writes_the_authored_raw_id() -> None:
    payload = _id_payloads()["FACEID"]
    field = {"normalized_name": "FACEID", "display_name": "Face ID"}

    assert _raw_to_display_value("Vitals", field, payload, 4642) == "[4642] Kareem Abdul-Jabbar"
    assert _display_to_raw_value("Vitals", field, payload, "[4643] Kareem Abdul-Jabbar") == 4643
    assert _display_to_raw_value("Vitals", field, payload, "[1643] Jeff Pendergraph") == 1643


def test_players_editor_exposes_the_combined_roster_id_options() -> None:
    model = EditorDataModel(target_executable="NBA2K26.exe")

    face_entry = model._field_by_normalized_name("Players", "FACEID")
    assert face_entry is not None
    options = model.field_options(face_entry)

    assert len(options) == EXPECTED_COUNTS["FACEID"]
    assert "[8011] Tyrese Maxey" in options
