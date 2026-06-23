"""runner + app-helper tests — process state logic without launching a tray."""

import os

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    from cloophole import paths, runner
    importlib.reload(paths)
    importlib.reload(runner)
    return runner, paths


def test_not_running_without_pid_file(env):
    runner, _ = env
    assert runner.pid() is None
    assert runner.is_running() is False


def test_is_running_checks_liveness(env, monkeypatch):
    runner, paths = env
    paths.pid_file().write_text("4321")
    from cloophole import winproc
    monkeypatch.setattr(winproc, "pid_alive", lambda p: p == 4321)
    assert runner.pid() == 4321
    assert runner.is_running() is True
    monkeypatch.setattr(winproc, "pid_alive", lambda p: False)
    assert runner.is_running() is False


def test_launch_skips_when_running(env, monkeypatch):
    runner, _ = env
    monkeypatch.setattr(runner, "is_running", lambda: True)
    launched = {"n": 0}
    monkeypatch.setattr(runner.subprocess, "Popen",
                        lambda *a, **k: launched.__setitem__("n", launched["n"] + 1))
    assert runner.launch() is False
    assert launched["n"] == 0


def test_launch_spawns_when_not_running(env, monkeypatch):
    runner, _ = env
    monkeypatch.setattr(runner, "is_running", lambda: False)
    calls = []
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: calls.append(a))
    assert runner.launch() is True
    assert calls and "daemon" in calls[0][0]


def test_stop_returns_false_when_idle(env):
    runner, _ = env
    assert runner.stop() is False


def test_cmd_open_clean_restarts_before_launch(monkeypatch):
    from cloophole import __main__ as m
    from cloophole import claude_hook, runner
    calls = []
    for fn in ("stop_gui", "stop", "kill_all", "launch", "launch_gui"):
        monkeypatch.setattr(runner, fn, lambda *a, _n=fn: (calls.append(_n), True)[1])
    monkeypatch.setattr(claude_hook, "hook_installed", lambda: True)
    monkeypatch.setattr(claude_hook, "install_hook", lambda: True)
    m.cmd_open([])
    # the sweep must happen before we launch a fresh daemon (no duplicates -> no flicker)
    assert calls.index("kill_all") < calls.index("launch") < calls.index("launch_gui")


def test_cmd_sessions_lists_dirs(monkeypatch, capsys):
    from cloophole import __main__ as m
    from cloophole import daemon
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (True, ["C:/a/proj"]))
    m.cmd_sessions([])
    out = capsys.readouterr().out
    assert "proj" in out and "C:/a/proj" in out


def test_cmd_sessions_none(monkeypatch, capsys):
    from cloophole import __main__ as m
    from cloophole import daemon
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    m.cmd_sessions([])
    assert "no live Claude session" in capsys.readouterr().out


def test_fire_visible_launches_continue_window(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    import sys
    from cloophole import config, fire
    importlib.reload(config)
    importlib.reload(fire)
    captured = {}
    monkeypatch.setattr(fire.subprocess, "Popen",
                        lambda args, **k: captured.update(args=args, kw=k))
    err = fire.fire_visible("C:/proj", "do the thing")
    assert err is None
    assert captured["args"][:2] == [config.get("claude_path"), "--continue"]
    assert "do the thing" in " ".join(captured["args"])  # note passed as guidance
    assert captured["kw"]["cwd"] == "C:/proj"
    if sys.platform == "win32":
        assert captured["kw"]["creationflags"] == 0x00000010  # CREATE_NEW_CONSOLE


def test_fire_inject_types_into_matching_session(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    from cloophole import config, fire, inject, winproc
    importlib.reload(config)
    importlib.reload(fire)
    monkeypatch.setattr(fire.sys, "platform", "win32")
    monkeypatch.setattr(winproc, "session_pids",
                        lambda name: [(111, "C:/a"), (222, "C:/b")])
    sent = {}
    monkeypatch.setattr(inject, "send_text",
                        lambda pid, text, **k: (sent.update(pid=pid, text=text), True)[1])
    err = fire.fire_inject("C:/b", "continue your work")
    assert err is None
    assert sent["pid"] == 222                       # the session whose folder matched
    assert "continue your work" in sent["text"]
    # no matching session -> a clear error, nothing sent
    assert "no live Claude session" in fire.fire_inject("C:/zzz", "x")


def test_gui_helpers():
    from cloophole import gui, state
    st = state.State(phase=state.WAITING, reset_at="2099-01-01T00:00:00+00:00")
    cd = gui._countdown(st)
    assert cd and cd != "-"
    assert gui._countdown(state.State()) == "-"


def test_spawn_silences_stdio(env, monkeypatch):
    """Windowless children must get DEVNULL stdio, else the GUI child crashes on
    its first write with no console (no window appears). Regression for B7."""
    runner, _ = env
    import subprocess
    captured = {}
    monkeypatch.setattr(runner.subprocess, "Popen",
                        lambda *a, **k: captured.update(k))
    runner._spawn("_gui")
    assert captured["stdin"] == subprocess.DEVNULL
    assert captured["stdout"] == subprocess.DEVNULL
    assert captured["stderr"] == subprocess.DEVNULL


def test_spawn_no_console_but_window_shows(env, monkeypatch):
    """CREATE_NO_WINDOW alone: not combined with DETACHED_PROCESS (0x8, which makes
    Win32 ignore no-window -> blank console, B8), and NOT with STARTUPINFO SW_HIDE
    (which also hides the GUI's own window -> no window, B10)."""
    import sys
    if sys.platform != "win32":
        import pytest
        pytest.skip("Windows-only spawn flags")
    runner, _ = env
    captured = {}
    monkeypatch.setattr(runner.subprocess, "Popen",
                        lambda *a, **k: captured.update(k))
    runner._spawn("_gui")
    flags = captured["creationflags"]
    assert flags & 0x08000000          # CREATE_NO_WINDOW set (no console)
    assert not (flags & 0x00000008)    # DETACHED_PROCESS NOT set (B8)
    # No SW_HIDE startupinfo, which would hide the GUI window itself (B10).
    si = captured.get("startupinfo")
    assert si is None or not (si.dwFlags & 0x00000001)  # STARTF_USESHOWWINDOW unset


def test_spawn_strips_pyinstaller_env(env, monkeypatch):
    """The onefile self-spawn must not pass PyInstaller's _MEIPASS2/_PYI_* to the
    child, or the child attaches to the parent's _MEI temp (deleted on exit) and
    the GUI window never appears. Regression for B11."""
    runner, _ = env
    monkeypatch.setenv("_MEIPASS2", "C:/Temp/_MEI123")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "x")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))  # keep a normal var
    captured = {}
    monkeypatch.setattr(runner.subprocess, "Popen",
                        lambda *a, **k: captured.update(k))
    runner._spawn("_gui")
    env_passed = captured["env"]
    assert "_MEIPASS2" not in env_passed
    assert not any(k.startswith("_PYI") for k in env_passed)
    assert "PATH" in env_passed  # ordinary vars are preserved


def test_kill_all_noop_from_source(env):
    runner, _ = env
    # tests aren't frozen -> no process sweep, just returns 0 (and clears pid files)
    assert runner.kill_all() == 0


def test_kill_all_spares_self_and_bootloader(env, monkeypatch):
    runner, _ = env
    import os
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\x\cloophole.exe", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    me = os.getpid()
    boot = 999001  # our PyInstaller bootloader (parent) — must NOT be killed
    from cloophole import winproc
    # (pid, ppid): self (child of boot), the bootloader, and two other instances
    monkeypatch.setattr(winproc, "list_procs",
                        lambda name: [(me, boot), (boot, 5), (4242, 9), (4243, 9)])
    killed = []
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: killed.append(a[0]))
    n = runner.kill_all()
    assert n == 2  # only the two unrelated instances
    flat = [" ".join(map(str, cmd)) for cmd in killed]
    assert not any(str(me) in c for c in flat)      # never ourselves
    assert not any(str(boot) in c for c in flat)    # never our bootloader (B15)
    assert any("4242" in c for c in flat) and any("4243" in c for c in flat)


def test_gui_launch_skips_when_running(env, monkeypatch):
    runner, _ = env
    monkeypatch.setattr(runner, "is_gui_running", lambda: True)
    spawned = {"n": 0}
    monkeypatch.setattr(runner, "_spawn", lambda sub: spawned.__setitem__("n", spawned["n"] + 1))
    assert runner.launch_gui() is False
    assert spawned["n"] == 0
