"""StopFailure rate-limit hook tests (ADR-0008) — settings I/O + signal consume.

No Claude is ever invoked: install/uninstall touch a temp settings.json, the
signal is a temp file, and the daemon's detector is stubbed.
"""

import json

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path / "cloophole"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    import importlib
    from cloophole import claude_hook, config, daemon, paths, state
    for m in (paths, state, config, claude_hook, daemon):
        importlib.reload(m)
    return claude_hook, daemon, state, config


def test_signal_roundtrip_carries_cwd(env):
    claude_hook, _, _, _ = env
    claude_hook.record_signal('{"cwd": "C:/work/proj", "hook_event_name": "StopFailure"}')
    sig = claude_hook.read_signal()
    assert sig and sig["cwd"] == "C:/work/proj"
    assert sig["source"] == "rate_limit"
    claude_hook.clear_signal()
    assert claude_hook.read_signal() is None


def test_record_signal_never_raises_on_garbage(env):
    claude_hook, _, _, _ = env
    claude_hook.record_signal("not json at all")  # must not raise
    assert claude_hook.read_signal()["cwd"] is None


def test_install_is_idempotent_and_removable(env):
    claude_hook, _, _, _ = env
    assert not claude_hook.hook_installed()
    claude_hook.install_hook()
    claude_hook.install_hook()  # twice -> still one entry
    assert claude_hook.hook_installed()
    data = json.loads(claude_hook.settings_path().read_text())
    entries = data["hooks"]["StopFailure"]
    ours = [e for e in entries
            if any("limit-signal" in h.get("command", "") for h in e["hooks"])]
    assert len(ours) == 1
    assert ours[0]["matcher"] == "rate_limit"
    assert claude_hook.uninstall_hook()
    assert not claude_hook.hook_installed()


def test_install_preserves_foreign_hooks(env):
    claude_hook, _, _, _ = env
    p = claude_hook.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "echo mine"}]}]}}))
    claude_hook.install_hook()
    claude_hook.uninstall_hook()
    data = json.loads(p.read_text())
    # the user's own Stop hook is untouched
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo mine"


def test_hook_schedules_two_rechecks(env, monkeypatch):
    claude_hook, daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    state.save(state.State(phase=state.WATCHING))
    claude_hook.record_signal('{"cwd": "C:/p"}')
    out = daemon.tick(config.load())
    assert out.phase == state.WAITING
    assert len(out.recheck_at) == 2  # ~+10min and ~reset-10min, both future


def test_recheck_lifts_limit_when_probe_clear(env, monkeypatch):
    from datetime import datetime, timedelta, timezone
    _, daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    monkeypatch.setattr(daemon.probe, "probe", lambda c: (False, None))  # not limited
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    future = (now + timedelta(hours=4)).isoformat()
    state.save(state.State(phase=state.WAITING, reset_at=future, recheck_at=[past]))
    out = daemon.tick(config.load())
    assert out.recheck_at == []          # consumed
    assert out.phase == state.ARMED      # reset pulled to now, no live session -> ARMED


def test_recheck_keeps_waiting_when_still_limited(env, monkeypatch):
    from datetime import datetime, timedelta, timezone
    _, daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    monkeypatch.setattr(daemon.probe, "probe",
                        lambda c: (True, "usage limit reached, try again in 3h"))
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    later = (now + timedelta(hours=4)).isoformat()
    state.save(state.State(phase=state.WAITING, reset_at=later, recheck_at=[past, later]))
    out = daemon.tick(config.load())
    assert out.phase == state.WAITING
    assert len(out.recheck_at) == 1      # consumed the due one, kept the future one


def test_daemon_consumes_signal_into_waiting(env, monkeypatch):
    claude_hook, daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    state.save(state.State(phase=state.WATCHING))
    claude_hook.record_signal('{"cwd": "C:/work/proj"}')
    cfg = config.load()
    cfg["limit_window_hours"] = 5
    out = daemon.tick(cfg)
    assert out.phase == state.WAITING
    assert out.hook_dir == "C:/work/proj"
    assert claude_hook.read_signal() is None  # consumed


def test_daemon_records_live_dirs_for_gui(env, monkeypatch):
    _, daemon, state, config = env
    monkeypatch.setattr(daemon, "detect_sessions",
                        lambda c: (True, ["C:/a", "C:/b"]))
    state.save(state.State(phase=state.WATCHING))
    out = daemon.tick(config.load())
    assert out.live_dirs == ["C:/a", "C:/b"]
    assert out.live_session is True


def test_fire_dirs_falls_back_to_hook_dir(env):
    _, daemon, state, _ = env
    st = state.State(work_dir=None, hook_dir="C:/work/proj")
    assert daemon._fire_dirs(st, []) == ["C:/work/proj"]
    # a live cwd still wins over the hook fallback
    assert daemon._fire_dirs(st, ["C:/live"]) == ["C:/live"]


def test_live_dirs_kept_on_transient_empty_read(env, monkeypatch):
    _, daemon, state, config = env
    state.save(state.State(phase=state.WATCHING, live_dirs=["C:/a"]))
    # live but cwd unreadable this tick -> keep the last good list (no GUI flicker)
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (True, []))
    assert daemon.tick(config.load()).live_dirs == ["C:/a"]
    # genuinely no live session -> clear it
    monkeypatch.setattr(daemon, "detect_sessions", lambda c: (False, []))
    assert daemon.tick(config.load()).live_dirs == []


def test_fire_dirs_respects_unticked_sessions(env):
    _, daemon, state, _ = env
    st = state.State(excluded_dirs=["C:/b"])
    # only the ticked (non-excluded) live sessions fire
    assert daemon._fire_dirs(st, ["C:/a", "C:/b", "C:/c"]) == ["C:/a", "C:/c"]
    # un-ticking all live sessions -> fire nowhere
    st2 = state.State(excluded_dirs=["C:/a", "C:/b"])
    assert daemon._fire_dirs(st2, ["C:/a", "C:/b"]) == []
    # a pin still overrides the tick boxes
    st3 = state.State(work_dir="C:/pin", excluded_dirs=["C:/a"])
    assert daemon._fire_dirs(st3, ["C:/a"]) == ["C:/pin"]
