"""Run child processes without popping a console window.

@context  The daemon runs under pythonw (no console). Spawning a console app
          like claude.exe then makes Windows allocate a fresh blank console
          window titled "claude". We capture output anyway, so suppress it.
@done     run() wrapper applying CREATE_NO_WINDOW on Windows.
@todo     —
@limits   No-op flag off Windows. Pass-through to subprocess.run otherwise.
@affects  Used by fire and probe for every claude.exe invocation.
"""

from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run that never flashes a console window on Windows."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.run(cmd, **kwargs)
