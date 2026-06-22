"""Fire the resume: run `claude --continue` headless in the work directory.

@context  The action half of the Golden Rule: resume work only through the
          public `claude` CLI, never by touching the REPL or internals.
@done     build_prompt (queue note or fallback), fire() -> FireResult,
          still_limited text heuristic, FileNotFound/Timeout handling.
@todo     harden still_limited beyond text matching (Phase 6, B3).
@limits   Headless needs permission_mode=acceptEdits or it blocks (§9.5).
          still_limited is text-based (BUGS B3).
@affects  Called by daemon._do_fire and CLI fire-now. FireResult in DATA_MODEL.

Per product plan §3: we do NOT keystroke-inject into the visible REPL. We run
`claude -p --continue` in the recorded directory; --continue resumes the most
recent conversation there (same thread the open session belongs to) and the
queued note tells it what to do next. Headless needs a non-interactive
permission mode or it blocks on confirmations no one can answer (§9.5).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from . import config, subproc
from .reset_parser import is_limit_message

CREATE_NEW_CONSOLE = 0x00000010  # open the resume in its own visible window

FALLBACK_NOTE = "continue where you left off before the usage limit"


def build_prompt(queue_note: Optional[str]) -> str:
    note = (queue_note or "").strip() or FALLBACK_NOTE
    return (
        "Your usage limit reset. Resume the work automatically without waiting "
        f"for me: {note}. If the previous task is complete, move to the next "
        "phase."
    )


@dataclass
class FireResult:
    ok: bool
    still_limited: bool
    new_reset_text: Optional[str]
    stdout: str
    stderr: str
    returncode: Optional[int]
    error: Optional[str] = None


def fire_visible(work_dir: Optional[str], queue_note: Optional[str],
                 cfg: Optional[dict] = None) -> Optional[str]:
    """Resume in a VISIBLE terminal window so the user can watch Claude work.

    Launches `claude --continue [prompt]` in its own console (CREATE_NEW_CONSOLE) in
    the work dir, non-blocking. Still public-CLI only and never touches the user's
    existing REPL (Golden Rule). Returns None on launch, or an error string.
    """
    cfg = cfg or config.load()
    args = [cfg["claude_path"], "--continue"]
    note = (queue_note or "").strip()
    if note:
        args.append(build_prompt(queue_note))  # initial guidance for the resume
    flags = CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    try:
        subprocess.Popen(args, cwd=work_dir or None, creationflags=flags,
                         close_fds=True)
        return None
    except FileNotFoundError:
        return f"claude not found: {cfg['claude_path']}"
    except OSError as e:
        return str(e)


def fire(work_dir: Optional[str], queue_note: Optional[str], cfg: Optional[dict] = None) -> FireResult:
    cfg = cfg or config.load()
    prompt = build_prompt(queue_note)
    cmd = [
        cfg["claude_path"],
        "--continue",
        "-p",
        prompt,
        "--permission-mode",
        cfg["permission_mode"],
    ]
    try:
        proc = subproc.run(
            cmd,
            cwd=work_dir or None,
            capture_output=True,
            text=True,
            timeout=cfg.get("fire_timeout_sec", 1800),
        )
    except FileNotFoundError:
        return FireResult(False, False, None, "", "", None,
                          error=f"claude not found: {cfg['claude_path']}")
    except subprocess.TimeoutExpired:
        return FireResult(False, False, None, "", "", None, error="fire timed out")

    out = proc.stdout or ""
    err = proc.stderr or ""
    combined = f"{out}\n{err}"
    # If the output itself announces a limit, the reset didn't actually land.
    still_limited = is_limit_message(combined)
    return FireResult(
        ok=(proc.returncode == 0 and not still_limited),
        still_limited=still_limited,
        new_reset_text=combined if still_limited else None,
        stdout=out,
        stderr=err,
        returncode=proc.returncode,
    )
