"""Per-CLI adapters. Each adapter exposes an async `send(prompt, spec, timeout, use_fallback=False)`
that returns a dict with keys: {route, exit_code, stdout, stderr, latency_sec, fallback_used}.
"""
from __future__ import annotations

from . import aichat as aichat_adapter
from . import gemini_cli as gemini_adapter
from . import codex_cli as codex_adapter
from . import claude_cli as claude_adapter
from . import opencode_cli as opencode_adapter
from . import copilot_cli as copilot_adapter


ROUTE_ADAPTERS = {
    "aichat": aichat_adapter,
    "gemini-cli": gemini_adapter,
    "codex-cli": codex_adapter,
    "claude-cli": claude_adapter,
    "opencode-cli": opencode_adapter,
    "copilot-cli": copilot_adapter,
}


def get(route: str):
    return ROUTE_ADAPTERS.get(route)
