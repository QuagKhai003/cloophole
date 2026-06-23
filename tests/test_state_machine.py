"""State-machine transition tests with detection + fire stubbed out."""

import os
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    from cloophole import daemon, state
    importlib.reload(state)
    importlib.reload(daemon)
    return daemon, state


def _cfg():
    # These tests exercise the headless fire engine (still_limited re-arm, dir
    # selection), which lives behind resume_mode="headless"; the inject/window paths
    # are covered separately (test_runner.test_fire_*).
    from cloophole import config
    cfg = config.load()
    cfg["resume_mode"] = "headless"
    return cfg


def test_waiting_no_session_goes_armed(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda cfg: (False, []))
    st = state.State(phase=state.WAITING,
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    out = daemon.tick(_cfg())
    assert out.phase == state.ARMED


def test_waiting_with_session_fires(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda cfg: (True, ["C:/proj"]))
    fired = {}

    def fake_fire(work_dir, note, cfg):
        from cloophole.fire import FireResult
        fired["dir"] = work_dir
        return FireResult(True, False, None, "done", "", 0)

    monkeypatch.setattr(daemon.fire, "fire", fake_fire)
    st = state.State(phase=state.WAITING,
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    out = daemon.tick(_cfg())
    assert fired["dir"] == "C:/proj"
    assert out.phase == state.WATCHING
    assert out.reset_at is None


def test_armed_fires_when_session_appears(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda cfg: (True, ["C:/x"]))
    monkeypatch.setattr(daemon.fire, "fire",
                        lambda *a, **k: __import__("cloophole.fire", fromlist=["FireResult"]).FireResult(True, False, None, "", "", 0))
    st = state.State(phase=state.ARMED)
    state.save(st)
    out = daemon.tick(_cfg())
    assert out.phase == state.WATCHING


def test_still_limited_rearms(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda cfg: (True, []))
    future_text = "limit reached, try again in 2h"

    def fake_fire(work_dir, note, cfg):
        from cloophole.fire import FireResult
        return FireResult(False, True, future_text, "", future_text, 1)

    monkeypatch.setattr(daemon.fire, "fire", fake_fire)
    st = state.State(phase=state.WAITING,
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    out = daemon.tick(_cfg())
    assert out.phase == state.WAITING
    assert out.reset_dt() > datetime.now(timezone.utc)


def test_fires_in_all_session_dirs(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions",
                        lambda cfg: (True, ["C:/a", "C:/b", "C:/c"]))
    fired = []

    def fake_fire(work_dir, note, cfg):
        from cloophole.fire import FireResult
        fired.append(work_dir)
        return FireResult(True, False, None, "ok", "", 0)

    monkeypatch.setattr(daemon.fire, "fire", fake_fire)
    st = state.State(phase=state.WAITING,
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    out = daemon.tick(_cfg())
    assert fired == ["C:/a", "C:/b", "C:/c"]  # fired in every live session dir
    assert out.phase == state.WATCHING


def test_default_resume_dispatches_per_dir(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda cfg: (True, ["C:/a", "C:/b"]))
    done = []
    monkeypatch.setattr(daemon.fire, "resume",
                        lambda d, note, cfg: (done.append(d), None)[1])
    from cloophole import config
    cfg = config.load()  # resume_mode defaults "inject"
    st = state.State(phase=state.WAITING,
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    out = daemon.tick(cfg)
    assert done == ["C:/a", "C:/b"]  # resume() called per ticked dir
    assert out.phase == state.WATCHING


def test_pin_overrides_session_dirs(env, monkeypatch):
    daemon, state = env
    monkeypatch.setattr(daemon, "detect_sessions",
                        lambda cfg: (True, ["C:/a", "C:/b"]))
    fired = []
    monkeypatch.setattr(daemon.fire, "fire",
                        lambda wd, note, cfg: (fired.append(wd),
                        __import__("cloophole.fire", fromlist=["FireResult"]).FireResult(True, False, None, "", "", 0))[1])
    st = state.State(phase=state.WAITING, work_dir="C:/pinned",
                     reset_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    state.save(st)
    daemon.tick(_cfg())
    assert fired == ["C:/pinned"]  # pin wins over detected dirs
