# Decisions (ADRs)

One file per non-obvious decision. Numbered, immutable once accepted (supersede with
a new ADR rather than rewriting history). Each ADR carries a **Plan (batches)**
checklist — the resumable work plan the build loop follows.

Copy `0000-template.md` → `NNNN-<slug>.md` and link it below.

| # | Title | Status |
|---|-------|--------|
| 0001 | Windows-first engine, gating, UI, installer | Accepted — COMPLETE |
| 0002 | Idle quota poll | Accepted — COMPLETE |
| 0003 | Desktop tray app (no terminal/browser/logon) | Partly superseded by 0006 (tray/web dropped; open/close kept) |
| 0004 | Polish: version-tolerant patterns, logging, hot-reload | Planned |
| 0005 | Standalone .exe + one-line PowerShell installer | Accepted — COMPLETE |
| 0006 | Terminal menu UI (drop web dashboard + tray) | Superseded by 0007 |
| 0007 | Dedicated desktop window (Tkinter) | Accepted — COMPLETE |
| 0008 | Zero-quota limit auto-detect via Claude `StopFailure` hook | Accepted — COMPLETE (supersedes 0002 as default) |
| 0009 | Clean uninstall: sweep cloophole.exe by name + deregister hook | Accepted — COMPLETE |
| 0010 | Per-session tick boxes choose where to resume (+ GUI redesign) | Accepted — COMPLETE |
| 0011 | Resume in a visible window (watch Claude work) | Accepted — COMPLETE |
