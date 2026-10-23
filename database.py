"""SQLite access layer.

Design rules for this module:
* the database path comes from ``config.get_db_path()`` or an explicit argument,
  never from a hardcoded literal;
* every connection enables foreign keys, WAL and a busy timeout;
* writes happen inside a transaction (``with conn:``);
* nothing here prints, unless it is a ``*_workflow`` convenience used by the CLI.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import config
from errors import NotFoundError
from migrations import compute_description_hash, migrate

# --- connection management -------------------------------------------------


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Turn an optional override into a concrete path."""
    if db_path is None:
        return Path(config.get_db_path())
    return Path(db_path)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with the pragmas this project relies on."""
    path = resolve_db_path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_conn(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Connection scope: commits on success, rolls back on error, always closes."""
    conn = connect(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Create or migrate the database. Safe to call on every start."""
    path = resolve_db_path(db_path)
    with get_conn(path) as conn:
        migrate(conn)
    return path


# --- repository -------------------------------------------------------------


def _validate_status(status: str) -> str:
    status = (status or "").strip().lower()
    if status not in config.ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}; choose one of {', '.join(config.ALLOWED_STATUSES)}"
        )
    return status


def _normalise_requirements(requirements: Sequence) -> list[tuple[str, str]]:
    """Validate, de-duplicate and normalise extracted skills."""
    normalised: dict[str, tuple[str, str]] = {}
    for requirement in requirements:
        if isinstance(requirement, dict):
            skill = requirement.get("skill", "")
            importance = requirement.get("importance", "preferred")
        else:  # tolerate (skill, importance) tuples
            skill, importance = requirement
        skill = str(skill).strip()
        if not skill:
            continue
        importance = str(importance).strip().lower()
        if importance not in config.ALLOWED_IMPORTANCE:
            importance = "preferred"
        # Last occurrence wins, keyed case-insensitively to avoid "SQL"/"sql".
        normalised[skill.lower()] = (skill, importance)
    return sorted(normalised.values(), key=lambda item: item[0].lower())


def _upsert_requirements(
    conn: sqlite3.Connection, job_id: int, requirements: Sequence
) -> int:
    rows = [
        (job_id, skill, importance)
        for skill, importance in _normalise_requirements(requirements)
    ]
    conn.executemany(
        """
        INSERT INTO requirements (job_id, skill, importance)
        VALUES (?, ?, ?)
        ON CONFLICT (job_id, skill) DO UPDATE SET importance = excluded.importance
        """,
        rows,
    )
    return len(rows)


def create_job(
    company: str,
    title: str,
    salary: str,
    status: str,
    description: str,
    db_path: str | Path | None = None,
) -> int:
    """Insert a job without requirements (analysis still pending)."""
    status = _validate_status(status)
    description = (description or "").strip()
    if not description:
        raise ValueError("Job description is empty.")
    digest = compute_description_hash(company, title, description)
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE description_hash = ?", (digest,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE jobs
                   SET company = ?, title = ?, salary = ?, status = ?,
                       description = ?
                 WHERE id = ?
                """,
                (company, title, salary, status, description, existing["id"]),
            )
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO jobs
                (company, title, salary, status, description, description_hash,
                 analysis_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (company, title, salary, status, description, digest),
        )
        return int(cursor.lastrowid)


def insert_job_with_requirements(
    company: str,
    title: str,
    salary: str,
    status: str,
    description: str,
    requirements: Sequence,
    db_path: str | Path | None = None,
) -> tuple[int, bool]:
    """Write a job and its skills in one transaction.

    Returns ``(job_id, reused)`` where ``reused`` is True when an identical
    posting was already stored (its status is refreshed instead of duplicating).
    """
    status = _validate_status(status)
    description = (description or "").strip()
    if not description:
        raise ValueError("Job description is empty.")
    digest = compute_description_hash(company, title, description)
    with get_conn(db_path) as conn:
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
            job_id = int(cursor.lastrowid)
            reused = False
        _upsert_requirements(conn, job_id, requirements)
    return job_id, reused


def save_requirements(
    job_id: int,
    requirements: Sequence,
    db_path: str | Path | None = None,
) -> int:
    """Idempotently store skills for an existing job."""
    with get_conn(db_path) as conn:
        exists = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not exists:
            raise NotFoundError(f"Job with id {job_id} does not exist.")
        saved = _upsert_requirements(conn, job_id, requirements)
        conn.execute("UPDATE jobs SET analysis_status = 'done' WHERE id = ?", (job_id,))
    return saved


def get_job(job_id: int, db_path: str | Path | None = None):
    with get_conn(db_path) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def get_job_description(job_id: int, db_path: str | Path | None = None):
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT description FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return None if row is None else row["description"]


def get_stored_jobs(db_path: str | Path | None = None, limit: int = 100) -> list:
    with get_conn(db_path) as conn:
        return conn.execute(
            """
            SELECT id, company, title, status, created_at
              FROM jobs
             ORDER BY id
             LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_requirements(job_id: int, db_path: str | Path | None = None) -> list:
    with get_conn(db_path) as conn:
        return conn.execute(
            """
            SELECT skill, importance
              FROM requirements
             WHERE job_id = ?
             ORDER BY importance, skill COLLATE NOCASE
            """,
            (job_id,),
        ).fetchall()


def get_user_skills(db_path: str | Path | None = None) -> list:
    with get_conn(db_path) as conn:
        return conn.execute(
            "SELECT skill, level, evidence FROM user_skills ORDER BY skill COLLATE NOCASE"
        ).fetchall()


# --- interactive workflows (CLI convenience) --------------------------------


def get_job_from_user() -> tuple[str, str, str, str, str]:
    """Prompt for the fields of a new job. Returns the raw tuple."""
    from utils import prompt_status  # local import keeps the CLI helper optional

    company = input("Company: ").strip()
    title = input("Title: ").strip()
    salary = input("Salary: ").strip()
    status = prompt_status()

    print("Paste the job description.")
    print("Type END on a new line when finished:")

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "END":
            break
        lines.append(line)

    description = "\n".join(lines).strip()
    return company, title, salary, description, status


def create_job_workflow(db_path: str | Path | None = None) -> None:
    """Collect a job, extract its skills, then store both atomically.

    Analysis happens *before* anything is written, so a failed API call cannot
    leave a half-initialised job behind.
    """
    from analyzer import analyze_job

    company, title, salary, description, status = get_job_from_user()

    if not description:
        print("No job description entered. Nothing was saved.")
        return

    # AnalysisError propagates to the CLI, which reports it. Nothing is written.
    requirements = analyze_job(description)

    job_id, reused = insert_job_with_requirements(
        company, title, salary, status, description, requirements, db_path=db_path
    )
    if reused:
        print(
            f"An identical description already exists; job {job_id} was updated "
            f"with {len(requirements)} skills."
        )
    else:
        print(f"Job created! Job id is {job_id} ({len(requirements)} skills saved).")
