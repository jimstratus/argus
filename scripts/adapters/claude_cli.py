"""Claude CLI adapter — `claude -p --output-format text --bare` with prompt on stdin.

`--bare` skips hooks, LSP, plugin sync, CLAUDE.md auto-discovery — the right
flags for a one-shot reviewer call that shouldn't mutate anything or incur
startup overhead. Exits cleanly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, load_config


async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
    cfg = load_config()
    cmd = list(cfg["cli_commands"]["claude-cli"])
    env = os.environ.copy()
    # Ensure we don't accidentally recurse into Argus itself inside the nested Claude
    env["ARGUS_NESTED"] = "1"
    rc, stdout, stderr, dt = await run_subprocess(cmd, prompt, timeout, env=env)
    return {
        "route": "claude-cli",
        "cmd": cmd,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
