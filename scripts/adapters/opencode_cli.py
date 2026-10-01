"""OpenCode CLI adapter — `opencode run -` reads the prompt from stdin.

When the reviewer pins a model, `-m provider/model` is injected after `run`.
"""
from __future__ import annotations

from .stdin_cli import make_stdin_cli_adapter

send = make_stdin_cli_adapter("opencode-cli", model_mode="inject_after_run")
