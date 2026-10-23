"""Allow ``python -m joblens``."""

import sys

from joblens.cli import main

if __name__ == "__main__":
    sys.exit(main())
