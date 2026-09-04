"""Regression test for `collect_lib_versions` (Principle II) — with Ollama
moved out of docker-compose and onto the host (research.md's "Ambiente de
execução canônico"), this is what records which build a run actually
talked to, since no pinned image tag does it anymore.
"""

import pytest

from qcagent import config


def test_includes_every_tracked_package_and_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ollama_version", lambda base_url: "0.4.7")

    versions = config.collect_lib_versions(ollama_base_url="http://host.docker.internal:11434")

    for package in config._TRACKED_PACKAGES:
        assert package in versions
        assert versions[package] != ""  # actually resolved, not skipped
    assert versions["ollama"] == "0.4.7"


def test_defaults_ollama_base_url_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_ollama_version(base_url: str) -> str:
        seen["base_url"] = base_url
        return "0.4.7"

    monkeypatch.setattr(config, "ollama_version", fake_ollama_version)

    config.collect_lib_versions()

    assert seen["base_url"] == config.settings.ollama_base_url
