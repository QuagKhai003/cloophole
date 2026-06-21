"""Tiny local status page served by the stdlib http server (product plan §6).

@context  A read-only window onto state.json so you can see phase + countdown
          without the CLI. Never mutates state.
@done     serve() (ThreadingHTTPServer), HTML page (5s self-refresh) + /state
          JSON, phase colors, countdown.
@todo     —
@limits   Read-only; binds 127.0.0.1 only. Port = config ui_port.
@affects  Reads state via state.load(). Launched by CLI `ui`.

Shows: current phase, countdown to reset, live-session indicator, queued note,
work dir. No native GUI toolkit, no JS framework — one self-refreshing page and
a /state JSON endpoint. Read-only view onto the same state file the CLI writes.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, state

_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>cloophole</title>
<meta http-equiv=refresh content=5>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:2rem;}}
 .card{{max-width:520px;margin:auto;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:1.5rem 1.75rem;}}
 h1{{margin:0 0 .25rem;font-size:1.3rem;}} .sub{{color:#8b949e;font-size:.8rem;margin-bottom:1.25rem;}}
 .phase{{display:inline-block;padding:.25rem .7rem;border-radius:999px;font-weight:600;font-size:.85rem;}}
 .row{{display:flex;justify-content:space-between;padding:.45rem 0;border-top:1px solid #21262d;}}
 .k{{color:#8b949e;}} .v{{font-weight:600;text-align:right;}}
 .big{{font-size:2rem;font-weight:700;margin:.5rem 0;}}
 .on{{color:#3fb950;}} .off{{color:#f85149;}}
</style></head><body><div class=card>
 <h1>cloophole</h1><div class=sub>auto-resume Claude Code on quota reset</div>
 <span class="phase" style="background:{phase_bg};color:{phase_fg}">{phase}</span>
 <div class=big>{countdown}</div>
 <div class=row><span class=k>reset at</span><span class=v>{reset_at}</span></div>
 <div class=row><span class=k>live session</span><span class="v {live_cls}">{live}</span></div>
 <div class=row><span class=k>work dir</span><span class=v>{work_dir}</span></div>
 <div class=row><span class=k>queued</span><span class=v>{queue}</span></div>
 <div class=row><span class=k>last fired</span><span class=v>{last_fired}</span></div>
</div></body></html>"""

_PHASE_COLORS = {
    "WATCHING": ("#1f6feb33", "#58a6ff"),
    "WAITING": ("#9e6a0333", "#d29922"),
    "ARMED": ("#8957e533", "#bc8cff"),
    "FIRING": ("#23863633", "#3fb950"),
    "FIRED": ("#23863633", "#3fb950"),
    "ERROR": ("#da363333", "#f85149"),
}


def _countdown(st: state.State) -> str:
    dt = st.reset_dt()
    if not dt:
        return "—"
    delta = dt - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "now"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}h {m:02d}m {s:02d}s" if h else f"{m:d}m {s:02d}s"


def _render(st: state.State) -> str:
    bg, fg = _PHASE_COLORS.get(st.phase, ("#30363d", "#c9d1d9"))
    return _PAGE.format(
        phase=st.phase, phase_bg=bg, phase_fg=fg,
        countdown=_countdown(st),
        reset_at=st.reset_at or "—",
        live="yes" if st.live_session else "no",
        live_cls="on" if st.live_session else "off",
        work_dir=st.work_dir or "(claude cwd)",
        queue=st.queue_note or "(fallback)",
        last_fired=st.last_fired or "never",
    )


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        st = state.load()
        if self.path.startswith("/state"):
            body = json.dumps(asdict(st), indent=2).encode()
            ctype = "application/json"
        else:
            body = _render(st).encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):  # silence default stderr logging
        pass


def serve(port: int | None = None) -> None:
    port = port or config.get("ui_port")
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"cloophole UI -> http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
