from __future__ import annotations

from nba2k_editor.models.data_model import EditorDataModel


SEASON_ID_SELECTOR_ROLE = "season_id_selector"
SEASON_ID_DETAIL_SOURCE = {
    "base_pointer": "PlayerSeasonStats",
    "stride": "playerSeasonStatsSize",
    "selector_role": SEASON_ID_SELECTOR_ROLE,
    "invalid_ids": [0, 65535],
}
class FakeMemory:
    base_addr: int | None = None
    pointer_size = 8

    def __init__(self) -> None:
        self.data: dict[int, int] = {}

    def open_process(self) -> bool:
        return True

    def read_bytes(self, addr: int, length: int) -> bytes:
        return bytes(self.data.get(addr + offset, 0) for offset in range(length))

    def write_u16(self, addr: int, value: int) -> None:
        raw = int(value).to_bytes(2, "little")
        for offset, byte in enumerate(raw):
            self.data[addr + offset] = byte

    def write_u64(self, addr: int, value: int) -> None:
        raw = int(value).to_bytes(8, "little")
        for offset, byte in enumerate(raw):
            self.data[addr + offset] = byte

    def read_u64(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 8), "little")


class FakeOffsets:
    def initialize_offsets(self, target_executable: str, force: bool = False) -> None:
        return None

    def get_active_offset_config(self, target_executable: str) -> dict:
        return {
            "base_pointers": {
                "Player": {"address": 1000, "direct_table": True},
                "PlayerSeasonStats": {"address": 5000, "direct_table": True},
            },
            "game_info": {
                "playerSize": 128,
                "playerSeasonStatsSize": 16,
            },
        }

    def get_editor_layout_for_super(self, domain: str) -> dict:
        assert domain == "Players"
        return {
            "Stats": {
                "Season IDs": [
                    {
                        "normalized_name": "STATSID1",
                        "display_name": "STATS_ID#1",
                        "stat_role": SEASON_ID_SELECTOR_ROLE,
                        "versions": {"2K26": {"address": 2, "type": "ushort"}},
                    },
                    {
                        "normalized_name": "POINTS",
                        "display_name": "Points",
                        "stat_role": "season_id_detail",
                        "selected_record_source": SEASON_ID_DETAIL_SOURCE,
                        "versions": {"2K26": {"address": 4, "type": "ushort"}},
                    },
                ]
            }
        }


def test_selected_player_season_stat_id_routes_detail_reads_to_selected_stats_row() -> None:
    memory = FakeMemory()
    memory.write_u16(1002, 7)  # player row selector: STATS_ID#1 -> stat row 7
    memory.write_u16(1002 + 4, 4095)  # poison value near the selector/player row
    memory.write_u16(5000 + 7 * 16 + 4, 1369)  # selected season-stat row Points

    model = EditorDataModel(memory=memory, offsets_api=FakeOffsets(), target_executable="NBA2K26.exe")
    entries = model.grouped_fields("Players")["Stats"]["Season IDs"]
    points_entry = next(entry for entry in entries if entry.display_name == "Points")

    value = model.read_entry_value(points_entry, index=0, stat_selector="STATS_ID#1")

    assert value["address"] == 5000 + 7 * 16 + 4
    assert value["raw_value"] == 1369
    assert value["display_value"] == 1369


def test_selected_player_season_stat_id_supports_chained_stats_table_pointer() -> None:
    class ChainedOffsets(FakeOffsets):
        def get_active_offset_config(self, target_executable: str) -> dict:
            return {
                "base_pointers": {
                    "Player": {"address": 1000, "direct_table": True, "absolute": True},
                    "PlayerSeasonStats": {
                        "address": 200,
                        "chain": [{"offset": 0x1D8, "dereference": True}],
                    },
                },
                "game_info": {
                    "playerSize": 128,
                    "playerSeasonStatsSize": 0x40,
                },
            }

    memory = FakeMemory()
    memory.base_addr = 10000
    memory.write_u16(1002, 7)
    memory.write_u64(10200, 3000)  # module_base + 200 -> LearnFrom roster base
    memory.write_u64(3000 + 0x1D8, 5000)  # roster + 0x1D8 -> career stats table
    memory.write_u16(5000 + 7 * 0x40 + 4, 1369)

    model = EditorDataModel(memory=memory, offsets_api=ChainedOffsets(), target_executable="NBA2K26.exe")
    entries = model.grouped_fields("Players")["Stats"]["Season IDs"]
    points_entry = next(entry for entry in entries if entry.display_name == "Points")

    value = model.read_entry_value(points_entry, index=0, stat_selector="STATS_ID#1")

    assert value["address"] == 5000 + 7 * 0x40 + 4
    assert value["raw_value"] == 1369


def test_michael_jordan_player_418_yearly_points_use_stat_id_table_stride() -> None:
    class JordanOffsets(FakeOffsets):
        def get_active_offset_config(self, target_executable: str) -> dict:
            return {
                "base_pointers": {
                    "Player": {"address": 1000, "direct_table": True},
                    "PlayerSeasonStats": {"address": 500000, "direct_table": True},
                },
                "game_info": {
                    "playerSize": 0x498,
                    "playerSeasonStatsSize": 0x40,
                },
            }

        def get_editor_layout_for_super(self, domain: str) -> dict:
            assert domain == "Players"
            selectors = [
                ("CURRENTYEARSTATID", "Current Year Stat ID", 0x128),
                ("STATSID1", "STATS_ID#1", 0x12A),
                ("STATSID2", "STATS_ID#2", 0x12C),
                ("STATSID3", "STATS_ID#3", 0x12E),
                ("STATSID4", "STATS_ID#4", 0x130),
                ("STATSID5", "STATS_ID#5", 0x132),
                ("STATSID6", "STATS_ID#6", 0x134),
            ]
            return {
                "Stats": {
                    "Season IDs": [
                        *[
                            {
                                "normalized_name": name,
                                "display_name": display,
                                "stat_role": SEASON_ID_SELECTOR_ROLE,
                                "versions": {"2K26": {"address": offset, "type": "ushort"}},
                            }
                            for name, display, offset in selectors
                        ],
                        {
                            "normalized_name": "POINTS",
                            "display_name": "Points",
                            "stat_role": "season_id_detail",
                            "selected_record_source": SEASON_ID_DETAIL_SOURCE,
                            "versions": {"2K26": {"address": 0x2C, "type": "bitfield", "bit_offset": 0, "bit_length": 12}},
                        },
                    ]
                }
            }

    memory = FakeMemory()
    player_index = 418
    player_addr = 1000 + player_index * 0x498
    stats_base = 500000
    stat_ids = [4005, 29, 3687, 3467, 3354, 3170, 3096]
    # Live evidence for player 418 Michael Jordan through LearnFrom career-stats table:
    # Current Year Stat ID -> 969; STATS_ID#1..#6 -> 2274, 2211, 1631, 2401, 2482, 2240.
    yearly_points = [969, 2274, 2211, 1631, 2401, 2482, 2240]
    for selector_offset, stat_id, points in zip(range(0x128, 0x136, 2), stat_ids, yearly_points, strict=True):
        memory.write_u16(player_addr + selector_offset, stat_id)
        memory.write_u16(stats_base + stat_id * 0x40 + 0x2C, points)
    # Poison the player row so the test fails if detail reads are made relative to selector addresses.
    for selector_offset in range(0x128, 0x136, 2):
        memory.write_u16(player_addr + selector_offset + 0x2C, 4095)

    model = EditorDataModel(memory=memory, offsets_api=JordanOffsets(), target_executable="NBA2K26.exe")
    entries = model.grouped_fields("Players")["Stats"]["Season IDs"]
    points_entry = next(entry for entry in entries if entry.display_name == "Points")

    got = [
        model.read_entry_value(points_entry, index=player_index, stat_selector=selector)["raw_value"]
        for selector in ["Current Year Stat ID", "STATS_ID#1", "STATS_ID#2", "STATS_ID#3", "STATS_ID#4", "STATS_ID#5", "STATS_ID#6"]
    ]

    assert got == yearly_points
