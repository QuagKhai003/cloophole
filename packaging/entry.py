"""PyInstaller entry point — builds the standalone cloophole.exe.

@context  PyInstaller needs a real script (not a package), and the package uses
          relative imports, so this thin shim imports the package CLI and runs it.
@done     calls cloophole.__main__.main() with argv.
@todo     —
@limits   —
@affects  Target of packaging/cloophole.spec -> dist/cloophole.exe.
"""

import sys

from cloophole.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
