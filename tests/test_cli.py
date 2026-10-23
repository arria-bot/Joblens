"""CLI: subcommands, JSON output, exit codes and the interactive menu."""

from __future__ import annotations

import json

import pytest

from joblens import cli
from joblens.db.repository import Repository
from joblens.models import Requirement
from joblens.prompts import prompt_int, prompt_status
from joblens.services.analyzer import SkillAnalyzer


def run(argv, capsys):
    code = cli.main(argv)
    return code, capsys.readouterr().out


def feed(monkeypatch, answers):
    """Patch ``input`` with a sequence, ignoring the prompt argument."""
    pending = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_args: next(pending))


def seed_job(db_path, company="Acme", title="Dev"):
    repo = Repository(db_path)
    repo.init()
    return repo.add_job(company, title, "$90k", "saved", "We need SQL.")


def test_list_reports_empty_database(db_path, capsys):
    code, out = run(["--db", str(db_path), "list"], capsys)
    assert code == 0
    assert "No jobs stored yet." in out


def test_list_prints_jobs(db_path, capsys):
    seed_job(db_path)
    code, out = run(["--db", str(db_path), "list"], capsys)

    assert code == 0
    assert "1. Acme - Dev [saved]" in out


def test_list_json_is_machine_readable(db_path, capsys):
    seed_job(db_path)
    code, out = run(["--db", str(db_path), "list", "--json"], capsys)

    payload = json.loads(out)
    assert code == 0
    assert payload[0]["company"] == "Acme"
    assert "description" not in payload[0]


def test_show_missing_job_returns_error_code(db_path, capsys):
    code, out = run(["--db", str(db_path), "show", "99"], capsys)
    assert code == 1
    assert "Error:" in out


def test_show_prints_details_and_skills(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    job = repo.add_job("Acme", "Dev", "$90k", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("SQL", "required")])

    code, out = run(["--db", str(db_path), "show", str(job.id)], capsys)

    assert code == 0
    assert "Company:  Acme" in out
    assert "SQL (required)" in out


def test_show_json_includes_requirements(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    job = repo.add_job("Acme", "Dev", "$90k", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("SQL", "required")])

    _, out = run(["--db", str(db_path), "show", str(job.id), "--json"], capsys)

    payload = json.loads(out)
    assert payload["company"] == "Acme"
    assert payload["requirements"] == [{"skill": "SQL", "importance": "required"}]


def test_add_accepts_flags_and_description_file(db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        SkillAnalyzer, "analyze", lambda self, description: [Requirement("Python", "required")]
    )
    description = tmp_path / "jd.txt"
    description.write_text("We need Python.", encoding="utf-8")

    code, out = run(
        [
            "--db",
            str(db_path),
            "add",
            "--company",
            "Acme",
            "--title",
            "Backend Dev",
            "--salary",
            "$90k",
            "--status",
            "applied",
            "--description-file",
            str(description),
        ],
        capsys,
    )

    assert code == 0
    assert "Job created!" in out
    assert Repository(db_path).count_jobs() == 1


def test_add_without_api_key_fails_cleanly(db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    description = tmp_path / "jd.txt"
    description.write_text("We need Python.", encoding="utf-8")

    code, out = run(
        [
            "--db",
            str(db_path),
            "add",
            "--company",
            "Acme",
            "--title",
            "Dev",
            "--salary",
            "$90k",
            "--status",
            "saved",
            "--description-file",
            str(description),
        ],
        capsys,
    )

    assert code == 1
    assert "DEEPSEEK_API_KEY" in out
    assert Repository(db_path).count_jobs() == 0


def test_match_prints_score_and_alias_source(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("APIs", "preferred")])
    repo.add_user_skill("REST API / API integration")

    code, out = run(["--db", str(db_path), "match", str(job.id)], capsys)

    assert code == 0
    assert "score 100.0%" in out
    assert "token" in out
    assert "REST API / API integration" in out


def test_match_json_contains_both_lists(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(
        job.id, [Requirement("SQL", "required"), Requirement("Rust", "required")]
    )
    repo.add_user_skill("SQL")

    _, out = run(["--db", str(db_path), "match", str(job.id), "--json"], capsys)

    payload = json.loads(out)
    assert payload["score"] == 50.0
    assert [m["skill"] for m in payload["matched"]] == ["SQL"]
    assert [m["skill"] for m in payload["missing"]] == ["Rust"]


def test_skills_add_list_and_remove(db_path, capsys):
    code, out = run(
        [
            "--db",
            str(db_path),
            "skills",
            "add",
            "Python",
            "--level",
            "Advanced",
            "--evidence",
            "CS50x",
        ],
        capsys,
    )
    assert code == 0 and "Saved skill: Python (Advanced)" in out

    code, out = run(["--db", str(db_path), "skills", "list"], capsys)
    assert code == 0 and "- Python (Advanced)" in out and "CS50x" in out

    _, out = run(["--db", str(db_path), "skills", "list", "--json"], capsys)
    assert json.loads(out)[0]["level"] == "Advanced"

    code, out = run(["--db", str(db_path), "skills", "remove", "python"], capsys)
    assert code == 0 and "Removed skill" in out

    code, out = run(["--db", str(db_path), "skills", "remove", "python"], capsys)
    assert code == 1 and "No such skill" in out


def test_analyze_command_reports_skill_count(db_path, capsys, monkeypatch):
    repo = Repository(db_path)
    repo.init()
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("SQL", "required")])
    monkeypatch.setattr(
        SkillAnalyzer, "analyze", lambda self, description: [Requirement("Go", "required")]
    )

    code, out = run(["--db", str(db_path), "analyze", str(job.id), "--force"], capsys)

    assert code == 0
    assert "now has 1 skills" in out
    assert [r.skill for r in repo.get_requirements(job.id)] == ["Go"]


def test_interactive_menu_exits(db_path, monkeypatch, capsys):
    feed(monkeypatch, ["8"])
    code = cli.main(["--db", str(db_path)])

    assert code == 0
    assert "Goodbye!" in capsys.readouterr().out


def test_interactive_menu_survives_invalid_option(db_path, monkeypatch, capsys):
    feed(monkeypatch, ["9", "8"])
    code = cli.main(["--db", str(db_path)])

    assert code == 0
    assert "Invalid option" in capsys.readouterr().out


def test_interactive_menu_reports_errors_without_dying(db_path, monkeypatch, capsys, stub_analyzer):
    feed(monkeypatch, ["3", "abc", "8"])
    code = cli.main(["--db", str(db_path)])

    assert code == 0
    assert "whole number" in capsys.readouterr().out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "joblens" in capsys.readouterr().out


def test_match_requires_a_job_id(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["match"])
    assert excinfo.value.code == 2


def test_prompt_int_handles_text(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *_args: "abc")
    assert prompt_int("id? ") is None
    assert "whole number" in capsys.readouterr().out


def test_prompt_status_reprompts_until_valid(monkeypatch, capsys):
    answers = iter(["nope", "applied"])
    monkeypatch.setattr("builtins.input", lambda *_args: next(answers))

    assert prompt_status() == "applied"
    assert "Please choose one of" in capsys.readouterr().out


def test_list_paginates_and_hints_at_more(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    for index in range(3):
        repo.add_job(f"C{index}", "Dev", "", "saved", f"description {index}")

    code, out = run(["--db", str(db_path), "list", "--limit", "1", "--offset", "1"], capsys)

    assert code == 0
    assert "2. C1 - Dev [saved]" in out
    assert "Showing 2-2 of 3" in out
    assert "--offset 2" in out


def test_list_json_respects_offset(db_path, capsys):
    repo = Repository(db_path)
    repo.init()
    for index in range(3):
        repo.add_job(f"C{index}", "Dev", "", "saved", f"description {index}")

    _, out = run(["--db", str(db_path), "list", "--json", "--offset", "2"], capsys)

    payload = json.loads(out)
    assert [item["company"] for item in payload] == ["C2"]
