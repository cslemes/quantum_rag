"""`scripts/distill_pilot.py` spends only when told to, whatever credential exists."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "distill_pilot.py"


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("distill_pilot_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["distill_pilot_script"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    def forbidden(*_a, **_k):
        raise AssertionError("reached the credential or the network before the gate refused")

    monkeypatch.setattr(module, "build_client", forbidden)
    monkeypatch.setattr(module, "listing_entry", forbidden)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-a-credential-is-present")
    return module


def test_a_present_credential_without_the_flag_refuses_before_looking_at_anything(
    script, monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["x", "--out-dir", str(tmp_path / "o"), "--dataset-version", "v"]
    )
    assert script.main() == 2
    assert "not permission" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_a_grant_below_the_stop_ceiling_refuses(script, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--out-dir",
            str(tmp_path / "o"),
            "--dataset-version",
            "v",
            "--authorize-spend",
            "0.1",
        ],
    )
    assert script.main() == 2
    assert "below the stop ceiling" in capsys.readouterr().err


def test_the_sandbox_pool_is_forked_before_anything_does_linear_algebra(
    script, monkeypatch, tmp_path
) -> None:
    order: list[str] = []

    class Pool:
        def __init__(self, *a, **k) -> None:
            order.append("pool")

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

    def listing(*_a, **_k):
        order.append("listing")
        raise RuntimeError("stop here")

    monkeypatch.setattr(script, "WorkerPool", Pool)
    monkeypatch.setattr(script, "listing_entry", listing)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--out-dir",
            str(tmp_path / "o"),
            "--dataset-version",
            "v",
            "--authorize-spend",
            "0.36",
        ],
    )
    with pytest.raises(RuntimeError, match="stop here"):
        script.main()
    assert order == ["pool", "listing"]
