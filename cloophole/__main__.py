"""cloophole CLI — terminal menu + background watcher control.

@context  The human entry point. `open` starts the background daemon and opens
          the terminal menu; the rest report limits, queue work, inspect state.
@done     open/menu/close/status/report/arm/queue/dir/clear/fire-now/poll/config/
          daemon/uninstall; main() arg dispatch.
@todo     —
@limits   open/close/uninstall are Windows-first.
@affects  Reads/writes state + config; calls runner, menu, daemon, fire.

  cloophole open                   start the daemon + open the terminal menu
  cloophole menu                   open the terminal menu
  cloophole close                  stop the background daemon
  cloophole status                 show state + countdown
  cloophole report "<limit text>"  parse reset time, arm -> WAITING
  cloophole queue "<note>"         set what to continue
  cloophole dir <path>             pin one dir (else fire all live sessions)
  cloophole fire-now               fire immediately (ignores gate)
  cloophole poll on|off            idle quota auto-detection
  cloophole arm <when>             manually arm: "5:30 PM" / "in 2h" / ISO
  cloophole clear                  back to WATCHING, drop reset/limit
  cloophole config [key [value]]   show / get / set config
  cloophole daemon                 run the watcher in the foreground
  cloophole uninstall              stop everything + remove app data
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import config, daemon, fire, state
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
    from . import runner
    st = state.load()
    print(f"daemon       {'running' if runner.is_running() else 'stopped'}")
    print(f"phase        {st.phase}")
    print(f"reset_at     {st.reset_at or '-'}{_fmt_countdown(st)}")
    print(f"live session {'yes' if st.live_session else 'no'}")
    print(f"work_dir     {st.work_dir or '(all live sessions)'}")
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


def cmd_open(_args: list[str]) -> int:
    """Ensure the background daemon is running, then open the terminal menu."""
    from . import menu, runner
    if not runner.is_running():
        runner.launch()
        print("cloophole daemon started in the background.")
    menu.run()
    return 0


def cmd_menu(_args: list[str]) -> int:
    """Open the terminal menu (does not auto-start the daemon)."""
    from . import menu
    menu.run()
    return 0


def cmd_close(_args: list[str]) -> int:
    """Stop the background daemon."""
    from . import runner
    if runner.stop():
        print("cloophole stopped.")
    else:
        print("cloophole was not running.")
    return 0


def cmd_uninstall(_args: list[str]) -> int:
    """Stop everything, then remove app data (and legacy autostart entries)."""
    import shutil
    from . import runner
    from .paths import home
    if runner.stop():
        print("stopped the running app.")
    if sys.platform == "win32":  # clear any legacy autostart from older builds
        try:
            from . import install_win
            install_win._uninstall_shim()
            install_win._uninstall_task(quiet=True)
        except Exception:
            pass
    try:
        shutil.rmtree(home())
        print(f"removed app data ({home()}).")
    except OSError as e:
        print(f"note: could not remove app data: {e}")

    if getattr(sys, "frozen", False):
        _self_remove_exe()
    else:
        print("done. To remove the package itself:  pip uninstall cloophole")
    return 0


def _self_remove_exe() -> None:
    """Frozen (.exe) uninstall: drop the PATH entry and delete the install dir.

    The running exe can't delete itself, so a detached shell removes the folder
    a moment after we exit."""
    import os
    import subprocess
    install_dir = os.path.dirname(sys.executable)
    # remove our dir from the user PATH
    try:
        ps = (
            "$d='%s';"
            "$p=[Environment]::GetEnvironmentVariable('Path','User');"
            "if($p -like \"*$d*\"){"
            "$n=($p.Split(';')|?{$_ -and $_ -ne $d}) -join ';';"
            "[Environment]::SetEnvironmentVariable('Path',$n,'User')}"
        ) % install_dir
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
        print("removed from PATH.")
    except Exception:
        pass
    # schedule deletion of the install dir after this process exits
    try:
        subprocess.Popen(
            ["cmd", "/c", "timeout /t 2 >nul & rmdir /s /q \"%s\"" % install_dir],
            creationflags=0x00000008 | 0x08000000,  # DETACHED | NO_WINDOW
            close_fds=True,
        )
        print(f"removing {install_dir} ...")
    except Exception:
        print(f"note: delete {install_dir} manually.")
    print("done.")


COMMANDS = {
    "open": cmd_open,
    "menu": cmd_menu,
    "close": cmd_close,
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
    "uninstall": cmd_uninstall,
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
