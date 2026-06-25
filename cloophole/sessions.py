"""Unified list of resumable Claude sessions: Windows claude.exe + WSL tmux panes.

@context  The GUI, the watcher, and the resume path all need ONE list of sessions
          regardless of whether claude runs as a native Windows process or inside
          WSL+tmux. Each session has a unique `key` (so multiple tmux panes sharing a
          folder are distinct), a display `folder`, a `label`, and routing info.
@done     list_all(cfg) -> [ {key, folder, label, kind, handle, path?} ].
@todo     macOS/Linux hosts.
@limits   Windows host only; WSL part needs WSL + tmux (best-effort).
@affects  Used by gui (display + tick boxes keyed by `key`), fire.resume (routes by
          key prefix), daemon._do_fire (auto-resume both kinds). Keys are stored in
          state.excluded_dirs / state.session_notes.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path, PurePosixPath
from typing import List

# Windows detection (winproc) is fast — run it FRESH every call so adds/removes show
# immediately. WSL detection spawns wsl.exe a few times (slow) — cache that part ~_TTL
# so we never block the watch thread or hammer wsl.exe.
_TTL = 3.0
_lock = threading.Lock()
_cache: dict = {"t": None, "v": [], "refreshing": False}


def list_all(cfg: dict) -> List[dict]:
    """Every detectable Claude session: Windows fresh + WSL cached. A caller never blocks
    on the slow WSL detection (while one thread refreshes it, others get the last result)."""
    if sys.platform != "win32":
        return []
    return _detect_windows(cfg) + _wsl_cached(cfg)


def _detect_windows(cfg: dict) -> List[dict]:
    from . import winproc
    out: List[dict] = []
    # Key Windows sessions by pid so multiple claude in ONE folder are controlled
    # separately. A reopened/re-run claude is a new pid -> a fresh row (not carried over).
    for pid, cwd, term in winproc.sessions_detail(cfg["claude_process_name"]):
        if not cwd:
            continue
        out.append({
            "key": f"win:{pid}",
            "folder": Path(cwd).name or cwd,
            "path": cwd,
            "label": f"{term or 'cmd'} · pid {pid}",
            "kind": "win",
            "handle": pid,
        })
    return out


def _wsl_cached(cfg: dict) -> List[dict]:
    with _lock:
        fresh = _cache["t"] is not None and (time.monotonic() - _cache["t"]) < _TTL
        if fresh or _cache["refreshing"]:
            return list(_cache["v"])
        _cache["refreshing"] = True
    out = None
    try:
        out = _detect_wsl(cfg)
    except Exception:
        out = None
    with _lock:
        if out is not None:
            _cache["v"] = out
        _cache["t"] = time.monotonic()
        _cache["refreshing"] = False
        return list(_cache["v"])


def _detect_wsl(cfg: dict) -> List[dict]:
    from . import wsl
    out: List[dict] = []
    try:
        for pane, path, where in wsl.claude_sessions():
            folder = PurePosixPath(path).name or path
            out.append({
                "key": f"wsl:{pane}",         # WSL+tmux: the pane id makes it unique
                "folder": f"{folder}  {where}",
                "path": path,
                "label": "WSL · tmux · click to flash",
                "kind": "wsl",
                "handle": pane,               # the %id, for send-keys + highlight
            })
        for host_pid, path in wsl.plain_sessions():
            folder = PurePosixPath(path).name or path
            out.append({
                "key": f"wslp:{host_pid}",    # plain WSL: the Windows host pid
                "folder": f"{folder}  (WSL)",
                "path": path,
                "label": f"WSL · pid {host_pid}",
                "kind": "wslp",
                "handle": host_pid,
            })
    except Exception:
        pass
    return out
