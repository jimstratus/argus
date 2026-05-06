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
    # Pass prompt via STDIN (gemini CLI: empty -p arg forces non-interactive,
    # then it appends stdin content). The previous {prompt}-in-argv approach
    # broke on Windows for prompts > ~32 KB (ARG_MAX limit) — see 2026-05-06
    # lab notes in /d/Projects/waterwall/docs/superpowers/lab-notes/phase-1.md.
    cmd = list(template)  # template should be ["gemini","--yolo","-p",""]
    env = os.environ.copy()
    rc, stdout, stderr, dt = await run_subprocess(cmd, prompt, timeout, env=env)
    return {
        "route": "gemini-cli",
        "cmd": cmd,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
