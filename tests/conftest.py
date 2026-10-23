"""Shared fixtures.

Everything here is offline: the LLM is replaced by a stub, so the suite runs
without ``DEEPSEEK_API_KEY`` and without network access.
"""

from __future__ import annotations

import types

import pytest

from joblens.db.repository import Repository
from joblens.models import Requirement
from joblens.services.jobs import JobService


class StubAnalyzer:
    """Stand-in for :class:`joblens.services.analyzer.SkillAnalyzer`."""

    def __init__(self, requirements=None, error=None):
        self.requirements = list(requirements) if requirements is not None else [
            Requirement("SQL", "required")
        ]
        self.error = error
        self.calls: list[str] = []

    def analyze(self, description):
        self.calls.append(description)
        if self.error is not None:
            raise self.error
        return list(self.requirements)


class FakeClient:
    """Minimal OpenAI-compatible client.

    ``responses`` holds strings (message content) or exceptions to raise.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
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


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "jobs.db"


@pytest.fixture
def repo(db_path):
    repository = Repository(db_path)
    repository.init()
    return repository


@pytest.fixture
def stub_analyzer():
    return StubAnalyzer()


@pytest.fixture
def service(repo, stub_analyzer):
    return JobService(repo, analyzer=stub_analyzer)


@pytest.fixture
def make_stub():
    return StubAnalyzer


@pytest.fixture
def make_client():
    return FakeClient
