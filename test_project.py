"""Tests for JobLens.

Every test runs offline: the LLM client is always injected or mocked, so the
suite passes with no DEEPSEEK_API_KEY and no network access.
"""

import sqlite3
import types

import pytest

import analyzer
import config
import database
import migrations
import project
import skills

# The schema as it existed in the original repository (no FK, no constraints).
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


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "jobs.db"
    database.init_db(path)
    return path


@pytest.fixture
def legacy_db(tmp_path):
    """A database created by the original code, with real-ish rows."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO jobs (id, company, title, salary, description, status) "
        "VALUES (1, 'edison TALENT', 'Graduate .NET Developer', '$80k', 'C# and SQL', 'saved')"
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


class FakeClient:
    """Minimal stand-in for ``openai.OpenAI``.

    ``responses`` is a list of either strings (used as message content) or
    exceptions (raised instead).
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        message = types.SimpleNamespace(content=item)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def make_error(status_code):
    error = Exception(f"http {status_code}")
    error.status_code = status_code
    return error


# --- schema and migrations ---------------------------------------------------


def test_init_db_creates_tables_and_sets_version(tmp_path):
    db_path = tmp_path / "test_jobs.db"
    database.init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert {"jobs", "requirements", "user_skills"} <= tables
    assert version == len(migrations.MIGRATIONS)


def test_init_db_is_idempotent(db):
    before = database.get_stored_jobs(db_path=db)
    database.init_db(db)
    database.init_db(db)
    assert database.get_stored_jobs(db_path=db) == before


def test_foreign_keys_are_enforced(db):
    conn = database.connect(db)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO requirements (job_id, skill, importance) "
                "VALUES (9999, 'Ghost', 'required')"
            )
    finally:
        conn.close()


def test_delete_job_cascades_to_requirements(db):
    job_id = database.create_job("A", "B", "", "saved", "desc", db_path=db)
    database.save_requirements(job_id, [{"skill": "SQL", "importance": "required"}], db_path=db)

    with database.get_conn(db) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    assert database.get_requirements(job_id, db_path=db) == []


def test_legacy_database_is_migrated_without_data_loss(legacy_db):
    database.init_db(legacy_db)

    job = database.get_job(1, db_path=legacy_db)
    assert job["company"] == "edison TALENT"
    assert job["status"] == "saved"
    assert job["analysis_status"] == "done"
    assert len(job["description_hash"]) == 64

    requirements = database.get_requirements(1, db_path=legacy_db)
    # The duplicated ("SQL", "SQL") pair collapses thanks to UNIQUE(job_id, skill).
    assert [row["skill"] for row in requirements] == ["C#", "SQL"]

    assert {row["skill"] for row in database.get_user_skills(db_path=legacy_db)} == {
        "Python",
        "SQL",
    }

    with sqlite3.connect(legacy_db) as conn:
        fk_targets = [row[2] for row in conn.execute("PRAGMA foreign_key_list(requirements)")]
    assert fk_targets == ["jobs"]


# --- database paths ----------------------------------------------------------


def test_db_path_is_independent_of_cwd(tmp_path, monkeypatch):
    workdir = tmp_path / "somewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    target = tmp_path / "nested" / "custom.db"
    resolved = database.init_db(target)
    job_id = database.create_job("A", "B", "", "saved", "desc", db_path=resolved)

    assert database.get_job(job_id, db_path=target) is not None
    assert not (workdir / "jobs.db").exists()


def test_db_path_env_override(tmp_path, monkeypatch):
    target = tmp_path / "from_env.db"
    monkeypatch.setenv(config.DB_PATH_ENV_VAR, str(target))

    assert config.get_db_path() == target

    database.init_db()
    job_id = database.create_job("A", "B", "", "saved", "unique description")
    assert database.get_job(job_id, db_path=target) is not None


# --- idempotent writes -------------------------------------------------------


def test_saving_the_same_skills_twice_does_not_duplicate(db):
    job_id = database.create_job("A", "B", "", "saved", "desc", db_path=db)

    requirements = [{"skill": "Python", "importance": "required"}]
    database.save_requirements(job_id, requirements, db_path=db)
    database.save_requirements(job_id, requirements, db_path=db)

    rows = database.get_requirements(job_id, db_path=db)
    assert len(rows) == 1


def test_skill_names_are_case_insensitive_for_uniqueness(db):
    job_id = database.create_job("A", "B", "", "saved", "desc", db_path=db)

    database.save_requirements(job_id, [{"skill": "SQL", "importance": "required"}], db_path=db)
    database.save_requirements(job_id, [{"skill": "sql", "importance": "preferred"}], db_path=db)

    rows = database.get_requirements(job_id, db_path=db)
    assert len(rows) == 1
    assert rows[0]["importance"] == "preferred"


def test_identical_description_reuses_the_job(db):
    requirements = [{"skill": "C#", "importance": "required"}]
    job_id, reused = database.insert_job_with_requirements(
        "Acme", "Dev", "$90k", "saved", "same description", requirements, db_path=db
    )
    assert reused is False

    second_id, reused_again = database.insert_job_with_requirements(
        "Acme", "Dev", "$90k", "applied", "same description", requirements, db_path=db
    )
    assert reused_again is True
    assert second_id == job_id

    assert database.get_job(job_id, db_path=db)["status"] == "applied"
    assert len(database.get_stored_jobs(db_path=db)) == 1


def test_invalid_status_is_rejected(db):
    with pytest.raises(ValueError):
        database.create_job("A", "B", "", "not-a-status", "desc", db_path=db)


# --- analyzer ----------------------------------------------------------------


def test_analyzer_parses_fenced_json():
    fenced = '```json\n{"requirements": [{"skill": "C#", "importance": "required"}]}\n```'
    client = FakeClient([fenced])
    assert analyzer.analyze_job("We need C#.", client=client) == [
        {"skill": "C#", "importance": "required"}
    ]


def test_analyzer_parses_bare_json_and_normalises_importance():
    client = FakeClient(['{"requirements": [{"skill": "SQL", "importance": "MUST HAVE"}]}'])
    result = analyzer.analyze_job("SQL please", client=client)
    assert result == [{"skill": "SQL", "importance": "preferred"}]


def test_analyzer_deduplicates_skills():
    client = FakeClient(['{"requirements": [{"skill": "SQL"}, {"skill": "sql"}]}'])
    assert analyzer.analyze_job("jd", client=client) == [
        {"skill": "SQL", "importance": "preferred"}
    ]


def test_analyzer_raises_on_invalid_json():
    client = FakeClient(["I think this job needs Python and SQL."])
    with pytest.raises(analyzer.AnalysisError):
        analyzer.analyze_job("jd", client=client)


def test_analyzer_raises_when_no_skills_found():
    client = FakeClient(['{"requirements": []}'])
    with pytest.raises(analyzer.AnalysisError):
        analyzer.analyze_job("jd", client=client)


def test_analyzer_truncates_long_descriptions(monkeypatch):
    monkeypatch.setattr(config, "MAX_JD_CHARS", 40)
    client = FakeClient(['{"requirements": [{"skill": "SQL"}]}'])

    analyzer.analyze_job("word " * 500, client=client)

    prompt = client.calls[0]["messages"][1]["content"]
    assert "[truncated]" in prompt
    assert len(prompt) < 200


def test_analyzer_requests_json_mode_without_creativity():
    client = FakeClient(['{"requirements": [{"skill": "SQL"}]}'])
    analyzer.analyze_job("jd", client=client)

    kwargs = client.calls[0]
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["temperature"] == 0
    assert "timeout" in kwargs


def test_analyzer_retries_on_rate_limit(monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda _seconds: None)
    client = FakeClient([make_error(429), '{"requirements": [{"skill": "SQL"}]}'])

    assert analyzer.analyze_job("jd", client=client) == [
        {"skill": "SQL", "importance": "preferred"}
    ]
    assert len(client.calls) == 2


def test_analyzer_does_not_retry_on_auth_error(monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda _seconds: None)
    client = FakeClient([make_error(401), '{"requirements": [{"skill": "SQL"}]}'])

    with pytest.raises(analyzer.AnalysisError):
        analyzer.analyze_job("jd", client=client)
    assert len(client.calls) == 1


def test_analyzer_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(analyzer.AnalysisError, match="DEEPSEEK_API_KEY"):
        analyzer.analyze_job("jd")


# --- CLI behaviour -----------------------------------------------------------


def test_prompt_int_returns_none_for_text(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "abc")
    assert project.prompt_int("id? ") is None
    assert "whole number" in capsys.readouterr().out


def test_view_job_workflow_survives_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "abc")
    project.view_job_workflow(db_path=None)  # must not raise
    assert "whole number" in capsys.readouterr().out


def test_view_job_workflow_reports_missing_job(db, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "42")
    project.view_job_workflow(db_path=db)
    assert "not found" in capsys.readouterr().out


def test_create_job_workflow_does_not_save_when_analysis_fails(db, monkeypatch, capsys):
    monkeypatch.setattr(
        database,
        "get_job_from_user",
        lambda: ("Acme", "Dev", "$90k", "a description", "saved"),
    )

    def boom(_description):
        raise analyzer.AnalysisError("model unavailable")

    monkeypatch.setattr(analyzer, "analyze_job", boom)

    with pytest.raises(analyzer.AnalysisError):
        database.create_job_workflow(db_path=db)

    assert database.get_stored_jobs(db_path=db) == []


def test_create_job_workflow_stores_job_and_skills(db, monkeypatch, capsys):
    monkeypatch.setattr(
        database,
        "get_job_from_user",
        lambda: ("Acme", "Dev", "$90k", "a description", "saved"),
    )
    monkeypatch.setattr(
        analyzer,
        "analyze_job",
        lambda _description: [{"skill": "SQL", "importance": "required"}],
    )

    database.create_job_workflow(db_path=db)

    jobs = database.get_stored_jobs(db_path=db)
    assert len(jobs) == 1
    assert database.get_job(jobs[0]["id"], db_path=db)["analysis_status"] == "done"
    assert [row["skill"] for row in database.get_requirements(jobs[0]["id"], db_path=db)] == ["SQL"]


# --- matching ----------------------------------------------------------------


def test_match_skills_is_case_insensitive(db):
    job_id = database.create_job("A", "B", "", "saved", "desc", db_path=db)
    database.save_requirements(
        job_id,
        [{"skill": "SQL", "importance": "required"}, {"skill": "C#", "importance": "required"}],
        db_path=db,
    )
    with database.get_conn(db) as conn:
        conn.execute("INSERT INTO user_skills (skill, level, evidence) VALUES ('sql', 'ok', '')")

    matched, missing = skills.match_skills(job_id, db_path=db)

    assert [row["skill"] for row in matched] == ["SQL"]
    assert [row["skill"] for row in missing] == ["C#"]


def test_match_skills_for_unknown_job_is_empty(db):
    matched, missing = skills.match_skills(12345, db_path=db)
    assert matched == [] and missing == []
