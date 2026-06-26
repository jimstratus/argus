"""OpenCode CLI adapter — `opencode run -` reads the prompt from stdin."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, load_config


async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
    cfg = load_config()
    cmd = list(cfg["cli_commands"]["opencode-cli"])
    # When the reviewer pins a model, inject `-m provider/model` after `run`
    # (e.g. minimax-coding-plan/MiniMax-M3, ollama-cloud/glm-5.2). No model →
    # opencode's default, preserving the original `opencode run -` behavior.
    model = route_cfg.get("model")
    if model:
        i = cmd.index("run") if "run" in cmd else 0
        cmd = cmd[:i + 1] + ["-m", model] + cmd[i + 1:]
    env = os.environ.copy()
    rc, stdout, stderr, dt = await run_subprocess(cmd, prompt, timeout, env=env)
    return {
        "route": "opencode-cli",
        "cmd": cmd,
        "model": model,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
