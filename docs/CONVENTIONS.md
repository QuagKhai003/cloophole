# CONVENTIONS — how we keep cloophole production-grade

Assume **many people work here**. Optimise for a stranger finding their way. These
rules are mandatory.

## 1. Folder & file structure
- **Split by responsibility.** One module = one job (see the map in `CLAUDE.md`).
- **Keep files small.** Soft cap **~200 lines**. Past that, or doing two jobs → split.
- One concept per file; name the file after the concept. No "utils" dumping ground.
- **Zero third-party runtime deps.** Stdlib + `ctypes` only. `pytest` is dev-only.
  Adding a runtime dependency requires an ADR.

## 2. Every source file starts with a header brief
```python
"""<Title> — one line.

@context  What this file is and why it exists.
@done     What is implemented here.
@todo     What's left (or "—").
@limits   Hard constraints (e.g. Windows-only; PURE: no I/O).
@affects  What it depends on / is depended on by.
"""
```
Update the header when behaviour changes.

## 3. Two always-current "what's happening" files
- **`docs/STATUS.md`** — the truth for *right now* (active task, next, blockers).
  Update at the start and end of every session.
- **`docs/progress/`** — the history (changelog), one file per month, newest on top.

## 4. Keep the model current
- **`docs/DATA_MODEL.md`** — the `State` fields, config keys, `FireResult` shape,
  and limit-text patterns. Update whenever you add or change any of them.

## 5. Decisions & issues are logged, not remembered
- Non-obvious choice → an ADR under `docs/decisions/`, linked from its `README.md`.
- Bug/limitation → log in `docs/BUGS.md` immediately.

## 6. Tests
- Core/logic changes ship a deterministic offline test. Stub `detect_session` and
  `fire.fire` for state-machine tests; never spawn a real `claude` in the fast suite.
- The `reset_parser` is the riskiest unit (free-form text) — every new pattern gets
  a test, including a garbage-returns-None case.
- `$CLOOPHOLE_HOME` isolates state per test (see `tests/test_state_machine.py`).

## 7. Platform discipline (Windows-first)
- Windows-specific code lives in clearly named modules (`winproc.py`,
  `install_win.py`) and is imported lazily / guarded by `sys.platform`.
- `winproc.py` PEB offsets are **64-bit**. Document any 32-bit handling explicitly.
- Never let a Windows-only import crash a non-Windows import of the package.

## 8. Definition of "done"
1. Code + header brief updated. 2. Tests green. 3. `STATUS.md` + `progress/`
   (+ `DATA_MODEL.md` if shapes changed) updated. 4. ADR batch ticked; new
   decision/limitation logged if any.

## 9. Git
- Always branch (`feature/…`, `fix/…`, `phase/…`, `docs/…`). One unit per branch.
- Conventional commits. Merge to main locally when green. No push without approval.
- End commit messages with the required Co-Authored-By trailer.
