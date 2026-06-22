# ADR-0005 — Standalone .exe + one-line PowerShell installer

**Status:** Accepted — COMPLETE · 2026-06-22 · Builds on ADR-0003.

## Context
Users want the now-common open-source install UX: one PowerShell line
(`irm …/install.ps1 | iex`) that needs no Python, no pip, no manual steps — then
`cloophole open`. That requires shipping a self-contained executable, not a Python
package.

## Decision & key rules
- **Ship a standalone `cloophole.exe`** built with PyInstaller (onefile, console).
  Console so CLI output works; the detached tray child uses `CREATE_NO_WINDOW`, so it
  still shows no window.
- **`install.ps1`** downloads the exe from the repo's latest GitHub Release into
  `%LOCALAPPDATA%\Programs\cloophole` and adds it to the user PATH. No admin.
- **Frozen-aware launch:** `runner._app_command()` relaunches `sys.executable _app`
  when frozen (no Python to call); `cloophole uninstall` removes PATH + the install
  dir (delete scheduled after exit, since a running exe can't delete itself).
- **CI builds it:** pushing a `v*` tag runs `.github/workflows/release.yml`
  (test → PyInstaller → upload asset), so the install URL always has a fresh exe.
- Source install (`pip install -e .`) stays supported for developers.

## Plan (batches)
- [x] **P1 — PyInstaller build.** `packaging/entry.py` + `cloophole.spec`; onefile exe.
  Verified: status/open/attach/close all work from the exe (no Python). Shipped.
- [x] **P2 — installer scripts.** `install.ps1` (download + PATH), `uninstall.ps1`;
  frozen-aware `runner` + `uninstall` self-removal. Shipped.
- [x] **P3 — release CI.** `release.yml` builds + attaches `cloophole.exe` on tag.
  Shipped.

## Acceptance
- `irm …/install.ps1 | iex` then `cloophole open` works on a machine without Python.
- A tag push produces a release with `cloophole.exe` attached.
- `cloophole uninstall` (exe) removes PATH + files; source path unaffected.

## Notes for the executor
- `OWNER/REPO` in the scripts/README must be set to the real GitHub repo before the
  one-liner resolves; the repo must be pushed and a `v*` tag released once.
- mac/Linux packaging is future (separate ADR).
