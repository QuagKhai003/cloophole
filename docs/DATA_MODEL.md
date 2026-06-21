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
| `poll_enabled` | `false` | Phase 3 idle probing (not yet wired) |
| `poll_interval_min` | `30` | gentle — probing costs quota |
| `ui_enabled` | `true` | daemon serves the status page on a bg thread |
| `ui_port` | `8787` | local status page |
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

## UI (`cloophole/ui.py`)
The daemon serves the status page itself: `daemon.run` calls `ui.start_background(port)`
(a daemon thread) when `ui_enabled`, so the page is live at `http://127.0.0.1:<ui_port>`
without a separate process. `cloophole open` launches a browser; `cloophole ui` runs it
in the foreground. `start_background(0)` binds a free port (used in tests).

## Install methods (`cloophole/install_win.py`)
- **shim** (default, no admin): `.vbs` in the user Startup folder, runs the daemon
  hidden at logon. `cloophole install`.
- **task** (opt-in): Task Scheduler ONLOGON. `cloophole install --task` (may need an
  elevated terminal).
- `install` is idempotent + no-admin: stops the old daemon, best-effort drops a
  leftover task, writes the shim, and `start_now()` (detached + hidden) — no reboot.
- `start` / `stop` manage the daemon via `daemon.pid` (liveness-checked).
- **Single instance:** `daemon.run` exits if a live daemon already holds `daemon.pid`
  (`winproc.pid_alive`), so duplicate launchers (leftover task + shim) can't double-fire.

## Filesystem (`cloophole/paths.py`)
`~/.cloophole/` (or `$CLOOPHOLE_HOME`): `state.json`, `config.json`,
`cloophole.log`, `daemon.pid`.
