"""Detect & drive Claude running inside WSL + tmux (ADR-0013).

@context  An agent team often runs in WSL under tmux (split panes), one `claude`
          per pane. Those are LINUX processes — invisible to Windows process scans —
          so we detect/inject via tmux: `wsl tmux list-panes` to find claude panes,
          `wsl tmux send-keys -t <pane>` to type into a specific pane (exact, no focus
          games). Still public-CLI only (Golden Rule, ADR-0012 action side).
@done     claude_sessions() -> [(pane_id, cwd)]; send_keys(pane_id, text).
@todo     non-default WSL distro / custom tmux socket selection.
@limits   Windows-only host; needs WSL + a running tmux. Best-effort: any failure
          returns [] / False. A pane's command shows as `claude` or its version
          string (e.g. 2.1.186) — both are matched.
@affects  Used by sessions.list_all (detect) and fire.resume (inject when key is
          'wsl:<pane>'). Runs wsl.exe via subproc (no console window).
"""

from __future__ import annotations

import re
import sys
from typing import List, Tuple

from . import subproc

# A claude pane's current command is "claude" or the Claude Code version (2.1.186).
_IS_CLAUDE = re.compile(r"^(claude|\d+\.\d+\.\d+)")
_SEP = "\t"


def _wsl(args: list[str], timeout: int = 10):
    """Run `wsl.exe <args>` capturing output, no window. None on failure."""
    if sys.platform != "win32":
        return None
    try:
        return subproc.run(["wsl.exe", *args], capture_output=True,
                           text=True, timeout=timeout)
    except Exception:
        return None


def available() -> bool:
    p = _wsl(["tmux", "list-panes", "-a", "-F", "#{pane_id}"], timeout=6)
    return bool(p and p.returncode == 0)


def claude_sessions() -> List[Tuple[str, str]]:
    """[(pane_id, cwd)] for every tmux pane running claude in the default distro."""
    fmt = f"#{{pane_id}}{_SEP}#{{pane_current_command}}{_SEP}#{{pane_current_path}}"
    p = _wsl(["tmux", "list-panes", "-a", "-F", fmt])
    if not p or p.returncode != 0 or not p.stdout:
        return []
    out: List[Tuple[str, str]] = []
    for line in p.stdout.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 3:
            continue
        pane, cmd, path = (x.strip() for x in parts)
        if pane and _IS_CLAUDE.match(cmd):
            out.append((pane, path))
    return out


def send_keys(pane_id: str, text: str) -> bool:
    """Type `text` then Enter into tmux pane `pane_id`. True on success.

    Uses send-keys -l (literal) so the text isn't interpreted as key names, then a
    separate Enter — args are passed as a list, so no shell escaping is needed.
    """
    if not pane_id:
        return False
    lit = _wsl(["tmux", "send-keys", "-t", pane_id, "-l", text])
    if not lit or lit.returncode != 0:
        return False
    ent = _wsl(["tmux", "send-keys", "-t", pane_id, "Enter"])
    return bool(ent and ent.returncode == 0)
