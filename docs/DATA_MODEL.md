# DATA_MODEL — cloophole

> The shapes that matter. Update in the SAME change that alters a field, key, or pattern.

## `State` — durable runtime record (`cloophole/state.py`)
Persisted as `~/.cloophole/state.json`. The single source of truth for the machine.

| field | type | meaning |
|---|---|---|
| `phase` | str | one of WATCHING / WAITING / ARMED / FIRING / FIRED / ERROR |
| `reset_at` | ISO8601 UTC \| None | when the quota window reopens |
| `queue_note` | str \| None | explicit "what to continue"; None → fallback note |
| `work_dir` | path \| None | **pin**: if set, fire only here; None → fire in every live session's dir |
| `limit_text` | str \| None | raw limit message last parsed |
| `last_fired` | ISO \| None | last successful fire |
| `last_error` | str \| None | last fire error |
| `last_poll` | ISO \| None | last idle probe (gates poll cadence) |
| `live_session` | bool | last observed gate result |
| `updated_at` | ISO | set on every `save()` |

### Phases (state machine, plan §7)
```
WATCHING --limit known (report/poll)--> WAITING
WAITING  --reset reached + live session--> FIRING
WAITING  --reset reached + no session--> ARMED
ARMED    --claude process appears--> FIRING
FIRING   --still limited--> WAITING (re-arm with new reset)
FIRING   --ok--> FIRED --> WATCHING
FIRING   --error--> ERROR --> WATCHING
```
FIRED/ERROR are transient: `daemon._do_fire` lands back on WATCHING within the tick.

**Fire targets (`daemon._fire_dirs`):** a pinned `work_dir` wins; else `--continue`
runs once per live session directory (`winproc.detect_all`, deduped) — "fire in all
selected terminals"; else once in the inherited cwd. Any dir reporting still-limited
re-arms WAITING.

## Config keys (`cloophole/config.py`)
Persisted as `~/.cloophole/config.json`; missing keys fall back to `DEFAULTS`.

| key | default | meaning |
|---|---|---|
| `claude_path` | `claude` | executable name / full path |
| `permission_mode` | `acceptEdits` | non-interactive; headless can't confirm |
| `daemon_tick_sec` | `15` | watcher loop cadence |
| `poll_enabled` | `true` | auto-watch: idle probing to auto-detect the limit |
| `poll_interval_min` | `30` | gentle — probing costs quota |
| `fire_timeout_sec` | `1800` | cap one `--continue` run |
| `claude_process_name` | `claude.exe` | name matched by the live gate |

## `FireResult` (`cloophole/fire.py`)
`ok: bool`, `still_limited: bool`, `new_reset_text: str|None`, `stdout`, `stderr`,
`returncode: int|None`, `error: str|None`. `still_limited` is true when the fire's
own output parses as a fresh limit message.

## Reset-text patterns (`cloophole/reset_parser.py`)
Parse order = most explicit first: **ISO** → **relative** → **clock-time**.
- ISO: `2026-06-22T17:30:00Z`, `2026-06-22 18:00` (naive = local).
- relative: `in 4h 30m`, `in 90 minutes`, `try again in 2 hours`.
- clock: `resets at 5:30 PM`, `try again at 17:00`, `resets 5pm` (rolls to tomorrow
  if already past). All results returned as aware UTC.

## Idle probe (`cloophole/probe.py`)
`probe(cfg) -> (limited: bool, text: str|None)`. Sends one `claude -p` call via
`subproc.run` (no console window). `limited` uses `reset_parser.is_limit_message`
— the same helper as `fire.still_limited`, so they cannot diverge. Gated by
`poll_enabled` + `poll_interval_min` + `State.last_poll` in `daemon.tick`.

## UI — desktop window (`cloophole/gui.py`)
`gui.run()` is the interface (ADR-0007): a Tkinter window showing live status (phase in
plain language, countdown, watcher up?, Claude open now, resume-where) with a note
field, an auto-detect checkbox, and buttons (Resume now, Enter limit time, Choose
folder, Reset status, Stop watching, Close). Auto-refreshes every 1 s from `state.json`;
`fire` runs on a worker thread so the window stays responsive. Stdlib `tkinter` only.
Closing the window leaves the watcher running. (`menu.py`, `ui.py`, `app.py` removed.)

## App lifecycle (`cloophole/runner.py`, `daemon.py`, `gui.py`)
- **Background watcher** = a detached, hidden, single-instance daemon process running
  `daemon.run` (claims `daemon.pid`, runs `daemon.loop`).
- **GUI window** = a separate detached process (`_gui` → `gui.run`), single-instance via
  `gui.pid`.
- **`open`**: `runner.launch()` (watcher) if not running, then `runner.launch_gui()`
  (spawn `pythonw -m cloophole _gui` / frozen exe `_gui`, detached + no window).
- **`close`**: `runner.stop_gui()` + `runner.stop()` (taskkill pid trees).
- **`uninstall`**: stop both + remove `~/.cloophole` + legacy autostart cleanup; exe
  build also drops PATH + deletes its install dir.
- **Single instance:** `daemon.run` exits if `daemon.pid` is live; `gui.run` exits if
  `gui.pid` is live (`winproc.pid_alive`). No run-at-logon.
- `cloophole/install_win.py` is **legacy** — autostart cleanup for old installs only.

## Filesystem (`cloophole/paths.py`)
`~/.cloophole/` (or `$CLOOPHOLE_HOME`): `state.json`, `config.json`,
`cloophole.log`, `daemon.pid`.
