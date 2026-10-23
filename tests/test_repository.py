"""Repository behaviour: writes, reads, constraints and the user skill store."""

from __future__ import annotations

import pytest

from joblens.db.repository import Repository, normalise_requirements
from joblens.errors import NotFoundError, ValidationError
from joblens.models import Requirement


def test_add_job_with_requirements(repo):
    job, reused = repo.add_job_with_requirements(
        "Acme",
        "Backend Dev",
        "$90k",
        "saved",
        "We need Python.",
        [Requirement("Python", "required"), Requirement("SQL", "preferred")],
    )

    assert reused is False
    assert job.id == 1
    assert job.analysis_status == "done"
    assert [r.skill for r in repo.get_requirements(job.id)] == ["SQL", "Python"]


def test_identical_description_is_reused_and_status_updated(repo):
    requirements = [Requirement("C#", "required")]
    first, reused_first = repo.add_job_with_requirements(
        "Acme", "Dev", "$90k", "saved", "same description", requirements
    )
    second, reused_second = repo.add_job_with_requirements(
        "Acme", "Dev", "$90k", "applied", "same description", requirements
    )

    assert reused_first is False
    assert reused_second is True
    assert second.id == first.id
    assert repo.get_job(first.id).status == "applied"
    assert repo.count_jobs() == 1


def test_saving_requirements_is_idempotent(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("Python", "required")])
    repo.save_requirements(job.id, [Requirement("Python", "required")])
    assert len(repo.get_requirements(job.id)) == 1


def test_skill_uniqueness_ignores_case(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("SQL", "required")])
    repo.save_requirements(job.id, [Requirement("sql", "preferred")])

    requirements = repo.get_requirements(job.id)
    assert len(requirements) == 1
    assert requirements[0].importance == "preferred"


def test_replace_requirements_drops_old_rows(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    repo.save_requirements(job.id, [Requirement("COBOL", "required")])
    repo.replace_requirements(job.id, [Requirement("Python", "required")])

    assert [r.skill for r in repo.get_requirements(job.id)] == ["Python"]


def test_save_requirements_for_missing_job_raises(repo):
    with pytest.raises(NotFoundError):
        repo.save_requirements(9999, [Requirement("SQL")])


def test_invalid_status_is_rejected(repo):
    with pytest.raises(ValidationError):
        repo.add_job("Acme", "Dev", "", "not-a-status", "desc")


def test_empty_description_is_rejected(repo):
    with pytest.raises(ValidationError):
        repo.add_job("Acme", "Dev", "", "saved", "   ")


def test_list_jobs_is_ordered_and_limited(repo):
    for index in range(3):
        repo.add_job(f"C{index}", "Dev", "", "saved", f"description {index}")

    assert [job.id for job in repo.list_jobs()] == [1, 2, 3]
    assert len(repo.list_jobs(limit=2)) == 2


def test_require_job_raises_not_found(repo):
    with pytest.raises(NotFoundError):
        repo.require_job(42)


def test_user_skill_upsert_and_case_insensitive_lookup(repo):
    repo.add_user_skill("Python", level="Intermediate", evidence="CS50x")
    repo.add_user_skill("python", level="Advanced", evidence="work")

    skills = repo.list_user_skills()
    assert len(skills) == 1
    assert skills[0].skill.lower() == "python"
    assert skills[0].level == "Advanced"
    assert repo.get_user_skill("PYTHON").evidence == "work"


def test_remove_user_skill(repo):
    repo.add_user_skill("Python")
    assert repo.remove_user_skill("python") is True
    assert repo.remove_user_skill("python") is False
    assert repo.list_user_skills() == []


def test_empty_skill_name_is_rejected(repo):
    with pytest.raises(ValidationError):
        repo.add_user_skill("   ")


def test_normalise_requirements_dedupes_and_sorts():
    prepared = normalise_requirements(
        [Requirement("SQL", "required"), Requirement("sql", "preferred"), ("Python", "bogus")]
    )
    assert [(r.skill, r.importance) for r in prepared] == [
        ("Python", "preferred"),
        ("sql", "preferred"),
    ]


def test_repository_accepts_plain_tuples(repo):
    job = repo.add_job("Acme", "Dev", "", "saved", "desc")
    assert repo.save_requirements(job.id, [("SQL", "required")]) == 1
    assert repo.get_requirements(job.id)[0].skill == "SQL"


def test_two_repositories_share_the_same_file(db_path):
    first = Repository(db_path)
    first.init()
    job = first.add_job("Acme", "Dev", "", "saved", "desc")
    second = Repository(db_path)
    assert second.require_job(job.id).company == "Acme"


def _seed_jobs(repo, count: int) -> list[int]:
    ids = []
    for index in range(count):
        ids.append(repo.add_job(f"C{index}", "Dev", "", "saved", f"description {index}").id)
    return ids


def test_list_jobs_paginates(repo):
    _seed_jobs(repo, 3)

    assert [job.id for job in repo.list_jobs(limit=2)] == [1, 2]
    assert [job.id for job in repo.list_jobs(limit=2, offset=1)] == [2, 3]
    assert [job.id for job in repo.list_jobs(limit=2, offset=2)] == [3]


def test_list_jobs_offset_past_the_end_is_empty(repo):
    _seed_jobs(repo, 2)
    assert repo.list_jobs(offset=10) == []
    assert repo.count_jobs() == 2


def test_list_jobs_ignores_negative_offset(repo):
    _seed_jobs(repo, 2)
    assert [job.id for job in repo.list_jobs(limit=5, offset=-3)] == [1, 2]
