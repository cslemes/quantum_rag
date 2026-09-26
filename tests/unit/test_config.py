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


def test_git_sha_marks_a_dirty_tree(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A record made with uncommitted changes must not claim a clean commit."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    (tmp_path / "f.py").write_text("a = 1\n")
    git("add", "f.py")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "f")
    monkeypatch.chdir(tmp_path)

    clean = config.git_sha()
    assert len(clean) == 40 and not clean.endswith("-dirty")

    (tmp_path / "f.py").write_text("a = 2\n")
    assert config.git_sha() == clean + "-dirty"

    (tmp_path / "untracked.txt").write_text("")  # untracked files do not count
    (tmp_path / "f.py").write_text("a = 1\n")
    assert config.git_sha() == clean
