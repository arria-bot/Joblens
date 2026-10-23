"""Repository: the only place that talks SQL.

It knows nothing about the LLM, argparse or printing.  It returns typed models
from :mod:`joblens.models`, and every write runs inside a transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TypeAlias

from joblens.config import ALLOWED_IMPORTANCE, ALLOWED_STATUSES
from joblens.db.connection import get_conn, resolve_db_path
from joblens.db.migrations import compute_description_hash, migrate
from joblens.errors import JobLensError, NotFoundError, ValidationError
from joblens.models import Job, Requirement, UserSkill

#: Anything the repository can turn into requirement rows.
RequirementInput: TypeAlias = "Requirement | Mapping[str, str] | tuple[str, str]"


def validate_status(status: str) -> str:
    cleaned = (status or "").strip().lower()
    if cleaned not in ALLOWED_STATUSES:
        raise ValidationError(
            f"Invalid status {cleaned!r}; choose one of {', '.join(ALLOWED_STATUSES)}"
        )
    return cleaned


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        company=row["company"],
        title=row["title"],
        salary=row["salary"],
        status=row["status"],
        description=row["description"],
        description_hash=row["description_hash"],
        analysis_status=row["analysis_status"],
        created_at=row["created_at"],
    )


def _row_to_requirement(row: sqlite3.Row) -> Requirement:
    return Requirement(skill=row["skill"], importance=row["importance"])


def _row_to_user_skill(row: sqlite3.Row) -> UserSkill:
    return UserSkill(skill=row["skill"], level=row["level"], evidence=row["evidence"])


def _last_row_id(cursor: sqlite3.Cursor) -> int:
    """lastrowid is typed as int | None; an INSERT always produces one."""
    if cursor.lastrowid is None:  # pragma: no cover - defensive
        raise JobLensError("SQLite did not return an id for the inserted row.")
    return int(cursor.lastrowid)


def normalise_requirements(requirements: Iterable[RequirementInput]) -> list[Requirement]:
    """Validate, de-duplicate (case-insensitively) and order requirements."""
    normalised: dict[str, Requirement] = {}
    for item in requirements:
        if isinstance(item, Requirement):
            skill, importance = item.skill, item.importance
        elif isinstance(item, dict):
            skill, importance = item.get("skill", ""), item.get("importance", "preferred")
        else:
            skill, importance = item
        skill = str(skill).strip()
        if not skill:
            continue
        importance = str(importance).strip().lower()
        if importance not in ALLOWED_IMPORTANCE:
            importance = "preferred"
        normalised[skill.lower()] = Requirement(skill=skill, importance=importance)
    return sorted(normalised.values(), key=lambda requirement: requirement.skill.lower())


class Repository:
    """Data access for jobs, requirements and the user's own skills."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_db_path(db_path)

    # --- lifecycle ---------------------------------------------------------
    def init(self) -> None:
        """Create or migrate the schema. Cheap enough to call on every run."""
        with get_conn(self.db_path) as conn:
            migrate(conn)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with get_conn(self.db_path) as conn:
            yield conn

    # --- jobs --------------------------------------------------------------
    def add_job_with_requirements(
        self,
        company: str,
        title: str,
        salary: str,
        status: str,
        description: str,
        requirements: Iterable[RequirementInput],
    ) -> tuple[Job, bool]:
        """Insert (or refresh) a job and its skills in a single transaction.

        Returns ``(job, reused)``; ``reused`` is True when an identical posting
        already existed, so its status is refreshed instead of duplicated.
        """
        status = validate_status(status)
        description = (description or "").strip()
        if not description:
            raise ValidationError("The job description is empty.")
        digest = compute_description_hash(company, title, description)
        prepared = normalise_requirements(requirements)

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE description_hash = ?", (digest,)
            ).fetchone()
            if existing:
                job_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE jobs
                       SET company = ?, title = ?, salary = ?, status = ?,
                           description = ?, analysis_status = 'done'
                     WHERE id = ?
                    """,
                    (company, title, salary, status, description, job_id),
                )
                reused = True
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO jobs
                        (company, title, salary, status, description,
                         description_hash, analysis_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'done')
                    """,
                    (company, title, salary, status, description, digest),
                )
                job_id = _last_row_id(cursor)
                reused = False
            self._write_requirements(conn, job_id, prepared)
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row), reused

    def add_job(
        self,
        company: str,
        title: str,
        salary: str,
        status: str,
        description: str,
    ) -> Job:
        """Insert a job without requirements (analysis still pending)."""
        status = validate_status(status)
        description = (description or "").strip()
        if not description:
            raise ValidationError("The job description is empty.")
        digest = compute_description_hash(company, title, description)
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs
                    (company, title, salary, status, description,
                     description_hash, analysis_status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (company, title, salary, status, description, digest),
            )
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (_last_row_id(cursor),)
            ).fetchone()
        return _row_to_job(row)

    def get_job(self, job_id: int) -> Job | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return None if row is None else _row_to_job(row)

    def require_job(self, job_id: int) -> Job:
        job = self.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Job with id {job_id} does not exist.")
        return job

    def list_jobs(self, limit: int = 100, offset: int = 0) -> list[Job]:
        """One page of jobs, oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                 ORDER BY id
                 LIMIT ? OFFSET ?
                """,
                (max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def count_jobs(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT count(*) FROM jobs").fetchone()[0])

    # --- requirements ------------------------------------------------------
    def _write_requirements(
        self, conn: sqlite3.Connection, job_id: int, requirements: Iterable[Requirement]
    ) -> int:
        rows = [(job_id, item.skill, item.importance) for item in requirements]
        conn.executemany(
            """
            INSERT INTO requirements (job_id, skill, importance)
            VALUES (?, ?, ?)
            ON CONFLICT (job_id, skill) DO UPDATE SET importance = excluded.importance
            """,
            rows,
        )
        return len(rows)

    def save_requirements(self, job_id: int, requirements: Iterable[RequirementInput]) -> int:
        """Idempotently store skills for an existing job."""
        prepared = normalise_requirements(requirements)
        with self._conn() as conn:
            exists = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not exists:
                raise NotFoundError(f"Job with id {job_id} does not exist.")
            saved = self._write_requirements(conn, job_id, prepared)
            conn.execute("UPDATE jobs SET analysis_status = 'done' WHERE id = ?", (job_id,))
        return saved

    def replace_requirements(self, job_id: int, requirements: Iterable[RequirementInput]) -> int:
        """Drop existing skills for a job and write the new set (re-analysis)."""
        prepared = normalise_requirements(requirements)
        with self._conn() as conn:
            conn.execute("DELETE FROM requirements WHERE job_id = ?", (job_id,))
            saved = self._write_requirements(conn, job_id, prepared)
            conn.execute("UPDATE jobs SET analysis_status = 'done' WHERE id = ?", (job_id,))
        return saved

    def get_requirements(self, job_id: int) -> list[Requirement]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT skill, importance
                  FROM requirements
                 WHERE job_id = ?
                 ORDER BY importance, skill COLLATE NOCASE
                """,
                (job_id,),
            ).fetchall()
        return [_row_to_requirement(row) for row in rows]

    def set_analysis_status(self, job_id: int, status: str) -> None:
        if status not in ("pending", "done", "failed"):
            raise ValidationError(f"Invalid analysis status {status!r}")
        with self._conn() as conn:
            conn.execute("UPDATE jobs SET analysis_status = ? WHERE id = ?", (status, job_id))

    # --- user skills -------------------------------------------------------
    def add_user_skill(self, skill: str, level: str = "unknown", evidence: str = "") -> UserSkill:
        skill = (skill or "").strip()
        if not skill:
            raise ValidationError("Skill name cannot be empty.")
        level = (level or "unknown").strip() or "unknown"
        evidence = (evidence or "").strip()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO user_skills (skill, level, evidence)
                VALUES (?, ?, ?)
                ON CONFLICT (skill) DO UPDATE
                   SET level = excluded.level, evidence = excluded.evidence
                """,
                (skill, level, evidence),
            )
            row = conn.execute(
                "SELECT skill, level, evidence FROM user_skills WHERE skill = ?", (skill,)
            ).fetchone()
        return _row_to_user_skill(row)

    def get_user_skill(self, skill: str) -> UserSkill | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT skill, level, evidence FROM user_skills WHERE skill = ? COLLATE NOCASE",
                ((skill or "").strip(),),
            ).fetchone()
        return None if row is None else _row_to_user_skill(row)

    def list_user_skills(self) -> list[UserSkill]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT skill, level, evidence
                  FROM user_skills
                 ORDER BY skill COLLATE NOCASE
                """
            ).fetchall()
        return [_row_to_user_skill(row) for row in rows]

    def remove_user_skill(self, skill: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_skills WHERE skill = ? COLLATE NOCASE",
                ((skill or "").strip(),),
            )
            return cursor.rowcount > 0
