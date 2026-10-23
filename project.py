"""Backwards-compatible entry point.

``python project.py`` keeps working exactly as before, while the real code lives
in the ``src/joblens`` package.  Use ``joblens <command>`` (after
``pip install -e .``) or ``python -m joblens`` for the packaged CLI.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from joblens.cli import main  # noqa: E402  (path setup must run first)

if __name__ == "__main__":
    sys.exit(main())
