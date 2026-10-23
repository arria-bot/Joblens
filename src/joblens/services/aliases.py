"""Skill-name normalisation and the alias table.

The built-in table lives in ``joblens/data/skill_aliases.json`` so it can grow
without touching code.  A user file (``JOBLENS_ALIAS_FILE``) is merged on top,
which is how you teach JobLens your own equivalences — for example that "K8s"
means Kubernetes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from importlib import resources
from typing import Any

from joblens import config
from joblens.errors import ValidationError

_NON_SKILL_CHARS = re.compile(r"[^\w+#.]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(skill: str) -> str:
    """Fold case, width and punctuation so comparisons are like-for-like."""
    text = unicodedata.normalize("NFKC", skill or "").lower().replace("&", " and ")
    text = _NON_SKILL_CHARS.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _load_builtin() -> dict[str, Any]:
    data = (
        resources.files("joblens.data").joinpath("skill_aliases.json").read_text(encoding="utf-8")
    )
    parsed: Any = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValidationError("The bundled alias table must be a JSON object.")
    return parsed


def _load_user_groups() -> dict[str, Any]:
    override = config.get_alias_file()
    if override is None or not override.is_file():
        return {}
    try:
        data = json.loads(override.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read alias file {override}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(
            f"Alias file {override} must contain an object of {{canonical: [variants]}}."
        )
    return data


@lru_cache(maxsize=1)
def alias_groups() -> dict[str, tuple[str, ...]]:
    """Canonical name -> accepted spellings, built-in merged with the user file."""
    groups: dict[str, tuple[str, ...]] = {}
    for source in (_load_builtin(), _load_user_groups()):
        for canonical_name, variants in source.items():
            if not isinstance(variants, list):
                raise ValidationError(f"Alias for {canonical_name!r} must be a list of spellings.")
            key = canonical_name.strip()
            existing = groups.get(key, ())
            merged = dict.fromkeys([*existing, *(str(variant) for variant in variants)])
            groups[key] = tuple(merged)
    return groups


@lru_cache(maxsize=1)
def alias_lookup() -> dict[str, str]:
    """Normalised spelling -> normalised canonical name."""
    lookup: dict[str, str] = {}
    for canonical_name, variants in alias_groups().items():
        canonical = normalize(canonical_name)
        lookup[canonical] = canonical
        for variant in variants:
            lookup[normalize(variant)] = canonical
    return lookup


def reload_aliases() -> None:
    """Drop cached tables (useful after changing ``JOBLENS_ALIAS_FILE``)."""
    alias_groups.cache_clear()
    alias_lookup.cache_clear()


def canonical_skill(skill: str) -> str:
    """Map a skill name onto its canonical spelling."""
    folded = normalize(skill)
    return alias_lookup().get(folded, folded)


def canonical_tokens(skill: str) -> frozenset[str]:
    """Tokens of a skill, each canonicalised on its own.

    That is what makes ``{"api"}`` a subset of ``{"rest", "api", "integration"}``.
    """
    lookup = alias_lookup()
    return frozenset(lookup.get(token, token) for token in normalize(skill).split())
