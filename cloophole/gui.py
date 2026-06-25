"""Dedicated desktop window (Tkinter) — the app UI (ADR-0007, ADR-0010).

@context  cloophole's UI is a small native window (not web, not tray) AND the watcher:
          it self-detects sessions, runs the state-machine tick in a thread, and shows
          a scrollable list of detected Claude sessions with a tick box each (ticked =
          resume there; default all ticked) + a message box per session.
@done     run(): single-instance Tk window, fast refresh, phase badge, message field
          (bulk/per-session), hook on/off line, scrollable per-session checkboxes
          (excluded_dirs); buttons = Resume now / Not limited-clear / Close. Two
          threads: detect (display) + watch (daemon.tick). Stdlib tkinter only.
@todo     mac/Linux polish.
@limits   Needs a display. The window IS the watcher — CLOSING IT STOPS WATCHING.
          One window at a time (gui.pid). `cloophole daemon` still runs headless.
@affects  Launched by CLI `_gui` (spawned by runner from `open`). READS winproc.
          sessions_detail (self thread) + claude_hook.hook_installed. WRITES state via
          save_user (queue_note, excluded_dirs, note_mode, session_notes). Resume +
          the watch thread call fire.resume / daemon.tick. State/config field or
          fire.resume signature changes affect this file.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import fire, state
from .paths import gui_pid_file

_PHASE_PLAIN = {
    state.WATCHING: "Watching for your usage limit",
    state.WAITING: "Limit reached — waiting for the reset",
    state.ARMED: "Reset due — waiting for a Claude window",
    state.FIRING: "Resuming your work now…",
    state.FIRED: "Just resumed your work",
    state.ERROR: "Something went wrong last time",
}

# palette
BG = "#0d1117"
PANEL = "#161b22"
PANEL2 = "#1b2230"
BORDER = "#2a3140"
FG = "#e6edf3"
SUB = "#8b949e"
ACCENT = "#3fb950"
ACCENT_DK = "#2ea043"
AMBER = "#d29922"
DANGER = "#f85149"

_PHASE_COLOR = {
    state.WATCHING: SUB,
    state.WAITING: AMBER,
    state.ARMED: ACCENT,
    state.FIRING: ACCENT,
    state.FIRED: ACCENT,
    state.ERROR: DANGER,
}


def _fmt_until(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _countdown(st: state.State) -> str:
    return _fmt_until(st.reset_dt())


def _iso_dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def run() -> None:
    import os
    import tkinter as tk
    from tkinter import messagebox

    from . import claude_hook, runner

    if runner.is_gui_running():
        return
    gui_pid_file().write_text(str(os.getpid()), encoding="utf-8")

    root = tk.Tk()
    root.title("cloophole")
    root.configure(bg=BG)
    root.resizable(True, True)  # geometry is fit to content at the end of run()

    def lbl(parent, text, color=FG, font=("Segoe UI", 10), **kw):
        bg = kw.pop("bg", BG)
        return tk.Label(parent, text=text, bg=bg, fg=color, font=font, **kw)

    def card(parent, **kw):
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1, **kw)

    # Detect sessions ourselves (OS process inspection — Golden-Rule-fine) on a
    # background thread, rather than depend on the daemon writing live_dirs to state
    # at just the right moment (a spawned GUI could otherwise read it empty forever).
    import sys as _sys
    import time as _time

    from . import config as _config, daemon as _daemon, sessions as _sessions
    _detected = {"sessions": [], "live": False}

    def _detect_loop():
        while True:
            try:
                sess = _sessions.list_all(_config.load())  # Windows + WSL tmux panes
                _detected["live"] = bool(sess)
                _detected["sessions"] = sess
            except Exception:
                pass
            _time.sleep(1.5)

    threading.Thread(target=_detect_loop, daemon=True).start()

    # The WINDOW is the watcher (no separate daemon process): this thread runs the
    # state-machine tick — read the rate-limit hook signal, count down to the reset,
    # fire the resume when due. One process = no daemon races/orphans/clobbering.
    def _watch_loop():
        while True:
            try:
                _daemon.tick(_config.load())
            except Exception:
                pass
            try:
                interval = max(2, int(_config.load().get("daemon_tick_sec", 5)))
            except Exception:
                interval = 5
            _time.sleep(interval)

    threading.Thread(target=_watch_loop, daemon=True).start()

    PAD = 16  # one consistent horizontal margin for everything

    # ---------- header ----------
    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=PAD, pady=(12, 0))
    lbl(head, "● ", ACCENT, ("Segoe UI", 11, "bold")).pack(side="left")
    lbl(head, "cloophole", FG, ("Segoe UI", 16, "bold")).pack(side="left")
    lbl(root, "Keeps your Claude Code going after the usage limit resets.",
        SUB, ("Segoe UI", 9)).pack(anchor="w", padx=PAD + 2)

    # ---------- status card ----------
    sc = card(root)
    sc.pack(fill="x", padx=PAD, pady=(10, 6))
    phase_row = tk.Frame(sc, bg=PANEL)
    phase_row.pack(fill="x", padx=12, pady=(10, 2))
    v_dot = lbl(phase_row, "●", SUB, ("Segoe UI", 11), bg=PANEL)
    v_dot.pack(side="left", padx=(0, 8))
    v_status = lbl(phase_row, "", FG, ("Segoe UI", 11, "bold"), bg=PANEL)
    v_status.pack(side="left")
    set_link = tk.Label(phase_row, text="set reset time", fg=ACCENT, bg=PANEL,
                        font=("Segoe UI", 8, "underline"), cursor="hand2")
    set_link.pack(side="right")
    set_link.bind("<Button-1>", lambda _e: set_reset_time())
    # big countdown — only shown when there's a reset to count down to.
    v_count = lbl(sc, "", ACCENT, ("Segoe UI", 24, "bold"), bg=PANEL)
    v_meta = lbl(sc, "", SUB, ("Segoe UI", 9), bg=PANEL, justify="left")
    v_meta.pack(anchor="w", padx=12, pady=(4, 10))

    # ---------- message + mode ----------
    rw = tk.Frame(root, bg=BG)
    rw.pack(fill="x", padx=PAD, pady=(6, 2))
    v_notehdr = lbl(rw, "MESSAGE TO SEND", SUB, ("Segoe UI", 8, "bold"))
    v_notehdr.pack(side="left")
    mode_btn = tk.Label(rw, text="", fg=ACCENT, bg=BG,
                        font=("Segoe UI", 8, "underline"), cursor="hand2")
    mode_btn.pack(side="right")

    note_var = tk.StringVar(value=state.load().queue_note or "")

    def save_note(*_):
        st = state.load()
        st.queue_note = note_var.get().strip() or None
        state.save_user(st)

    note_var.trace_add("write", save_note)  # save on every keystroke, not just focus-out
    note_box = card(root)
    note_box.pack(fill="x", padx=PAD)
    note_entry = tk.Entry(note_box, textvariable=note_var, bg=PANEL, fg=FG,
                          insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    note_entry.pack(fill="x", padx=10, pady=8)
    note_entry.bind("<Return>", save_note)
    note_entry.bind("<FocusOut>", save_note)
    note_hint = lbl(root, "", SUB, ("Segoe UI", 8))
    note_hint.pack(anchor="w", padx=PAD + 2, pady=(2, 0))

    def _apply_note_mode():
        per = state.load().note_mode == "per"
        v_notehdr.config(text="DEFAULT MESSAGE (per-session below overrides)" if per
                         else "MESSAGE TO SEND ON RESUME")
        mode_btn.config(text="↔ one message for all" if per else "↔ per-session messages")
        note_hint.config(text="each ticked session gets its own box below; blank = use default"
                         if per else "blank = pick up where you left off")
        _render_sessions(force=True)

    def _toggle_note_mode(*_):
        st = state.load()
        st.note_mode = "bulk" if st.note_mode == "per" else "per"
        state.save_user(st)
        _apply_note_mode()

    mode_btn.bind("<Button-1>", _toggle_note_mode)

    # ---------- auto-detect (zero-quota Claude hook) ----------
    try:
        _hook_on = claude_hook.hook_installed()
    except Exception:
        _hook_on = False
    ad = tk.Frame(root, bg=BG)
    ad.pack(fill="x", padx=PAD, pady=(6, 0))
    lbl(ad, "Auto-detect:", SUB, ("Segoe UI", 9)).pack(side="left")
    lbl(ad, "  ON" if _hook_on else "  OFF",
        ACCENT if _hook_on else SUB, ("Segoe UI", 9, "bold")).pack(side="left")
    lbl(ad, "  Claude signals the limit — no quota used." if _hook_on
            else "  run `cloophole hook on`.", SUB, ("Segoe UI", 8)).pack(side="left")

    # ---------- actions (pinned to the bottom so they're never clipped) ----------
    actions = tk.Frame(root, bg=BG)
    actions.pack(fill="x", padx=PAD, pady=(8, 12), side="bottom")
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)

    def _hover(btn, normal, hot):
        btn.bind("<Enter>", lambda _e: btn.config(bg=hot))
        btn.bind("<Leave>", lambda _e: btn.config(bg=normal))

    def mkbtn(parent, text, cmd, *, accent=False, grid=None, **gridkw):
        normal = ACCENT if accent else PANEL
        hot = ACCENT_DK if accent else "#222b39"
        b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0,
                      bg=normal, fg="#06210d" if accent else FG,
                      activebackground=hot, activeforeground="#06210d" if accent else FG,
                      font=("Segoe UI", 10, "bold" if accent else "normal"),
                      padx=10, pady=9, cursor="hand2",
                      highlightthickness=1, highlightbackground=BORDER)
        _hover(b, normal, hot)
        if grid is not None:
            b.grid(row=grid[0], column=grid[1], sticky="ew", padx=4, pady=4, **gridkw)
        return b

    # ---------- detected sessions, with tick boxes (fills middle) ----------
    sess_head = tk.Frame(root, bg=BG)
    sess_head.pack(fill="x", padx=PAD, pady=(8, 2))
    lbl(sess_head, "SESSIONS TO RESUME", SUB, ("Segoe UI", 8, "bold")).pack(side="left")
    v_sesscount = lbl(sess_head, "", SUB, ("Segoe UI", 8))
    v_sesscount.pack(side="left", padx=6)

    def _set_all(ticked: bool):
        st = state.load()
        keys = list(_rendered.get("keys") or [])  # the sessions currently shown
        st.excluded_dirs = [] if ticked else list(keys)
        state.save_user(st)
        _render_sessions(force=True)

    allbtn = tk.Label(sess_head, text="all", fg=ACCENT, bg=BG,
                      font=("Segoe UI", 8, "underline"), cursor="hand2")
    allbtn.pack(side="right", padx=(6, 0))
    allbtn.bind("<Button-1>", lambda _e: _set_all(True))
    nonebtn = tk.Label(sess_head, text="none", fg=SUB, bg=BG,
                       font=("Segoe UI", 8, "underline"), cursor="hand2")
    nonebtn.pack(side="right")
    nonebtn.bind("<Button-1>", lambda _e: _set_all(False))

    sess_wrap = card(root)
    sess_wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, 2))
    sess_canvas = tk.Canvas(sess_wrap, bg=PANEL, highlightthickness=0, height=100)
    vsb = tk.Scrollbar(sess_wrap, orient="vertical", command=sess_canvas.yview)
    sess_holder = tk.Frame(sess_canvas, bg=PANEL)
    sess_window = sess_canvas.create_window((0, 0), window=sess_holder, anchor="nw")
    sess_canvas.configure(yscrollcommand=vsb.set)
    sess_canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    vsb.pack(side="right", fill="y")
    sess_holder.bind("<Configure>",
                     lambda _e: sess_canvas.configure(scrollregion=sess_canvas.bbox("all")))
    sess_canvas.bind("<Configure>",
                     lambda e: sess_canvas.itemconfig(sess_window, width=e.width))
    sess_canvas.bind_all(
        "<MouseWheel>", lambda e: sess_canvas.yview_scroll(int(-e.delta / 120), "units"))

    def toggle_dir(key: str, var) -> None:
        st = state.load()
        ex = set(st.excluded_dirs or [])
        ex.discard(key) if var.get() else ex.add(key)
        st.excluded_dirs = sorted(ex)
        state.save_user(st)
        _update_count()

    # Per-session stickiness (keyed by the unique session key, so a WSL pane and a
    # Windows folder are distinct): each session lingers _STICKY_SEC after it stops
    # being seen, so one flaky detection can't blink it in and out.
    _rendered = {"keys": None}
    _seen: dict[str, tuple] = {}   # key -> (monotonic_time, session dict)

    def _sticky_for(key: str) -> float:
        # Windows detection is reliable -> drop fast; WSL detection can flake -> hold
        # longer so it doesn't blink in and out.
        return 1.5 if key.startswith("win:") else 6.0

    def _effective_sessions() -> list:
        now = _time.monotonic()
        for s in _detected["sessions"] or []:
            _seen[s["key"]] = (now, s)
        for k in [k for k, (t, _s) in _seen.items() if now - t > _sticky_for(k)]:
            del _seen[k]
        return [s for _t, s in sorted(_seen.values(), key=lambda ts: ts[1]["key"])]

    def _update_count():
        keys = _rendered.get("keys") or []
        ex = set(state.load().excluded_dirs or [])
        ticked = sum(1 for k in keys if k not in ex)
        v_sesscount.config(text=f"({ticked} of {len(keys)} ticked)" if keys else "")

    def _focus_session(sess: dict) -> None:
        # Bring the session's terminal window to the front. tmux: flash the pane too
        # (its Windows host terminal isn't tracked, so we at least highlight the pane).
        kind, handle = sess.get("kind"), sess.get("handle")

        def work():
            try:
                if kind == "wsl":
                    from . import wsl
                    wsl.highlight(handle)
                else:
                    from . import inject
                    inject.focus(int(handle))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _autosize() -> None:
        # Grow the window to show every detected session, up to the laptop's screen
        # height; beyond that the list scrolls (scrollregion is always live, so the
        # user can scroll regardless of window size).
        try:
            root.update_idletasks()
            screen_h = root.winfo_screenheight()
            max_h = screen_h - 80  # leave room for taskbar + title bar
            content_h = max(96, sess_holder.winfo_reqheight() + 6)
            sess_canvas.config(height=content_h)        # try to show all rows
            root.update_idletasks()
            need = root.winfo_reqheight()
            if need > max_h:                            # too tall -> cap + scroll
                sess_canvas.config(height=max(96, content_h - (need - max_h)))
                need = max_h
            cur_w = root.winfo_width()
            w = max(460, cur_w if cur_w > 1 else root.winfo_reqwidth())
            root.geometry(f"{w}x{need + 4}")
        except Exception:
            pass

    def _render_sessions(force: bool = False) -> None:
        st = state.load()
        sess = _effective_sessions()
        keys = [s["key"] for s in sess]
        if not force and keys == _rendered["keys"]:
            _update_count()
            return
        _rendered["keys"] = keys
        for w in sess_holder.winfo_children():
            w.destroy()
        if not sess:
            lbl(sess_holder, "•  no Claude session detected right now",
                SUB, ("Segoe UI", 9), bg=PANEL).pack(anchor="w", padx=8, pady=10)
            _update_count()
            root.after_idle(_autosize)
            return
        ex = set(st.excluded_dirs or [])
        for s in sess:
            key = s["key"]
            var = tk.BooleanVar(value=(key not in ex))
            row = tk.Frame(sess_holder, bg=PANEL2, highlightbackground=BORDER,
                           highlightthickness=1)
            row.pack(fill="x", padx=2, pady=1)
            cb = tk.Checkbutton(row, variable=var,
                                command=lambda kk=key, vv=var: toggle_dir(kk, vv),
                                bg=PANEL2, activebackground=PANEL2, fg=ACCENT,
                                selectcolor=PANEL, bd=0, highlightthickness=0,
                                cursor="hand2")
            cb.pack(side="left", padx=(5, 0), pady=2)
            txt = tk.Frame(row, bg=PANEL2)
            txt.pack(side="left", fill="x", expand=True, pady=2)
            head = tk.Frame(txt, bg=PANEL2)
            head.pack(anchor="w", fill="x")
            fl = lbl(head, s["folder"], FG, ("Segoe UI", 9, "bold"), bg=PANEL2)
            fl.pack(side="left")
            if s.get("label"):
                lbl(head, f"  ·  {s['label']}", ACCENT, ("Segoe UI", 7), bg=PANEL2).pack(side="left")
            pl = lbl(txt, s.get("path", key), SUB, ("Segoe UI", 7), bg=PANEL2)
            pl.pack(anchor="w")
            # Click the row (name/path) to bring that terminal to the front; a tmux
            # pane also flashes so you see which split it is.
            for w in (fl, pl, head, txt):
                w.config(cursor="hand2")
                w.bind("<Button-1>", lambda _e, ss=s: _focus_session(ss))
            if st.note_mode == "per":
                svar = tk.StringVar(value=(st.session_notes or {}).get(key, ""))

                def _save_sess_note(kk=key, vv=svar):
                    s2 = state.load()
                    notes = dict(s2.session_notes or {})
                    t = vv.get().strip()
                    if t:
                        notes[kk] = t
                    else:
                        notes.pop(kk, None)
                    s2.session_notes = notes
                    state.save_user(s2)

                svar.trace_add("write", lambda *_a, f=_save_sess_note: f())
                e = tk.Entry(txt, textvariable=svar, bg=PANEL, fg=FG, insertbackground=FG,
                             relief="flat", font=("Segoe UI", 8))
                e.pack(fill="x", pady=(2, 1))
        _update_count()
        root.after_idle(_autosize)

    # ---------- button actions ----------
    def do_resume():
        save_note()
        st = state.load()
        # Resume the sessions the user SEES ticked (keys = Windows folders + WSL panes).
        if st.work_dir:
            targets = [st.work_dir]
        else:
            ex = set(st.excluded_dirs or [])
            targets = [k for k in (_rendered.get("keys") or []) if k not in ex]
        if not targets:
            messagebox.showinfo("cloophole", "No sessions are ticked to resume.")
            return
        # Resume per the configured mode (default: type the note into the open
        # session). Each session gets its own message in per-session mode.
        done, errs = 0, []
        for d in targets:
            err = fire.resume(d, state.note_for(st, d))
            if err:
                errs.append(err)
            else:
                done += 1
        if done:
            messagebox.showinfo("cloophole", f"Resumed {done} session(s).")
        else:
            messagebox.showwarning(
                "cloophole", f"Couldn't resume: {errs[0] if errs else 'unknown'}")

    def clear_limit():
        # forget a detected/typed reset and go back to watching
        st = state.load()
        st.phase = state.WATCHING
        st.reset_at = None
        st.limit_text = None
        st.last_error = None
        st.manual_reset = False
        st.recheck_at = []
        state.save_runtime(st)

    def set_reset_time():
        # Let the user type the reset time they can already see in Claude (e.g. it
        # shows "resets 10pm") so the countdown is live BEFORE they hit the limit.
        from tkinter import simpledialog

        from .reset_parser import parse_user_time
        txt = simpledialog.askstring(
            "Set reset time",
            "Reset time (e.g. 7:30 PM, 10pm, 22:00) or a countdown (e.g. 2 min, 1h30m):",
            parent=root)
        if not txt:
            return
        dt = parse_user_time(txt)
        if not dt:
            messagebox.showwarning(
                "cloophole", "Couldn't read a time from that. Try '7:30 PM', '10pm', "
                "'22:00', or '2 min' / '1h30m'.")
            return
        st = state.load()
        st.reset_at = dt.isoformat()
        st.limit_text = "(set manually)"
        st.manual_reset = True
        st.recheck_at = []
        st.phase = state.WAITING
        state.save_runtime(st)
        messagebox.showinfo(
            "cloophole", f"Counting down to {dt.astimezone():%I:%M %p}. "
            "It will resume your ticked sessions then.")

    mkbtn(actions, "▶  Resume now", do_resume, accent=True, grid=(0, 0), columnspan=2)
    mkbtn(actions, "Reset the detected time limit", clear_limit, grid=(1, 0))
    mkbtn(actions, "Close", lambda: (_cleanup(), root.destroy()), grid=(1, 1))

    # ---------- live refresh ----------
    def refresh():
        # Never let one bad refresh kill the loop — always reschedule in `finally`.
        try:
            st = state.load()
            from . import statusline as _sl
            info = _sl.read_status()
            win_dt = _iso_dt(info.get("window_reset_at")) if info else None
            usage = (f"{info['used_pct']:.0f}% of 5h used"
                     if info and "used_pct" in info else None)

            status_txt = _PHASE_PLAIN.get(st.phase, st.phase)
            if st.phase == state.WAITING and getattr(st, "manual_reset", False):
                status_txt = "Counting down to your reset"
            # Live 5h countdown from Claude's statusLine (before any limit), unless we're
            # already counting down to an actual limit reset.
            show_window = (st.phase == state.WATCHING and win_dt
                           and win_dt > datetime.now(timezone.utc))
            if show_window and usage:
                status_txt = f"Watching · {usage}"
            v_status.config(text=status_txt)
            v_dot.config(fg=_PHASE_COLOR.get(st.phase, SUB))

            count_text = None
            if st.reset_at:
                count_text = _countdown(st)            # actual/typed reset
            elif show_window:
                count_text = _fmt_until(win_dt)         # live 5h window reset
            if count_text is not None:
                v_count.config(text=count_text)
                if not v_count.winfo_ismapped():
                    v_count.pack(anchor="w", padx=16, before=v_meta)
            elif v_count.winfo_ismapped():
                v_count.pack_forget()

            where = (f"pinned → {st.work_dir}" if st.work_dir else "the ticked sessions")
            line1 = "Watching (this window)"
            if show_window and win_dt:
                line1 = f"5h quota resets {win_dt.astimezone().strftime('%I:%M %p').lstrip('0')}"
            meta = (f"{line1}   ·   Claude open now: {'yes' if _detected['live'] else 'no'}\n"
                    f"Resume in: {where}")
            if st.last_error:
                meta += f"\nLast problem: {st.last_error}"
            v_meta.config(text=meta)
            _render_sessions()
        except Exception:
            pass
        finally:
            root.after(400, refresh)

    def _cleanup():
        try:
            gui_pid_file().unlink()
        except OSError:
            pass

    root.protocol("WM_DELETE_WINDOW", lambda: (_cleanup(), root.destroy()))
    _apply_note_mode()  # set the toggle label + render per-session boxes if enabled
    # Fit the window to its content so nothing clips. The session list scrolls, so
    # height stays bounded; buttons are bottom-pinned as a backstop.
    root.update_idletasks()
    fit_w = max(460, root.winfo_reqwidth())
    root.geometry(f"{fit_w}x{root.winfo_reqheight() + 10}")
    root.minsize(fit_w, 300)  # _autosize grows/caps height to the session count
    refresh()
    root.after_idle(_autosize)  # size to the session count once mapped
    import gc
    gc.collect()  # drop import/build garbage before the window goes idle
    try:
        root.mainloop()
    finally:
        _cleanup()
