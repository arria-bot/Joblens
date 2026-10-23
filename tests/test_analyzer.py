"""Skill extraction: prompt building, parsing, retries and failure modes."""

from __future__ import annotations

import pytest

from joblens import config
from joblens.errors import AnalysisError
from joblens.services.analyzer import SkillAnalyzer, build_prompt, parse_requirements


def make_http_error(status_code: int) -> Exception:
    error = Exception(f"http {status_code}")
    error.status_code = status_code  # type: ignore[attr-defined]
    return error


def test_parses_markdown_fenced_json(make_client):
    client = make_client(
        ['```json\n{"requirements": [{"skill": "C#", "importance": "required"}]}\n```']
    )
    requirements = SkillAnalyzer(client=client).analyze("We need C#.")

    assert [r.skill for r in requirements] == ["C#"]
    assert requirements[0].importance == "required"


def test_parses_bare_json_and_normalises_importance(make_client):
    client = make_client(['{"requirements": [{"skill": "SQL", "importance": "MUST HAVE"}]}'])
    requirements = SkillAnalyzer(client=client).analyze("SQL please")

    assert requirements[0].skill == "SQL"
    assert requirements[0].importance == "preferred"


def test_accepts_a_top_level_list(make_client):
    client = make_client(['[{"skill": "Go", "importance": "preferred"}]'])
    assert [r.skill for r in SkillAnalyzer(client=client).analyze("jd")] == ["Go"]


def test_accepts_plain_strings_and_deduplicates(make_client):
    client = make_client(['{"requirements": ["SQL", "sql", "Python"]}'])
    requirements = SkillAnalyzer(client=client).analyze("jd")

    assert [r.skill for r in requirements] == ["SQL", "Python"]


def test_invalid_json_raises_analysis_error(make_client):
    client = make_client(["I think it needs Python."])
    with pytest.raises(AnalysisError):
        SkillAnalyzer(client=client).analyze("jd")


def test_empty_response_raises_analysis_error(make_client):
    client = make_client(["   "])
    with pytest.raises(AnalysisError):
        SkillAnalyzer(client=client).analyze("jd")


def test_no_skills_found_raises_instead_of_returning_empty(make_client):
    client = make_client(['{"requirements": []}'])
    with pytest.raises(AnalysisError, match="no technical skills"):
        SkillAnalyzer(client=client).analyze("jd")


def test_empty_description_is_rejected(make_client):
    client = make_client([])
    with pytest.raises(AnalysisError):
        SkillAnalyzer(client=client).analyze("   ")
    assert client.calls == []


def test_missing_api_key_is_reported_clearly(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(AnalysisError, match="DEEPSEEK_API_KEY"):
        SkillAnalyzer().analyze("jd")


def test_requests_json_mode_without_creativity(make_client):
    client = make_client(['{"requirements": [{"skill": "SQL"}]}'])
    SkillAnalyzer(client=client).analyze("jd")

    kwargs = client.calls[0]
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["temperature"] == 0
    assert kwargs["timeout"] == config.REQUEST_TIMEOUT_SECONDS
    assert kwargs["model"] == config.DEFAULT_MODEL
    assert kwargs["messages"][0]["role"] == "system"
    assert "<job_description>" in kwargs["messages"][1]["content"]


def test_retries_on_rate_limit_then_succeeds(make_client):
    slept: list[float] = []
    client = make_client([make_http_error(429), '{"requirements": [{"skill": "SQL"}]}'])
    analyzer = SkillAnalyzer(client=client, sleeper=slept.append)

    requirements = analyzer.analyze("jd")

    assert [r.skill for r in requirements] == ["SQL"]
    assert len(client.calls) == 2
    assert slept == [1]


def test_gives_up_after_max_retries(make_client):
    client = make_client([make_http_error(500), make_http_error(500), make_http_error(500)])
    analyzer = SkillAnalyzer(client=client, max_retries=2, sleeper=lambda _s: None)

    with pytest.raises(AnalysisError):
        analyzer.analyze("jd")
    assert len(client.calls) == 2


def test_does_not_retry_on_authentication_error(make_client):
    client = make_client([make_http_error(401), '{"requirements": [{"skill": "SQL"}]}'])
    analyzer = SkillAnalyzer(client=client, sleeper=lambda _s: None)

    with pytest.raises(AnalysisError):
        analyzer.analyze("jd")
    assert len(client.calls) == 1


def test_client_is_built_lazily(make_client):
    created: list[object] = []

    def factory():
        created.append(True)
        return make_client(
            [
                '{"requirements": [{"skill": "SQL"}]}',
                '{"requirements": [{"skill": "SQL"}]}',
            ]
        )

    analyzer = SkillAnalyzer(client_factory=factory)
    assert created == []

    analyzer.analyze("jd")
    analyzer.analyze("second jd")
    assert created == [True]  # built once, then reused


def test_long_descriptions_are_truncated(monkeypatch, make_client):
    monkeypatch.setattr(config, "MAX_JD_CHARS", 40)
    client = make_client(['{"requirements": [{"skill": "SQL"}]}'])

    SkillAnalyzer(client=client).analyze("word " * 500)

    prompt = client.calls[0]["messages"][1]["content"]
    assert "[truncated]" in prompt
    assert len(prompt) < 200


def test_build_prompt_keeps_short_descriptions_intact():
    prompt = build_prompt("Short job description.")
    assert "Short job description." in prompt
    assert "[truncated]" not in prompt


def test_parse_requirements_rejects_wrong_shape():
    with pytest.raises(AnalysisError):
        parse_requirements('{"skills": []}')
