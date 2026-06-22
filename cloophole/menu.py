"""Interactive terminal menu — the control surface (ADR-0006).

@context  cloophole's UI is a terminal menu, not a web page or tray. Plain-
          language status + actions; the background watcher runs separately.
@done     run(): clear-screen status + numbered actions with one-line help;
          reads state each redraw; calls fire/config/state. Stdlib only.
@todo     optional live auto-refresh (currently manual).
@limits   Blocking input() loop; quitting leaves the watcher running.
@affects  Launched by CLI `open`/`menu`. Reuses state, config, fire, runner,
          reset_parser.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from . import config, fire, state
from .reset_parser import parse_reset

# Internal phase -> plain-language one-liner shown to the user.
_PHASE_PLAIN = {
    state.WATCHING: "Watching for your usage limit",
    state.WAITING: "Limit reached - waiting for the reset time",
    state.ARMED: "Reset is due - waiting for a Claude window to open",
    state.FIRING: "Resuming your work now...",
    state.FIRED: "Just resumed your work",
    state.ERROR: "Something went wrong last time",
}


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _countdown(st: state.State) -> str:
    dt = st.reset_dt()
    if not dt:
        return "-"
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _header(st: state.State, running: bool) -> None:
    print("=" * 52)
    print("  cloophole")
    print("  Keeps your Claude Code work going after the")
    print("  usage limit resets - so you don't have to wait.")
    print("=" * 52)
    print(f"  Status          {_PHASE_PLAIN.get(st.phase, st.phase)}")
    if st.reset_at:
        print(f"  Resets in       {_countdown(st)}")
    print(f"  Running         {'yes - watching in the background' if running else 'no - not watching'}")
    print(f"  Claude open now {'yes' if st.live_session else 'no'}")
    print(f"  Resume what     {st.queue_note or 'pick up where you left off'}")
    print(f"  Resume where    {st.work_dir or 'every open Claude window'}")
    print(f"  Auto-detect     {'on - finds the limit by itself' if config.get('poll_enabled') else 'off - you enter it yourself'}")
    if st.last_error:
        print(f"  Last problem    {st.last_error}")
    print("-" * 52)


def _actions() -> None:
    print("  What do you want to do?")
    print()
    print("  [1] Resume now          continue your Claude work right now")
    print("  [2] Set what to resume  a note telling it what to continue")
    print("  [3] Enter limit time    if you know when it resets (e.g. 5:30 PM)")
    auto = "on" if config.get("poll_enabled") else "off"
    print(f"  [4] Auto-detect ({auto})    let it find the limit on its own")
    print("  [5] Choose folder       resume in one project (default: all)")
    print("  [6] Reset status        clear the limit and start watching again")
    print()
    print("  [r] Refresh   [s] Stop & quit   [q] Close menu (keeps running)")
    print("-" * 52)


def run() -> None:
    from . import runner
    while True:
        st = state.load()
        _clear()
        _header(st, runner.is_running())
        _actions()
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "q":
            return
        elif choice == "r":
            continue
        elif choice == "1":
            _do_fire(st)
        elif choice == "2":
            note = input("  What should it continue? (blank = pick up where you left off)\n  > ").strip()
            st = state.load()
            st.queue_note = note or None
            state.save(st)
        elif choice == "3":
            print("  Paste Claude's limit message, or type a time like '5:30 PM'")
            text = input("  > ").strip()
            dt = parse_reset(text)
            if dt:
                st = state.load()
                st.reset_at = dt.isoformat()
                st.limit_text = text
                st.phase = state.WAITING
                state.save(st)
                print(f"  Got it - will resume after {dt.astimezone():%I:%M %p on %b %d}.")
            else:
                print("  Couldn't read a time from that. Try e.g. 'resets at 5:30 PM'.")
            input("  [enter to go back] ")
        elif choice == "4":
            on = not config.get("poll_enabled")
            config.set_("poll_enabled", on)
            print(f"  Auto-detect is now {'ON' if on else 'OFF'}.")
            input("  [enter to go back] ")
        elif choice == "5":
            print("  Folder to resume in (blank = every open Claude window):")
            p = input("  > ").strip()
            st = state.load()
            st.work_dir = p or None
            state.save(st)
        elif choice == "6":
            st = state.load()
            st.phase = state.WATCHING
            st.reset_at = None
            st.limit_text = None
            st.last_error = None
            state.save(st)
        elif choice == "s":
            runner.stop()
            print("  Stopped. cloophole is no longer watching.")
            input("  [enter to close] ")
            return


def _do_fire(st: state.State) -> None:
    print("  Resuming your Claude work...")
    res = fire.fire(st.work_dir, st.queue_note)
    if res.error:
        print(f"  Couldn't resume: {res.error}")
    elif res.still_limited:
        print("  Still limited - the reset hasn't landed yet. Will keep watching.")
    else:
        print("  Done - told Claude to keep going.")
    input("  [enter to go back] ")
