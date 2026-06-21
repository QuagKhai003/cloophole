"""cloophole — auto-resume Claude Code work when your usage quota resets.

A lightweight background daemon (Windows-first). Watches limit state + live
`claude` sessions; when the reset lands and a session is present, it fires
`claude --continue` in the recorded directory to pick the work back up.
"""

__version__ = "0.1.0"
