"""Durable runtime state — the state machine's single source of truth.

@context  The State dataclass persisted to ~/.cloophole/state.json. Holds the
          phase, reset time, queue note, work dir, and last fire/error.
@done     State + reset_dt(), load/save (tolerant of partial/corrupt JSON).
@todo     —
@limits   PURE: no process/network. Phase set documented below + in DATA_MODEL.
@affects  Written by CLI + daemon; read by daemon, ui. Fields in DATA_MODEL.md.

Phases (per product plan §7):
  WATCHING  idle, no known limit
  WAITING   limit known, counting down to reset_at
  ARMED     reset reached but no live session; fire when one appears
  FIRING    actively running --continue
  FIRED     fired successfully this cycle (transient -> WATCHING)
  ERROR     last fire errored (transient -> WATCHING)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import paths

WATCHING = "WATCHING"
WAITING = "WAITING"
ARMED = "ARMED"
FIRING = "FIRING"
FIRED = "FIRED"
ERROR = "ERROR"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class State:
    phase: str = WATCHING
    reset_at: Optional[str] = None        # ISO8601 UTC
    queue_note: Optional[str] = None      # explicit "what to continue"
    work_dir: Optional[str] = None        # where to run --continue
    limit_text: Optional[str] = None      # raw parsed limit message
    last_fired: Optional[str] = None
    last_error: Optional[str] = None
    last_poll: Optional[str] = None       # last idle probe (ISO UTC)
    hook_dir: Optional[str] = None        # cwd from the rate-limit hook (fire fallback)
    recheck_at: list = field(default_factory=list)  # pending probe re-checks (ISO UTC)
    live_session: bool = False            # last observed
    live_dirs: list = field(default_factory=list)  # cwds of every live session (display)
    excluded_dirs: list = field(default_factory=list)  # sessions the user un-ticked (skip on fire)
    note_mode: str = "bulk"               # "bulk" (one note for all) | "per" (per-session)
    session_notes: dict = field(default_factory=dict)  # dir -> its own message (per mode)
    updated_at: str = field(default_factory=_now_iso)

    def reset_dt(self) -> Optional[datetime]:
        if not self.reset_at:
            return None
        try:
            return datetime.fromisoformat(self.reset_at)
        except ValueError:
            return None


def note_for(st: "State", work_dir: Optional[str]) -> Optional[str]:
    """The message to send to `work_dir`: its per-session note in 'per' mode (falling
    back to the bulk note), else the shared bulk note."""
    if st.note_mode == "per" and work_dir:
        n = (st.session_notes or {}).get(work_dir)
        if n and n.strip():
            return n
    return st.queue_note


def load() -> State:
    f = paths.state_file()
    if not f.exists():
        return State()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in State.__dataclass_fields__}
        return State(**known)
    except (json.JSONDecodeError, OSError, TypeError):
        return State()


def save(st: State) -> None:
    st.updated_at = _now_iso()
    # Atomic write (tmp + replace) so a concurrent reader (the daemon) never sees a
    # half-written file — the GUI now saves on every keystroke.
    import os
    f = paths.state_file()
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(asdict(st), indent=2), encoding="utf-8")
    os.replace(tmp, f)
