"""Shared factory for stdin-fed CLI adapters (issue #22 slice 3).

gemini / codex / claude / opencode / copilot were near-identical: load a
``cli_commands`` template, pipe the prompt via stdin, return the same result
dict. The ARG_MAX fix (prompt out of argv) had to be ported across them in
two separate commits — one factory so that cannot happen again.

aichat stays separate: it needs client:model templating + ``build_aichat_env``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Awaitable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import run_subprocess, load_config  # noqa: E402


SendFn = Callable[[str, dict, int], Awaitable[dict]]


def make_stdin_cli_adapter(
    route_key: str,
    *,
    cli_command_key: str | None = None,
    extra_env: dict[str, str] | None = None,
    setdefault_env: dict[str, str] | None = None,
    model_mode: str | None = None,
) -> SendFn:
    """Return an async ``send(prompt, route_cfg, timeout)`` for a stdin CLI.

    ``model_mode``:
      - ``None`` — ignore ``route_cfg["model"]``
      - ``"placeholder"`` — replace ``{model}`` tokens in the template
      - ``"inject_after_run"`` — insert ``-m <model>`` after the ``run`` token
        (OpenCode); no model → leave the template alone
    """
    cmd_key = cli_command_key or route_key
    env_extra = dict(extra_env or {})
    env_setdefault = dict(setdefault_env or {})

    async def send(prompt: str, route_cfg: dict, timeout: int) -> dict:
        cfg = load_config()
        cmd = list(cfg["cli_commands"][cmd_key])
        model = route_cfg.get("model") or ""

        if model_mode == "placeholder":
            cmd = [model if part == "{model}" else part for part in cmd]
        elif model_mode == "inject_after_run":
            if model:
                i = cmd.index("run") if "run" in cmd else 0
                cmd = cmd[: i + 1] + ["-m", model] + cmd[i + 1 :]
        elif model_mode is not None:
            raise ValueError(f"unknown model_mode: {model_mode!r}")

        env = os.environ.copy()
        for k, v in env_extra.items():
            env[k] = v
        for k, v in env_setdefault.items():
            env.setdefault(k, v)

        rc, stdout, stderr, dt = await run_subprocess(cmd, prompt, timeout, env=env)
        out: dict[str, Any] = {
            "route": route_key,
            "cmd": cmd,
            "exit_code": rc,
            "stdout": stdout,
            "stderr": stderr,
            "latency_sec": dt,
        }
        if model_mode is not None:
            out["model"] = model or route_cfg.get("model")
        return out

    send.__name__ = f"send_{route_key.replace('-', '_')}"
    send.__qualname__ = send.__name__
    send.__doc__ = f"stdin CLI adapter for route {route_key!r} (via make_stdin_cli_adapter)."
    return send
