"""UI server tests — background serve on an ephemeral port (no fixed binding)."""

import json
import urllib.request

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOOPHOLE_HOME", str(tmp_path))
    import importlib
    from cloophole import state, ui
    importlib.reload(state)
    importlib.reload(ui)
    return state, ui


def test_background_serves_state_and_html(env):
    state, ui = env
    state.save(state.State(phase=state.WAITING, reset_at="2099-01-01T00:00:00+00:00"))
    srv = ui.start_background(0)  # 0 -> free port
    try:
        port = srv.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=3) as r:
            data = json.loads(r.read())
        assert data["phase"] == "WAITING"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
            html = r.read().decode()
        assert "cloophole" in html and "WAITING" in html
    finally:
        srv.shutdown()
