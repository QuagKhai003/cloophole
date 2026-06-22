"""runner + app-helper tests — process state logic without launching a tray."""

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
    assert calls and "_app" in calls[0][0]


def test_stop_returns_false_when_idle(env):
    runner, _ = env
    assert runner.stop() is False


def test_app_helpers():
    from cloophole import app, state
    img = app.make_image((1, 2, 3))
    assert img.size == (64, 64)
    st = state.State(phase=state.WAITING, reset_at="2099-01-01T00:00:00+00:00")
    title = app._title(st)
    assert title.startswith("cloophole — WAITING")
