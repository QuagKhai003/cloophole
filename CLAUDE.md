# CLAUDE.md — cloophole

> Auto-loaded every session. The project's working memory. Read it first.
> Keep it short and current. Detail lives in `docs/`.

## What this is
cloophole is a lightweight background daemon that **auto-resumes your Claude Code
work when your usage quota resets**. You hit the limit and walk away; when the
window reopens and a `claude` session is present (or the next time one appears),
cloophole runs `claude --continue` in the recorded directory so the work picks
itself back up. Windows-first. Full vision: `claude-resume-product-plan.md`.

## The Golden Rule (never violate)
**cloophole never touches Claude Code's internals or its visible REPL. It observes
only via OS process inspection and acts only through the public `claude` CLI.**
That means: no reading session/transcript files to learn task state, no keystroke
injection into a live terminal, no scraping Claude Code internal state. The live
gate is process detection; "what to resume" comes from the user's queue note, not
from Claude's memory. If a feature needs to cross this line, stop and redesign.

## Tech stack
- **Language:** Python 3.10+ (developed on 3.14), standard library only.
- **Windows process/cwd detection:** `ctypes` reading the target PEB — **zero**
  third-party runtime dependencies (no psutil).
- **UI:** stdlib `http.server` — one self-refreshing page, no JS framework.
- **Install:** Task Scheduler via `schtasks` (run-at-logon).
- **Tests:** `pytest` (dev-only dependency).
- **Secrets:** none. State/config/logs live in `~/.cloophole/` (override
  `$CLOOPHOLE_HOME`); never committed.

## Where things live
```
cloophole/        # the package — one module per responsibility
  paths.py        #   filesystem locations (state/config/log/pid)
  config.py       #   tunables (JSON, defaults)
  state.py        #   durable state machine record (the source of truth)
  reset_parser.py #   limit text -> UTC reset timestamp
  winproc.py      #   Windows claude.exe detection + PEB cwd read
  fire.py         #   run `claude --continue` headless
  daemon.py       #   the watcher loop + transitions
  ui.py           #   local status page + /state JSON
  install_win.py  #   Task Scheduler install/uninstall
  __main__.py     #   CLI dispatch
tests/            # pytest (parser, state machine, idle poll)
docs/             # living documentation — read these, keep them updated
claude-resume-product-plan.md   # the product vision
README.md                       # user-facing readme
```

## How to run
```bash
pip install -e .            # first time (also gives the `cloophole` command)
python -m cloophole daemon  # run the watcher in the foreground
python -m cloophole status  # inspect state
python -m pytest -q         # fast/offline suite
```

## Current state (read docs/STATUS.md for live detail)
- **Done & working:** engine + state machine, reset parser, Windows process/cwd
  detection (verified against the real `claude.exe`), `--continue` fire in **all**
  live session dirs (or a pinned one), idle quota poll, full CLI, local UI, no-admin
  Startup-shim installer + `start`/`stop`, hidden (no-window) fire.
- **In flight:** none — pick the next ADR.
- **Next direction:** cross-platform mac/Linux (Phase 5, ADR-0003); Phase 6 polish.
- **Tests:** 19 passing — `python -m pytest -q`.

## New here?
Start at `docs/ONBOARDING.md`. `docs/CONVENTIONS.md` is the mandatory hygiene contract.

## Working agreement (how to develop here)
Production code, many readers. Optimise for the next reader.
1. Follow `docs/CONVENTIONS.md` — small files, one concept per file, a header brief
   on every source file.
2. Before coding, check `docs/ROADMAP.md` (current phase scope) + `docs/STATUS.md`.
3. Core/logic changes need a deterministic, offline test. No exceptions.
4. Changed a state field / config key / message shape? Update `docs/DATA_MODEL.md`
   in the same change.
5. Hit a bug/limitation → log in `docs/BUGS.md`. Made a non-obvious choice → add an
   ADR under `docs/decisions/`.
6. "Done" = code + header updated, tests green, `docs/STATUS.md` + `docs/progress/`
   updated, ADR batch ticked.
