"""Gemini CLI adapter. Invokes `gemini -p "" --yolo` with the prompt piped to stdin.

`gemini` CLI help states: "-p/--prompt ... Appended to input on stdin (if any)."
We use empty -p to force non-interactive mode and feed the entire prompt via stdin.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, load_config


async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
    cfg = load_config()
    template = cfg["cli_commands"]["gemini-cli"]
    cmd = [p.replace("{prompt}", prompt) for p in template]
    env = os.environ.copy()
    # Prompt is embedded as arg — pass empty stdin
    rc, stdout, stderr, dt = await run_subprocess(cmd, "", timeout, env=env)
    return {
        "route": "gemini-cli",
        "cmd": cmd[:4] + ["...<prompt>"] if len(cmd) > 4 else cmd,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
