"""GitHub Copilot CLI adapter.

Copilot CLI uses GPT-family models (e.g., gpt-5.2) through the user's paid
GitHub Copilot subscription. Invocation:
    copilot -p "<prompt>" --model <model> --allow-all-tools \
            --no-color --no-banner --output-format text

Value vs direct GPT routes:
  - Uses the user's Copilot paid sub (no API spend)
  - Different harness than Codex CLI — worth benchmarking the same model across
    the two to detect harness-level quality or latency differences
  - Kept as `custom_only` by default so it appears in benchmark/custom mode
    but doesn't inflate every panel run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, load_config


async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
    cfg = load_config()
    template = list(cfg["cli_commands"]["copilot-cli"])
    model = route_cfg.get("model", "")
    cmd = []
    for part in template:
        if part == "{model}":
            cmd.append(model)
        elif part == "{prompt}":
            cmd.append(prompt)
        else:
            cmd.append(part)
    env = os.environ.copy()
    env.setdefault("COPILOT_ALLOW_ALL", "1")
    # Prompt already embedded as arg; no stdin needed
    rc, stdout, stderr, dt = await run_subprocess(cmd, "", timeout, env=env)
    return {
        "route": "copilot-cli",
        "model": model,
        "cmd": cmd[:6] + ["...", "<prompt>"] if len(cmd) > 6 else cmd,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
