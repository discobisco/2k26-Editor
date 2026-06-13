from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes

MODULE_NAME = "NBA2K26.exe"
HOOK_TARGETS: tuple[tuple[str, str], ...] = (
    ("NBA 2K26", "NBA2K26.exe"),
    ("NBA 2K25", "NBA2K25.exe"),
    ("NBA 2K24", "NBA2K24.exe"),
    ("NBA 2K23", "NBA2K23.exe"),
    ("NBA 2K22", "NBA2K22.exe"),
)

from .win32 import (
    PROCESS_ALL_ACCESS,
    TH32CS_SNAPMODULE,
    TH32CS_SNAPMODULE32,
    CreateToolhelp32Snapshot,
    Module32FirstW,
    Module32NextW,
    MODULEENTRY32W,
    OpenProcess,
    CloseHandle,
    ReadProcessMemory,
    WriteProcessMemory,
)


class GameMemory:
    """Utility class encapsulating process lookup and memory access."""

    def __init__(self, module_name: str = MODULE_NAME):
        self.module_name = module_name
        self.pid: int | None = None
        self.hproc: wintypes.HANDLE | None = None
        self.base_addr: int | None = None
        self.pointer_size = ctypes.sizeof(ctypes.c_void_p)

    def _detect_pointer_size(self, handle: wintypes.HANDLE | None) -> int:
        default = ctypes.sizeof(ctypes.c_void_p)
        if sys.platform != "win32" or not handle:
            return default
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except Exception:
            return default
        try:
            is_wow64_process2 = getattr(kernel32, "IsWow64Process2", None)
            if is_wow64_process2:
                process_machine = wintypes.USHORT()
                native_machine = wintypes.USHORT()
                is_wow64_process2.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(wintypes.USHORT),
                    ctypes.POINTER(wintypes.USHORT),
                ]
                is_wow64_process2.restype = wintypes.BOOL
                if is_wow64_process2(handle, ctypes.byref(process_machine), ctypes.byref(native_machine)):
                    if process_machine.value != 0:
                        return 4
                    if native_machine.value in (0x8664, 0xAA64):
                        return 8
                    return 4
        except Exception:
            pass
        try:
            is_wow64_process = getattr(kernel32, "IsWow64Process", None)
            if is_wow64_process:
                wow64 = wintypes.BOOL()
                is_wow64_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
                is_wow64_process.restype = wintypes.BOOL
                if is_wow64_process(handle, ctypes.byref(wow64)):
                    if wow64.value:
                        return 4
        except Exception:
            pass
        return default

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------
    @staticmethod
    def detect_running_module_name(preferred_module: str | None = None) -> str | None:
        candidates: list[str] = []
        if preferred_module:
            candidates.append(preferred_module)
        for _label, exe in HOOK_TARGETS:
            if exe and exe not in candidates:
                candidates.append(exe)
        if not candidates:
            return None
        try:
            import psutil  # type: ignore

            running = {
                proc.info.get("name")
                for proc in psutil.process_iter(["name"])
                if isinstance(proc.info, dict) and proc.info.get("name")
            }
            for candidate in candidates:
                if candidate in running:
                    return candidate
        except Exception:
            pass
        return None

    def find_pid(self) -> int | None:
        target_name = self.module_name or MODULE_NAME
        try:
            import psutil  # type: ignore

            for proc in psutil.process_iter(["name"]):
                name = proc.info.get("name") if isinstance(proc.info, dict) else None
                if name == target_name:
                    return proc.pid
        except Exception:
            pass
        return None

    def open_process(self) -> bool:
        """Open the game process and resolve its base address."""
        if sys.platform != "win32":
            self.close()
            return False
        pid = self.find_pid()
        if pid is None:
            self.close()
            return False
        if self.pid == pid and self.hproc:
            return True
        self.close()
        handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            self.close()
            return False
        base = self._get_module_base(pid, self.module_name)
        if base is None:
            CloseHandle(handle)
            self.close()
            return False
        self.pid = pid
        self.hproc = handle
        self.base_addr = base
        self.pointer_size = self._detect_pointer_size(handle)
        return True

    def close(self) -> None:
        """Close any open process handle and reset state."""
        if self.hproc:
            try:
                CloseHandle(self.hproc)
            except Exception:
                pass
        self.pid = None
        self.hproc = None
        self.base_addr = None
        self.pointer_size = ctypes.sizeof(ctypes.c_void_p)

    def _get_module_base(self, pid: int, module_name: str) -> int | None:
        if sys.platform != "win32":
            return None
        flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
        snap = CreateToolhelp32Snapshot(flags, pid)
        if not snap:
            return None
        me32 = MODULEENTRY32W()
        me32.dwSize = ctypes.sizeof(MODULEENTRY32W)
        try:
            if not Module32FirstW(snap, ctypes.byref(me32)):
                return None
            while True:
                if me32.szModule == module_name:
                    return ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                if not Module32NextW(snap, ctypes.byref(me32)):
                    break
        finally:
            CloseHandle(snap)
        return None

    # ------------------------------------------------------------------
    # Memory access helpers
    # ------------------------------------------------------------------
    def _check_open(self) -> None:
        if self.hproc is None or self.base_addr is None:
            raise RuntimeError("Game process not opened")

    def read_bytes(self, addr: int, length: int) -> bytes:
        """Read length bytes from absolute address addr."""
        self._check_open()
        buf = (ctypes.c_ubyte * length)()
        read_count = ctypes.c_size_t()
        ok = ReadProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(read_count))
        if not ok:
            winerr = ctypes.get_last_error()
            raise RuntimeError(f"Failed to read memory at 0x{addr:X} (error {winerr})")
        if read_count.value != length:
            raise RuntimeError(f"Partial read at 0x{addr:X}: {read_count.value}/{length} bytes")
        return bytes(buf)

    def write_bytes(self, addr: int, data: bytes) -> None:
        """Write data to absolute address addr."""
        length = len(data)
        self._check_open()
        buf = (ctypes.c_ubyte * length).from_buffer_copy(data)
        written = ctypes.c_size_t()
        ok = WriteProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(written))
        if not ok:
            winerr = ctypes.get_last_error()
            raise RuntimeError(f"Failed to write memory at 0x{addr:X} (error {winerr})")
        if written.value != length:
            raise RuntimeError(f"Partial write at 0x{addr:X}: {written.value}/{length} bytes")

    def read_uint32(self, addr: int) -> int:
        data = self.read_bytes(addr, 4)
        return struct.unpack("<I", data)[0]

    def write_uint32(self, addr: int, value: int) -> None:
        data = struct.pack("<I", value & 0xFFFFFFFF)
        self.write_bytes(addr, data)

    def read_u64(self, addr: int) -> int:
        data = self.read_bytes(addr, 8)
        return struct.unpack("<Q", data)[0]

    def read_wstring(self, addr: int, max_chars: int) -> str:
        """Read a UTF-16LE string of at most max_chars characters from addr."""
        raw = self.read_bytes(addr, max_chars * 2)
        try:
            s = raw.decode("utf-16le", errors="ignore")
        except Exception:
            return ""
        end = s.find("\x00")
        if end != -1:
            s = s[:end]
        return s

    def write_wstring_fixed(self, addr: int, value: str, max_chars: int) -> None:
        """Write a fixed length null-terminated UTF-16LE string at addr."""
        value = value[: max_chars - 1]
        encoded = value.encode("utf-16le") + b"\x00\x00"
        padded = encoded.ljust(max_chars * 2, b"\x00")
        self.write_bytes(addr, padded)

    # ASCII string helpers
    def read_ascii(self, addr: int, max_chars: int) -> str:
        """Read an ASCII string of up to max_chars bytes from addr."""
        raw = self.read_bytes(addr, max_chars)
        try:
            s = raw.decode("ascii", errors="ignore")
        except Exception:
            return ""
        end = s.find("\x00")
        if end != -1:
            s = s[:end]
        return s

    def write_ascii_fixed(self, addr: int, value: str, max_chars: int) -> None:
        """Write a fixed length null-terminated ASCII string at addr."""
        value = value[: max_chars - 1]
        encoded = value.encode("ascii", errors="ignore") + b"\x00"
        padded = encoded.ljust(max_chars, b"\x00")
        self.write_bytes(addr, padded)


__all__ = ["GameMemory"]
