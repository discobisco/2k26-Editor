"""
Process-level memory helper.

Wraps low-level Win32 calls to locate the NBA 2K process, resolve the module
base address, and perform reads/writes.
"""
from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes

from ..core.config import ALLOWED_MODULE_NAMES, MODULE_NAME
from ..logs.logging import MEMORY_LOGGER, LOG_ERROR, LOG_INFO
from .win32 import (
    PROCESS_ALL_ACCESS,
    TH32CS_SNAPMODULE,
    TH32CS_SNAPMODULE32,
    TH32CS_SNAPPROCESS,
    CreateToolhelp32Snapshot,
    Module32FirstW,
    Module32NextW,
    MODULEENTRY32W,
    PROCESSENTRY32W,
    Process32FirstW,
    Process32NextW,
    OpenProcess,
    CloseHandle,
    ReadProcessMemory,
    WriteProcessMemory,
)


class GameMemory:
    """Utility class encapsulating process lookup and memory access."""

    _dual_base_patched: bool = False

    def __init__(self, module_name: str = MODULE_NAME):
        self.module_name = module_name
        self.pid: int | None = None
        self.hproc: wintypes.HANDLE | None = None
        self.base_addr: int | None = None
        self.pointer_size = ctypes.sizeof(ctypes.c_void_p)
        self.last_dynamic_base_report: dict[str, object] | None = None
        self.last_dynamic_base_overrides: dict[str, int] | None = None

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

    def _log_event(self, level: int, op: str, addr: int, length: int, status: str, **extra: object) -> None:
        """Write a structured entry to the memory operation log."""
        try:
            parts: list[str] = [
                f"op={op}",
                f"addr=0x{int(addr):016X}",
                f"len={int(length)}",
                f"status={status}",
            ]
            if self.pid is not None:
                parts.append(f"pid={self.pid}")
            if self.base_addr is not None:
                rel = int(addr) - int(self.base_addr)
                sign = "-" if rel < 0 else ""
                parts.append(f"rva={sign}0x{abs(rel):X}")
            for key, value in extra.items():
                parts.append(f"{key}={value}")
            MEMORY_LOGGER.log(level, " | ".join(parts))
        except Exception:
            # Logging must never interfere with memory operations.
            pass

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------
    def find_pid(self) -> int | None:
        """Return the PID of the target process, or None if not found."""
        target_lower = (self.module_name or MODULE_NAME).lower()
        fallback_pid: int | None = None
        fallback_name: str | None = None
        # Prefer psutil when available
        try:
            import psutil  # type: ignore

            for proc in psutil.process_iter(["name"]):
                name_raw = proc.info.get("name") if isinstance(proc.info, dict) else None
                name = (name_raw or "").lower()
                if not name:
                    continue
                if name == target_lower:
                    self.module_name = name_raw or self.module_name or MODULE_NAME
                    return proc.pid
                if fallback_pid is None and name in ALLOWED_MODULE_NAMES:
                    fallback_pid = proc.pid
                    fallback_name = name_raw or fallback_name
        except Exception:
            pass
        if fallback_pid is not None:
            self.module_name = fallback_name or self.module_name or MODULE_NAME
            return fallback_pid
        # Fallback to toolhelp snapshot on Windows
        if sys.platform != "win32":
            return None
        if CreateToolhelp32Snapshot is None:
            return None
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap:
            return None
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        fallback_pid = None
        fallback_name = None
        try:
            success = Process32FirstW(snap, ctypes.byref(entry))
            while success:
                name = entry.szExeFile.lower()
                if name == target_lower:
                    self.module_name = entry.szExeFile
                    return entry.th32ProcessID
                if fallback_pid is None and name in ALLOWED_MODULE_NAMES:
                    fallback_pid = entry.th32ProcessID
                    fallback_name = entry.szExeFile
                success = Process32NextW(snap, ctypes.byref(entry))
        finally:
            CloseHandle(snap)
        if fallback_pid is not None:
            self.module_name = fallback_name or self.module_name or MODULE_NAME
            return fallback_pid
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
        """Return the base address of module_name in the given process."""
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
                if me32.szModule.lower() == module_name.lower():
                    return ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                if not Module32NextW(snap, ctypes.byref(me32)):
                    break
        finally:
            CloseHandle(snap)
        return None

    # ------------------------------------------------------------------
    # Memory access helpers
    # ------------------------------------------------------------------
    def _check_open(self, op: str | None = None, addr: int | None = None, length: int | None = None) -> None:
        if self.hproc is None or self.base_addr is None:
            if op is not None and addr is not None and length is not None:
                self._log_event(LOG_ERROR, op, addr, length, "process-closed", validation="not-open")
            raise RuntimeError("Game process not opened")

    def read_bytes(self, addr: int, length: int) -> bytes:
        """Read length bytes from absolute address addr."""
        self._check_open("read", addr, length)
        buf = (ctypes.c_ubyte * length)()
        read_count = ctypes.c_size_t()
        try:
            ok = ReadProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(read_count))
        except Exception as exc:
            self._log_event(
                LOG_ERROR,
                "read",
                addr,
                length,
                "exception",
                validation="exception",
                error=repr(exc),
            )
            raise
        if not ok:
            winerr = ctypes.get_last_error()
            self._log_event(
                LOG_ERROR,
                "read",
                addr,
                length,
                "failed",
                validation=f"win32={winerr}",
            )
            raise RuntimeError(f"Failed to read memory at 0x{addr:X} (error {winerr})")
        if read_count.value != length:
            self._log_event(
                LOG_ERROR,
                "read",
                addr,
                length,
                "failed",
                validation=f"bytes={read_count.value}",
            )
            raise RuntimeError(f"Partial read at 0x{addr:X}: {read_count.value}/{length} bytes")
        self._log_event(LOG_INFO, "read", addr, length, "success", validation="exact")
        return bytes(buf)

    def write_bytes(self, addr: int, data: bytes) -> None:
        """Write data to absolute address addr."""
        length = len(data)
        self._check_open("write", addr, length)
        buf = (ctypes.c_ubyte * length).from_buffer_copy(data)
        written = ctypes.c_size_t()
        try:
            ok = WriteProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(written))
        except Exception as exc:
            self._log_event(
                LOG_ERROR,
                "write",
                addr,
                length,
                "exception",
                validation="exception",
                error=repr(exc),
            )
            raise
        if not ok:
            winerr = ctypes.get_last_error()
            self._log_event(
                LOG_ERROR,
                "write",
                addr,
                length,
                "failed",
                validation=f"win32={winerr}",
            )
            raise RuntimeError(f"Failed to write memory at 0x{addr:X} (error {winerr})")
        if written.value != length:
            self._log_event(
                LOG_ERROR,
                "write",
                addr,
                length,
                "failed",
                validation=f"bytes={written.value}",
            )
            raise RuntimeError(f"Partial write at 0x{addr:X}: {written.value}/{length} bytes")
        self._log_event(LOG_INFO, "write", addr, length, "success", validation="exact")

    def write_pointer(self, addr: int, value: int) -> None:
        """Write a pointer-sized value to absolute address addr."""
        size = self.pointer_size or ctypes.sizeof(ctypes.c_void_p)
        if size <= 4:
            data = struct.pack("<I", int(value) & 0xFFFFFFFF)
        else:
            data = struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF)
        self.write_bytes(addr, data)

    def read_uint32(self, addr: int) -> int:
        data = self.read_bytes(addr, 4)
        return struct.unpack("<I", data)[0]

    def write_uint32(self, addr: int, value: int) -> None:
        data = struct.pack("<I", value & 0xFFFFFFFF)
        self.write_bytes(addr, data)

    def read_uint64(self, addr: int) -> int:
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
