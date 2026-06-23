"""cloophole CLI — desktop app window + background watcher control.

@context  The human entry point. `open` starts the background watcher and opens
          the app window (GUI); the rest report limits, queue work, inspect state.
@done     open/close/status/report/arm/queue/dir/clear/fire-now/poll/config/
          daemon/uninstall + internal _gui; main() arg dispatch.
@todo     —
@limits   open/close/uninstall are Windows-first; GUI needs a display.
@affects  Reads/writes state + config; calls runner, gui, daemon, fire.

  cloophole open                   start the watcher + open the app window
  cloophole close                  stop the watcher + close the window
  cloophole status                 show state + countdown
  cloophole sessions               list live Claude sessions (by folder)
  cloophole send "<text>"          type text into every live Claude session
  cloophole report "<limit text>"  parse reset time, arm -> WAITING
  cloophole queue "<note>"         set what to continue
  cloophole dir <path>             pin one dir (else fire all live sessions)
  cloophole fire-now               fire immediately (ignores gate)
  cloophole hook on|off            zero-quota limit auto-detect (Claude hook)
  cloophole poll on|off            idle quota auto-detection (opt-in; costs quota)
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

# Hardcoded so `cloophole help` still works in the frozen exe (optimize=2 strips
# module docstrings, which would otherwise make help print "None").
USAGE = """cloophole — auto-resume Claude Code after the usage limit resets.

  cloophole open                   start the watcher + open the app window
  cloophole close                  stop the watcher + close the window
  cloophole status                 show state + countdown
  cloophole sessions               list live Claude sessions (folder + terminal)
  cloophole send "<text>"          type text into every live Claude session
  cloophole report "<limit text>"  parse reset time, arm -> WAITING
  cloophole queue "<note>"         set what to continue
  cloophole dir <path>             pin one dir (else fire all live sessions)
  cloophole fire-now               fire immediately (ignores gate)
  cloophole hook on|off            zero-quota limit auto-detect (Claude hook)
  cloophole poll on|off            idle quota auto-detection (opt-in; costs quota)
  cloophole arm <when>             manually arm: "5:30 PM" / "in 2h" / ISO
  cloophole clear                  back to WATCHING, drop reset/limit
  cloophole config [key [value]]   show / get / set config
  cloophole daemon                 run the watcher in the foreground
  cloophole uninstall              stop everything + remove app data
"""


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
    state.save_runtime(st)
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
    state.save_user(st)
    print(f"queued: {st.queue_note}")
    return 0


def cmd_send(args: list[str]) -> int:
    """Type text into every live Claude session in place (ADR-0012). For testing."""
    from . import daemon, fire
    if not args:
        print('usage: cloophole send "<text>"')
        return 2
    text = " ".join(args)
    if sys.platform != "win32":
        print("send is Windows-only")
        return 1
    from . import inject, winproc
    detail = winproc.sessions_detail(config.load()["claude_process_name"])
    if not detail:
        print("no live Claude session with a readable folder.")
        return 1
    # Print ALL diagnostics first and flush — send_text may detach our console
    # (console-input path) and silence later prints.
    for pid, cwd, term in detail:
        d = inject.diagnose(pid)
        print(f"{cwd}  [{term}]  pid={pid}")
        print(f"   chain:   {' <- '.join(d['chain'])}")
        print(f"   windows: {d['windows'] or 'NONE found in ancestry'}")
        print(f"   hwnd:    {d['hwnd']}")
    sys.stdout.flush()
    results = []
    for pid, cwd, _t in detail:
        mode = inject.send_text(pid, text)
        results.append((cwd, mode, list(inject.last_reasons)))
    sent = sum(1 for _c, mode, _r in results if mode)
    try:
        for cwd, mode, reasons in results:
            print(f"  {cwd} -> {('via ' + mode) if mode else 'FAILED'}")
            for r in reasons:
                print(f"       {r}")
        print(f"typed into {sent} session(s).")
    except OSError:
        pass
    return 0 if sent else 1


def cmd_sessions(_args: list[str]) -> int:
    """List the live Claude sessions cloophole detects, named by folder + terminal."""
    from pathlib import Path

    if sys.platform == "win32":
        from . import winproc
        detail = winproc.sessions_detail(config.load()["claude_process_name"])
        if not detail:
            print("no live Claude session detected.")
            return 0
        print(f"{len(detail)} live Claude session(s):")
        for _pid, cwd, term in detail:
            where = f"{Path(cwd).name or cwd}   ({cwd})" if cwd else "(folder unreadable)"
            print(f"  - {where}" + (f"   [{term}]" if term else ""))
        return 0
    from . import daemon
    live, dirs = daemon.detect_sessions(config.load())
    if not live:
        print("no live Claude session detected.")
        return 0
    for d in dirs:
        print(f"  - {Path(d).name or d}   ({d})")
    return 0


def cmd_dir(args: list[str]) -> int:
    st = state.load()
    if not args:
        print(st.work_dir or "(claude cwd)")
        return 0
    st.work_dir = args[0]
    state.save_user(st)
    print(f"work_dir: {st.work_dir}")
    return 0


def cmd_clear(_args: list[str]) -> int:
    st = state.load()
    st.phase = state.WATCHING
    st.reset_at = None
    st.limit_text = None
    st.last_error = None
    state.save_runtime(st)
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
        state.save_runtime(st)
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
    """Clean-restart the background watcher and open the app window.

    Sweeps any existing/orphan cloophole processes first so EXACTLY ONE current
    daemon runs — duplicates (e.g. left over from an upgrade) would otherwise race
    on state.json and make the session list flicker (B14)."""
    from . import claude_hook, runner
    runner.stop_gui()
    runner.stop()
    runner.kill_all()  # drop orphan/duplicate daemons + windows (frozen)
    runner.launch()
    print("cloophole watcher started in the background.")
    # Zero-quota auto-detect: register the rate-limit hook in Claude's settings.
    try:
        newly = not claude_hook.hook_installed()
        claude_hook.install_hook()
        if newly:
            print(f"auto-detect on: registered a rate-limit hook in "
                  f"{claude_hook.settings_path()}")
            print("  (costs no quota; restart Claude Code to load it; "
                  "`cloophole hook off` to remove)")
    except Exception:
        pass
    runner.launch_gui()
    print("Opening cloophole...")
    return 0


def cmd_limit_signal(_args: list[str]) -> int:
    """Internal: invoked by Claude's StopFailure/rate_limit hook. Records the
    limit (reads the hook's JSON on stdin) so the daemon arms — zero quota."""
    from . import claude_hook
    claude_hook.record_signal()
    return 0


def cmd_hook(args: list[str]) -> int:
    """Register/remove the zero-quota rate-limit auto-detect hook."""
    from . import claude_hook
    if args and args[0] == "on":
        claude_hook.install_hook()
        print(f"limit auto-detect hook installed -> {claude_hook.settings_path()}")
        print("  restart Claude Code to load it.")
    elif args and args[0] == "off":
        print("removed." if claude_hook.uninstall_hook() else "no cloophole hook found.")
    else:
        print(f"limit auto-detect hook is {'ON' if claude_hook.hook_installed() else 'OFF'}")
        print("usage: cloophole hook on|off")
    return 0


def cmd_gui(_args: list[str]) -> int:
    """Internal: run the GUI window (spawned detached by `open`)."""
    from . import gui
    gui.run()
    return 0


def cmd_close(_args: list[str]) -> int:
    """Stop the background watcher (and close the window)."""
    from . import runner
    runner.stop_gui()
    stopped = runner.stop()
    swept = runner.kill_all()  # catch orphans the pid-file stops missed
    if stopped or swept:
        print("cloophole stopped.")
    else:
        print("cloophole was not running.")
    return 0


def cmd_uninstall(_args: list[str]) -> int:
    """Stop everything, then remove app data (and legacy autostart entries)."""
    import shutil
    from . import runner
    from .paths import home
    runner.stop_gui()
    if runner.stop():
        print("stopped the running app.")
    swept = runner.kill_all()  # sweep any leftover/orphan cloophole processes
    if swept:
        print(f"stopped {swept} leftover cloophole process(es).")
    try:  # remove our rate-limit hook from Claude's settings
        from . import claude_hook
        if claude_hook.uninstall_hook():
            print("removed the rate-limit hook from Claude settings.")
    except Exception:
        pass
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
    # Schedule deletion after this process exits. A running .exe can't delete
    # itself, so a detached shell waits, then retries rmdir up to 10x (the exe
    # file stays briefly locked after exit). cwd is forced to %TEMP% so it isn't
    # sitting inside the folder it's trying to remove.
    tmp = os.environ.get("TEMP", "C:\\Windows\\Temp")
    # %i (single) because this runs via `cmd /c`, not a .bat file.
    bat = (
        'ping 127.0.0.1 -n 3 >nul'
        ' & for /l %i in (1,1,10) do ('
        '   rmdir /s /q "{d}" 2>nul'
        '   & if not exist "{d}" exit'
        '   & ping 127.0.0.1 -n 2 >nul'
        ' )'
    ).format(d=install_dir)
    try:
        subprocess.Popen(
            ["cmd", "/c", bat],
            cwd=tmp,
            creationflags=0x00000008 | 0x08000000,  # DETACHED | NO_WINDOW
            close_fds=True,
        )
        print(f"removing {install_dir} ...")
    except Exception:
        print(f"note: delete {install_dir} manually.")
    print("done. (Open a NEW terminal - this one still has the old PATH.)")


COMMANDS = {
    "open": cmd_open,
    "_gui": cmd_gui,
    "limit-signal": cmd_limit_signal,
    "hook": cmd_hook,
    "close": cmd_close,
    "status": cmd_status,
    "sessions": cmd_sessions,
    "send": cmd_send,
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
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"unknown command: {cmd}\n")
        print(USAGE)
        return 2
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
