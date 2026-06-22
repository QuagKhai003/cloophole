"""Interactive terminal menu — the control surface (ADR-0006).

@context  cloophole's UI is a terminal menu, not a web page or tray. Shows live
          status and lets you act (fire, queue, poll, report). The background
          watcher daemon runs separately; this just views/controls it.
@done     run(): clear-screen status header + numbered actions; reads state each
          redraw; calls fire/config/state. Pure stdlib (no curses/deps).
@todo     optional live auto-refresh (currently manual [r]).
@limits   Blocking input() loop; quitting leaves the daemon running.
@affects  Launched by CLI `open`/`menu`. Reuses state, config, fire, daemon,
          reset_parser, runner.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from . import config, fire, state
from .reset_parser import parse_reset


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
    print("=" * 44)
    print("  cloophole")
    print("=" * 44)
    print(f"  daemon        {'running' if running else 'STOPPED'}")
    print(f"  phase         {st.phase}")
    print(f"  reset in      {_countdown(st)}")
    print(f"  live session  {'yes' if st.live_session else 'no'}")
    print(f"  work dir      {st.work_dir or '(all live sessions)'}")
    print(f"  queued        {st.queue_note or '(fallback)'}")
    print(f"  auto-watch    {'on' if config.get('poll_enabled') else 'off'}"
          f"  (every {config.get('poll_interval_min')}m)")
    if st.last_error:
        print(f"  last error    {st.last_error}")
    print("-" * 44)


def _actions() -> None:
    print("  [1] Fire now")
    print("  [2] Set queue note")
    print("  [3] Report limit text  (arm a reset time)")
    print("  [4] Toggle auto-watch (auto-detect the limit)")
    print("  [5] Pin / clear work dir")
    print("  [6] Clear (back to WATCHING)")
    print("  [r] Refresh    [s] Stop daemon    [q] Quit menu")
    print("-" * 44)


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
            note = input("  what should it continue? > ").strip()
            st = state.load()
            st.queue_note = note or None
            state.save(st)
        elif choice == "3":
            text = input("  paste the limit message > ").strip()
            dt = parse_reset(text)
            if dt:
                st = state.load()
                st.reset_at = dt.isoformat()
                st.limit_text = text
                st.phase = state.WAITING
                state.save(st)
                print(f"  armed for {dt.astimezone():%Y-%m-%d %H:%M}")
            else:
                print("  could not parse a reset time.")
            input("  [enter] ")
        elif choice == "4":
            config.set_("poll_enabled", not config.get("poll_enabled"))
        elif choice == "5":
            p = input("  pin dir (blank = all live sessions) > ").strip()
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
            print("  daemon stopped.")
            input("  [enter] ")


def _do_fire(st: state.State) -> None:
    print("  firing --continue ...")
    res = fire.fire(st.work_dir, st.queue_note)
    if res.error:
        print(f"  error: {res.error}")
    else:
        print(f"  done (rc={res.returncode}, still_limited={res.still_limited})")
    input("  [enter] ")
