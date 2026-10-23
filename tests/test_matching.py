"""Matching: normalisation, aliases, token containment, fuzzy and scoring."""

from __future__ import annotations

import pytest

from joblens.models import Requirement, UserSkill
from joblens.services.matching import (
    SkillMatcher,
    canonical_skill,
    match_skills,
    normalize,
)


def skills(*names: str) -> list[UserSkill]:
    return [UserSkill(name) for name in names]


def requirements(*pairs: tuple[str, str]) -> list[Requirement]:
    return [Requirement(skill, importance) for skill, importance in pairs]


def test_normalize_folds_case_width_and_punctuation():
    assert normalize("  REST   API  ") == "rest api"
    assert normalize("Ｃ＃") == "c#"
    assert normalize("C++") == "c++"
    assert normalize("Node.js") == "node.js"


def test_canonical_skill_maps_aliases():
    assert canonical_skill("APIs") == "api"
    assert canonical_skill("REST API") == "api"
    assert canonical_skill("JS") == "javascript"
    assert canonical_skill("dotnet") == ".net"


def test_exact_match_ignores_case_and_spacing():
    result = match_skills(requirements(("Python", "required")), skills("  python "), job_id=3)

    assert result.job_id == 3
    assert [match.skill for match in result.matched] == ["Python"]
    assert result.matched[0].method == "exact"
    assert result.missing == ()
    assert result.score == 100.0


def test_alias_match_js_and_javascript():
    result = match_skills(requirements(("JavaScript", "required")), skills("JS"))

    assert result.matched[0].your_skill == "JS"
    assert result.matched[0].method == "alias"


def test_token_match_reports_apis_covered_by_rest_api():
    """The original matcher called this a missing skill."""
    result = match_skills(
        requirements(("APIs", "preferred")),
        skills("REST API / API integration"),
    )

    assert result.missing == ()
    assert result.matched[0].your_skill == "REST API / API integration"
    assert result.matched[0].method == "token"


def test_token_match_does_not_merge_unrelated_skills():
    result = match_skills(requirements(("SQL", "required")), skills("MySQL", "SQLite"))

    assert result.matched == ()
    assert [match.skill for match in result.missing] == ["SQL"]


def test_c_is_not_c_sharp():
    result = match_skills(requirements(("C#", "required")), skills("C"))

    assert result.missing[0].skill == "C#"
    assert result.score == 0.0


def test_typescript_is_not_javascript():
    result = match_skills(requirements(("TypeScript", "required")), skills("JavaScript"))

    assert result.missing[0].skill == "TypeScript"


def test_fuzzy_match_handles_plural_variants():
    result = match_skills(requirements(("PostgreSQL", "required")), skills("Postgres"))

    assert result.matched
    assert result.matched[0].method in {"alias", "fuzzy"}


def test_fuzzy_threshold_can_be_configured():
    strict = SkillMatcher(fuzzy_threshold=1.0)
    result = strict.match(requirements(("Kubernetes", "required")), skills("Kubernetse"))

    assert result.matched == ()


def test_unmatched_requirements_are_reported_with_importance():
    result = match_skills(
        requirements(("Python", "required"), ("Rust", "preferred")),
        skills("Python"),
    )

    assert [match.skill for match in result.missing] == ["Rust"]
    assert result.missing[0].importance == "preferred"


def test_score_weights_required_higher_than_preferred():
    # one required of two required + one preferred => 2/3 of the weight
    result = match_skills(
        requirements(("Python", "required"), ("Go", "required"), ("Rust", "preferred")),
        skills("Python"),
    )

    assert result.total == 3
    assert result.score == pytest.approx(40.0)


def test_score_is_zero_without_requirements():
    result = match_skills([], skills("Python"))
    assert result.score == 0.0
    assert result.total == 0


def test_no_user_skills_means_everything_is_missing():
    result = match_skills(requirements(("Python", "required")), [])
    assert result.matched == ()
    assert result.missing[0].skill == "Python"
