"""Versioned schema migrations.

``CREATE TABLE IF NOT EXISTS`` can never evolve an existing database; the
original ``jobs.db`` shipped a ``requirements`` table without a foreign key and
no code path would ever have fixed it.  Instead: ``PRAGMA user_version`` plus an
ordered list of migration callables.

Migration 1 is a *rebuild*: read whatever legacy tables exist, drop them, create
the final schema, copy the rows back.  One code path therefore handles both a
fresh database and a drifted one.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from joblens.config import ALLOWED_IMPORTANCE, ALLOWED_STATUSES
from joblens.errors import JobLensError

SCHEMA_V1 = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    salary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'saved'
        CHECK (status IN ('saved', 'applied', 'interview', 'offer', 'rejected')),
    description TEXT NOT NULL,
    description_hash TEXT NOT NULL UNIQUE,
    analysis_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (analysis_status IN ('pending', 'done', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE requirements (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill TEXT NOT NULL COLLATE NOCASE,
    importance TEXT NOT NULL DEFAULT 'required'
        CHECK (importance IN ('required', 'preferred')),
    UNIQUE (job_id, skill)
);

CREATE INDEX idx_requirements_job_id ON requirements(job_id);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

CREATE TABLE user_skills (
    id INTEGER PRIMARY KEY,
    skill TEXT NOT NULL COLLATE NOCASE UNIQUE,
    level TEXT NOT NULL DEFAULT 'unknown',
    evidence TEXT NOT NULL DEFAULT ''
);
"""

EMPTY_STRING = "''"


def compute_description_hash(company: str, title: str, description: str) -> str:
    """Stable fingerprint of a posting, used to avoid storing/paying twice."""
    raw = "\x1f".join(
        part.strip().lower() for part in (company or "", title or "", description or "")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- legacy readers ---------------------------------------------------------


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _expr(columns: set[str], name: str, default: str) -> str:
    return f"COALESCE({name}, {default})" if name in columns else default


def _read_legacy_jobs(conn: sqlite3.Connection, tables: set[str]) -> list[Any]:
    if "jobs" not in tables:
        return []
    cols = _columns(conn, "jobs")
    if "id" not in cols:
        return []
    fields = [
        "id",
        _expr(cols, "company", EMPTY_STRING),
        _expr(cols, "title", EMPTY_STRING),
        _expr(cols, "salary", EMPTY_STRING),
        _expr(cols, "status", "'saved'"),
        _expr(cols, "description", EMPTY_STRING),
    ]
    return conn.execute("SELECT " + ", ".join(fields) + " FROM jobs ORDER BY id").fetchall()


def _read_legacy_requirements(conn: sqlite3.Connection, tables: set[str]) -> list[Any]:
    if "requirements" not in tables:
        return []
    cols = _columns(conn, "requirements")
    if not {"job_id", "skill"} <= cols:
        return []
    fields = [
        "job_id",
        _expr(cols, "skill", EMPTY_STRING),
        _expr(cols, "importance", "'required'"),
    ]
    sql = "SELECT " + ", ".join(fields) + " FROM requirements"
    if "id" in cols:
        sql += " ORDER BY id"
    return conn.execute(sql).fetchall()


def _read_legacy_user_skills(conn: sqlite3.Connection, tables: set[str]) -> list[Any]:
    if "user_skills" not in tables:
        return []
    cols = _columns(conn, "user_skills")
    if "skill" not in cols:
        return []
    fields = [
        _expr(cols, "skill", EMPTY_STRING),
        _expr(cols, "level", "'unknown'"),
        _expr(cols, "evidence", EMPTY_STRING),
    ]
    sql = "SELECT " + ", ".join(fields) + " FROM user_skills"
    if "id" in cols:
        sql += " ORDER BY id"
    return conn.execute(sql).fetchall()


# --- migrations -------------------------------------------------------------


def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    tables = _table_names(conn)
    legacy_jobs = _read_legacy_jobs(conn, tables)
    legacy_requirements = _read_legacy_requirements(conn, tables)
    legacy_user_skills = _read_legacy_user_skills(conn, tables)

    conn.execute("DROP TABLE IF EXISTS requirements")
    conn.execute("DROP TABLE IF EXISTS jobs")
    conn.execute("DROP TABLE IF EXISTS user_skills")
    conn.executescript(SCHEMA_V1)

    requirements_by_old_job: dict[int, list[tuple[Any, Any]]] = {}
    for job_id, skill, importance in legacy_requirements:
        if job_id is None or not (skill or "").strip():
            continue
        requirements_by_old_job.setdefault(job_id, []).append((skill, importance))

    old_to_new: dict[int, int] = {}
    seen_hashes: dict[str, int] = {}
    for old_id, company, title, salary, status, description in legacy_jobs:
        description = description or ""
        digest = compute_description_hash(company, title, description)
        if digest in seen_hashes:
            old_to_new[old_id] = seen_hashes[digest]
            continue
        status = (status or "saved").strip().lower()
        if status not in ALLOWED_STATUSES:
            status = "saved"
        analysis_status = "done" if requirements_by_old_job.get(old_id) else "pending"
        conn.execute(
            """
            INSERT INTO jobs
                (id, company, title, salary, status, description,
                 description_hash, analysis_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                old_id,
                (company or "").strip(),
                (title or "").strip(),
                (salary or "").strip(),
                status,
                description,
                digest,
                analysis_status,
            ),
        )
        seen_hashes[digest] = old_id
        old_to_new[old_id] = old_id

    for old_job_id, skill, importance in legacy_requirements:
        new_job_id = old_to_new.get(old_job_id)
        if new_job_id is None:
            continue
        skill = (skill or "").strip()
        if not skill:
            continue
        importance = (importance or "required").strip().lower()
        if importance not in ALLOWED_IMPORTANCE:
            importance = "preferred"
        conn.execute(
            """
            INSERT INTO requirements (job_id, skill, importance)
            VALUES (?, ?, ?)
            ON CONFLICT (job_id, skill) DO NOTHING
            """,
            (new_job_id, skill, importance),
        )

    for skill, level, evidence in legacy_user_skills:
        skill = (skill or "").strip()
        if not skill:
            continue
        conn.execute(
            """
            INSERT INTO user_skills (skill, level, evidence)
            VALUES (?, ?, ?)
            ON CONFLICT (skill) DO NOTHING
            """,
            (skill, (level or "unknown").strip(), (evidence or "").strip()),
        )


MIGRATIONS = (_migration_001_initial_schema,)


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration newer than the database's user_version."""
    version = current_version(conn)
    for index, migration in enumerate(MIGRATIONS, start=1):
        if index <= version:
            continue
        migration(conn)
        conn.execute(f"PRAGMA user_version = {index}")
        version = index
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise JobLensError(f"Foreign key violations after migration: {violations}")
    return version
