from __future__ import annotations

import unittest

from nba2k_editor.models.data_model import EditorDataModel


TEAM_POINTER_RVA = 132254856
TEAM_BASE = 0x50000000
TEAM_STATS_BASE_OFFSET = 0x46139E
TEAM_STATS_ROW_STRIDE = 0x3E


class TeamStatsMemory:
    base_addr = 0x140000000
    hproc = object()
    pointer_size = 8

    def __init__(self) -> None:
        self.reads: list[tuple[int, int]] = []
        self.writes: list[tuple[int, bytes]] = []

    def read_u64(self, address: int) -> int:
        if address == self.base_addr + TEAM_POINTER_RVA:
            return TEAM_BASE
        raise AssertionError(f"unexpected u64 read: 0x{address:X}")

    def read_bytes(self, address: int, width: int) -> bytes:
        self.reads.append((address, width))
        return (1234).to_bytes(width, "little")

    def write_bytes(self, address: int, data: bytes) -> None:
        self.writes.append((address, data))


class TeamStatsEditRoutingTests(unittest.TestCase):
    def test_team_stats_edit_reads_from_compact_table_not_normal_team_record(self) -> None:
        memory = TeamStatsMemory()
        model = EditorDataModel(memory=memory, target_executable="NBA2K26.exe")
        entry = model._field_by_normalized_name("Teams", "POINTS")
        assert entry is not None

        value = model.read_entry_value(entry, index=8)

        expected = TEAM_BASE + TEAM_STATS_BASE_OFFSET + 8 * TEAM_STATS_ROW_STRIDE
        self.assertEqual(1234, value["raw_value"])
        self.assertEqual([(expected, 2)], memory.reads)

    def test_team_stats_edit_writes_to_compact_table_not_normal_team_record(self) -> None:
        memory = TeamStatsMemory()
        model = EditorDataModel(memory=memory, target_executable="NBA2K26.exe")
        entry = model._field_by_normalized_name("Teams", "PA")
        assert entry is not None

        model.write_entry_value(entry, index=8, value=4321)

        expected = TEAM_BASE + TEAM_STATS_BASE_OFFSET + 8 * TEAM_STATS_ROW_STRIDE + 2
        self.assertEqual([(expected, (4321).to_bytes(2, "little"))], memory.writes)


if __name__ == "__main__":
    unittest.main()
