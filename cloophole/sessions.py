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
from pathlib import Path, PurePosixPath
from typing import List


def list_all(cfg: dict) -> List[dict]:
    """Every detectable Claude session, Windows + WSL. Newest detection each call."""
    out: List[dict] = []
    if sys.platform != "win32":
        return out
    from . import winproc, wsl

    for pid, cwd, term in winproc.sessions_detail(cfg["claude_process_name"]):
        if not cwd:
            continue
        out.append({
            "key": cwd,                       # Windows: the folder is the key
            "folder": Path(cwd).name or cwd,
            "path": cwd,
            "label": term or "",
            "kind": "win",
            "handle": pid,
        })

    try:
        for pane, path in wsl.claude_sessions():
            folder = PurePosixPath(path).name or path
            out.append({
                "key": f"wsl:{pane}",         # WSL+tmux: the pane id makes it unique
                "folder": f"{folder}  {pane}",
                "path": path,
                "label": "WSL · tmux",
                "kind": "wsl",
                "handle": pane,
            })
        for host_pid, path in wsl.plain_sessions():
            folder = PurePosixPath(path).name or path
            out.append({
                "key": f"wslp:{host_pid}",    # plain WSL: the Windows host pid
                "folder": f"{folder}  (WSL)",
                "path": path,
                "label": "WSL",
                "kind": "wslp",
                "handle": host_pid,
            })
    except Exception:
        pass
    return out
