"""cloophole CLI — manual control surface over the state file (plan §6).

@context  The human entry point: report limits, queue work, inspect state, run
          the daemon/UI, install. Thin dispatch over the other modules.
@done     status/report/arm/queue/dir/clear/fire-now/poll/config/daemon/ui/
          install/uninstall/start/stop; main() arg dispatch.
@todo     —
@limits   install/uninstall are Windows-only in this build.
@affects  Reads/writes state + config; calls daemon.run, ui.serve, fire.fire,
          install_win. Commands listed below.

  cloophole status                 show state + countdown
  cloophole report "<limit text>"  parse reset time, arm -> WAITING
  cloophole queue "<note>"         set what to continue
  cloophole dir <path>             set work directory for --continue
  cloophole fire-now               fire immediately (ignores gate)
  cloophole poll on|off            idle quota auto-detection
  cloophole arm <when>             manually arm: "5:30 PM" / "in 2h" / ISO
  cloophole clear                  back to WATCHING, drop reset/limit
  cloophole config [key [value]]   show / get / set config
  cloophole daemon                 run the watcher loop (foreground)
  cloophole ui [port]              serve the local status page
  cloophole install [--task]       run-at-logon: Startup shim (no admin) or
                                   Task Scheduler (--task); also starts it now
  cloophole uninstall              remove shim + task, stop the daemon
  cloophole start | stop           start/stop the background daemon now
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import config, daemon, fire, state, ui
from .reset_parser import parse_reset


def _fmt_countdown(st: state.State) -> str:
    dt = st.reset_dt()
    if not dt:
        return ""
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "  (reset reached)"
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    return f"  (in {h}h {m:02d}m)" if h else f"  (in {m}m)"


def cmd_status(_args: list[str]) -> int:
    st = state.load()
    print(f"phase        {st.phase}")
    print(f"reset_at     {st.reset_at or '-'}{_fmt_countdown(st)}")
    print(f"live session {'yes' if st.live_session else 'no'}")
    print(f"work_dir     {st.work_dir or '(claude cwd)'}")
    print(f"queued       {st.queue_note or '(fallback)'}")
    print(f"last_fired   {st.last_fired or 'never'}")
    if st.last_error:
        print(f"last_error   {st.last_error}")
    return 0


def cmd_report(args: list[str]) -> int:
    if not args:
        print("usage: cloophole report \"<limit message text>\"")
        return 2
    text = " ".join(args)
    dt = parse_reset(text)
    if not dt:
        print("could not parse a reset time from that text.")
        print("  report is for Claude's limit message, e.g.:")
        print('    cloophole report "resets at 5:30 PM"')
        print('  to set WHAT to continue, use:  cloophole queue "<note>"')
        return 1
    st = state.load()
    st.reset_at = dt.isoformat()
    st.limit_text = text
    st.phase = state.WAITING
    state.save(st)
    print(f"armed -> WAITING, reset at {dt.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    return 0


def cmd_arm(args: list[str]) -> int:
    return cmd_report(args)


def cmd_queue(args: list[str]) -> int:
    st = state.load()
    if not args:
        print(st.queue_note or "(none)")
        return 0
    st.queue_note = " ".join(args)
    state.save(st)
    print(f"queued: {st.queue_note}")
    return 0


def cmd_dir(args: list[str]) -> int:
    st = state.load()
    if not args:
        print(st.work_dir or "(claude cwd)")
        return 0
    st.work_dir = args[0]
    state.save(st)
    print(f"work_dir: {st.work_dir}")
    return 0


def cmd_clear(_args: list[str]) -> int:
    st = state.load()
    st.phase = state.WATCHING
    st.reset_at = None
    st.limit_text = None
    st.last_error = None
    state.save(st)
    print("cleared -> WATCHING")
    return 0


def cmd_fire_now(_args: list[str]) -> int:
    st = state.load()
    print(f"firing in {st.work_dir or '(claude cwd)'} ...")
    res = fire.fire(st.work_dir, st.queue_note)
    if res.error:
        print(f"error: {res.error}")
        return 1
    print(f"rc={res.returncode} still_limited={res.still_limited}")
    if res.stdout.strip():
        print("--- stdout ---")
        print(res.stdout.strip()[:2000])
    if not res.still_limited and res.ok:
        st.last_fired = datetime.now(timezone.utc).isoformat()
        st.phase = state.WATCHING
        st.reset_at = None
        state.save(st)
    return 0 if res.ok else 1


def cmd_poll(args: list[str]) -> int:
    if not args or args[0] not in ("on", "off"):
        print(f"idle poll is {'on' if config.get('poll_enabled') else 'off'} "
              f"(every {config.get('poll_interval_min')} min)")
        print("usage: cloophole poll on|off")
        return 0
    config.set_("poll_enabled", args[0] == "on")
    print(f"idle poll {args[0]} (every {config.get('poll_interval_min')} min)")
    return 0


def cmd_config(args: list[str]) -> int:
    if not args:
        for k, v in config.load().items():
            print(f"{k} = {v}")
        return 0
    key = args[0]
    if len(args) == 1:
        print(config.get(key))
        return 0
    raw = args[1]
    val: object = raw
    if raw.lower() in ("true", "false"):
        val = raw.lower() == "true"
    elif raw.isdigit():
        val = int(raw)
    config.set_(key, val)
    print(f"{key} = {val}")
    return 0


def cmd_daemon(_args: list[str]) -> int:
    daemon.run()
    return 0


def cmd_ui(args: list[str]) -> int:
    port = int(args[0]) if args else None
    ui.serve(port)
    return 0


def cmd_install(args: list[str]) -> int:
    if sys.platform != "win32":
        print("install is Windows-only in this build")
        return 1
    from . import install_win
    method = "task" if "--task" in args else "shim"
    return install_win.install(method)


def cmd_uninstall(_args: list[str]) -> int:
    if sys.platform != "win32":
        print("uninstall is Windows-only in this build")
        return 1
    from . import install_win
    return install_win.uninstall()


def cmd_start(_args: list[str]) -> int:
    if sys.platform != "win32":
        print("start is Windows-only in this build")
        return 1
    from . import install_win
    return install_win.start_now()


def cmd_stop(_args: list[str]) -> int:
    if sys.platform != "win32":
        print("stop is Windows-only in this build")
        return 1
    from . import install_win
    return install_win.stop()


COMMANDS = {
    "status": cmd_status,
    "report": cmd_report,
    "arm": cmd_arm,
    "queue": cmd_queue,
    "dir": cmd_dir,
    "clear": cmd_clear,
    "fire-now": cmd_fire_now,
    "poll": cmd_poll,
    "config": cmd_config,
    "daemon": cmd_daemon,
    "ui": cmd_ui,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
    "start": cmd_start,
    "stop": cmd_stop,
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"unknown command: {cmd}\n")
        print(__doc__)
        return 2
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
