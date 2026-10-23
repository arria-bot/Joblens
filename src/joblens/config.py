"""Configuration for JobLens: one place for paths, limits and domain values.

Nothing in this package hardcodes ``jobs.db``; every path flows from
:func:`get_db_path` (or an explicit override passed down from the CLI).
"""

from __future__ import annotations

import os
from pathlib import Path

DB_PATH_ENV = "JOBLENS_DB"
ALIAS_FILE_ENV = "JOBLENS_ALIAS_FILE"

# --- LLM settings -----------------------------------------------------------
# "deepseek-flash" is not a public DeepSeek API model name; "deepseek-chat" is.
DEFAULT_MODEL = os.environ.get("JOBLENS_MODEL", "deepseek-chat")
API_BASE_URL = os.environ.get("JOBLENS_API_BASE_URL", "https://api.deepseek.com")
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("JOBLENS_TIMEOUT", "30"))
MAX_JD_CHARS = int(os.environ.get("JOBLENS_MAX_JD_CHARS", "8000"))
MAX_RETRIES = int(os.environ.get("JOBLENS_MAX_RETRIES", "3"))

# --- Domain values ----------------------------------------------------------
ALLOWED_STATUSES = ("saved", "applied", "interview", "offer", "rejected")
ALLOWED_IMPORTANCE = ("required", "preferred")

# --- Matching ---------------------------------------------------------------
# Two names must be at least this similar (difflib ratio) to count as the same
# skill when no alias applies. 0.86 keeps "javascript"/"typescript" apart.
FUZZY_THRESHOLD = float(os.environ.get("JOBLENS_FUZZY_THRESHOLD", "0.86"))

IMPORTANCE_WEIGHTS = {"required": 2.0, "preferred": 1.0}

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parents[1]


def _source_checkout() -> bool:
    """True when this module is imported from a checkout rather than a wheel."""
    return (_REPO_ROOT / "pyproject.toml").is_file() and (_REPO_ROOT / "src" / "joblens").is_dir()


def default_db_path() -> Path:
    """Where the database lives when no override is given.

    Running from a source checkout keeps ``jobs.db`` at the repository root so
    existing data is found (and so `python project.py` works from anywhere).
    An installed wheel falls back to the per-user data directory.
    """
    if _source_checkout():
        return _REPO_ROOT / "jobs.db"
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "joblens" / "jobs.db"


def get_db_path() -> Path:
    """Resolve the database path, honouring ``JOBLENS_DB``."""
    override = os.environ.get(DB_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return default_db_path()


def get_alias_file() -> Path | None:
    """Optional user-supplied alias table, merged over the bundled one."""
    override = os.environ.get(ALIAS_FILE_ENV)
    if not override:
        return None
    return Path(override).expanduser()
