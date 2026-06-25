"""Windows process detection for the live-session gate (product plan §6, §9.3).

@context  The OS half of the Golden Rule: confirm a live `claude` session and
          where it runs, purely by process inspection — never by reading Claude
          Code internals.
@done     find_pids (Toolhelp), process_cwd (PEB read), detect() combo.
@todo     mac/Linux equivalents (Phase 5, ADR-0003); exclude own child PID (B2).
@limits   Windows-only; PEB offsets are 64-bit (see BUGS B1). Best-effort: any
          failure returns None and the caller falls back to configured work_dir.
@affects  detect_all -> daemon.detect_sessions (live gate + dirs). session_pids +
          host_terminal/sessions_detail -> fire.fire_inject (dir->pid) + gui session
          list + CLI sessions. all_procs/all_procs_named/list_procs -> runner.kill_all
          (sweep) + inject._terminal_hwnd (ancestor walk). Config claude_process_name.

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


def session_root_pids(process_name: str) -> list[int]:
    """ONE pid per Claude session. `claude` launches a parent claude.exe that spawns a
    child claude.exe, so a session shows as two processes; keep only the ROOT (whose
    parent is NOT claude.exe). Injecting into the root reaches the child via their
    shared console. Falls back to all matches if the parent map is unavailable."""
    named = all_procs_named()
    if not named:
        return find_pids(process_name)
    target = process_name.lower()
    claude = [pid for pid, (_ppid, nm) in named.items() if (nm or "").lower() == target]
    roots = []
    for pid in claude:
        ppid = named[pid][0]
        parent = named.get(ppid)
        if not parent or (parent[1] or "").lower() != target:  # parent isn't claude
            roots.append(pid)
    return roots


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
    """[(pid, cwd)] for each live session (one ROOT pid per session, no child dup)."""
    return [(pid, process_cwd(pid)) for pid in session_root_pids(process_name)]


# Friendly names for the terminals/shells a claude session may run under. Used to
# label sessions and to know which injection path fits (console vs paste).
_TERMINALS = {
    "windowsterminal.exe": "Windows Terminal",
    "code.exe": "VS Code",
    "conemu64.exe": "ConEmu", "conemuc64.exe": "ConEmu",
    "alacritty.exe": "Alacritty", "wezterm-gui.exe": "WezTerm",
    "cmd.exe": "cmd",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell",
    "bash.exe": "Git Bash", "sh.exe": "Git Bash", "mintty.exe": "mintty",
    "wsl.exe": "WSL", "wslhost.exe": "WSL",
    "conhost.exe": "Console",
}
# A window-owning terminal app beats an inner shell when both are in the ancestry.
_WINDOW_APPS = {"windowsterminal.exe", "code.exe", "conemu64.exe",
                "alacritty.exe", "wezterm-gui.exe", "mintty.exe"}


def all_procs_named() -> dict[int, tuple[int, str]]:
    """{pid: (parent_pid, exe_name)} for every process."""
    if _k32 is None:
        return {}
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or snap == -1:
        return {}
    out: dict[int, tuple[int, str]] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return out


def host_terminal(pid: int, named: Optional[dict] = None) -> Optional[str]:
    """Friendly label of the terminal hosting `pid` (walk its ancestors). The
    outermost window-owning app (e.g. Windows Terminal) wins over an inner shell."""
    named = all_procs_named() if named is None else named
    label = None
    cur = pid
    seen: set[int] = set()
    for _ in range(12):
        info = named.get(cur)
        if not info:
            break
        ppid, name = info
        low = (name or "").lower()
        if low in _TERMINALS:
            # window app always wins; otherwise take the first shell we see
            if low in _WINDOW_APPS or label is None:
                label = _TERMINALS[low]
        if not ppid or ppid in seen:
            break
        seen.add(cur)
        cur = ppid
    return label


def sessions_detail(process_name: str) -> list[tuple[int, Optional[str], Optional[str]]]:
    """[(pid, cwd, terminal_label)] for each live session (one ROOT pid per session)."""
    named = all_procs_named()
    return [(pid, process_cwd(pid), host_terminal(pid, named))
            for pid in session_root_pids(process_name)]


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
