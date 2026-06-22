"""Phase 3 idle-poll tests — probe is always stubbed (never hits the network)."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    from cloophole import config, daemon, state
    importlib.reload(state)
    importlib.reload(daemon)
    importlib.reload(config)
    return daemon, state, config


def _cfg(config, **over):
    cfg = config.load()
    cfg.update(over)
    return cfg


def test_no_probe_when_disabled(env, monkeypatch):
    daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    called = {"n": 0}
    monkeypatch.setattr(daemon.probe, "probe", lambda c: (called.__setitem__("n", called["n"] + 1), (False, None))[1])
    state.save(state.State(phase=state.WATCHING))
    out = daemon.tick(_cfg(config, poll_enabled=False))
    assert called["n"] == 0
    assert out.phase == state.WATCHING


def test_probe_limited_arms_waiting(env, monkeypatch):
    daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    monkeypatch.setattr(daemon.probe, "probe",
                        lambda c: (True, "usage limit reached, try again in 2h"))
    state.save(state.State(phase=state.WATCHING))
    out = daemon.tick(_cfg(config, poll_enabled=True))
    assert out.phase == state.WAITING
    assert out.reset_dt() > datetime.now(timezone.utc)
    assert out.last_poll is not None


def test_probe_not_due_before_interval(env, monkeypatch):
    daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    called = {"n": 0}

    def fake_probe(c):
        called["n"] += 1
        return (False, None)

    monkeypatch.setattr(daemon.probe, "probe", fake_probe)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    state.save(state.State(phase=state.WATCHING, last_poll=recent))
    daemon.tick(_cfg(config, poll_enabled=True, poll_interval_min=30))
    assert called["n"] == 0  # 5 min < 30 min interval


def test_probe_due_after_interval(env, monkeypatch):
    daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    monkeypatch.setattr(daemon.probe, "probe", lambda c: (False, None))
    old = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    state.save(state.State(phase=state.WATCHING, last_poll=old))
    out = daemon.tick(_cfg(config, poll_enabled=True, poll_interval_min=30))
    assert out.last_poll != old  # ran, stamp refreshed


def test_poll_off_by_default(env):
    _, _, config = env
    # OFF out of the box: the probe spends quota each interval (B9). Opt in only.
    assert config.load()["poll_enabled"] is False


def test_fire_and_probe_share_limit_helper():
    from cloophole.reset_parser import is_limit_message
    assert is_limit_message("usage limit reached, resets at 5pm")
    assert not is_limit_message("ok")
    assert not is_limit_message("resets at 5pm")  # no limit wording
