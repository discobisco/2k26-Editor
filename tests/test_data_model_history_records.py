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
        self.read_u64_counts: dict[int, int] = {}

    def read_u64(self, addr: int) -> int:
        self.read_u64_counts[addr] = self.read_u64_counts.get(addr, 0) + 1
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

    def read_wstring(self, addr: int, max_chars: int) -> str:
        raw = self.read_bytes(addr, max_chars * 2)
        return raw.decode("utf-16le", errors="ignore").split("\x00", 1)[0]

    def write_bytes(self, addr: int, data: bytes) -> None:
        self.bytes_by_addr[addr] = bytes(data)

    def write_uint32(self, addr: int, value: int) -> None:
        self.write_bytes(addr, int(value).to_bytes(4, "little"))


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


def _write_wstring(memory: FakeMemory, addr: int, text: str, length: int = 20) -> None:
    memory.bytes_by_addr[addr] = text.encode("utf-16le")[: length * 2].ljust(length * 2, b"\x00")


def test_fixed_width_numeric_types_do_not_require_redundant_bytelength() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    layout = {
        "Players": {
            "Vitals": {
                "ID": [
                    {"normalized_name": "SIGNATUREID", "display_name": "Signature ID", "versions": {"2K26": {"address": 0x10, "type": "uint"}}},
                    {"normalized_name": "HEIGHTCM", "display_name": "Height (cm)", "versions": {"2K26": {"address": 0x14, "type": "ushort"}}},
                    {"normalized_name": "TEAMADDRESS", "display_name": "Team Address", "versions": {"2K26": {"address": 0x18, "type": "uint64"}}},
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Player": {"address": 0x200, "chain": []}},
            "game_info": {"playerSize": 0x100},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")
    memory.bytes_by_addr[0x7010] = (0x12345678).to_bytes(4, "little")
    memory.bytes_by_addr[0x7014] = (0x8765).to_bytes(2, "little")
    memory.u64_by_addr[0x7018] = 0xAABBCCDDEEFF0011

    fields = model.grouped_fields("Players")["Vitals"]["ID"]
    assert model.read_entry_value(fields[0], index=0)["raw_value"] == 0x12345678
    assert model.read_entry_value(fields[1], index=0)["raw_value"] == 0x8765
    assert model.read_entry_value(fields[2], index=0)["raw_value"] == 0xAABBCCDDEEFF0011


def test_dereferenced_fields_use_pointer_slot_then_field_offset() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.u64_by_addr[0x7000 + 0xFC8] = 0x9000
    _write_wstring(memory, 0x9000 + 0x82, "Philadelphia", length=24)
    layout = {
        "Teams": {
            "Team Stadium": {
                "Team Stadium": [
                    {
                        "normalized_name": "STADIUMCITYNAME",
                        "display_name": "Stadium City Name",
                        "versions": {
                            "2K26": {
                                "address": 0x82,
                                "type": "WString",
                                "length": 24,
                                "requiresDereference": True,
                                "dereferenceAddress": 0xFC8,
                            }
                        },
                    }
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Team": {"address": 0x200, "chain": []}},
            "game_info": {"teamSize": 0x1000},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    field = model.grouped_fields("Teams")["Team Stadium"]["Team Stadium"][0]
    assert model.read_entry_value(field, index=0)["raw_value"] == "Philadelphia"


def test_ptr_string_reads_pointer_target_but_remains_read_only() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.u64_by_addr[0x7000 + 0xB0] = 0x9000
    _write_ascii(memory, 0x9000, "Kentucky", length=40)
    layout = {
        "Players": {
            "Vitals": {
                "Vitals": [
                    {
                        "normalized_name": "COLLEGEFROM",
                        "display_name": "College/From",
                        "versions": {
                            "2K26": {
                                "address": 0xB0,
                                "type": "ptr_string",
                                "length": 40,
                                "unicode": False,
                                "from_address_dropdown": True,
                            }
                        },
                    }
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Player": {"address": 0x200, "chain": []}},
            "game_info": {"playerSize": 0x1000},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    field = model.grouped_fields("Players")["Vitals"]["Vitals"][0]
    value = model.read_entry_value(field, index=0)
    assert value["raw_value"] == "Kentucky"
    assert value["display_value"] == "Kentucky"
    assert value["writeable"] is False
    assert value["value_behavior"] == "implementation_required"


def test_player_current_team_address_displays_team_label() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.u64_by_addr[0x1300] = 0x9000
    memory.u64_by_addr[0x7000 + 0x60] = 0x9200
    memory.u64_by_addr[0x7000 + 0x1000 + 0x60] = 0x9300
    _write_ascii(memory, 0x9200, "Philadelphia", length=24)
    _write_ascii(memory, 0x9220, "76ers", length=24)
    _write_ascii(memory, 0x9300, "Boston", length=24)
    _write_ascii(memory, 0x9320, "Celtics", length=24)
    layout = {
        "Players": {
            "Vitals": {
                "Team": [
                    {
                        "normalized_name": "CURRENTTEAM",
                        "display_name": "Current Team",
                        "versions": {
                            "2K26": {
                                "address": 0x60,
                                "type": "uint64",
                                "team_address_dropdown": True,
                            }
                        },
                    }
                ]
            }
        },
        "Teams": {
            "Info": {
                "Info": [
                    _field("CITYNAME", 0x00, "string", 24),
                    _field("TEAMNAME", 0x20, "string", 24),
                ]
            }
        },
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {
                "Player": {"address": 0x200, "chain": []},
                "Team": {"address": 0x300, "chain": []},
            },
            "game_info": {"playerSize": 0x1000, "teamSize": 0x100},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")

    field = model.grouped_fields("Players")["Vitals"]["Team"][0]
    value = model.read_entry_value(field, index=0)
    assert value["raw_value"] == 0x9200
    assert value["display_value"] == "Philadelphia 76ers"

    model.selected_items["Players"] = RecordListItem("Players", 0, 0x7000, "Tyrese Maxey")
    assert model.selected_player_detail_values()["Team"] == "Philadelphia 76ers"

    player_a = RecordListItem("Players", 0, 0x7000, "Tyrese Maxey")
    player_b = RecordListItem("Players", 1, 0x8000, "Jayson Tatum")
    team_a = RecordListItem("Teams", 2, 0x9200, "Philadelphia 76ers")
    team_b = RecordListItem("Teams", 3, 0x9300, "Boston Celtics")
    model.loaded_items["Players"] = {item.display_label: item for item in (player_a, player_b)}
    model.loaded_items["Teams"] = {item.display_label: item for item in (team_a, team_b)}

    assert model.player_team_filter_options() == ("All Players", "[2] Philadelphia 76ers", "[3] Boston Celtics")
    assert model.player_item_labels_for_team_filter("All Players") == ["[0] Tyrese Maxey", "[1] Jayson Tatum"]
    assert model.player_item_labels_for_team_filter("[2] Philadelphia 76ers") == ["[0] Tyrese Maxey"]
    assert model.player_item_labels_for_team_filter("[3] Boston Celtics") == ["[1] Jayson Tatum"]

    current_team_read_counts = {0x7000 + 0x60: memory.read_u64_counts[0x7000 + 0x60], 0x8000 + 0x60: memory.read_u64_counts[0x8000 + 0x60]}
    assert model.player_item_labels_for_team_filter("[2] Philadelphia 76ers") == ["[0] Tyrese Maxey"]
    assert model.player_item_labels_for_team_filter("[3] Boston Celtics") == ["[1] Jayson Tatum"]
    assert memory.read_u64_counts[0x7000 + 0x60] == current_team_read_counts[0x7000 + 0x60]
    assert memory.read_u64_counts[0x8000 + 0x60] == current_team_read_counts[0x8000 + 0x60]


def test_grouped_fields_skips_hidden_payloads() -> None:
    layout = {
        "Players": {
            "Vitals": {
                "Body": [
                    {"normalized_name": "APPEARANCEDATA", "display_name": "Appearance Data", "versions": {"2K26": {"address": 0x78, "type": "binary", "hidden": True}}},
                    {"normalized_name": "HEIGHTCM", "display_name": "Height (cm)", "versions": {"2K26": {"address": 0x14, "type": "ushort"}}},
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Player": {"address": 0x200, "chain": []}},
            "game_info": {"playerSize": 0x100},
        },
        layout,
    )
    model = EditorDataModel(memory=FakeMemory(), offsets_api=offsets, target_executable="NBA2K26.exe")

    fields = model.grouped_fields("Players")["Vitals"]["Body"]
    assert [field.field["normalized_name"] for field in fields] == ["HEIGHTCM"]


def test_color_payload_reads_hex_and_writes_exact_bytes() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.bytes_by_addr[0x7010] = bytes.fromhex("2e3c70")
    layout = {
        "Jerseys": {
            "Colors": {
                "Colors": [
                    {"normalized_name": "PRIMARYCOLOR", "display_name": "Primary Color", "versions": {"2K26": {"address": 0x10, "type": "color", "length": 3}}},
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"Jersey": {"address": 0x200, "chain": []}},
            "game_info": {"jerseySize": 0x100},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")
    field = model.grouped_fields("Jerseys")["Colors"]["Colors"][0]

    value = model.read_entry_value(field, index=0)
    assert value["raw_value"] == bytes.fromhex("2e3c70")
    assert value["display_value"] == "#2E3C70"

    model.write_entry_value(field, index=0, value="#AABBCC")
    assert memory.bytes_by_addr[0x7010] == bytes.fromhex("aabbcc")


def test_result_score_reads_and_writes_two_float_components() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.bytes_by_addr[0x7018] = struct.pack("<f", 108.0)
    memory.bytes_by_addr[0x701C] = struct.pack("<f", 101.0)
    layout = {
        "NBA History": {
            "History Tab": {
                "History Tab": [
                    {"normalized_name": "RESULT", "display_name": "Result", "versions": {"2K26": {"address": 0x18, "offset2": 0x1C, "type": "result_score"}}},
                ]
            }
        }
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {"NBAHistory": {"address": 0x200, "chain": []}},
            "game_info": {"historySize": 0xA8},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")
    field = model.grouped_fields("NBA History")["History Tab"]["History Tab"][0]

    value = model.read_entry_value(field, index=0)
    assert value["raw_value"] == (108, 101)
    assert value["display_value"] == "108-101"

    model.write_entry_value(field, index=0, value="99-98")
    assert struct.unpack("<f", memory.bytes_by_addr[0x7018])[0] == 99.0
    assert struct.unpack("<f", memory.bytes_by_addr[0x701C])[0] == 98.0


def test_address_dropdown_reads_pointer_sized_value_and_displays_target_label() -> None:
    memory = FakeMemory()
    memory.u64_by_addr[0x1200] = 0x7000
    memory.u64_by_addr[0x1300] = 0x9000
    memory.u64_by_addr[0x7020] = 0x9000
    _write_wstring(memory, 0x9000, "Xfinity Mobile Arena", length=32)
    _write_wstring(memory, 0x9020, "Philadelphia", length=32)
    layout = {
        "Teams": {
            "Vitals": {
                "Info": [
                    {"normalized_name": "STADIUM", "display_name": "Stadium", "versions": {"2K26": {"address": 0x20, "type": "stadium_address_dropdown"}}},
                ]
            }
        },
        "Stadiums": {
            "Arena Info": {
                "Basic": [
                    {"normalized_name": "ARENANAME", "display_name": "Arena Name", "versions": {"2K26": {"address": 0x00, "type": "WString", "length": 32}}},
                    {"normalized_name": "CITYNAME", "display_name": "City Name", "versions": {"2K26": {"address": 0x20, "type": "WString", "length": 32}}},
                ]
            }
        },
    }
    offsets = FakeOffsets(
        {
            "base_pointers": {
                "Team": {"address": 0x200, "chain": []},
                "Stadium": {"address": 0x300, "chain": []},
            },
            "game_info": {"teamSize": 0x100, "stadiumSize": 0x200},
        },
        layout,
    )
    model = EditorDataModel(memory=memory, offsets_api=offsets, target_executable="NBA2K26.exe")
    field = model.grouped_fields("Teams")["Vitals"]["Info"][0]

    value = model.read_entry_value(field, index=0)
    assert value["raw_value"] == 0x9000
    assert value["display_value"] == "Xfinity Mobile Arena Philadelphia"


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
