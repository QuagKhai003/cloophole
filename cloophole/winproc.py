"""Windows process detection for the live-session gate (product plan §6, §9.3).

@context  The OS half of the Golden Rule: confirm a live `claude` session and
          where it runs, purely by process inspection — never by reading Claude
          Code internals.
@done     find_pids (Toolhelp), process_cwd (PEB read), detect() combo.
@todo     mac/Linux equivalents (Phase 5, ADR-0003); exclude own child PID (B2).
@limits   Windows-only; PEB offsets are 64-bit (see BUGS B1). Best-effort: any
          failure returns None and the caller falls back to configured work_dir.
@affects  Imported by daemon.detect_session. Config key claude_process_name.

Two jobs, both via ctypes (zero third-party deps):
  1. Is any `claude` process running?  -> gate firing.
  2. What is that process's current working directory?  -> fire --continue
     in the right folder, since --continue is per-directory.

CWD discovery reads the target's PEB -> ProcessParameters -> CurrentDirectory
via NtQueryInformationProcess + ReadProcessMemory. This is the same technique
psutil uses; offsets below are the 64-bit layout. Best-effort: any failure
returns None and the caller falls back to the configured work_dir.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
else:  # pragma: no cover - non-Windows import guard
    _k32 = None
    _ntdll = None

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002

# 64-bit PEB layout offsets
_OFF_PEB_PROCESS_PARAMS = 0x20
_OFF_PARAMS_CURDIR = 0x38   # CURDIR.DosPath (UNICODE_STRING) starts here
_OFF_USTRING_LENGTH = 0x00  # USHORT
_OFF_USTRING_BUFFER = 0x08  # PWSTR


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_void_p),
        ("Reserved3", ctypes.c_void_p),
    ]


def find_pids(process_name: str) -> list[int]:
    """PIDs whose exe name matches process_name (case-insensitive)."""
    if _k32 is None:
        return []
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or snap == -1:
        return []
    pids: list[int] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        target = process_name.lower()
        while ok:
            if entry.szExeFile.lower() == target:
                pids.append(entry.th32ProcessID)
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return pids


def list_procs(process_name: str) -> list[tuple[int, int]]:
    """[(pid, parent_pid)] for processes whose exe matches process_name.

    Used to sweep cloophole's own processes safely: a PyInstaller onefile app is a
    bootloader (parent) + the real app (child), both named the same, so callers must
    know the parent to avoid tree-killing themselves.
    """
    if _k32 is None:
        return []
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or snap == -1:
        return []
    out: list[tuple[int, int]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        target = process_name.lower()
        while ok:
            if entry.szExeFile.lower() == target:
                out.append((entry.th32ProcessID, entry.th32ParentProcessID))
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return out


def _read(handle, address: int, size: int) -> Optional[bytes]:
    buf = (ctypes.c_char * size)()
    read = ctypes.c_size_t(0)
    ok = _k32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read)
    )
    if not ok or read.value != size:
        return None
    return bytes(buf)


def process_cwd(pid: int) -> Optional[str]:
    """Current working directory of a process, or None if unreadable."""
    if _k32 is None:
        return None
    handle = _k32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None
    try:
        pbi = PROCESS_BASIC_INFORMATION()
        ret_len = ctypes.c_ulong(0)
        status = _ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), ctypes.byref(ret_len)
        )
        if status != 0 or not pbi.PebBaseAddress:
            return None
        peb = ctypes.cast(pbi.PebBaseAddress, ctypes.c_void_p).value

        params_raw = _read(handle, peb + _OFF_PEB_PROCESS_PARAMS, 8)
        if not params_raw:
            return None
        params = int.from_bytes(params_raw, "little")

        len_raw = _read(handle, params + _OFF_PARAMS_CURDIR + _OFF_USTRING_LENGTH, 2)
        buf_raw = _read(handle, params + _OFF_PARAMS_CURDIR + _OFF_USTRING_BUFFER, 8)
        if not len_raw or not buf_raw:
            return None
        length = int.from_bytes(len_raw, "little")
        buffer = int.from_bytes(buf_raw, "little")
        if length == 0 or buffer == 0:
            return None

        data = _read(handle, buffer, length)
        if not data:
            return None
        path = data.decode("utf-16-le", errors="replace").rstrip("\\").rstrip()
        return path or None
    finally:
        _k32.CloseHandle(handle)


def detect(process_name: str) -> tuple[bool, Optional[str]]:
    """(any_running, first_readable_cwd). cwd may be None even if running."""
    pids = find_pids(process_name)
    if not pids:
        return False, None
    for pid in pids:
        cwd = process_cwd(pid)
        if cwd:
            return True, cwd
    return True, None


def pid_alive(pid: int) -> bool:
    """True if a process with this pid currently exists."""
    if _k32 is None or not pid:
        return False
    handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    _k32.CloseHandle(handle)
    return True


def all_procs() -> dict[int, int]:
    """{pid: parent_pid} for every process — to walk a claude.exe up to its terminal."""
    if _k32 is None:
        return {}
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or snap == -1:
        return {}
    out: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return out


def session_pids(process_name: str) -> list[tuple[int, Optional[str]]]:
    """[(pid, cwd)] for each live session — so the caller can target the right
    process (e.g. inject the resume into the session whose folder was ticked)."""
    return [(pid, process_cwd(pid)) for pid in find_pids(process_name)]


def detect_all(process_name: str) -> tuple[bool, list[str]]:
    """(any_running, unique readable cwds of every live session).

    Order preserved, duplicates dropped. Empty list means running but no cwd
    was readable (caller falls back to a pin or the inherited cwd).
    """
    pids = find_pids(process_name)
    if not pids:
        return False, []
    seen: list[str] = []
    for pid in pids:
        # one retry: the PEB read can flake for a tick, which would otherwise drop a
        # live session's folder and make the GUI list blink (B16).
        cwd = process_cwd(pid) or process_cwd(pid)
        if cwd and cwd not in seen:
            seen.append(cwd)
    return True, seen
