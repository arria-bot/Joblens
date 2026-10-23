"""Skill matching: exact names, known aliases, token containment, then fuzzy.

The matcher runs four passes, cheapest first:

1. ``exact``  – same text after normalisation;
2. ``alias``  – both sides map to the same canonical name (``js`` ↔ ``JavaScript``);
3. ``token``  – the requirement's tokens are contained in the user's skill
   (``APIs`` ⊂ ``REST API / API integration``);
4. ``fuzzy``  – difflib ratio above a threshold, disabled for short names so
   that ``C`` never matches ``C#``.

The alias table itself lives in ``joblens/data/skill_aliases.json`` and can be
extended per user through ``JOBLENS_ALIAS_FILE``.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from joblens import config
from joblens.models import MatchResult, Requirement, SkillMatch, UserSkill
from joblens.services.aliases import canonical_skill, canonical_tokens, normalize

__all__ = [
    "SkillMatcher",
    "canonical_skill",
    "canonical_tokens",
    "match_skills",
    "normalize",
]


def _fuzzy_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


class _PreparedUserSkill:
    __slots__ = ("skill", "normalized", "canonical", "tokens")

    def __init__(self, skill: UserSkill) -> None:
        self.skill = skill
        self.normalized = normalize(skill.skill)
        self.canonical = canonical_skill(skill.skill)
        self.tokens = canonical_tokens(skill.skill)


class SkillMatcher:
    """Match requirements against the user's skills."""

    def __init__(self, fuzzy_threshold: float | None = None) -> None:
        self.fuzzy_threshold = (
            config.FUZZY_THRESHOLD if fuzzy_threshold is None else fuzzy_threshold
        )

    def _find(
        self, requirement: Requirement, users: list[_PreparedUserSkill]
    ) -> tuple[UserSkill, str] | None:
        normalized = normalize(requirement.skill)
        canonical = canonical_skill(requirement.skill)
        tokens = canonical_tokens(requirement.skill)

        for user in users:  # 1. exact
            if user.normalized == normalized:
                return user.skill, "exact"
        for user in users:  # 2. alias
            if user.canonical == canonical:
                return user.skill, "alias"
        for user in users:  # 3. token containment
            if tokens and tokens <= user.tokens and tokens != user.tokens:
                return user.skill, "token"

        best: tuple[float, UserSkill] | None = None  # 4. fuzzy
        if len(canonical) >= 4:
            for user in users:
                if len(user.canonical) < 4:
                    continue
                ratio = _fuzzy_ratio(canonical, user.canonical)
                if ratio >= self.fuzzy_threshold and (best is None or ratio > best[0]):
                    best = (ratio, user.skill)
        if best is not None:
            return best[1], "fuzzy"
        return None

    def match(
        self,
        requirements: list[Requirement],
        user_skills: list[UserSkill],
        job_id: int = 0,
    ) -> MatchResult:
        users = [_PreparedUserSkill(skill) for skill in user_skills]
        matched: list[SkillMatch] = []
        missing: list[SkillMatch] = []

        for requirement in requirements:
            found = self._find(requirement, users)
            if found is None:
                missing.append(
                    SkillMatch(skill=requirement.skill, importance=requirement.importance)
                )
            else:
                user_skill, method = found
                matched.append(
                    SkillMatch(
                        skill=requirement.skill,
                        importance=requirement.importance,
                        your_skill=user_skill.skill,
                        method=method,
                    )
                )

        return MatchResult(job_id=job_id, matched=tuple(matched), missing=tuple(missing))


def match_skills(
    requirements: list[Requirement],
    user_skills: list[UserSkill],
    job_id: int = 0,
    fuzzy_threshold: float | None = None,
) -> MatchResult:
    """Convenience wrapper around :class:`SkillMatcher`."""
    return SkillMatcher(fuzzy_threshold).match(requirements, user_skills, job_id=job_id)
