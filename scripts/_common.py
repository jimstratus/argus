"""Shared helpers for Argus scripts."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("Argus requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)


ARGUS_HOME = Path(os.environ.get("ARGUS_HOME") or Path(__file__).resolve().parent.parent).resolve()
CONFIG_PATH = ARGUS_HOME / "config.yaml"
PROMPT_PATH = ARGUS_HOME / "prompts" / "reviewer_prompt.md"
OVERLAYS_DIR = ARGUS_HOME / "prompts" / "overlays"
HISTORY_DB = ARGUS_HOME / "history.db"

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_config(path: Path | None = None) -> dict:
    p = path or CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_prompt(diff: str, overlay: str | None = None) -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    overlay_text = ""
    if overlay:
        overlay_path = OVERLAYS_DIR / f"{overlay}.md"
        if overlay_path.exists():
            overlay_text = overlay_path.read_text(encoding="utf-8")
    return tpl.replace("<<<OVERLAY>>>", overlay_text).replace("<<<DIFF>>>", diff)


def estimate_tokens(text: str) -> int:
    """Rough char->token estimate. ~4 chars/token for mixed English+code."""
    return max(1, len(text) // 4)


def extract_json(text: str) -> dict | None:
    """Tolerant JSON extractor.

    1. Direct parse
    2. Strip <think>...</think> reasoning blocks (Qwen, DeepSeek-R1 style)
    3. Fenced code block (```json ... ``` or ``` ... ```)
    4. First balanced {...} object containing "findings"
    5. First balanced {...} object anywhere
    """
    text = (text or "").strip()
    if not text:
        return None

    # Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Strip reasoning blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned and cleaned != text:
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        text = cleaned

    # Fenced code block (prefer the largest match)
    fence_matches = list(re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL))
    for m in sorted(fence_matches, key=lambda x: -(x.end() - x.start())):
        try:
            return json.loads(m.group(1))
        except Exception:
            continue

    # Prefer first balanced {...} containing "findings"
    for needle in ('"findings"', '"ok"', None):
        if needle:
            idx = text.find(needle)
            if idx < 0:
                continue
            start_range = [text.rfind("{", 0, idx)]
        else:
            # Try every `{` from largest block first
            start_range = [i for i, c in enumerate(text) if c == "{"]
        for start in start_range:
            if start < 0:
                continue
            depth = 0
            for i in range(start, len(text)):
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : i + 1]
                        try:
                            return json.loads(chunk)
                        except Exception:
                            break
                        break
    return None


def normalize_findings(raw: Any) -> list[dict]:
    out = []
    if not isinstance(raw, list):
        return out
    for f in raw:
        if not isinstance(f, dict):
            continue
        try:
            out.append({
                "file": str(f.get("file", "")).strip(),
                "line": int(f.get("line", 0) or 0),
                "severity": str(f.get("severity", "medium")).lower().strip(),
                "category": str(f.get("category", "bug")).lower().strip(),
                "description": str(f.get("description", "")).strip(),
                "confidence": max(0, min(100, int(f.get("confidence", 50) or 50))),
            })
        except Exception:
            continue
    return out


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """On Windows, npm-installed shims are `.cmd` files that bash finds via PATH
    but Python's subprocess (with shell=False) does not. Use shutil.which to
    resolve the first element to its actual on-disk path.
    """
    if not cmd:
        return cmd
    import shutil
    resolved = shutil.which(cmd[0])
    if resolved:
        return [resolved] + cmd[1:]
    return cmd


async def run_subprocess(cmd: list[str], stdin_data: str, timeout: int,
                         env: dict | None = None, cwd: str | None = None) -> tuple[int, str, str, float]:
    """Run a subprocess with stdin + timeout. Returns (rc, stdout, stderr, elapsed_sec).

    Uses subprocess.run inside a thread for simplicity and Windows compatibility.
    Resolves argv[0] via shutil.which so npm/.cmd shims work.
    """
    resolved_cmd = _resolve_cmd(cmd)

    def _runit() -> tuple[int, str, str, float]:
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                resolved_cmd,
                input=stdin_data.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
                cwd=cwd,
                check=False,
                shell=False,
            )
            return (
                result.returncode,
                result.stdout.decode("utf-8", errors="replace"),
                result.stderr.decode("utf-8", errors="replace"),
                time.monotonic() - t0,
            )
        except subprocess.TimeoutExpired:
            return 124, "", "timeout", time.monotonic() - t0
        except FileNotFoundError as e:
            return 127, "", f"command not found: {e}", time.monotonic() - t0
        except Exception as e:
            return 1, "", f"launch error: {type(e).__name__}: {e}", time.monotonic() - t0

    return await asyncio.to_thread(_runit)


def resolve_roster(cfg: dict, mode: str, names: list[str] | None, host: str,
                   allow_free: bool = False, allow_logging: bool = False,
                   explicit_custom_only: set[str] | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (final_roster, drop_reasons)."""
    explicit_custom_only = explicit_custom_only or set()
    reviewers = cfg["reviewers"]
    profiles = cfg["profiles"]
    host_rules = cfg.get("host_rules", {}).get(host, {"skip": [], "add": []})

    if mode == "profile":
        base = list(profiles[names[0]]["members"])  # type: ignore
    elif mode in ("custom", "models"):
        base = list(names or [])
    else:
        base = list(profiles[cfg["defaults"]["profile"]]["members"])

    # Host adaptation
    base = [n for n in base if n not in set(host_rules.get("skip", []))]
    for n in host_rules.get("add", []):
        if n not in base:
            base.append(n)

    drops: list[tuple[str, str]] = []
    final = []
    for n in base:
        spec = reviewers.get(n)
        if not spec:
            drops.append((n, "not in registry"))
            continue
        if spec.get("disabled"):
            drops.append((n, "disabled in config"))
            continue
        if spec.get("tier") == "free" and not allow_free:
            drops.append((n, "free tier (use --allow-free)"))
            continue
        if spec.get("privacy") == "LOGS" and not allow_logging:
            drops.append((n, "logs prompts (use --allow-logging)"))
            continue
        if spec.get("custom_only") and n not in explicit_custom_only:
            drops.append((n, "custom-only (name via --custom/--models)"))
            continue
        final.append(n)

    # Dedupe preserving order
    seen: set[str] = set()
    dedup: list[str] = []
    for n in final:
        if n not in seen:
            seen.add(n)
            dedup.append(n)
    return dedup, drops


def build_aichat_env(client: str) -> dict[str, str]:
    """Build env dict for an aichat subprocess with the right API key var set.

    aichat looks up AICHAT_<CLIENT>_API_KEY for a named openai-compatible client.
    We pull from the source env var named in config.yaml and forward it.
    """
    cfg = load_config()
    src_env = cfg["aichat_clients"][client]["api_key_env"]
    env = os.environ.copy()
    src_val = env.get(src_env, "")
    if src_val:
        target = f"AICHAT_{client.upper()}_API_KEY"
        env[target] = src_val
        # Also forward the provider-specific canonical names some clients expect.
        env.setdefault(src_env, src_val)
    return env


# ─────── history.db ───────────────────────────────────────────────────

HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    host TEXT,
    profile TEXT,
    roster TEXT NOT NULL,
    diff_sha256 TEXT,
    diff_bytes INTEGER,
    cost_est_usd REAL,
    latency_sec REAL
);
CREATE TABLE IF NOT EXISTS reviewer_runs (
    run_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    route TEXT,
    exit_code INTEGER,
    fallback_used INTEGER DEFAULT 0,
    latency_sec REAL,
    n_findings INTEGER,
    error TEXT,
    PRIMARY KEY (run_id, reviewer)
);
CREATE TABLE IF NOT EXISTS findings (
    run_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    file TEXT,
    line INTEGER,
    severity TEXT,
    category TEXT,
    confidence INTEGER,
    n_reviewers INTEGER,
    reviewers TEXT,
    description TEXT,
    PRIMARY KEY (run_id, idx)
);
CREATE TABLE IF NOT EXISTS benchmarks (
    ts TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    fixture TEXT NOT NULL,
    run_idx INTEGER NOT NULL,
    "precision" REAL,
    recall REAL,
    f1 REAL,
    n_findings INTEGER,
    latency_sec REAL,
    error TEXT,
    PRIMARY KEY (ts, reviewer, fixture, run_idx)
);
"""


def history_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(HISTORY_DB)
    conn.executescript(HISTORY_SCHEMA)
    return conn
