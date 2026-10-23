"""Small CLI helpers shared by the command modules."""

import config


def prompt_int(prompt: str):
    """Read an integer, returning None instead of raising on bad input."""
    raw = input(prompt).strip()
    try:
        return int(raw)
    except ValueError:
        print(f"Please enter a whole number, got {raw!r}.")
        return None


def prompt_status(prompt: str = "Status", default: str = "saved") -> str:
    """Read a status from the allowed set, re-prompting until valid."""
    options = "/".join(config.ALLOWED_STATUSES)
    while True:
        raw = input(f"{prompt} ({options}) [{default}]: ").strip().lower()
        if not raw:
            return default
        if raw in config.ALLOWED_STATUSES:
            return raw
        print(f"Please choose one of: {', '.join(config.ALLOWED_STATUSES)}")
