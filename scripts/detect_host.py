#!/usr/bin/env python3
"""Detect which CLI host Argus is running inside.

Output: one of `claude | codex | gemini | opencode | unknown`.
With `--json`, emits {"host": "name", "signals": [...]}.
"""
from __future__ import annotations

import json
import os
import sys


HOSTS = ("claude", "codex", "gemini", "opencode")


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
    # Specific session markers only — a prefix scan would misfire on user
    # credentials like CODEX_API_KEY exported in a shell profile.
    codex_markers = ("CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
                     "CODEX_THREAD_ID", "CODEX_SESSION_ID")
    codex_hit = next((k for k in codex_markers if k in env), None)
    if codex_hit:
        signals.append(f"env:{codex_hit}")
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
            # Match the executable and its script (argv[0]/argv[1] basenames,
            # covering `node /path/gemini.js`), never the full cmdline —
            # arguments like `--roster codex` in a wrapping shell must not
            # read as a codex host.
            cmdline = p.cmdline() or []
            heads = " ".join(os.path.basename(a).lower() for a in cmdline[:2])
            for host in HOSTS:
                if host in name or host in heads:
                    signals.append(f"proc:{name or heads}")
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
