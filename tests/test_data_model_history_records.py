from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel, RecordListItem


class FakeMemory:
    pointer_size = 8

    def __init__(self) -> None:
        self.hproc = object()
        self.base_addr = 0x1000
        self.bytes_by_addr: dict[int, bytes] = {}
        self.u64_by_addr: dict[int, int] = {}

    def read_u64(self, addr: int) -> int:
        if addr in self.u64_by_addr:
            return self.u64_by_addr[addr]
        return struct.unpack("<Q", self.read_bytes(addr, 8))[0]

    def read_bytes(self, addr: int, length: int) -> bytes:
        if addr in self.bytes_by_addr:
            data = self.bytes_by_addr[addr]
            return data[:length].ljust(length, b"\x00")
        raise RuntimeError(f"missing memory at 0x{addr:X}")

    def read_ascii(self, addr: int, max_chars: int) -> str:
        raw = self.read_bytes(addr, max_chars)
        return raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore")


class FakeOffsets:
    MODULE_NAME = "NBA2K26.exe"

    def __init__(self, config: dict[str, Any], layouts: dict[str, dict[str, Any]]) -> None:
        self.config = config
        self.layouts = layouts

    def initialize_offsets(self, target_executable: str | None = None, force: bool = False) -> None:
        return None

    def get_active_offset_config(self, target_executable: str | None = None) -> dict[str, Any]:
        return self.config

    def get_editor_layout_for_super(self, super_type: str) -> dict[str, Any]:
        return self.layouts[super_type]

    def _select_active_version(self, versions: dict[str, Any], target_executable: str | None, require_hint: bool = True):
        return "2K26", "2K26", versions["2K26"]

    def _resolved_length_bits(self, payload: dict[str, Any]) -> int:
        if "byteLength" in payload:
            return int(payload["byteLength"])
        if "length" in payload and payload.get("type") not in {"string", "wstring"}:
            return int(payload["length"])
        if "bit_length" in payload:
            return int(payload["bit_length"])
        return 0


def _field(name: str, address: int, type_: str = "string", length: int = 20) -> dict[str, Any]:
    payload: dict[str, Any] = {"address": address, "type": type_}
    if type_ == "string":
        payload["length"] = length
    return {"normalized_name": name, "display_name": name.title(), "versions": {"2K26": payload}}


def _write_ascii(memory: FakeMemory, addr: int, text: str, length: int = 20) -> None:
    memory.bytes_by_addr[addr] = text.encode("ascii")[:length].ljust(length, b"\x00")


def _write_float(memory: FakeMemory, addr: int, value: float) -> None:
    memory.bytes_by_addr[addr] = struct.pack("<f", value)


def _write_u64(memory: FakeMemory, addr: int, value: int) -> None:
    memory.u64_by_addr[addr] = value


def _write_byte(memory: FakeMemory, addr: int, value: int) -> None:
    memory.bytes_by_addr[addr] = bytes([value & 0xFF])


def test_domain_base_applies_final_offset_after_pointer_read() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1100] = 0x5000
    offsets = FakeOffsets(
        {
            "base_pointers": {"NBAHistory": {"address": 0x100, "chain": [], "finalOffset": 8}},
            "game_info": {"historySize": 0xA8},
        },
        {"NBA History": {"History Tab": {"History Tab": []}}},
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    assert model.domain_base("NBA History") == 0x5008


def test_nba_records_uses_record_base_and_skips_sparse_noise_rows() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "NBA Records": {
            "Record": {
                "Basic Info": [
                    _field("FIRSTNAME", 0x0C),
                    _field("LASTNAME", 0x20),
                    _field("DATA", 0x34, "float"),
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Record": {"address": 0x200, "chain": []}},
            "game_info": {"recordSize": 0x98},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    _write_ascii(memory, 0x7000 + 0x0C, "Wilt")
    _write_ascii(memory, 0x7000 + 0x20, "Chamberlain")
    _write_float(memory, 0x7000 + 0x34, 100.0)
    noisy = 0x7000 + 0x98
    _write_ascii(memory, noisy + 0x0C, "pson")
    _write_ascii(memory, noisy + 0x20, "t")
    _write_float(memory, noisy + 0x34, 7.4e31)
    valid_later = 0x7000 + 8 * 0x98
    _write_ascii(memory, valid_later + 0x0C, "Adrian")
    _write_ascii(memory, valid_later + 0x20, "Dantley")
    _write_float(memory, valid_later + 0x34, 23.0)

    items = model.scan_records("NBA Records", limit=9)

    assert [item.index for item in items] == [0, 8]
    assert [item.label for item in items] == ["Wilt Chamberlain 100.0", "Adrian Dantley 23.0"]


def test_sparse_nba_records_scan_is_not_capped_at_old_max() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "NBA Records": {
            "Record": {
                "Basic Info": [
                    _field("FIRSTNAME", 0x0C),
                    _field("LASTNAME", 0x20),
                    _field("DATA", 0x34, "float"),
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Record": {"address": 0x200, "chain": []}},
            "game_info": {"recordSize": 0x98},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    for index in range(0, 209, 8):
        addr = 0x7000 + index * 0x98
        _write_ascii(memory, addr + 0x0C, "First")
        _write_ascii(memory, addr + 0x20, "Last")
        _write_float(memory, addr + 0x34, float(index))

    items = model.scan_records("NBA Records")

    assert items[-1].index == 208


def test_history_scan_stops_at_zeroed_invalid_rows_without_cap() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1100] = 0x5000
    layout = {
        "NBA History": {
            "Season Awards": {
                "Awards": [
                    _field("TEAMCITY", 0x3D),
                    _field("TEAMNAME", 0x56),
                    _field("FIRSTNAME", 0x7A),
                    _field("LASTNAME", 0x8E),
                    _field("DATA", 0x18, "float"),
                    _field("TYPE", 0x10, "byte"),
                ]
            }
        }
    }
    layout["NBA History"]["Season Awards"]["Awards"][5]["versions"]["2K26"].update({"byteLength": 1})
    offsets = FakeOffsets(
        {
            "base_pointers": {"NBAHistory": {"address": 0x100, "chain": []}},
            "game_info": {"historySize": 0xA8},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    for index, first_name in enumerate(("Larry", "Magic")):
        addr = 0x5000 + index * 0xA8
        _write_ascii(memory, addr + 0x3D, "Boston")
        _write_ascii(memory, addr + 0x56, "Celtics")
        _write_ascii(memory, addr + 0x7A, first_name)
        _write_ascii(memory, addr + 0x8E, "Winner")
        _write_float(memory, addr + 0x18, 0.0)
        _write_byte(memory, addr + 0x10, 8)
    zeroed = 0x5000 + 2 * 0xA8
    _write_float(memory, zeroed + 0x18, 0.0)
    _write_byte(memory, zeroed + 0x10, 0)

    items = model.scan_records("NBA History")

    assert [item.index for item in items] == [0, 1]


def test_contiguous_domain_scan_is_not_capped_at_old_stadium_max() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "Stadiums": {
            "Vitals": {
                "Vitals": [
                    _field("ARENANAME", 0x00),
                    _field("CITYNAME", 0x20),
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Stadium": {"address": 0x200, "chain": []}},
            "game_info": {"stadiumSize": 0x80},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    for index in range(202):
        addr = 0x7000 + index * 0x80
        _write_ascii(memory, addr, f"Arena{index}")
        _write_ascii(memory, addr + 0x20, "City")

    items = model.scan_records("Stadiums")

    assert items[-1].index == 201


def test_history_summary_formats_season_and_team_pointer_logo() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1100] = 0x5000
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "NBA History": {
            "Season Awards": {
                "Awards": [
                    _field("SEASON", 0x20, "byte"),
                    _field("TEAMLOGO", 0x00, "uint64"),
                    _field("FIRSTNAME", 0x40),
                    _field("LASTNAME", 0x54),
                    _field("DATA", 0x68, "float"),
                    _field("TYPE", 0x10, "byte"),
                ]
            }
        },
        "Teams": {
            "Vitals": {
                "Vitals": [
                    _field("TEAMNAME", 0x00),
                ]
            }
        },
    }
    layout["NBA History"]["Season Awards"]["Awards"][0]["versions"]["2K26"].update(
        {"byteLength": 1, "season_year_base": 1791, "season_range": True}
    )
    layout["NBA History"]["Season Awards"]["Awards"][1]["versions"]["2K26"].update(
        {"byteLength": 8, "team_dropdown": True}
    )
    layout["NBA History"]["Season Awards"]["Awards"][5]["versions"]["2K26"].update({"byteLength": 1})
    offsets = FakeOffsets(
        {
            "base_pointers": {
                "NBAHistory": {"address": 0x100, "chain": []},
                "Team": {"address": 0x200, "chain": []},
            },
            "game_info": {"historySize": 0xA8, "teamSize": 0x100},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    _write_byte(memory, 0x5000 + 0x20, 193)
    _write_u64(memory, 0x5000, 0x7000)
    _write_ascii(memory, 0x5000 + 0x40, "Larry")
    _write_ascii(memory, 0x5000 + 0x54, "Bird")
    _write_float(memory, 0x5000 + 0x68, 0.0)
    _write_byte(memory, 0x5000 + 0x10, 8)
    _write_ascii(memory, 0x7000, "Celtics")

    item = model.scan_records("NBA History", limit=1)[0]
    values = model._record_summary_values_for_item("NBA History", item)

    assert values["Season"] == "1984-1985"
    assert values["Team Logo"] == "Celtics"



def _packaged_history_payload(domain: str, normalized_name: str) -> dict[str, Any]:
    offsets_path = Path(__file__).parent.parent / "nba2k_editor" / "core" / "Offsets" / "offsets_history.json"
    layout = json.loads(offsets_path.read_text())
    for section in layout[domain].values():
        for fields in section.values():
            for field in fields:
                if field.get("normalized_name") == normalized_name:
                    return field["versions"]["2K26"]
    raise AssertionError(f"missing {domain} field {normalized_name}")


def test_packaged_history_and_record_summary_numeric_fields_have_read_widths() -> None:
    expected_widths = {
        ("NBA History", "SEASON"): 1,
        ("NBA History", "TEAMLOGO"): 8,
        ("NBA History", "TYPE"): 1,
        ("NBA Records", "SIGNATUREID"): 4,
        ("NBA Records", "TEAMLOGO"): 8,
        ("NBA Records", "DAY"): 4,
        ("NBA Records", "MONTH"): 4,
        ("NBA Records", "YEAR"): 4,
    }

    for (domain, field_name), width in expected_widths.items():
        assert _packaged_history_payload(domain, field_name).get("byteLength") == width


def test_history_summary_rows_filter_by_requested_type() -> None:
    model = EditorDataModel(memory=FakeMemory(), offsets_api=FakeOffsets({}, {}), target_executable="NBA2K26.exe")
    mvp = RecordListItem(domain="NBA History", index=1, address=0x1000, label="MVP")
    rookie = RecordListItem(domain="NBA History", index=2, address=0x1100, label="ROY")
    model.loaded_items["NBA History"] = {mvp.display_label: mvp, rookie.display_label: rookie}
    type_by_index = {1: 8, 2: 9}
    season_by_index = {1: 200, 2: 201}
    model._read_named_raw_int = lambda _domain, item, name: type_by_index[item.index] if name == "TYPE" else season_by_index[item.index]  # type: ignore[method-assign]
    model._record_summary_values_for_item = lambda _domain, item, rank=None: {"label": item.label, "Rank": str(rank)}  # type: ignore[method-assign]

    rows = model.record_summary_rows("NBA History", limit=10, history_type=9)

    assert rows == [{"label": "ROY", "Rank": "1"}]


def test_record_summary_rows_read_full_requested_record_row_group() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "NBA Records": {
            "Record": {
                "Basic Info": [
                    _field("FIRSTNAME", 0x0C),
                    _field("LASTNAME", 0x20),
                    _field("DATA", 0x34, "float"),
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Record": {"address": 0x200, "chain": []}},
            "game_info": {"recordSize": 0x98},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")
    first = 0x7000 + 0x40
    second = 0x7000 + 0x80
    _write_ascii(memory, first + 0x0C, "Kobe")
    _write_ascii(memory, first + 0x20, "Bryant")
    _write_float(memory, first + 0x34, 81.0)
    _write_ascii(memory, second + 0x0C, "Wilt")
    _write_ascii(memory, second + 0x20, "Chamberlain")
    _write_float(memory, second + 0x34, 78.0)

    rows = model.record_summary_rows("NBA Records", limit=30, record_row_start=1, record_row_count=2, record_row_stride=0x40)

    assert rows == [
        {
            "Rank": "1",
            "First Name": "Kobe",
            "Last Name": "Bryant",
            "Signature ID": "--",
            "Team Logo": "--",
            "Year": "--",
            "Month": "--",
            "Day": "--",
            "Data": "81.0",
        },
        {
            "Rank": "2",
            "First Name": "Wilt",
            "Last Name": "Chamberlain",
            "Signature ID": "--",
            "Team Logo": "--",
            "Year": "--",
            "Month": "--",
            "Day": "--",
            "Data": "78.0",
        },
    ]
