"""Dedicated desktop window (Tkinter) — the app UI (ADR-0007, ADR-0010).

@context  cloophole's UI is a small native window (not web, not tray). Shows live
          status, a scrollable list of detected Claude sessions with a tick box each
          (ticked = resume fired there; default all ticked), and action buttons. The
          background watcher runs as a separate process; this views/controls it via
          the shared state file.
@done     run(): single-instance Tk window, 1s refresh, phase badge, note field,
          hook on/off line, scrollable per-session checkboxes (excluded_dirs),
          resume-selected + limit/folder/reset/stop. Stdlib tkinter only.
@todo     mac/Linux polish.
@limits   Needs a display. Headless? use `cloophole daemon`. One window at a time
          (gui.pid). Closing the window leaves the watcher running.
@affects  Launched by CLI `_gui` (spawned by runner from `open`). READS via a self
          thread: winproc.sessions_detail (dirs + terminal label). WRITES state
          (queue_note, excluded_dirs ticks, work_dir pin). Resume -> fire.resume per
          ticked dir. Also: claude_hook.hook_installed (status line), runner.stop.
          Changing state/config fields or fire.resume's signature affects this file.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from . import fire, state
from .paths import gui_pid_file
from .reset_parser import parse_reset

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


def _countdown(st: state.State) -> str:
    dt = st.reset_dt()
    if not dt:
        return "-"
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def run() -> None:
    import os
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog

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

    from . import config as _config, daemon as _daemon
    _detected = {"dirs": [], "live": False, "terms": {}}

    def _detect_loop():
        while True:
            try:
                if _sys.platform == "win32":
                    from . import winproc
                    detail = winproc.sessions_detail(_config.load()["claude_process_name"])
                    dirs = [cwd for _pid, cwd, _t in detail if cwd]
                    live = bool(detail)
                    _detected["terms"] = {cwd: term for _pid, cwd, term in detail if cwd}
                else:
                    live, dirs = _daemon.detect_sessions(_config.load())
                _detected["live"] = live
                if dirs or not live:  # keep last good on a transient empty read
                    _detected["dirs"] = list(dirs)
            except Exception:
                pass
            _time.sleep(3)

    threading.Thread(target=_detect_loop, daemon=True).start()

    # ---------- header ----------
    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=20, pady=(16, 6))
    lbl(head, "● ", ACCENT, ("Segoe UI", 12, "bold")).pack(side="left")
    lbl(head, "cloophole", FG, ("Segoe UI", 18, "bold")).pack(side="left")
    lbl(root, "Keeps your Claude Code work going after the usage limit resets.",
        SUB, ("Segoe UI", 9)).pack(anchor="w", padx=22)

    # ---------- status card ----------
    sc = card(root)
    sc.pack(fill="x", padx=18, pady=(12, 8))
    phase_row = tk.Frame(sc, bg=PANEL)
    phase_row.pack(fill="x", padx=16, pady=(14, 2))
    v_dot = lbl(phase_row, "●", SUB, ("Segoe UI", 11), bg=PANEL)
    v_dot.pack(side="left", padx=(0, 8))
    v_status = lbl(phase_row, "", FG, ("Segoe UI", 11, "bold"), bg=PANEL)
    v_status.pack(side="left")
    # big countdown — only shown (packed) when there's a reset to count down to,
    # otherwise it would leave a tall empty gap in the card.
    v_count = lbl(sc, "", ACCENT, ("Segoe UI", 26, "bold"), bg=PANEL)
    v_meta = lbl(sc, "", SUB, ("Segoe UI", 9), bg=PANEL, justify="left")
    v_meta.pack(anchor="w", padx=16, pady=(6, 14))

    # ---------- "resume what" + message mode ----------
    rw = tk.Frame(root, bg=BG)
    rw.pack(fill="x", padx=20, pady=(4, 2))
    v_notehdr = lbl(rw, "MESSAGE TO SEND ON RESUME", SUB, ("Segoe UI", 8, "bold"))
    v_notehdr.pack(side="left")
    mode_btn = tk.Label(rw, text="", fg=ACCENT, bg=BG,
                        font=("Segoe UI", 8, "underline"), cursor="hand2")
    mode_btn.pack(side="right")

    note_var = tk.StringVar(value=state.load().queue_note or "")

    def save_note(*_):
        st = state.load()
        st.queue_note = note_var.get().strip() or None
        state.save(st)

    note_box = card(root)
    note_box.pack(fill="x", padx=18)
    note_entry = tk.Entry(note_box, textvariable=note_var, bg=PANEL, fg=FG,
                          insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    note_entry.pack(fill="x", padx=10, pady=8)
    note_entry.bind("<Return>", save_note)
    note_entry.bind("<FocusOut>", save_note)
    note_hint = lbl(root, "", SUB, ("Segoe UI", 8))
    note_hint.pack(anchor="w", padx=20, pady=(2, 0))

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
        state.save(st)
        _apply_note_mode()

    mode_btn.bind("<Button-1>", _toggle_note_mode)

    # ---------- auto-detect (zero-quota Claude hook) ----------
    try:
        _hook_on = claude_hook.hook_installed()
    except Exception:
        _hook_on = False
    ad = tk.Frame(root, bg=BG)
    ad.pack(fill="x", padx=20, pady=(8, 0))
    lbl(ad, "Auto-detect:", SUB, ("Segoe UI", 9)).pack(side="left")
    lbl(ad, "  ON" if _hook_on else "  OFF",
        ACCENT if _hook_on else SUB, ("Segoe UI", 9, "bold")).pack(side="left")
    lbl(ad, "  Claude signals the limit — no quota used." if _hook_on
            else "  run `cloophole hook on`.", SUB, ("Segoe UI", 8)).pack(side="left")

    # ---------- actions (pinned to the bottom so they're never clipped) ----------
    actions = tk.Frame(root, bg=BG)
    actions.pack(fill="x", padx=18, pady=(8, 14), side="bottom")
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
    sess_head.pack(fill="x", padx=20, pady=(10, 2))
    lbl(sess_head, "SESSIONS TO RESUME", SUB, ("Segoe UI", 8, "bold")).pack(side="left")
    v_sesscount = lbl(sess_head, "", SUB, ("Segoe UI", 8))
    v_sesscount.pack(side="left", padx=6)

    def _set_all(ticked: bool):
        st = state.load()
        dirs = list(st.live_dirs or [])
        st.excluded_dirs = [] if ticked else list(dirs)
        state.save(st)
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
    sess_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 2))
    sess_canvas = tk.Canvas(sess_wrap, bg=PANEL, highlightthickness=0, height=132)
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

    def toggle_dir(d: str, var) -> None:
        st = state.load()
        ex = set(st.excluded_dirs or [])
        ex.discard(d) if var.get() else ex.add(d)
        st.excluded_dirs = sorted(ex)
        state.save(st)
        _update_count()

    # Per-folder stickiness: each detected folder lingers for _STICKY refreshes after
    # it stops being seen, so one missed PEB read (the daemon re-detects every ~15s and
    # a folder read can flake for a tick) can't blink a session in and out. A folder
    # that genuinely closes disappears after _STICKY seconds.
    _rendered = {"dirs": None}
    _seen: dict[str, int] = {}
    _ticks = {"n": 0}
    _STICKY = 22  # refreshes (~22s) — must exceed daemon_tick_sec (15) plus headroom

    def _effective_dirs() -> list:
        _ticks["n"] += 1
        now = _ticks["n"]
        for d in _detected["dirs"] or []:
            _seen[d] = now
        for d in [d for d, t in _seen.items() if now - t > _STICKY]:
            del _seen[d]
        return sorted(_seen)

    def _update_count():
        dirs = _rendered["dirs"] or []
        ex = set(state.load().excluded_dirs or [])
        ticked = sum(1 for d in dirs if d not in ex)
        v_sesscount.config(text=f"({ticked} of {len(dirs)} ticked)" if dirs else "")

    def _render_sessions(force: bool = False) -> None:
        st = state.load()
        dirs = _effective_dirs()
        if not force and dirs == _rendered["dirs"]:
            _update_count()
            return
        _rendered["dirs"] = dirs
        for w in sess_holder.winfo_children():
            w.destroy()
        if not dirs:
            msg = ("a Claude session is open but its folder is unreadable"
                   if _detected["live"] else "no Claude session detected right now")
            lbl(sess_holder, "•  " + msg, SUB, ("Segoe UI", 9), bg=PANEL).pack(
                anchor="w", padx=8, pady=10)
            _update_count()
            return
        ex = set(st.excluded_dirs or [])
        for d in dirs:
            var = tk.BooleanVar(value=(d not in ex))
            row = tk.Frame(sess_holder, bg=PANEL2, highlightbackground=BORDER,
                           highlightthickness=1)
            row.pack(fill="x", padx=3, pady=3)
            cb = tk.Checkbutton(row, variable=var,
                                command=lambda dd=d, vv=var: toggle_dir(dd, vv),
                                bg=PANEL2, activebackground=PANEL2, fg=ACCENT,
                                selectcolor=PANEL, bd=0, highlightthickness=0,
                                cursor="hand2")
            cb.pack(side="left", padx=(8, 2), pady=6)
            txt = tk.Frame(row, bg=PANEL2)
            txt.pack(side="left", fill="x", expand=True, pady=4)
            head = tk.Frame(txt, bg=PANEL2)
            head.pack(anchor="w", fill="x")
            lbl(head, Path(d).name or d, FG, ("Segoe UI", 10, "bold"), bg=PANEL2).pack(side="left")
            term = (_detected["terms"] or {}).get(d)
            if term:
                lbl(head, f"  ·  {term}", ACCENT, ("Segoe UI", 8), bg=PANEL2).pack(side="left")
            lbl(txt, d, SUB, ("Segoe UI", 8), bg=PANEL2).pack(anchor="w")
            if st.note_mode == "per":
                svar = tk.StringVar(value=(st.session_notes or {}).get(d, ""))

                def _save_sess_note(dd=d, vv=svar):
                    s = state.load()
                    notes = dict(s.session_notes or {})
                    txt_ = vv.get().strip()
                    if txt_:
                        notes[dd] = txt_
                    else:
                        notes.pop(dd, None)
                    s.session_notes = notes
                    state.save(s)

                e = tk.Entry(txt, textvariable=svar, bg=PANEL, fg=FG, insertbackground=FG,
                             relief="flat", font=("Segoe UI", 9))
                e.pack(fill="x", pady=(3, 1))
                e.bind("<Return>", lambda _e, f=_save_sess_note: f())
                e.bind("<FocusOut>", lambda _e, f=_save_sess_note: f())
        _update_count()

    # ---------- button actions ----------
    def do_resume():
        save_note()
        st = state.load()
        # Fire the folders the user actually SEES ticked (the sticky displayed list),
        # not the raw live_dirs which can be momentarily empty between daemon ticks.
        if st.work_dir:
            targets = [st.work_dir]
        else:
            ex = set(st.excluded_dirs or [])
            targets = [d for d in (_rendered["dirs"] or []) if d not in ex]
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

    def enter_limit():
        text = simpledialog.askstring(
            "Enter limit time",
            "Paste Claude's limit message, or type a time like '5:30 PM':",
            parent=root)
        if not text:
            return
        dt = parse_reset(text)
        if dt:
            st = state.load()
            st.reset_at = dt.isoformat()
            st.limit_text = text
            st.phase = state.WAITING
            state.save(st)
            messagebox.showinfo(
                "cloophole",
                f"Got it — will resume after {dt.astimezone():%I:%M %p on %b %d}.")
        else:
            messagebox.showwarning(
                "cloophole",
                "Couldn't read a time from that. Try e.g. 'resets at 5:30 PM'.")

    def choose_folder():
        d = filedialog.askdirectory(
            title="Pin one folder to resume in (Cancel = use the ticked sessions)")
        st = state.load()
        st.work_dir = d or None
        state.save(st)

    def reset_status():
        st = state.load()
        st.phase = state.WATCHING
        st.reset_at = None
        st.limit_text = None
        st.last_error = None
        state.save(st)

    def stop_watcher():
        if messagebox.askyesno("cloophole", "Stop watching and close cloophole?"):
            runner.stop()
            _cleanup()
            root.destroy()

    mkbtn(actions, "▶  Resume ticked sessions now", do_resume, accent=True,
          grid=(0, 0), columnspan=2)
    mkbtn(actions, "Enter limit time", enter_limit, grid=(1, 0))
    mkbtn(actions, "Pin a folder", choose_folder, grid=(1, 1))
    mkbtn(actions, "Reset status", reset_status, grid=(2, 0))
    mkbtn(actions, "Stop watching", stop_watcher, grid=(2, 1))
    mkbtn(actions, "Close window", lambda: (_cleanup(), root.destroy()),
          grid=(3, 0), columnspan=2)

    # ---------- live refresh ----------
    def refresh():
        # Never let one bad refresh kill the loop — always reschedule in `finally`.
        try:
            st = state.load()
            running = runner.is_running()
            v_status.config(text=_PHASE_PLAIN.get(st.phase, st.phase))
            v_dot.config(fg=_PHASE_COLOR.get(st.phase, SUB))
            if st.reset_at:
                v_count.config(text=_countdown(st))
                if not v_count.winfo_ismapped():
                    v_count.pack(anchor="w", padx=16, before=v_meta)
            elif v_count.winfo_ismapped():
                v_count.pack_forget()
            where = (f"pinned → {st.work_dir}" if st.work_dir else "the ticked sessions")
            meta = (f"Watcher {'running' if running else 'stopped'}   ·   "
                    f"Claude open now: {'yes' if _detected['live'] else 'no'}\n"
                    f"Resume in: {where}")
            if st.last_error:
                meta += f"\nLast problem: {st.last_error}"
            v_meta.config(text=meta)
            _render_sessions()
        except Exception:
            pass
        finally:
            root.after(1000, refresh)

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
    fit_w = max(520, root.winfo_reqwidth())
    fit_h = root.winfo_reqheight() + 12
    root.geometry(f"{fit_w}x{fit_h}")
    root.minsize(fit_w, 540)
    refresh()
    import gc
    gc.collect()  # drop import/build garbage before the window goes idle
    try:
        root.mainloop()
    finally:
        _cleanup()
