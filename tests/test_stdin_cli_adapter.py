"""Regression tests for adapters.stdin_cli.make_stdin_cli_adapter (#22 slice 3)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "adapters"))

from adapters.stdin_cli import make_stdin_cli_adapter  # noqa: E402
from adapters import (  # noqa: E402
    claude_cli,
    codex_cli,
    copilot_cli,
    gemini_cli,
    opencode_cli,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake_cfg(monkeypatch):
    cfg = {
        "cli_commands": {
            "claude-cli": ["claude", "-p", "--bare"],
            "codex-cli": ["codex", "exec", "-"],
            "gemini-cli": ["gemini", "--yolo", "-p", ""],
            "opencode-cli": ["opencode", "run", "-"],
            "copilot-cli": ["copilot", "-p", "ptr", "--model", "{model}"],
        }
    }
    monkeypatch.setattr("adapters.stdin_cli.load_config", lambda: cfg)
    return cfg


def test_prompt_piped_via_stdin_not_argv(fake_cfg):
    """ARG_MAX fix: prompt must be the stdin arg to run_subprocess, not in cmd."""
    send = make_stdin_cli_adapter("gemini-cli")
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "ok", "", 0.1),
    ) as mock:
        r = _run(send("HUGE PROMPT " * 1000, {}, 30))
    assert mock.await_count == 1
    args, kwargs = mock.await_args
    cmd, prompt = args[0], args[1]
    assert prompt.startswith("HUGE PROMPT")
    assert all("HUGE PROMPT" not in str(p) for p in cmd)
    assert r["route"] == "gemini-cli"
    assert r["exit_code"] == 0


def test_extra_env_forced(fake_cfg, monkeypatch):
    monkeypatch.setenv("ARGUS_NESTED", "0")
    send = make_stdin_cli_adapter("claude-cli", extra_env={"ARGUS_NESTED": "1"})
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        _run(send("p", {}, 10))
    env = mock.await_args.kwargs["env"]
    assert env["ARGUS_NESTED"] == "1"


def test_setdefault_env_preserves_existing(fake_cfg, monkeypatch):
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "0")
    send = make_stdin_cli_adapter(
        "copilot-cli",
        setdefault_env={"COPILOT_ALLOW_ALL": "1"},
        model_mode="placeholder",
    )
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        _run(send("p", {"model": "gpt-x"}, 10))
    assert mock.await_args.kwargs["env"]["COPILOT_ALLOW_ALL"] == "0"


def test_setdefault_env_fills_missing(fake_cfg, monkeypatch):
    monkeypatch.delenv("COPILOT_ALLOW_ALL", raising=False)
    send = make_stdin_cli_adapter(
        "copilot-cli",
        setdefault_env={"COPILOT_ALLOW_ALL": "1"},
        model_mode="placeholder",
    )
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        _run(send("p", {"model": "gpt-x"}, 10))
    assert mock.await_args.kwargs["env"]["COPILOT_ALLOW_ALL"] == "1"


def test_placeholder_model(fake_cfg):
    send = make_stdin_cli_adapter("copilot-cli", model_mode="placeholder")
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        r = _run(send("p", {"model": "gpt-5.2"}, 10))
    assert mock.await_args.args[0] == ["copilot", "-p", "ptr", "--model", "gpt-5.2"]
    assert r["model"] == "gpt-5.2"


def test_inject_after_run_with_model(fake_cfg):
    send = make_stdin_cli_adapter("opencode-cli", model_mode="inject_after_run")
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        r = _run(send("p", {"model": "ollama-cloud/glm-5.2"}, 10))
    assert mock.await_args.args[0] == [
        "opencode", "run", "-m", "ollama-cloud/glm-5.2", "-",
    ]
    assert r["model"] == "ollama-cloud/glm-5.2"


def test_inject_after_run_without_model(fake_cfg):
    send = make_stdin_cli_adapter("opencode-cli", model_mode="inject_after_run")
    with patch(
        "adapters.stdin_cli.run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, "", "", 0.0),
    ) as mock:
        _run(send("p", {}, 10))
    assert mock.await_args.args[0] == ["opencode", "run", "-"]


def test_thin_wrappers_are_factory_products():
    """All five stdin adapters must be produced by the shared factory."""
    for mod, route in (
        (claude_cli, "claude-cli"),
        (codex_cli, "codex-cli"),
        (gemini_cli, "gemini-cli"),
        (opencode_cli, "opencode-cli"),
        (copilot_cli, "copilot-cli"),
    ):
        assert callable(mod.send)
        assert route.replace("-", "_") in (mod.send.__name__ or "")


def test_unknown_model_mode_raises(fake_cfg):
    send = make_stdin_cli_adapter("codex-cli", model_mode="nope")
    with pytest.raises(ValueError, match="unknown model_mode"):
        _run(send("p", {}, 10))
