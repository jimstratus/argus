"""Codex CLI adapter — `codex exec -` reads the prompt from stdin and runs non-interactively."""
from __future__ import annotations

from .stdin_cli import make_stdin_cli_adapter

send = make_stdin_cli_adapter("codex-cli")
