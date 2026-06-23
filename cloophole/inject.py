"""Send the resume into an existing Claude session (ADR-0012).

@context  The user drives their OWN open `claude` session in place (no new window).
          This crosses the original Golden Rule's "no keystroke injection" line by
          explicit owner decision. The read-ban stands — we only WRITE input.
@done     send_text(pid, text): try WriteConsoleInput (classic conhost / Win10); else
          clipboard paste (find the host window + Ctrl+V) for Windows Terminal / ConPTY
          / Win11. Reports which path worked + per-step failure reasons.
@todo     mac/Linux (tmux send-keys / AppleScript).
@limits   Windows-only. ALL Win32 calls set argtypes/restype — on 64-bit, unset args
          truncate HANDLE/HWND to 32-bit and silently fail.
@affects  send_text/diagnose CALLED BY fire.fire_inject + CLI `send`. USES
          winproc.all_procs_named (ancestor walk -> terminal window). NOTE: the
          console-input path FreeConsole()s then re-attaches the caller's console.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
else:  # pragma: no cover - import guard off Windows
    _k32 = _u32 = None

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ATTACH_PARENT_PROCESS = 0xFFFFFFFF
KEY_EVENT = 0x0001
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = ctypes.c_void_p


def _configure() -> None:
    """Set argtypes/restype on every call — critical on 64-bit (else handles
    truncate to 32-bit and calls fail silently)."""
    H, B, D, U = wintypes.HANDLE, wintypes.BOOL, wintypes.DWORD, wintypes.UINT
    _k32.AttachConsole.argtypes = [D]; _k32.AttachConsole.restype = B
    _k32.FreeConsole.argtypes = []; _k32.FreeConsole.restype = B
    _k32.CloseHandle.argtypes = [H]; _k32.CloseHandle.restype = B
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, D, D, ctypes.c_void_p, D, D, H]
    _k32.CreateFileW.restype = H
    _k32.WriteConsoleInputW.argtypes = [H, ctypes.c_void_p, D, ctypes.POINTER(D)]
    _k32.WriteConsoleInputW.restype = B
    _k32.GlobalAlloc.argtypes = [U, ctypes.c_size_t]; _k32.GlobalAlloc.restype = wintypes.HGLOBAL
    _k32.GlobalLock.argtypes = [wintypes.HGLOBAL]; _k32.GlobalLock.restype = wintypes.LPVOID
    _k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]; _k32.GlobalUnlock.restype = B
    _u32.OpenClipboard.argtypes = [wintypes.HWND]; _u32.OpenClipboard.restype = B
    _u32.EmptyClipboard.argtypes = []; _u32.EmptyClipboard.restype = B
    _u32.SetClipboardData.argtypes = [U, H]; _u32.SetClipboardData.restype = H
    _u32.CloseClipboard.argtypes = []; _u32.CloseClipboard.restype = B
    _u32.SetForegroundWindow.argtypes = [wintypes.HWND]; _u32.SetForegroundWindow.restype = B
    _u32.SendInput.argtypes = [U, ctypes.c_void_p, ctypes.c_int]; _u32.SendInput.restype = U
    _u32.IsWindowVisible.argtypes = [wintypes.HWND]; _u32.IsWindowVisible.restype = B
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(D)]
    _u32.GetWindowThreadProcessId.restype = D
    _u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]; _u32.GetWindowTextLengthW.restype = ctypes.c_int
    _u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextW.restype = ctypes.c_int
    _u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]; _u32.EnumWindows.restype = B


if _k32 is not None:
    _configure()


# ---- console-input path (classic conhost / Win10) --------------------------
class _KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
        ("UnicodeChar", ctypes.c_wchar), ("dwControlKeyState", wintypes.DWORD),
    ]


class _EVENT_UNION(ctypes.Union):
    # No padding: KEY_EVENT_RECORD is the full union, so INPUT_RECORD stays 20 bytes.
    # An over-sized record makes WriteConsoleInput fail with err=87 (invalid param).
    _fields_ = [("KeyEvent", _KEY_EVENT_RECORD)]


class _INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_UNION)]


def _rec(ch: str, down: bool) -> _INPUT_RECORD:
    r = _INPUT_RECORD()
    r.EventType = KEY_EVENT
    ke = r.Event.KeyEvent
    ke.bKeyDown = down
    ke.wRepeatCount = 1
    ke.wVirtualKeyCode = VK_RETURN if ch == "\r" else 0
    ke.UnicodeChar = ch
    return r


def _write_console_input(pid: int, text: str, submit: bool) -> tuple[bool, str]:
    _k32.FreeConsole()
    if not _k32.AttachConsole(int(pid)):
        err = ctypes.get_last_error()
        _k32.AttachConsole(ATTACH_PARENT_PROCESS)
        return False, f"AttachConsole err={err}"
    handle = None
    try:
        handle = _k32.CreateFileW("CONIN$", GENERIC_READ | GENERIC_WRITE,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                  OPEN_EXISTING, 0, None)
        if not handle or handle == INVALID_HANDLE_VALUE:
            return False, f"CONIN$ err={ctypes.get_last_error()}"
        seq = text + ("\r" if submit else "")
        recs = []
        for ch in seq:
            recs.append(_rec(ch, True))
            recs.append(_rec(ch, False))
        arr = (_INPUT_RECORD * len(recs))(*recs)
        written = wintypes.DWORD(0)
        ok = _k32.WriteConsoleInputW(handle, arr, len(recs), ctypes.byref(written))
        if not ok:
            return False, f"WriteConsoleInput err={ctypes.get_last_error()}"
        return True, f"wrote {written.value} records"
    finally:
        if handle and handle != INVALID_HANDLE_VALUE:
            _k32.CloseHandle(handle)
        _k32.FreeConsole()
        _k32.AttachConsole(ATTACH_PARENT_PROCESS)  # restore caller's console output


# ---- clipboard-paste path (Windows Terminal / ConPTY / Win11) --------------
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _set_clipboard(text: str) -> tuple[bool, str]:
    if not _u32.OpenClipboard(None):
        return False, f"OpenClipboard err={ctypes.get_last_error()}"
    try:
        _u32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        hglob = _k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not hglob:
            return False, "GlobalAlloc failed"
        ptr = _k32.GlobalLock(hglob)
        if not ptr:
            return False, "GlobalLock failed"
        ctypes.memmove(ptr, data, len(data))
        _k32.GlobalUnlock(hglob)
        if not _u32.SetClipboardData(CF_UNICODETEXT, hglob):
            return False, f"SetClipboardData err={ctypes.get_last_error()}"
        return True, "ok"
    finally:
        _u32.CloseClipboard()


def _ancestors(pid: int, ppid: dict, depth: int = 8) -> set:
    chain, cur = {pid}, pid
    for _ in range(depth):
        p = ppid.get(cur)
        if not p or p in chain:
            break
        chain.add(p)
        cur = p
    return chain


def _terminal_hwnd(pid: int) -> int | None:
    from . import winproc
    named = winproc.all_procs_named()
    chain = _ancestors(pid, {p: v[0] for p, v in named.items()})
    found: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if _u32.IsWindowVisible(hwnd):
            wpid = wintypes.DWORD()
            _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            # the SHELL/terminal that owns the console window, not explorer (the desktop)
            node = named.get(wpid.value)
            name = (node[1] if node else "").lower()
            if wpid.value in chain and name != "explorer.exe":
                found.append((hwnd, _u32.GetWindowTextLengthW(hwnd)))
        return True

    _u32.EnumWindows(_cb, 0)
    if not found:
        return None
    found.sort(key=lambda t: -t[1])
    return found[0][0]


def _ki(vk: int, up: bool = False) -> _INPUT:
    i = _INPUT()
    i.type = INPUT_KEYBOARD
    i.u.ki.wVk = vk
    i.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    return i


def _send_keys(seq: list[_INPUT]) -> None:
    arr = (_INPUT * len(seq))(*seq)
    _u32.SendInput(len(seq), ctypes.byref(arr), ctypes.sizeof(_INPUT))


def _paste_into(pid: int, text: str, submit: bool) -> tuple[bool, str]:
    import time
    hwnd = _terminal_hwnd(pid)
    if not hwnd:
        return False, "no terminal window in ancestry"
    ok, why = _set_clipboard(text)
    if not ok:
        return False, why
    _u32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    _send_keys([_ki(VK_CONTROL), _ki(VK_V), _ki(VK_V, True), _ki(VK_CONTROL, True)])
    time.sleep(0.08)
    if submit:
        _send_keys([_ki(VK_RETURN), _ki(VK_RETURN, True)])
    return True, f"pasted to hwnd={hwnd}"


# Last per-path failure reasons (for `cloophole send` diagnostics).
last_reasons: list[str] = []


def send_text(pid: int, text: str, submit: bool = True) -> str:
    """Put `text` (+ Enter) into the console of `pid`. Returns the method that worked
    ("console"/"paste") or "" on failure (reasons in `last_reasons`). Never raises."""
    global last_reasons
    last_reasons = []
    if _k32 is None or not pid:
        return ""
    for name, fn in (("console", _write_console_input), ("paste", _paste_into)):
        try:
            ok, why = fn(pid, text, submit)
        except Exception as e:  # never raise into callers
            ok, why = False, f"{type(e).__name__}: {e}"
        if ok:
            return name
        last_reasons.append(f"{name}: {why}")
    return ""


def diagnose(pid: int) -> dict:
    info: dict = {"pid": pid, "chain": [], "hwnd": None, "windows": []}
    if _k32 is None:
        return info
    from . import winproc
    named = winproc.all_procs_named()
    cur, seen = pid, set()
    for _ in range(12):
        node = named.get(cur)
        if not node:
            break
        ppid, name = node
        info["chain"].append(f"{cur}:{name}")
        if not ppid or ppid in seen:
            break
        seen.add(cur)
        cur = ppid
    info["hwnd"] = _terminal_hwnd(pid)
    return info
