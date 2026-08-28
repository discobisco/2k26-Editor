from __future__ import annotations


class ReadOnlyMemoryBuffer:
    """Addressed read-only bytes captured from one contiguous process-memory range."""

    def __init__(self, start_address: int, data: bytes, *, pointer_size: int = 8) -> None:
        self.start_address = int(start_address)
        self._data = bytes(data)
        self.pointer_size = int(pointer_size)

    @classmethod
    def capture(cls, memory, start_address: int, length: int) -> "ReadOnlyMemoryBuffer":
        return cls(
            start_address,
            memory.read_bytes(int(start_address), int(length)),
            pointer_size=int(memory.pointer_size or 8),
        )

    def read_bytes(self, address: int, length: int) -> bytes:
        offset = int(address) - self.start_address
        end = offset + int(length)
        if offset < 0 or end > len(self._data):
            raise RuntimeError(
                f"buffer read outside captured range: 0x{int(address):X}+{int(length)}"
            )
        return self._data[offset:end]

    def read_uint32(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 4), "little")

    def read_u64(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 8), "little")

    def read_wstring(self, address: int, max_chars: int) -> str:
        return self.read_bytes(address, int(max_chars) * 2).decode("utf-16le", errors="ignore").split("\x00", 1)[0]

    def read_ascii(self, address: int, max_chars: int) -> str:
        return self.read_bytes(address, int(max_chars)).decode("ascii", errors="ignore").split("\x00", 1)[0]
