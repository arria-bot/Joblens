"""Service-layer orchestration: analyse-then-write, re-analysis, matching."""

from __future__ import annotations

import pytest

from joblens.errors import AnalysisError, NotFoundError, ValidationError
from joblens.models import Requirement


def test_add_job_stores_job_and_skills(service, repo, stub_analyzer):
    job, reused, requirements = service.add_job(
        company="Acme", title="Dev", salary="$90k", status="saved",
        description="We need SQL.",
    )

    assert reused is False
    assert job.analysis_status == "done"
    assert [r.skill for r in requirements] == ["SQL"]
    assert repo.count_jobs() == 1
    assert [r.skill for r in repo.get_requirements(job.id)] == ["SQL"]


def test_failed_analysis_writes_nothing(service, repo, stub_analyzer):
    stub_analyzer.error = AnalysisError("model down")

    with pytest.raises(AnalysisError):
        service.add_job("Acme", "Dev", "", "saved", "description")

    assert repo.count_jobs() == 0


def test_empty_description_is_rejected_before_calling_the_model(service, repo, stub_analyzer):
    with pytest.raises(ValidationError):
        service.add_job("Acme", "Dev", "", "saved", "   ")

    assert stub_analyzer.calls == []
    assert repo.count_jobs() == 0


def test_duplicate_posting_is_reused(service, repo):
    first, _, _ = service.add_job("Acme", "Dev", "", "saved", "same text")
    second, reused, _ = service.add_job("Acme", "Dev", "", "applied", "same text")

    assert reused is True
    assert second.id == first.id
    assert repo.count_jobs() == 1
    assert repo.require_job(first.id).status == "applied"


def test_reanalyze_without_force_skips_the_model(service, repo, stub_analyzer):
    job, _, _ = service.add_job("Acme", "Dev", "", "saved", "description")
    calls_before = len(stub_analyzer.calls)

    requirements = service.reanalyze(job.id)

    assert len(stub_analyzer.calls) == calls_before
    assert [r.skill for r in requirements] == ["SQL"]


def test_reanalyze_force_replaces_skills(service, repo, stub_analyzer):
    job, _, _ = service.add_job("Acme", "Dev", "", "saved", "description")
    stub_analyzer.requirements = [Requirement("Rust", "required")]

    requirements = service.reanalyze(job.id, force=True)

    assert [r.skill for r in requirements] == ["Rust"]
    assert [r.skill for r in repo.get_requirements(job.id)] == ["Rust"]


def test_reanalyze_failure_marks_job_and_keeps_old_skills(service, repo, stub_analyzer):
    job, _, _ = service.add_job("Acme", "Dev", "", "saved", "description")
    stub_analyzer.error = AnalysisError("nope")

    with pytest.raises(AnalysisError):
        service.reanalyze(job.id, force=True)

    assert repo.require_job(job.id).analysis_status == "failed"
    assert [r.skill for r in repo.get_requirements(job.id)] == ["SQL"]


def test_match_uses_stored_requirements_and_skills(service, repo):
    job, _, _ = service.add_job("Acme", "Dev", "", "saved", "description")
    repo.add_user_skill("SQL", level="Intermediate")
    repo.add_user_skill("REST API / API integration", level="Beginner")
    repo.save_requirements(
        job.id, [Requirement("SQL", "required"), Requirement("APIs", "preferred")]
    )

    result = service.match(job.id)

    assert {m.skill for m in result.matched} == {"SQL", "APIs"}
    assert result.missing == ()
    assert result.score == 100.0


def test_match_for_missing_job_raises(service):
    with pytest.raises(NotFoundError):
        service.match(999)


def test_skill_management_round_trip(service, repo):
    service.add_skill("Python", level="Advanced", evidence="CS50x")
    assert [s.skill for s in service.list_skills()] == ["Python"]

    assert service.remove_skill("python") is True
    assert service.list_skills() == []
    assert service.remove_skill("python") is False


def test_get_job_raises_for_unknown_id(service):
    with pytest.raises(NotFoundError):
        service.get_job(1234)


def test_list_jobs_respects_limit(service):
    for index in range(3):
        service.add_job(f"C{index}", "Dev", "", "saved", f"description {index}")
    assert len(service.list_jobs(limit=2)) == 2


def test_service_uses_injected_analyzer(service, stub_analyzer):
    service.add_job("Acme", "Dev", "", "saved", "some description")
    assert stub_analyzer.calls == ["some description"]
