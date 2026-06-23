"""Type text into an existing Claude session's console (ADR-0012).

@context  The user chose to drive their OWN open `claude` session in place rather than
          spawn a new window. This crosses the original Golden Rule's "no keystroke
          injection" line by explicit owner decision (ADR-0012). The observe-only half
          stands: we still never READ Claude's internals/transcripts — we only WRITE
          input to a console the user already owns.
@done     send_text(pid, text): AttachConsole(pid) + WriteConsoleInput key events;
          types `text` (+ Enter) into that process's console. Windows-only.
@todo     mac/Linux (tmux send-keys / AppleScript) later.
@limits   Windows-only; needs the target to have a real/pseudo console. Best-effort:
          any failure returns False and the caller falls back / reports it.
@affects  Called by fire.fire_inject. Uses winproc.session_pids to map dir -> pid.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # pragma: no cover - import guard off Windows
    _k32 = None

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
KEY_EVENT = 0x0001
VK_RETURN = 0x0D


class _KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("UnicodeChar", ctypes.c_wchar),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class _EVENT_UNION(ctypes.Union):
    # KEY_EVENT_RECORD is the only event we build; pad to cover the full union.
    _fields_ = [("KeyEvent", _KEY_EVENT_RECORD), ("_pad", ctypes.c_byte * 20)]


class _INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_UNION)]


def _key(ch: str, down: bool) -> _INPUT_RECORD:
    rec = _INPUT_RECORD()
    rec.EventType = KEY_EVENT
    ke = rec.Event.KeyEvent
    ke.bKeyDown = down
    ke.wRepeatCount = 1
    ke.wVirtualKeyCode = VK_RETURN if ch == "\r" else 0
    ke.wVirtualScanCode = 0
    ke.UnicodeChar = ch
    ke.dwControlKeyState = 0
    return rec


def send_text(pid: int, text: str, submit: bool = True) -> bool:
    """Type `text` (then Enter if submit) into the console of process `pid`.

    Returns True if the input was written. Never raises — any failure is False.
    """
    if _k32 is None or not pid:
        return False
    _k32.AttachConsole.argtypes = [wintypes.DWORD]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _k32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    # Detach our own (hidden) console first, then borrow the target's.
    _k32.FreeConsole()
    if not _k32.AttachConsole(int(pid)):
        return False
    handle = None
    try:
        handle = _k32.CreateFileW(
            "CONIN$", GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if not handle or handle == INVALID_HANDLE_VALUE:
            return False
        seq = text + ("\r" if submit else "")
        records = []
        for ch in seq:
            records.append(_key(ch, True))
            records.append(_key(ch, False))
        arr = (_INPUT_RECORD * len(records))(*records)
        written = wintypes.DWORD(0)
        ok = _k32.WriteConsoleInputW(handle, arr, len(records), ctypes.byref(written))
        return bool(ok) and written.value > 0
    except OSError:
        return False
    finally:
        if handle and handle != INVALID_HANDLE_VALUE:
            _k32.CloseHandle(handle)
        _k32.FreeConsole()
