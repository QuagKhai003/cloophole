"""The long-lived watcher: drives the state machine each tick.

@context  The loop that enforces "never fire blind": each tick reloads state,
          checks the reset clock + live gate, and only then fires.
@done     tick() (WATCHING poll + WAITING/ARMED transitions), _do_fire (fires in
          every live session dir, or a pinned work_dir), detect_sessions,
          claim_pid/release_pid/loop/run (single-instance background watcher).
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


def _do_fire(st: state.State, cfg: dict, cwds: list[str]) -> None:
    dirs = _fire_dirs(st, cwds)
    if not dirs:  # user un-ticked every detected session -> nothing to resume
        log("no selected sessions to fire (all un-ticked); staying put")
        state.save(st)
        return
    st.phase = state.FIRING
    state.save(st)
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
            err = fire.resume(d, st.queue_note, cfg)
            if err:
                last_error = err
                log(f"  ERROR in {d or '(cwd)'}: {err}")
            else:
                fired_ok = True
                log(f"  resumed ({mode}) {d or '(cwd)'}")
    else:
        for d in dirs:
            res = fire.fire(d, st.queue_note, cfg)
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
        state.save(st)
        return

    if fired_ok:
        st.last_fired = datetime.now(timezone.utc).isoformat()
        st.last_error = None
        st.reset_at = None
        st.limit_text = None
        st.hook_dir = None
        st.recheck_at = []
    else:
        st.last_error = last_error
    st.phase = state.WATCHING
    state.save(st)


def tick(cfg: dict) -> state.State:
    """One iteration of the loop. Returns the (possibly updated) state."""
    st = state.load()
    live, cwds = detect_sessions(cfg)
    st.live_session = live
    # Keep the last good list on a transient empty read (a PEB cwd read can flake
    # while Claude is still live) so the GUI list doesn't flicker. Only clear it
    # when no session is live at all.
    if cwds or not live:
        st.live_dirs = list(cwds)
    now = datetime.now(timezone.utc)

    # Zero-quota auto-detect: Claude's StopFailure/rate_limit hook dropped a signal.
    sig = claude_hook.read_signal()
    if sig:
        claude_hook.clear_signal()
        if st.phase in (state.WATCHING, state.ARMED, state.FIRED, state.ERROR):
            hours = cfg.get("limit_window_hours", 5)
            reset = now + timedelta(hours=hours)
            st.reset_at = reset.isoformat()
            st.limit_text = f"rate-limit hook @ {sig.get('ts')}"
            st.hook_dir = sig.get("cwd")
            st.phase = state.WAITING
            # Surgical re-checks (a probe confirms reality, e.g. a plan upgrade that
            # cleared the limit early): once shortly after detection, once near the
            # estimated reset. Only future times, soonest first.
            after = now + timedelta(minutes=cfg.get("recheck_after_min", 10))
            before = reset - timedelta(minutes=cfg.get("recheck_before_min", 10))
            st.recheck_at = sorted(t.isoformat() for t in (after, before) if t > now)
            log(f"rate-limit hook -> WAITING, est reset {st.reset_at}, dir={st.hook_dir}, "
                f"rechecks={st.recheck_at}")
            state.save(st)
            return st

    if st.phase == state.WATCHING and _due_to_poll(st, cfg, now):
        st.last_poll = now.isoformat()
        limited, text = probe.probe(cfg)
        if limited:
            from .reset_parser import parse_reset
            dt = parse_reset(text or "")
            st.reset_at = dt.isoformat() if dt else st.reset_at
            st.limit_text = text
            st.phase = state.WAITING
            log(f"idle probe: limited -> WAITING, reset {st.reset_at}")
        state.save(st)
        return st

    if st.phase == state.WAITING:
        # Due re-check? Probe once to confirm the limit is real (catches an early reset).
        if st.recheck_at:
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
                    from .reset_parser import parse_reset
                    dt = parse_reset(text or "")
                    if dt:
                        st.reset_at = dt.isoformat()  # refine the estimate
                    log(f"recheck: still limited (reset ~{st.reset_at})")
                    state.save(st)
                    return st
        rst = st.reset_dt()
        if rst and now >= rst:
            if live:
                _do_fire(st, cfg, cwds)
                return state.load()
            st.phase = state.ARMED
            log("reset reached, no live session -> ARMED")

    elif st.phase == state.ARMED:
        if live:
            log("live session appeared -> FIRING")
            _do_fire(st, cfg, cwds)
            return state.load()

    state.save(st)
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


def claim_pid() -> bool:
    """Take the single-instance pid file. False if another daemon already holds it."""
    if _already_running():
        return False
    pid_file().write_text(str(__import__("os").getpid()), encoding="utf-8")
    return True


def release_pid() -> None:
    try:
        pid_file().unlink()
    except OSError:
        pass


def loop(cfg: dict, stop: "object | None" = None) -> None:
    """Run ticks until `stop` (a threading.Event) is set, or forever.

    Does NOT manage the pid file — `run()` owns that.
    """
    import threading
    stop = stop or threading.Event()
    interval = cfg["daemon_tick_sec"]
    while not stop.is_set():
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
