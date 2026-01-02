"""
Runtime helpers to locate player/team bases directly from the running game.

The scan mirrors the standalone find_bases_dynamic.py script but is packaged
for reuse inside the editor so we can optionally override offsets.json bases
at launch.
"""
from __future__ import annotations

import ctypes
import sys
import time
from typing import Iterable, Iterator, Tuple
from concurrent.futures import ThreadPoolExecutor

try:
    import psutil
except Exception:  # pragma: no cover - psutil may not be present
    psutil = None

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
READABLE_PROTECT = {
    0x02,  # PAGE_READONLY
    0x04,  # PAGE_READWRITE
    0x08,  # PAGE_WRITECOPY
    0x20,  # PAGE_EXECUTE_READ
    0x40,  # PAGE_EXECUTE_READWRITE
    0x80,  # PAGE_EXECUTE_WRITECOPY
}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("th32ModuleID", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("GlblcntUsage", ctypes.c_ulong),
        ("ProccntUsage", ctypes.c_ulong),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", ctypes.c_ulong),
        ("hModule", ctypes.c_void_p),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
OpenProcess.restype = ctypes.c_void_p

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [ctypes.c_void_p]
CloseHandle.restype = ctypes.c_bool

ReadProcessMemory = kernel32.ReadProcessMemory
ReadProcessMemory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
ReadProcessMemory.restype = ctypes.c_bool

VirtualQueryEx = kernel32.VirtualQueryEx
VirtualQueryEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
VirtualQueryEx.restype = ctypes.c_size_t

CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
CreateToolhelp32Snapshot.restype = ctypes.c_void_p

Module32FirstW = kernel32.Module32FirstW
Module32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MODULEENTRY32W)]
Module32FirstW.restype = ctypes.c_bool

Module32NextW = kernel32.Module32NextW
Module32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MODULEENTRY32W)]
Module32NextW.restype = ctypes.c_bool


def _encode_wstring(text: str) -> bytes:
    return (text + "\x00").encode("utf-16le", errors="ignore")


def _find_process_pid(exe_name: str = "nba2k26.exe") -> int | None:
    exe_lower = exe_name.lower()
    if psutil:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name == exe_lower:
                    return int(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return None


def _get_module_base(pid: int, module_name: str) -> int | None:
    """Return the base address of module_name in the given process."""
    snap_flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
    snap = CreateToolhelp32Snapshot(snap_flags, pid)
    if not snap:
        return None
    entry = MODULEENTRY32W()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
    target_lower = module_name.lower()
    try:
        if not Module32FirstW(snap, ctypes.byref(entry)):
            return None
        while True:
            name = entry.szModule.lower()
            if name == target_lower:
                return ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value
            if not Module32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        CloseHandle(snap)
    return None


def _iter_memory_regions(handle: int, start: int, end: int) -> Iterator[Tuple[int, int, int]]:
    mbi = MEMORY_BASIC_INFORMATION()
    current = start
    while current < end:
        result = VirtualQueryEx(handle, ctypes.c_void_p(current), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not result:
            current += 0x1000
            continue
        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize)
        if size <= 0:
            current += 0x1000
            continue
        region_end = base + size
        state = int(mbi.State)
        raw_protect = int(mbi.Protect)
        base_protect = raw_protect & 0xFF
        if state == MEM_COMMIT and base_protect in READABLE_PROTECT and not (raw_protect & PAGE_GUARD):
            yield base, min(size, end - base), raw_protect
        current = max(region_end, current + 0x1000)


def _read_memory(handle: int, address: int, size: int) -> bytes | None:
    if size <= 0:
        return None
    buffer = (ctypes.c_char * size)()
    read = ctypes.c_size_t(0)
    ok = ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(read))
    if not ok or read.value == 0:
        return None
    return bytes(buffer[: read.value])


def _find_all(data: bytes, pattern: bytes) -> Iterable[int]:
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        yield idx
        start = idx + 2  # step by 2 bytes to stay UTF-16 aligned


def _scan_player_names(
    handle: int,
    stride: int,
    first_offset: int,
    last_offset: int,
    targets: list[Tuple[str, str]],
    *,
    search_low: int = 0,
    search_high: int = 0x7FFFFFFFFFFF,
    vote_break_threshold: int = 151,
    stop_on_first_hit: bool = False,
    skip_bases: set[int] | None = None,
) -> tuple[list[dict], list[int], bool]:
    hits: list[dict] = []
    base_candidates: list[int] = []
    patterns = [(_encode_wstring(last), _encode_wstring(first), first_offset, last_offset, f"{first} {last}") for first, last in targets]
    search_low = max(0, int(search_low))
    search_high = max(search_low + 0x1000, int(search_high))
    early_exit = False
    for region_base, region_size, _ in _iter_memory_regions(handle, search_low, search_high):
        buf = _read_memory(handle, region_base, region_size)
        if not buf:
            continue
        region_hits_before = len(hits)
        for last_bytes, first_bytes, fo, lo, label in patterns:
            for idx in _find_all(buf, last_bytes):
                candidate = region_base + idx - lo
                first_start = candidate + fo
                block = _read_memory(handle, first_start, len(first_bytes))
                if not block or not block.startswith(first_bytes):
                    continue
                hits.append({"target": label, "address": candidate})
        if len(hits) > region_hits_before:
            # derive votes incrementally and check threshold
            for hit in hits[region_hits_before:]:
                addr = int(hit["address"])
                for i in range(600):
                    base = addr - i * stride
                    if base < 0:
                        break
                    base_candidates.append(base)
            counts = _summarize_candidates(base_candidates, skip_bases)
            if stop_on_first_hit and not skip_bases:
                early_exit = True
                break
            if counts and counts[0][1] >= vote_break_threshold:
                early_exit = True
                break
    if not early_exit:
        for hit in hits:
            addr = int(hit["address"])
            for idx in range(600):
                base = addr - idx * stride
                if base < 0:
                    break
                base_candidates.append(base)
    return hits, base_candidates, early_exit


def _find_team_table(
    handle: int,
    team_stride: int,
    name_offset: int,
    name_length: int,
    expected_names: list[str],
    search_low: int = 0,
    search_high: int = 0x7FFFFFFFFFFF,
) -> list[int]:
    if not expected_names:
        return []
    first_pat = _encode_wstring(expected_names[0])
    candidates: list[int] = []
    for region_base, region_size, _ in _iter_memory_regions(handle, search_low, search_high):
        buf = _read_memory(handle, region_base, region_size)
        if not buf:
            continue
        start = 0
        while True:
            idx = buf.find(first_pat, start)
            if idx == -1:
                break
            table_base = region_base + idx - name_offset
            ok = True
            for i, name in enumerate(expected_names[1:], start=1):
                addr = table_base + i * team_stride + name_offset
                chunk = _read_memory(handle, addr, name_length * 2)
                if not chunk:
                    ok = False
                    break
                val = chunk.decode("utf-16le", errors="ignore").split("\x00", 1)[0].strip().lower()
                if not val or val != name.lower():
                    ok = False
                    break
            if ok:
                candidates.append(table_base)
            start = idx + 2
    return candidates


def _summarize_candidates(values: list[int], skip_bases: set[int] | None = None) -> list[tuple[int, int]]:
    from collections import Counter

    counts = Counter(values)
    if skip_bases:
        for base in skip_bases:
            counts.pop(base, None)
    return counts.most_common(5)


def _scan_players_with_ranges(
    handle: int,
    stride: int,
    first_offset: int,
    last_offset: int,
    targets: list[Tuple[str, str]],
    ranges: list[tuple[int, int]],
    vote_break_threshold: int = 151,
    *,
    stop_on_first_hit: bool = False,
    max_workers: int = 1,
    skip_bases: set[int] | None = None,
) -> tuple[list[dict], list[int]]:
    player_hits: list[dict] = []
    player_base_votes: list[int] = []
    if max_workers <= 1 or len(ranges) <= 1:
        for low, high in ranges:
            hits_before = len(player_hits)
            hits, votes, early = _scan_player_names(
                handle,
                stride,
                first_offset,
                last_offset,
                targets,
                search_low=low,
                search_high=high,
                vote_break_threshold=vote_break_threshold,
                stop_on_first_hit=stop_on_first_hit,
                skip_bases=skip_bases,
            )
            player_hits.extend(hits)
            player_base_votes.extend(votes)
            if early:
                break
            if stop_on_first_hit and len(player_hits) > hits_before and not skip_bases:
                break
        return player_hits, player_base_votes

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _scan_player_names,
                handle,
                stride,
                first_offset,
                last_offset,
                targets,
                search_low=low,
                search_high=high,
                vote_break_threshold=vote_break_threshold,
                stop_on_first_hit=stop_on_first_hit,
                skip_bases=skip_bases,
            )
            for low, high in ranges
        ]
        for fut in futures:
            hits, votes, _ = fut.result()
            player_hits.extend(hits)
            player_base_votes.extend(votes)
    return player_hits, player_base_votes


def _scan_teams_with_ranges(
    handle: int,
    team_stride: int,
    team_name_offset: int,
    team_name_length: int,
    teams: list[str],
    ranges: list[tuple[int, int]],
    *,
    max_workers: int = 1,
    skip_bases: set[int] | None = None,
) -> list[int]:
    team_candidates: list[int] = []
    if max_workers <= 1 or len(ranges) <= 1:
        for low, high in ranges:
            team_candidates = _find_team_table(
                handle,
                team_stride,
                team_name_offset,
                team_name_length,
                teams,
                search_low=low,
                search_high=high,
            )
            if team_candidates:
                if skip_bases and all(candidate in skip_bases for candidate in team_candidates):
                    continue
                break
        return team_candidates

    with ThreadPoolExecutor(max_workers=min(max_workers, len(ranges))) as executor:
        futures = [
            executor.submit(
                _find_team_table,
                handle,
                team_stride,
                team_name_offset,
                team_name_length,
                teams,
                search_low=low,
                search_high=high,
            )
            for low, high in ranges
        ]
        for fut in futures:
            candidates = fut.result()
            if candidates:
                team_candidates.extend(candidates)
    return team_candidates


def find_dynamic_bases(
    *,
    process_name: str = "nba2k26.exe",
    player_stride: int | None = None,
    team_stride: int | None = None,
    first_offset: int = 0x28,
    last_offset: int = 0x0,
    team_name_offset: int = 0x2E2,
    team_name_length: int = 24,
    player_targets: list[Tuple[str, str]] | None = None,
    expected_teams: list[str] | None = None,
    pid: int | None = None,
    player_base_hint: int | None = None,
    team_base_hint: int | None = None,
    search_window: int = 0x8000000,
    run_parallel: bool = True,
) -> tuple[dict[str, int], dict[str, object]]:
    """
    Scan the running game for player/team base addresses.

    Returns (bases, report) where bases carries any discovered base pointers.
    """
    if sys.platform != "win32":
        return {}, {"error": "Dynamic base scan requires Windows."}
    targets = player_targets or [("Tyrese", "Maxey"), ("Victor", "Wembanyama")]
    teams = expected_teams or [
        "76ers",
        "Bucks",
        "Bulls",
        "Cavaliers",
        "Celtics",
        "Clippers",
        "Grizzlies",
        "Hawks",
        "Heat",
        "Hornets",
    ]
    stride = player_stride or 1176
    t_stride = team_stride or 5672
    proc_pid = pid or _find_process_pid(process_name)
    if not proc_pid:
        return {}, {"error": f"{process_name} is not running."}
    exe_base = _get_module_base(proc_pid, process_name) if process_name else None
    handle = OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, proc_pid)
    if not handle:
        return {}, {"error": "Failed to open process for reading."}
    bases: dict[str, int] = {}
    report: dict[str, object] = {"pid": proc_pid}
    min_player_votes = 151
    skip_player_bases = {int(player_base_hint)} if player_base_hint else set()
    skip_team_bases = {int(team_base_hint)} if team_base_hint else set()
    start_ts = time.time()
    try:
        # Player scan (hinted window first, then full if no candidates)
        p_ranges: list[tuple[int, int]] = []
        if exe_base:
            p_ranges.append((max(0, int(exe_base) - max(0x10000, search_window)), int(exe_base)))
            p_ranges.append((int(exe_base), int(exe_base) + max(0x20000, search_window)))
        if player_base_hint:
            base_hint = int(player_base_hint)
            p_ranges.append((max(0, base_hint - max(0x10000, search_window)), base_hint))
            p_ranges.append((base_hint, base_hint + max(0x20000, search_window)))
        # Fall back to scanning above 4GB to avoid slow low-address sweeps.
        p_ranges.append((0x100000000, 0x7FFFFFFFFFFF))

        # Team scan (hinted window first, then full)
        t_ranges: list[tuple[int, int]] = []
        if exe_base:
            t_ranges.append((max(0, int(exe_base) - max(0x10000, search_window)), int(exe_base)))
            t_ranges.append((int(exe_base), int(exe_base) + max(0x20000, search_window)))
        if team_base_hint:
            base_hint = int(team_base_hint)
            back_low = max(0, base_hint - max(0x10000, search_window))
            fwd_high = base_hint + max(0x20000, search_window)
            t_ranges.append((back_low, base_hint))
            t_ranges.append((base_hint, fwd_high))
        t_ranges.append((0x100000000, 0x7FFFFFFFFFFF))
        player_hits: list[dict] = []
        player_base_votes: list[int] = []
        top_player: list[tuple[int, int]] = []
        top_player_all: list[tuple[int, int]] = []
        top_team: list[tuple[int, int]] = []
        top_team_all: list[tuple[int, int]] = []

        if run_parallel:
            with ThreadPoolExecutor(max_workers=2) as executor:
                fut_player = executor.submit(
                    _scan_players_with_ranges,
                    handle,
                    stride,
                    first_offset,
                    last_offset,
                    targets,
                    p_ranges,
                    vote_break_threshold=151,
                    stop_on_first_hit=True,
                    max_workers=4,
                    skip_bases=skip_player_bases,
                )
                fut_team = executor.submit(
                    _scan_teams_with_ranges,
                    handle,
                    t_stride,
                    team_name_offset,
                    team_name_length,
                    teams,
                    t_ranges,
                    max_workers=4,
                    skip_bases=skip_team_bases,
                )
                team_candidates = fut_team.result()
                top_team_all = _summarize_candidates(team_candidates)
                top_team = _summarize_candidates(team_candidates, skip_team_bases) if skip_team_bases else top_team_all
                player_hits: list[dict] = []
                player_base_votes: list[int] = []
                top_player: list[tuple[int, int]] = []
                top_player_all: list[tuple[int, int]] = []
                player_hits, player_base_votes = fut_player.result()
                top_player_all = _summarize_candidates(player_base_votes)
                top_player = _summarize_candidates(player_base_votes, skip_player_bases) if skip_player_bases else top_player_all
        else:
            team_candidates = _scan_teams_with_ranges(
                handle,
                t_stride,
                team_name_offset,
                team_name_length,
                teams,
                t_ranges,
                max_workers=4,
                skip_bases=skip_team_bases,
            )
            top_team_all = _summarize_candidates(team_candidates)
            top_team = _summarize_candidates(team_candidates, skip_team_bases) if skip_team_bases else top_team_all
            player_hits, player_base_votes = _scan_players_with_ranges(
                handle,
                stride,
                first_offset,
                last_offset,
                targets,
                p_ranges,
                vote_break_threshold=151,
                stop_on_first_hit=True,
                max_workers=4,
                skip_bases=skip_player_bases,
            )
            top_player_all = _summarize_candidates(player_base_votes)
            top_player = _summarize_candidates(player_base_votes, skip_player_bases) if skip_player_bases else top_player_all
    finally:
        CloseHandle(handle)
    report["elapsed_sec"] = round(time.time() - start_ts, 3)
    report["player_hits"] = [
        {"target": h["target"], "address": f"0x{int(h['address']):X}"} for h in player_hits
    ]
    report["player_candidates"] = [
        {"address": f"0x{addr:X}", "votes": votes} for addr, votes in top_player_all
    ]
    report["team_candidates"] = [{"address": f"0x{addr:X}", "votes": votes} for addr, votes in top_team_all]
    chosen_player = None
    if top_player and top_player[0][1] >= min_player_votes:
        chosen_player = top_player[0]
    elif top_player_all and top_player_all[0][1] >= min_player_votes:
        chosen_player = top_player_all[0]
    if chosen_player and "Player" not in bases:
        bases["Player"] = int(chosen_player[0])
    elif top_player_all:
        report["player_rejected_votes"] = top_player_all[0][1]
    chosen_team = top_team[0] if top_team else (top_team_all[0] if top_team_all else None)
    if chosen_team and "Team" not in bases:
        bases["Team"] = int(chosen_team[0])

    # If nothing was resolved, fall back to the offsets-file hints so we don’t exit empty-handed.
    if not bases and player_base_hint and team_base_hint:
        bases["Team"] = int(team_base_hint)
        bases["Player"] = int(player_base_hint)
        report["fallback_offsets"] = True

    return bases, report


__all__ = ["find_dynamic_bases"]
