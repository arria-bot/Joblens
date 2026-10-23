"""Alias table: bundled data, user overrides and cache invalidation."""

from __future__ import annotations

import json

import pytest

from joblens import config
from joblens.errors import ValidationError
from joblens.services import aliases
from joblens.services.aliases import alias_groups, canonical_skill, reload_aliases


@pytest.fixture(autouse=True)
def clean_alias_cache(monkeypatch):
    """Never let one test's alias file leak into the next."""
    monkeypatch.delenv(config.ALIAS_FILE_ENV, raising=False)
    reload_aliases()
    yield
    reload_aliases()


def test_bundled_alias_table_is_loaded():
    groups = alias_groups()
    assert "api" in groups
    assert "apis" in groups["api"]
    assert ".net" in groups


def test_bundled_aliases_resolve():
    assert canonical_skill("APIs") == "api"
    assert canonical_skill("dotnet") == ".net"
    assert canonical_skill("JS") == "javascript"


def test_user_alias_file_extends_the_table(tmp_path, monkeypatch):
    alias_file = tmp_path / "aliases.json"
    alias_file.write_text(json.dumps({"kubernetes": ["k8s", "kube"]}), encoding="utf-8")
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(alias_file))
    reload_aliases()

    assert canonical_skill("K8s") == "kubernetes"
    assert "kube" in alias_groups()["kubernetes"]
    # Built-in entries survive the merge.
    assert canonical_skill("APIs") == "api"


def test_user_alias_file_can_extend_an_existing_group(tmp_path, monkeypatch):
    alias_file = tmp_path / "aliases.json"
    alias_file.write_text(json.dumps({"api": ["service api"]}), encoding="utf-8")
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(alias_file))
    reload_aliases()

    assert canonical_skill("service api") == "api"
    assert canonical_skill("REST API") == "api"


def test_invalid_alias_file_raises(tmp_path, monkeypatch):
    alias_file = tmp_path / "broken.json"
    alias_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(alias_file))
    reload_aliases()

    with pytest.raises(ValidationError, match="Cannot read alias file"):
        alias_groups()


def test_non_list_alias_variants_are_rejected(tmp_path, monkeypatch):
    alias_file = tmp_path / "bad.json"
    alias_file.write_text(json.dumps({"api": "not-a-list"}), encoding="utf-8")
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(alias_file))
    reload_aliases()

    with pytest.raises(ValidationError, match="list of spellings"):
        alias_groups()


def test_missing_alias_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(tmp_path / "nope.json"))
    reload_aliases()

    assert canonical_skill("APIs") == "api"


def test_reload_aliases_picks_up_changes(tmp_path, monkeypatch):
    alias_file = tmp_path / "aliases.json"
    monkeypatch.setenv(config.ALIAS_FILE_ENV, str(alias_file))

    alias_file.write_text(json.dumps({"rust": ["rustlang"]}), encoding="utf-8")
    reload_aliases()
    assert canonical_skill("rustlang") == "rust"

    alias_file.write_text(json.dumps({"go": ["golang"]}), encoding="utf-8")
    reload_aliases()
    assert canonical_skill("golang") == "go"
    assert aliases.canonical_skill("rustlang") == "rustlang"
