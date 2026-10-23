"""Schema, migration and foreign-key behaviour."""

from __future__ import annotations

import sqlite3

import pytest

from joblens.db import migrations
from joblens.db.connection import get_conn
from joblens.db.migrations import compute_description_hash
from joblens.db.repository import Repository
from joblens.errors import JobLensError

LEGACY_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    company TEXT,
    title TEXT,
    salary TEXT,
    description TEXT,
    status TEXT
);
CREATE TABLE requirements (
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
    skill TEXT,
    importance TEXT
);
CREATE TABLE user_skills (
    id INTEGER PRIMARY KEY,
    skill TEXT,
    level TEXT,
    evidence TEXT
);
"""


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO jobs (id, company, title, salary, description, status) "
        "VALUES (1, 'edison TALENT', 'Graduate .NET Developer', '$80k', "
        "'C# and SQL', 'saved')"
    )
    conn.executemany(
        "INSERT INTO requirements (job_id, skill, importance) VALUES (?, ?, ?)",
        [(1, "C#", "required"), (1, "SQL", "required"), (1, "SQL", "required")],
    )
    conn.executemany(
        "INSERT INTO user_skills (skill, level, evidence) VALUES (?, ?, ?)",
        [("Python", "Intermediate", "CS50x"), ("SQL", "Intermediate", "CS50x")],
    )
    conn.commit()
    conn.close()
    return path


def test_fresh_database_gets_tables_and_version(tmp_path):
    path = tmp_path / "fresh.db"
    Repository(path).init()

    with sqlite3.connect(path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert {"jobs", "requirements", "user_skills"} <= tables
    assert version == len(migrations.MIGRATIONS)


def test_init_is_idempotent(repo):
    repo.init()
    repo.init()
    with get_conn(repo.db_path) as conn:
        assert migrations.current_version(conn) == len(migrations.MIGRATIONS)


def test_legacy_database_is_migrated_without_data_loss(legacy_db):
    Repository(legacy_db).init()

    job = Repository(legacy_db).require_job(1)
    assert job.company == "edison TALENT"
    assert job.title == "Graduate .NET Developer"
    assert job.status == "saved"
    assert job.analysis_status == "done"
    assert len(job.description_hash) == 64

    repository = Repository(legacy_db)
    # The duplicated ("SQL", "SQL") pair collapses thanks to UNIQUE(job_id, skill).
    assert [requirement.skill for requirement in repository.get_requirements(1)] == [
        "C#",
        "SQL",
    ]
    assert {skill.skill for skill in repository.list_user_skills()} == {"Python", "SQL"}

    with sqlite3.connect(legacy_db) as conn:
        assert [row[2] for row in conn.execute("PRAGMA foreign_key_list(requirements)")] == ["jobs"]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_legacy_rows_with_nulls_still_migrate(tmp_path):
    path = tmp_path / "nulls.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO jobs (id, company, title, salary, description, status) "
        "VALUES (7, NULL, NULL, NULL, NULL, 'weird-status')"
    )
    conn.commit()
    conn.close()

    Repository(path).init()

    job = Repository(path).require_job(7)
    assert job.company == ""
    assert job.salary == ""
    assert job.status == "saved"  # unknown statuses fall back to the default
    assert job.analysis_status == "pending"


def test_migration_rejects_orphan_rows(tmp_path):
    """Legacy data pointing at a missing job is dropped, not carried over."""
    path = tmp_path / "orphan.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO requirements (job_id, skill, importance) VALUES (99, 'SQL', 'required')"
    )
    conn.commit()
    conn.close()

    Repository(path).init()

    # The orphan had no job, so nothing survived; the FK check stays clean.
    with get_conn(path) as conn:
        assert conn.execute("SELECT count(*) FROM requirements").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_description_hash_is_stable_and_normalised():
    first = compute_description_hash("Acme", "Dev", "Some  text ")
    second = compute_description_hash("  acme ", "DEV", "some  text")
    assert first == second
    assert len(first) == 64
    assert compute_description_hash("Acme", "Dev", "other") != first


def test_migration_failure_raises_joblens_error(monkeypatch):
    def broken(_conn):
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "MIGRATIONS", (broken,))
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError):
            migrations.migrate(conn)
    finally:
        conn.close()


def test_foreign_keys_are_enabled_for_every_connection(repo):
    with get_conn(repo.db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO requirements (job_id, skill, importance) "
                "VALUES (4242, 'Ghost', 'required')"
            )


def test_deleting_a_job_cascades_to_requirements(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [("SQL", "required")])

    with get_conn(repo.db_path) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))

    assert repo.get_requirements(job.id) == []


def test_invalid_analysis_status_is_rejected(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    with pytest.raises(JobLensError):
        repo.set_analysis_status(job.id, "nonsense")
