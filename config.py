"""Central configuration for JobLens.

Every path and tunable value lives here so that no module hardcodes
``jobs.db`` or a model name ever again.
"""

import os
from pathlib import Path

# The database lives next to this file, NOT next to the current working
# directory.  This is what makes ``python project.py`` from any folder use the
# same data.
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "jobs.db"

# Environment override for tests, CI and power users.
DB_PATH_ENV_VAR = "JOBLENS_DB"

# --- LLM settings -----------------------------------------------------------
# "deepseek-flash" is not a public DeepSeek API model name; the public chat
# model is "deepseek-chat".
DEFAULT_MODEL = os.environ.get("JOBLENS_MODEL", "deepseek-chat")
API_BASE_URL = os.environ.get("JOBLENS_API_BASE_URL", "https://api.deepseek.com")
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("JOBLENS_TIMEOUT", "30"))
MAX_JD_CHARS = int(os.environ.get("JOBLENS_MAX_JD_CHARS", "8000"))
MAX_RETRIES = int(os.environ.get("JOBLENS_MAX_RETRIES", "3"))

# --- Domain values ----------------------------------------------------------
ALLOWED_STATUSES = ("saved", "applied", "interview", "offer", "rejected")
ALLOWED_IMPORTANCE = ("required", "preferred")


def get_db_path() -> Path:
    """Return the database path, honouring the JOBLENS_DB override."""
    override = os.environ.get(DB_PATH_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB_PATH
