"""System-tray desktop app (ADR-0003) — the face of cloophole.

@context  One background process: tray icon (main thread) + watcher loop + UI
          server (daemon threads). Launched by `cloophole open`, stopped only by
          the tray Quit item or `cloophole close`. Survives the launching shell.
@done     TrayApp.run(): single-instance, loop+UI threads, dynamic icon/title,
          menu (dashboard/fire/poll/queue/quit), toast on fire + start hint.
@todo     mac/Linux tray (P5). Optional PyInstaller .exe bundle.
@limits   GUI deps (pystray, Pillow) imported lazily here only; tkinter (stdlib)
          for the queue-note dialog. Other modules stay importable without them.
@affects  Reuses daemon.loop/_do_fire/start_ui, state, config, winproc, runner.
"""

from __future__ import annotations

import threading
import webbrowser
from datetime import datetime, timezone

from . import config, daemon, state

_COLORS = {
    state.WATCHING: (88, 166, 255),
    state.WAITING: (210, 153, 34),
    state.ARMED: (188, 140, 255),
    state.FIRING: (63, 185, 80),
    state.FIRED: (63, 185, 80),
    state.ERROR: (248, 81, 73),
}


def make_image(color):
    """A simple filled circle icon in the given RGB color."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=color + (255,))
    return img


def _countdown(st: state.State) -> str:
    dt = st.reset_dt()
    if not dt:
        return ""
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _title(st: state.State) -> str:
    cd = _countdown(st)
    return f"cloophole — {st.phase}" + (f" ({cd})" if cd else "")


class TrayApp:
    def __init__(self):
        self.cfg = config.load()
        self.stop_event = threading.Event()
        self.icon = None
        self._last_phase = None

    # --- menu actions -------------------------------------------------------
    def _open_dash(self, *_):
        webbrowser.open(f"http://127.0.0.1:{self.cfg['ui_port']}")

    def _fire(self, *_):
        threading.Thread(target=self._fire_now, daemon=True).start()

    def _fire_now(self):
        st = state.load()
        cwds = []
        live, cwds = daemon.detect_sessions(self.cfg)
        daemon._do_fire(st, self.cfg, cwds)
        self._notify("Fired --continue", "cloophole")

    def _toggle_poll(self, *_):
        new = not config.get("poll_enabled")
        config.set_("poll_enabled", new)
        self._notify(f"Idle poll {'on' if new else 'off'}", "cloophole")

    def _set_queue(self, *_):
        threading.Thread(target=self._ask_queue, daemon=True).start()

    def _ask_queue(self):
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            cur = state.load().queue_note or ""
            val = simpledialog.askstring(
                "cloophole", "What should it continue after the reset?",
                initialvalue=cur, parent=root)
            root.destroy()
        except Exception:
            return
        if val is not None:
            st = state.load()
            st.queue_note = val.strip() or None
            state.save(st)
            self._notify("Queue note saved", "cloophole")

    def _quit(self, *_):
        self.stop_event.set()
        if self.icon:
            self.icon.stop()

    # --- lifecycle ----------------------------------------------------------
    def _notify(self, msg, title="cloophole"):
        try:
            self.icon.notify(msg, title)
        except Exception:
            pass

    def _refresh(self):
        while not self.stop_event.is_set():
            st = state.load()
            if st.phase != self._last_phase:
                if st.phase == state.FIRING:
                    self._notify("Limit reset — resuming your work…", "cloophole")
                elif st.phase == state.ERROR and st.last_error:
                    self._notify(f"Fire error: {st.last_error}", "cloophole")
                self._last_phase = st.phase
            if self.icon is not None:
                self.icon.icon = make_image(_COLORS.get(st.phase, (139, 148, 158)))
                self.icon.title = _title(st)
                try:
                    self.icon.update_menu()
                except Exception:
                    pass
            self.stop_event.wait(2)

    def run(self):
        if not daemon.claim_pid():
            daemon.log("tray app: another instance already running; exiting")
            return
        try:
            import pystray
            from pystray import Menu, MenuItem as Item
        except ImportError:
            daemon.log("tray deps missing; run: pip install pystray pillow")
            daemon.release_pid()
            return

        daemon.start_ui(self.cfg)
        threading.Thread(target=daemon.loop, args=(self.cfg, self.stop_event),
                         daemon=True).start()

        menu = Menu(
            Item(lambda i: _title(state.load()), None, enabled=False),
            Menu.SEPARATOR,
            Item("Open dashboard", self._open_dash, default=True),
            Item("Fire now", self._fire),
            Item(lambda i: f"Idle poll: {'on' if config.get('poll_enabled') else 'off'}",
                 self._toggle_poll),
            Item("Set queue note…", self._set_queue),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )
        self.icon = pystray.Icon(
            "cloophole", make_image(_COLORS[state.WATCHING]), "cloophole", menu)
        threading.Thread(target=self._refresh, daemon=True).start()

        def _greet(icon):
            icon.visible = True
            self._notify("Running. Right-click the tray icon for the menu.",
                         "cloophole")

        try:
            self.icon.run(setup=_greet)
        finally:
            self.stop_event.set()
            daemon.release_pid()


def run():
    TrayApp().run()
