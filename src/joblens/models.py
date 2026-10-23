"""Typed domain objects.

The database layer returns these instead of raw ``sqlite3.Row`` tuples, so the
CLI never depends on column order and the service layer can be unit-tested with
plain objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    id: int
    company: str
    title: str
    salary: str = ""
    status: str = "saved"
    description: str = ""
    description_hash: str = ""
    analysis_status: str = "pending"
    created_at: str = ""

    def summary(self) -> str:
        return f"{self.id}. {self.company} - {self.title} [{self.status}]"


@dataclass(frozen=True)
class Requirement:
    skill: str
    importance: str = "required"

    @property
    def weight(self) -> float:
        from joblens.config import IMPORTANCE_WEIGHTS

        return IMPORTANCE_WEIGHTS.get(self.importance, 1.0)


@dataclass(frozen=True)
class UserSkill:
    skill: str
    level: str = "unknown"
    evidence: str = ""


@dataclass(frozen=True)
class SkillMatch:
    """One requirement, and whether the user covers it (and how)."""

    skill: str
    importance: str
    your_skill: str | None = None
    method: str | None = None  # "exact" | "alias" | "fuzzy"

    @property
    def matched(self) -> bool:
        return self.your_skill is not None


@dataclass(frozen=True)
class MatchResult:
    job_id: int
    matched: tuple[SkillMatch, ...] = field(default_factory=tuple)
    missing: tuple[SkillMatch, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.missing)

    @property
    def score(self) -> float:
        """Weighted coverage in percent (required counts double)."""
        from joblens.config import IMPORTANCE_WEIGHTS

        total = sum(
            IMPORTANCE_WEIGHTS.get(m.importance, 1.0) for m in self.matched + self.missing
        )
        if total == 0:
            return 0.0
        covered = sum(IMPORTANCE_WEIGHTS.get(m.importance, 1.0) for m in self.matched)
        return round(covered / total * 100, 1)
