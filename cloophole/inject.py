"""Send the resume into an existing Claude session (ADR-0012).

@context  The user drives their OWN open `claude` session in place (no new window).
          This crosses the original Golden Rule's "no keystroke injection" line by
          explicit owner decision. The read-ban stands — we only WRITE input.
@done     send_text(pid, text): try WriteConsoleInput (classic conhost); else paste
          (clipboard + focus the hosting terminal window + Ctrl+V + Enter), which is
          what Windows Terminal / VS Code / ConPTY need.
@todo     mac/Linux (tmux send-keys / AppleScript).
@limits   Windows-only. Paste targets the terminal's ACTIVE tab — if the session is in
          a background tab of a multi-tab window it can't be singled out. Background
          callers (daemon) may be denied SetForegroundWindow by Windows' focus lock.
@affects  Called by fire.fire_inject. Uses winproc.session_pids / all_procs.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
else:  # pragma: no cover - import guard off Windows
    _k32 = _u32 = None

# ---- console-input path (classic conhost) ----------------------------------
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
KEY_EVENT = 0x0001
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56


class _KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
        ("UnicodeChar", ctypes.c_wchar), ("dwControlKeyState", wintypes.DWORD),
    ]


class _EVENT_UNION(ctypes.Union):
    _fields_ = [("KeyEvent", _KEY_EVENT_RECORD), ("_pad", ctypes.c_byte * 20)]


class _INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_UNION)]


def _key_rec(ch: str, down: bool) -> _INPUT_RECORD:
    rec = _INPUT_RECORD()
    rec.EventType = KEY_EVENT
    ke = rec.Event.KeyEvent
    ke.bKeyDown = down
    ke.wRepeatCount = 1
    ke.wVirtualKeyCode = VK_RETURN if ch == "\r" else 0
    ke.UnicodeChar = ch
    return rec


def _write_console_input(pid: int, text: str, submit: bool) -> bool:
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _k32.FreeConsole()
    if not _k32.AttachConsole(int(pid)):
        return False
    handle = None
    try:
        handle = _k32.CreateFileW("CONIN$", GENERIC_READ | GENERIC_WRITE,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                  OPEN_EXISTING, 0, None)
        if not handle or handle == INVALID_HANDLE_VALUE:
            return False
        seq = text + ("\r" if submit else "")
        recs = []
        for ch in seq:
            recs.append(_key_rec(ch, True))
            recs.append(_key_rec(ch, False))
        arr = (_INPUT_RECORD * len(recs))(*recs)
        written = wintypes.DWORD(0)
        ok = _k32.WriteConsoleInputW(handle, arr, len(recs), ctypes.byref(written))
        return bool(ok) and written.value > 0
    except OSError:
        return False
    finally:
        if handle and handle != INVALID_HANDLE_VALUE:
            _k32.CloseHandle(handle)
        _k32.FreeConsole()


# ---- clipboard-paste path (Windows Terminal / VS Code / ConPTY) ------------
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = ctypes.c_void_p


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


def _set_clipboard(text: str) -> bool:
    if not _u32.OpenClipboard(None):
        return False
    try:
        _u32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        _k32.GlobalAlloc.restype = wintypes.HGLOBAL
        _k32.GlobalLock.restype = wintypes.LPVOID
        hglob = _k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        ptr = _k32.GlobalLock(hglob)
        ctypes.memmove(ptr, data, len(data))
        _k32.GlobalUnlock(hglob)
        _u32.SetClipboardData(CF_UNICODETEXT, hglob)
        return True
    finally:
        _u32.CloseClipboard()


def _ancestors(pid: int, ppid: dict[int, int], depth: int = 8) -> set[int]:
    chain = {pid}
    cur = pid
    for _ in range(depth):
        p = ppid.get(cur)
        if not p or p in chain:
            break
        chain.add(p)
        cur = p
    return chain


def _terminal_hwnd(pid: int) -> int | None:
    """Top-level visible window of the terminal hosting `pid` (walk its ancestors)."""
    from . import winproc
    chain = _ancestors(pid, winproc.all_procs())
    found: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not _u32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value in chain:
            found.append((hwnd, _u32.GetWindowTextLengthW(hwnd)))
        return True

    _u32.EnumWindows(_cb, 0)
    if not found:
        return None
    found.sort(key=lambda t: -t[1])  # prefer a titled, real window
    return found[0][0]


def _key_input(vk: int, up: bool = False) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    return inp


def _send(inputs: list[_INPUT]) -> None:
    arr = (_INPUT * len(inputs))(*inputs)
    _u32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(_INPUT))


def _paste_into(pid: int, text: str, submit: bool) -> bool:
    hwnd = _terminal_hwnd(pid)
    if not hwnd:
        return False
    if not _set_clipboard(text):
        return False
    _u32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    _send([_key_input(VK_CONTROL), _key_input(VK_V),
           _key_input(VK_V, True), _key_input(VK_CONTROL, True)])
    time.sleep(0.08)
    if submit:
        _send([_key_input(VK_RETURN), _key_input(VK_RETURN, True)])
    return True


def diagnose(pid: int) -> dict:
    """What the injector sees for `pid` — for debugging why a send failed."""
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
    chain_pids = _ancestors(pid, named)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if _u32.IsWindowVisible(hwnd):
            wpid = wintypes.DWORD()
            _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value in chain_pids:
                n = _u32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                _u32.GetWindowTextW(hwnd, buf, n + 1)
                info["windows"].append(f"{wpid.value}:{buf.value!r}")
        return True

    _u32.EnumWindows(_cb, 0)
    info["hwnd"] = _terminal_hwnd(pid)
    return info


def send_text(pid: int, text: str, submit: bool = True) -> bool:
    """Put `text` (+ Enter) into the console of process `pid`. Never raises.

    Tries classic console input first (conhost); falls back to clipboard paste +
    Ctrl+V (Windows Terminal / VS Code / ConPTY).
    """
    if _k32 is None or not pid:
        return False
    try:
        if _write_console_input(pid, text, submit):
            return True
    except Exception:
        pass
    try:
        return _paste_into(pid, text, submit)
    except Exception:
        return False
