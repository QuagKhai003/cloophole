"""The long-lived watcher: drives the state machine each tick.

@context  The loop that enforces "never fire blind": each tick reloads state,
          checks the reset clock + live gate, and only then fires.
@done     tick() (hook signal -> real reset via payload/probe/estimate; WATCHING
          poll + 1h auto-refetch; WAITING surgical rechecks + 1h refetch; ARMED),
          _do_fire (fires every live session dir, or a pinned work_dir),
          detect_sessions, claim_pid/release_pid/loop/run (single-instance watcher).
@todo     non-Windows detect (P5).
@limits   detect_sessions returns (False, []) off Windows in this build.
@affects  Reads/writes state; calls winproc.detect_all, claude_hook.read_signal
          (hook auto-detect), probe.probe (recheck), fire.resume (inject/window) or
          fire.fire (headless). _fire_dirs honors state.work_dir pin / excluded_dirs
          ticks / hook_dir fallback. CALLED BY: runner (spawns `daemon`), CLI daemon.
          Cadence = config daemon_tick_sec. Transitions documented in DATA_MODEL.

Transitions (product plan §7):
  WATCHING --limit known--> WAITING
  WAITING  --reset reached + live session--> FIRING
  WAITING  --reset reached + no session--> ARMED
  ARMED    --claude process appears--> FIRING
  FIRING   --still limited--> WAITING (re-arm with new reset)
  FIRING   --ok--> FIRED --> WATCHING
  FIRING   --error--> ERROR --> WATCHING

The live-session gate is OS process inspection only (§9.3); it cannot see what
the session is mid-task on, which is why the queue note exists.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone

from . import claude_hook, config, fire, probe, state
from .paths import log_file, pid_file


def _due_to_poll(st: state.State, cfg: dict, now: datetime) -> bool:
    if not cfg.get("poll_enabled"):
        return False
    if not st.last_poll:
        return True
    try:
        last = datetime.fromisoformat(st.last_poll)
    except ValueError:
        return True
    return (now - last).total_seconds() >= cfg.get("poll_interval_min", 30) * 60


def _due_to_refetch(st: state.State, cfg: dict, now: datetime) -> bool:
    """The separate 1-hour loop: catch the limit on our own (WATCHING) and refresh
    the reset time (WAITING). Distinct from poll_enabled and the surgical rechecks."""
    if not cfg.get("auto_refetch", True):
        return False
    if not st.last_poll:
        return True
    try:
        last = datetime.fromisoformat(st.last_poll)
    except (ValueError, TypeError):
        return True
    return (now - last).total_seconds() >= cfg.get("refetch_interval_min", 60) * 60


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()}  {msg}"
    try:
        with log_file().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def detect_sessions(cfg: dict) -> tuple[bool, list[str]]:
    """(any live claude, cwds of every live session). Windows-first build."""
    if sys.platform == "win32":
        from . import winproc
        return winproc.detect_all(cfg["claude_process_name"])
    # Non-Windows: detection not implemented here yet (ADR-0003).
    return False, []


def session_keys(cfg: dict) -> tuple[bool, list[str]]:
    """(any live, [session keys]) across Windows claude.exe + WSL tmux panes. The
    keys are what `_fire_dirs` selects and `fire.resume` routes on (a Windows folder,
    or 'wsl:<pane>')."""
    if sys.platform != "win32":
        return detect_sessions(cfg)
    from . import sessions
    sess = sessions.list_all(cfg)
    return bool(sess), [s["key"] for s in sess]


def _fire_dirs(st: state.State, cwds: list[str]) -> list[str | None]:
    """Which directories to fire in. A pin (st.work_dir) wins; otherwise every
    live session's dir ("fire in all selected terminals"); else inherit cwd."""
    if st.work_dir:
        return [st.work_dir]
    if cwds:
        excluded = set(st.excluded_dirs or [])
        selected = [d for d in cwds if d not in excluded]
        return selected  # may be [] if the user un-ticked every live session
    if st.hook_dir:  # no live cwd readable -> fall back to where the limit hit
        return [st.hook_dir]
    return [None]


def _iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _track_window(st: state.State, now: datetime) -> bool:
    """Remember the upcoming 5h quota-window reset that the statusLine reports, so we
    still know it after the window passes (the statusLine only reports the NEXT one on
    Claude's next turn). Returns True if we recorded a new window."""
    try:
        from . import statusline
        info = statusline.read_status() or {}
    except Exception:
        return False
    w = _iso(info.get("window_reset_at"))
    if w and w > now and st.window_at != w.isoformat():
        st.window_at = w.isoformat()
        return True
    return False


_no_targets_warned = False   # so an un-ticked reset doesn't spam the log every tick


def _do_fire(st: state.State, cfg: dict, cwds: list[str]) -> None:
    global _no_targets_warned
    dirs = _fire_dirs(st, cwds)
    if not dirs:
        # Nothing ticked. Stay armed (tick a session and the next tick fires) but do NOT
        # log or write state every tick — that spammed cloophole.log and rewrote state
        # every 5s forever.
        if not _no_targets_warned:
            log("nothing ticked to resume — staying armed; tick a session and it fires")
            _no_targets_warned = True
        return
    _no_targets_warned = False
    st.phase = state.FIRING
    state.save_runtime(st)
    log(f"FIRING in {len(dirs)} dir(s): {dirs} note={st.queue_note!r}")

    last_error = None
    relimit_text = None
    fired_ok = False
    mode = cfg.get("resume_mode", "inject")
    if mode != "headless":
        # inject (type into the open session) or window (new visible window). The
        # re-check probes already confirmed the reset, so we don't need headless
        # still_limited detection here.
        for d in dirs:
            err = fire.resume(d, state.note_for(st, d), cfg)
            if err:
                last_error = err
                log(f"  ERROR in {d or '(cwd)'}: {err}")
            else:
                fired_ok = True
                log(f"  resumed ({mode}) {d or '(cwd)'}")
    else:
        for d in dirs:
            res = fire.fire(d, state.note_for(st, d), cfg)
            if res.error:
                last_error = res.error
                log(f"  ERROR in {d or '(cwd)'}: {res.error}")
            elif res.still_limited:
                relimit_text = res.new_reset_text
                log(f"  still limited in {d or '(cwd)'}")
            else:
                fired_ok = True
                log(f"  fired {d or '(cwd)'} rc={res.returncode}")

    # Any dir still limited -> the reset didn't really land; re-arm.
    if relimit_text:
        from .reset_parser import parse_reset
        dt = parse_reset(relimit_text)
        st.reset_at = dt.isoformat() if dt else st.reset_at
        st.phase = state.WAITING
        log(f"re-armed for {st.reset_at}")
        state.save_runtime(st)
        return

    if fired_ok:
        st.last_fired = datetime.now(timezone.utc).isoformat()
        st.last_error = None
        st.reset_at = None
        st.limit_text = None
        st.hook_dir = None
        st.manual_reset = False
        st.recheck_at = []
        state.clear_notes()   # one-shot: retype a message for the next limit
        log("messages cleared (one-shot) — type a new one for the next limit")
    else:
        st.last_error = last_error
    st.phase = state.WATCHING
    state.save_runtime(st)


def tick(cfg: dict) -> state.State:
    """One iteration of the loop. Returns the (possibly updated) state.

    IMPORTANT: an idle tick must NOT write state. The GUI self-detects sessions and
    saves the user's intent (notes/ticks) on every change; if the daemon also wrote
    state every few seconds (for live_dirs the GUI doesn't even read) it would fight
    those saves and lose the user's edits. So we only save on a real transition.
    """
    st = state.load()
    live, cwds = session_keys(cfg)   # keys = Windows folders + WSL tmux panes
    now = datetime.now(timezone.utc)

    # Zero-quota auto-detect: Claude's StopFailure/rate_limit hook dropped a signal.
    sig = claude_hook.read_signal()
    if sig:
        claude_hook.clear_signal()
        if st.phase in (state.WATCHING, state.ARMED, state.FIRED, state.ERROR):
            from .reset_parser import parse_reset
            limit_text = f"rate-limit hook @ {sig.get('ts')}"
            reset = None
            # 1) real reset straight from the hook payload (zero quota)
            if sig.get("reset_at"):
                try:
                    reset = datetime.fromisoformat(sig["reset_at"])
                except (ValueError, TypeError):
                    reset = None
            # 1b) the statusLine already captured the real 5h reset (zero quota)
            if reset is None:
                try:
                    from . import statusline
                    info = statusline.read_status() or {}
                    wdt = datetime.fromisoformat(info["window_reset_at"]) \
                        if info.get("window_reset_at") else None
                    if wdt and wdt > now:
                        reset = wdt
                except Exception:
                    pass
            # 2) else one probe NOW: you're limited, so the call is rejected and
            #    returns the limit message with the real reset (cheap, one-shot).
            if reset is None and cfg.get("probe_on_limit", True):
                limited, text = probe.probe(cfg)
                if limited and text:
                    dt = parse_reset(text)
                    if dt:
                        reset = dt
                        limit_text = text.strip()[:200]
            # 3) else fall back to the worst-case window estimate
            estimated = reset is None
            if reset is None:
                reset = now + timedelta(hours=cfg.get("limit_window_hours", 5))
            st.reset_at = reset.isoformat()
            st.limit_text = limit_text
            st.hook_dir = sig.get("cwd")
            st.phase = state.WAITING
            st.last_poll = now.isoformat()  # start the 1h refetch clock from here
            # Re-checks: if we had to ESTIMATE, recheck soon to correct it; always
            # recheck near the reset (catches an early reset, e.g. a plan upgrade).
            before = reset - timedelta(minutes=cfg.get("recheck_before_min", 10))
            cands = [before]
            if estimated:
                cands.append(now + timedelta(minutes=cfg.get("recheck_after_min", 10)))
            st.recheck_at = sorted(t.isoformat() for t in cands if t > now)
            log(f"rate-limit hook -> WAITING, reset {st.reset_at} "
                f"({'estimate' if estimated else 'actual'}), dir={st.hook_dir}, "
                f"rechecks={st.recheck_at}")
            state.save_runtime(st)
            return st

    # WATCHING: the 5-HOUR QUOTA WINDOW rolling over is NOT a limit hit (nothing was
    # blocked), so we only resume then if the user actually QUEUED a message. Track the
    # upcoming window from the statusLine and fire once when it passes.
    if st.phase == state.WATCHING and cfg.get("fire_on_window_reset", True):
        changed = _track_window(st, now)
        wa = _iso(st.window_at)
        if wa and now >= wa and st.window_at != st.fired_window_at:
            st.fired_window_at = st.window_at          # never fire the same window twice
            queued = bool((st.queue_note or "").strip()) or bool(st.session_notes)
            if queued and live:
                state.save_runtime(st)
                log(f"5h window reset ({st.window_at}) + a queued message -> resuming")
                _do_fire(st, cfg, cwds)
                return state.load()
            if queued and not live:
                log("5h window reset, message queued, but no live session yet")
            changed = True
        if changed:
            state.save_runtime(st)

    # WATCHING: the idle poll AND the 1h refetch loop both probe to catch the limit
    # on our own (a backup to the hook). Either being due triggers one probe.
    if st.phase == state.WATCHING and (_due_to_poll(st, cfg, now)
                                       or _due_to_refetch(st, cfg, now)):
        st.last_poll = now.isoformat()
        limited, text = probe.probe(cfg)
        if limited:
            from .reset_parser import parse_reset
            dt = parse_reset(text or "")
            st.reset_at = dt.isoformat() if dt else st.reset_at
            st.limit_text = text
            st.phase = state.WAITING
            log(f"idle probe: limited -> WAITING, reset {st.reset_at}")
        state.save_runtime(st)
        return st

    if st.phase == state.WAITING:
        from .reset_parser import parse_reset
        # 1) Due surgical re-check? Probe once to confirm the limit (catches an early
        #    reset). Kept first so a cleared limit can fire in this same tick.
        #    Skipped when the user typed the reset time (their truth, no probing).
        if not st.manual_reset and st.recheck_at:
            try:
                nxt = datetime.fromisoformat(st.recheck_at[0])
            except (ValueError, TypeError):
                nxt = None
            if nxt is None or now >= nxt:
                st.recheck_at = st.recheck_at[1:]
                limited, text = probe.probe(cfg)
                if not limited:
                    log("recheck: no longer limited -> reset reached early")
                    st.reset_at = now.isoformat()  # let the reset logic below fire
                else:
                    dt = parse_reset(text or "")
                    if dt:
                        st.reset_at = dt.isoformat()  # refine the estimate
                    log(f"recheck: still limited (reset ~{st.reset_at})")
                    state.save_runtime(st)
                    return st
        # 2) Reset reached? fire / arm.
        rst = st.reset_dt()
        if rst and now >= rst:
            if live:
                _do_fire(st, cfg, cwds)
                return state.load()
            st.phase = state.ARMED
            log("reset reached, no live session -> ARMED")
            state.save_runtime(st)   # persist the WAITING -> ARMED transition
            return st
        # 3) Still waiting (reset in the future): the SEPARATE 1h refetch loop keeps
        #    the reset time fresh / catches an early reset. Not for a manual time.
        if not st.manual_reset and _due_to_refetch(st, cfg, now):
            st.last_poll = now.isoformat()
            limited, text = probe.probe(cfg)
            if not limited:
                log("refetch: no longer limited -> reset reached early")
                st.reset_at = now.isoformat()
            else:
                dt = parse_reset(text or "")
                if dt:
                    st.reset_at = dt.isoformat()
                log(f"refetch: still limited (reset ~{st.reset_at})")
            state.save_runtime(st)
            return st

    elif st.phase == state.ARMED:
        if live:
            log("live session appeared -> FIRING")
            _do_fire(st, cfg, cwds)
            return state.load()

    # Idle tick — no transition: DO NOT write state (would clobber the GUI's edits).
    return st


def _already_running() -> bool:
    """Single-instance guard: another live daemon holds the pid file.

    Makes duplicate launchers (e.g. a leftover Task Scheduler task + the Startup
    shim) harmless — the second daemon exits instead of double-firing.
    """
    if sys.platform != "win32":
        return False
    f = pid_file()
    if not f.exists():
        return False
    try:
        old = int(f.read_text().strip())
    except (ValueError, OSError):
        return False
    from . import winproc
    return old != __import__("os").getpid() and winproc.pid_alive(old)


def _owns_pid() -> bool:
    """True if this process is the one recorded in the pid file."""
    try:
        return int(pid_file().read_text().strip()) == __import__("os").getpid()
    except (ValueError, OSError):
        return False


def claim_pid() -> bool:
    """FORCE-claim the pid file — the newest daemon always wins. An older
    (new-build) daemon notices it lost ownership on its next tick and exits, so two
    daemons can never coexist and clobber each other's state."""
    pid_file().write_text(str(__import__("os").getpid()), encoding="utf-8")
    return True


def release_pid() -> None:
    if not _owns_pid():  # don't delete a newer daemon's pid file
        return
    try:
        pid_file().unlink()
    except OSError:
        pass


def loop(cfg: dict, stop: "object | None" = None) -> None:
    """Run ticks until `stop` (a threading.Event) is set, or forever.

    Does NOT manage the pid file beyond the self-heal ownership check — `run()`
    owns claiming/releasing it.
    """
    import threading
    stop = stop or threading.Event()
    interval = cfg["daemon_tick_sec"]
    while not stop.is_set():
        if sys.platform == "win32" and not _owns_pid():
            log("lost pid ownership to a newer daemon; exiting")
            return
        try:
            tick(cfg)
        except Exception as e:  # keep the loop alive
            log(f"tick error: {e!r}")
        stop.wait(interval)


def _trim_memory() -> None:
    """Shrink the long-lived watcher's footprint: collect once, freeze the
    survivors out of GC tracking (less churn), and relax thresholds so the idle
    loop barely allocates/collects."""
    import gc
    gc.collect()
    gc.freeze()
    gc.set_threshold(50_000, 500, 500)


def run() -> None:
    """The background watcher loop (foreground process; detached by `open`)."""
    cfg = config.load()
    if not claim_pid():
        log("another daemon is already running; exiting")
        return
    log(f"daemon start pid={__import__('os').getpid()} tick={cfg['daemon_tick_sec']}s")
    _trim_memory()
    try:
        loop(cfg)
    except KeyboardInterrupt:
        log("daemon stop (KeyboardInterrupt)")
    finally:
        release_pid()
