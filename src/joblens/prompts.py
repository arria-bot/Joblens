"""Input helpers for the interactive mode.

Kept separate from the CLI so they can be unit-tested (and mocked) on their own.
"""

from __future__ import annotations

from joblens import config


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{label}{suffix}: ").strip()
    return raw or default


def prompt_int(label: str) -> int | None:
    """Read a whole number, returning None instead of raising on bad input."""
    raw = input(label).strip()
    try:
        return int(raw)
    except ValueError:
        print(f"Please enter a whole number, got {raw!r}.")
        return None


def prompt_status(default: str = "saved") -> str:
    options = "/".join(config.ALLOWED_STATUSES)
    while True:
        raw = input(f"Status ({options}) [{default}]: ").strip().lower()
        if not raw:
            return default
        if raw in config.ALLOWED_STATUSES:
            return raw
        print(f"Please choose one of: {', '.join(config.ALLOWED_STATUSES)}")


def read_multiline(end_marker: str = "END") -> str:
    """Read until ``end_marker`` on its own line, or EOF."""
    print("Type END on a new line when finished:")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == end_marker:
            break
        lines.append(line)
    return "\n".join(lines).strip()
