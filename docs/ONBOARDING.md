# ONBOARDING

Welcome. This routes you to the right files by role. Read `CONVENTIONS.md` either
way — it's the contract everyone follows.

## Everyone, first 10 minutes
1. `CLAUDE.md` (repo root) — what cloophole is + the **Golden Rule** (never violate:
   no Claude Code internals, act only via the public CLI + OS process inspection).
2. `docs/STATUS.md` — what's happening right now + what's next.
3. `docs/ROADMAP.md` — the phases and where we are.
4. `claude-resume-product-plan.md` — the full vision and hard constraints.

## By role
- **Engine / state-machine** → `cloophole/daemon.py`, `state.py`, `fire.py` +
  ADR-0001. Every logic change needs a deterministic test (stub `detect_session`
  and `fire.fire`). Respect the Golden Rule.
- **Parsing** → `cloophole/reset_parser.py` + `docs/DATA_MODEL.md` (patterns). New
  pattern ⇒ new test, including garbage-returns-None.
- **Windows internals** → `cloophole/winproc.py` (ctypes PEB), `install_win.py`.
  PEB offsets are 64-bit; see BUGS B1.
- **CLI / UI** → `cloophole/__main__.py`, `ui.py`. Read-only views onto the state file.

## Your first task
Pick the first unchecked batch in the active ADR (`docs/decisions/`), branch from
main, and finish per the "done" definition in `docs/CONVENTIONS.md` §7 (code + header,
tests green, STATUS + progress + ADR checkbox updated in the same change).
Right now that's **Phase 5.2+** (cross-platform) — write ADR-0003 first.
