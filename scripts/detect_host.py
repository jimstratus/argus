#!/usr/bin/env python3
"""Detect which CLI host Argus is running inside.

Output: one of `claude | codex | gemini | opencode | unknown`.
With `--json`, emits {"host": "name", "signals": [...]}.
"""
from __future__ import annotations

import json
import os
import sys


NAME_HINTS = {
    "claude": ["claude"],
    "codex":  ["codex"],
    "gemini": ["gemini"],
    "opencode": ["opencode"],
}


def detect() -> tuple[str, list[str]]:
    signals: list[str] = []
    env = os.environ

    # 1. Env-var markers set by host CLIs
    if env.get("CLAUDECODE") == "1":
        signals.append("env:CLAUDECODE=1")
        return "claude", signals
    if "CLAUDE_CODE_SESSION" in env or "CLAUDE_CODE_SIMPLE" in env:
        signals.append("env:CLAUDE_CODE_*")
        return "claude", signals
    if any(k.startswith("CODEX_") for k in env):
        signals.append("env:CODEX_*")
        return "codex", signals
    if env.get("GEMINI_CLI") == "1" or "GEMINI_CLI_SESSION" in env:
        signals.append("env:GEMINI_CLI")
        return "gemini", signals
    if env.get("OPENCODE") == "1" or "OPENCODE_SESSION" in env:
        signals.append("env:OPENCODE")
        return "opencode", signals

    # 2. Parent-process walk (up to 8 levels)
    try:
        import psutil  # type: ignore
        p = psutil.Process(os.getppid())
        for _ in range(8):
            name = (p.name() or "").lower()
            cmdline = " ".join(p.cmdline()).lower() if p.cmdline() else ""
            for host, hints in NAME_HINTS.items():
                for h in hints:
                    if h in name or h in cmdline:
                        signals.append(f"proc:{name or cmdline}")
                        return host, signals
            parent = p.parent()
            if parent is None:
                break
            p = parent
    except Exception as e:
        signals.append(f"proc-walk-error:{type(e).__name__}")

    return "unknown", signals


def main() -> int:
    host, signals = detect()
    if "--json" in sys.argv:
        print(json.dumps({"host": host, "signals": signals}))
    else:
        print(host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
