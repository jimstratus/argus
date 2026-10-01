"""GitHub Copilot CLI adapter.

The full prompt is piped via STDIN (combined by the CLI with the short -p
pointer) — the previous {prompt}-in-argv approach breaks on Windows for
prompts > ~32 KB (ARG_MAX), the same bug fixed for gemini-cli. Kept as
`custom_only` by default so it appears in benchmark/custom mode but doesn't
inflate every panel run.
"""
from __future__ import annotations

from .stdin_cli import make_stdin_cli_adapter

send = make_stdin_cli_adapter(
    "copilot-cli",
    setdefault_env={"COPILOT_ALLOW_ALL": "1"},
    model_mode="placeholder",
)
