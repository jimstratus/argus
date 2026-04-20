"""aichat adapter — routes through `aichat -m CLIENT:MODEL -S` with prompt on stdin."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, build_aichat_env, load_config


async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
    client = route_cfg["client"]
    model = route_cfg["model"]
    cfg = load_config()
    template = cfg["cli_commands"]["aichat"]
    cmd = [part.replace("{client}", client).replace("{model}", model) for part in template]
    env = build_aichat_env(client)
    rc, stdout, stderr, dt = await run_subprocess(cmd, prompt, timeout, env=env)
    return {
        "route": "aichat",
        "client": client,
        "model": model,
        "cmd": cmd,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "latency_sec": dt,
    }
