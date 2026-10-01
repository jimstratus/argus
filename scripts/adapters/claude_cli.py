"""Claude CLI adapter — `claude -p --output-format text --bare` with prompt on stdin.

`--bare` skips hooks, LSP, plugin sync, CLAUDE.md auto-discovery — the right
flags for a one-shot reviewer call that shouldn't mutate anything or incur
startup overhead. Exits cleanly.
"""
from __future__ import annotations

from .stdin_cli import make_stdin_cli_adapter

send = make_stdin_cli_adapter(
    "claude-cli",
    extra_env={"ARGUS_NESTED": "1"},
)
