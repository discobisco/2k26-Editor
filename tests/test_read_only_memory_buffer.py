from __future__ import annotations

from nba2k_editor.memory.read_buffer import ReadOnlyMemoryBuffer


class SourceMemory:
    pointer_size = 8

    def __init__(self) -> None:
        self.reads: list[tuple[int, int]] = []

    def read_bytes(self, address: int, length: int) -> bytes:
        self.reads.append((address, length))
        return bytes(range(length))


def test_read_only_memory_buffer_captures_once_and_serves_addressed_reads() -> None:
    source = SourceMemory()

    memory = ReadOnlyMemoryBuffer.capture(source, 0x1000, 16)

    assert source.reads == [(0x1000, 16)]
    assert memory.read_bytes(0x1004, 4) == bytes((4, 5, 6, 7))
    assert memory.read_uint32(0x1000) == 0x03020100
    assert memory.read_u64(0x1008) == 0x0F0E0D0C0B0A0908