"""Application services: orchestration that is neither SQL nor CLI.

``JobService`` is the use-case layer.  It analyses before writing, keeps job and
requirements in one transaction, and owns the "add / re-analyse / match" story.
"""

from __future__ import annotations

from joblens.db.repository import Repository
from joblens.errors import AnalysisError, ValidationError
from joblens.models import Job, MatchResult, Requirement, UserSkill
from joblens.services.analyzer import SkillAnalyzer
from joblens.services.matching import SkillMatcher


class JobService:
    def __init__(
        self,
        repo: Repository,
        analyzer: SkillAnalyzer | None = None,
        matcher: SkillMatcher | None = None,
    ) -> None:
        self.repo = repo
        self.analyzer = analyzer or SkillAnalyzer()
        self.matcher = matcher or SkillMatcher()

    # --- jobs --------------------------------------------------------------
    def add_job(
        self,
        company: str,
        title: str,
        salary: str,
        status: str,
        description: str,
    ) -> tuple[Job, bool, list[Requirement]]:
        """Analyse first, then store. A failed analysis writes nothing."""
        if not (description or "").strip():
            raise ValidationError("The job description is empty.")

        requirements = self.analyzer.analyze(description)
        job, reused = self.repo.add_job_with_requirements(
            company=company,
            title=title,
            salary=salary,
            status=status,
            description=description,
            requirements=requirements,
        )
        return job, reused, requirements

    def list_jobs(self, limit: int = 100) -> list[Job]:
        return self.repo.list_jobs(limit=limit)

    def get_job(self, job_id: int) -> Job:
        return self.repo.require_job(job_id)

    def reanalyze(self, job_id: int, force: bool = False) -> list[Requirement]:
        """Re-run extraction for a stored job.

        Without ``force`` a job that is already analysed is left untouched.
        The job's skills are replaced, so running it twice cannot duplicate rows.
        """
        job = self.repo.require_job(job_id)
        if job.analysis_status == "done" and not force:
            return self.repo.get_requirements(job_id)

        try:
            requirements = self.analyzer.analyze(job.description)
        except AnalysisError:
            self.repo.set_analysis_status(job_id, "failed")
            raise

        self.repo.replace_requirements(job_id, requirements)
        return requirements

    # --- matching ----------------------------------------------------------
    def match(self, job_id: int) -> MatchResult:
        job = self.repo.require_job(job_id)
        requirements = self.repo.get_requirements(job.id)
        user_skills = self.repo.list_user_skills()
        return self.matcher.match(requirements, user_skills, job_id=job.id)

    # --- user skills -------------------------------------------------------
    def add_skill(self, skill: str, level: str = "unknown", evidence: str = "") -> UserSkill:
        return self.repo.add_user_skill(skill, level=level, evidence=evidence)

    def list_skills(self) -> list[UserSkill]:
        return self.repo.list_user_skills()

    def remove_skill(self, skill: str) -> bool:
        return self.repo.remove_user_skill(skill)
