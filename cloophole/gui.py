"""Dedicated desktop window (Tkinter) — the app UI (ADR-0007).

@context  cloophole's UI is a small native window (not web, not tray). Shows
          live status in plain language and offers buttons for every action.
          The background watcher runs as a separate process; this views/controls
          it via the shared state file.
@done     run(): single-instance Tk window, 1s auto-refresh, buttons for resume/
          limit/folder/auto-detect/reset/stop. Stdlib tkinter only.
@todo     mac/Linux polish; theming.
@limits   Needs a display. Headless? use `cloophole daemon`. One window at a time
          (gui.pid). Closing the window leaves the watcher running.
@affects  Launched by CLI `_gui` (spawned by `open`). Reuses state, config, fire,
          runner, reset_parser.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import config, fire, state
from .paths import gui_pid_file
from .reset_parser import parse_reset

_PHASE_PLAIN = {
    state.WATCHING: "Watching for your usage limit",
    state.WAITING: "Limit reached - waiting for the reset time",
    state.ARMED: "Reset is due - waiting for a Claude window to open",
    state.FIRING: "Resuming your work now...",
    state.FIRED: "Just resumed your work",
    state.ERROR: "Something went wrong last time",
}

BG = "#0d1117"
CARD = "#161b22"
FG = "#c9d1d9"
SUB = "#8b949e"
ACCENT = "#3fb950"


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

    from . import runner

    if runner.is_gui_running():
        return
    gui_pid_file().write_text(str(os.getpid()), encoding="utf-8")

    root = tk.Tk()
    root.title("cloophole")
    root.configure(bg=BG)
    root.geometry("440x600")  # tall enough for all rows; clamped to content below
    root.minsize(440, 560)

    def lbl(parent, text, color=FG, font=("Segoe UI", 10), **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=color, font=font, **kw)

    # --- header ---
    lbl(root, "cloophole", ACCENT, ("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(16, 0))
    lbl(root, "Keeps your Claude Code work going after the usage limit resets.",
        SUB, ("Segoe UI", 9)).pack(anchor="w", padx=18)

    # --- status card ---
    card = tk.Frame(root, bg=CARD)
    card.pack(fill="x", padx=14, pady=12)
    v_status = lbl(card, "", FG, ("Segoe UI", 11, "bold"), bg=CARD)
    v_status.pack(anchor="w", padx=14, pady=(12, 2))
    v_count = lbl(card, "", ACCENT, ("Segoe UI", 22, "bold"), bg=CARD)
    v_count.pack(anchor="w", padx=14)
    v_meta = lbl(card, "", SUB, ("Segoe UI", 9), bg=CARD, justify="left")
    v_meta.pack(anchor="w", padx=14, pady=(2, 12))

    # --- "resume what" ---
    lbl(root, "What to resume after the reset:", SUB, ("Segoe UI", 9)).pack(anchor="w", padx=18)
    note_var = tk.StringVar(value=state.load().queue_note or "")

    def save_note(*_):
        st = state.load()
        st.queue_note = note_var.get().strip() or None
        state.save(st)

    note_entry = tk.Entry(root, textvariable=note_var, bg=CARD, fg=FG,
                          insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    note_entry.pack(fill="x", padx=18, pady=(2, 2))
    note_entry.bind("<Return>", save_note)
    note_entry.bind("<FocusOut>", save_note)
    lbl(root, "(blank = pick up where you left off)", SUB, ("Segoe UI", 8)).pack(anchor="w", padx=18)

    # --- auto-detect toggle ---
    auto_var = tk.BooleanVar(value=config.get("poll_enabled"))

    def toggle_auto():
        config.set_("poll_enabled", auto_var.get())

    tk.Checkbutton(root, text="Auto-detect the limit by itself", variable=auto_var,
                   command=toggle_auto, bg=BG, fg=FG, selectcolor=CARD,
                   activebackground=BG, activeforeground=FG, font=("Segoe UI", 9)
                   ).pack(anchor="w", padx=14, pady=(8, 0))
    lbl(root, "(off by default - this probes Claude on a timer and spends a little "
              "of your usage)", SUB, ("Segoe UI", 8)).pack(anchor="w", padx=18)

    # --- actions ---
    btns = tk.Frame(root, bg=BG)
    btns.pack(fill="x", padx=14, pady=10)

    def mkbtn(text, cmd, col, accent=False):
        b = tk.Button(btns, text=text, command=cmd, relief="flat",
                      bg=ACCENT if accent else CARD, fg="#08110a" if accent else FG,
                      activebackground=ACCENT if accent else "#21262d",
                      font=("Segoe UI", 10, "bold" if accent else "normal"),
                      padx=8, pady=8, width=18, cursor="hand2")
        b.grid(row=col[0], column=col[1], padx=4, pady=4, sticky="ew")
        return b

    btns.columnconfigure(0, weight=1)
    btns.columnconfigure(1, weight=1)

    def do_resume():
        save_note()
        v_status.config(text="Resuming your Claude work...")
        def work():
            st = state.load()
            res = fire.fire(st.work_dir, st.queue_note)
            msg = ("Couldn't resume: " + res.error) if res.error else (
                "Still limited - the reset hasn't landed yet." if res.still_limited
                else "Done - told Claude to keep going.")
            root.after(0, lambda: messagebox.showinfo("cloophole", msg))
        threading.Thread(target=work, daemon=True).start()

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
            messagebox.showinfo("cloophole",
                                f"Got it - will resume after {dt.astimezone():%I:%M %p on %b %d}.")
        else:
            messagebox.showwarning("cloophole",
                                   "Couldn't read a time from that. Try e.g. 'resets at 5:30 PM'.")

    def choose_folder():
        d = filedialog.askdirectory(title="Resume in which folder? (Cancel = all windows)")
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

    mkbtn("Resume now", do_resume, (0, 0), accent=True)
    mkbtn("Enter limit time", enter_limit, (0, 1))
    mkbtn("Choose folder", choose_folder, (1, 0))
    mkbtn("Reset status", reset_status, (1, 1))
    mkbtn("Stop watching", stop_watcher, (2, 0))
    mkbtn("Close window", lambda: (_cleanup(), root.destroy()), (2, 1))

    # --- live refresh ---
    def refresh():
        st = state.load()
        running = runner.is_running()
        v_status.config(text=_PHASE_PLAIN.get(st.phase, st.phase))
        v_count.config(text=_countdown(st) if st.reset_at else "")
        meta = (
            f"Watcher: {'running' if running else 'stopped'}    "
            f"Claude open now: {'yes' if st.live_session else 'no'}\n"
            f"Resume in: {st.work_dir or 'every open Claude window'}"
        )
        if st.last_error:
            meta += f"\nLast problem: {st.last_error}"
        v_meta.config(text=meta)
        root.after(1000, refresh)

    def _cleanup():
        try:
            gui_pid_file().unlink()
        except OSError:
            pass

    root.protocol("WM_DELETE_WINDOW", lambda: (_cleanup(), root.destroy()))
    # Fit the window to its actual content so no button is clipped (DPI/font safe).
    root.update_idletasks()
    fit_w, fit_h = max(440, root.winfo_reqwidth()), root.winfo_reqheight()
    root.geometry(f"{fit_w}x{fit_h}")
    root.minsize(fit_w, fit_h)
    refresh()
    import gc
    gc.collect()  # drop import/build garbage before the window goes idle
    try:
        root.mainloop()
    finally:
        _cleanup()
