"""Shared helpers for Argus scripts."""
from __future__ import annotations

import asyncio
import functools
import json
import os
import re
import signal
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


@functools.lru_cache(maxsize=8)
def load_config(path: Path | None = None) -> dict:
    """Parse config.yaml once per process. Returns a shared cached dict —
    treat it as read-only (every adapter call goes through here)."""
    p = path or CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=16)
def _read_text_cached(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_prompt(diff: str, overlay: str | None = None) -> str:
    tpl = _read_text_cached(PROMPT_PATH)
    overlay_text = ""
    if overlay:
        overlay_path = OVERLAYS_DIR / f"{overlay}.md"
        if overlay_path.exists():
            overlay_text = _read_text_cached(overlay_path)
    # Escape ``` in the diff so it cannot terminate the outer fence early.
    # Use a zero-width joiner between backticks; reviewers see visually-identical
    # content while the fence stays intact.
    escaped_diff = diff.replace("```", "`\u200b``")
    return tpl.replace("<<<OVERLAY>>>", overlay_text).replace("<<<DIFF>>>", escaped_diff)


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
            # Last resort: one O(n) string-aware pass collecting every balanced
            # {...} span via a stack, then bounded parse attempts in document
            # order. (The old per-'{' rescan was O(n²) — minutes of CPU on
            # brace-heavy non-JSON reviewer output.)
            spans: list[tuple[int, int]] = []
            stack: list[int] = []
            in_str = esc = False
            for i, c in enumerate(text):
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    stack.append(i)
                elif c == "}" and stack:
                    spans.append((stack.pop(), i))
            spans.sort()
            for start, end in spans[:50]:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    continue
            return None
        for start in start_range:
            if start < 0:
                continue
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(text)):
                c = text[i]
                if in_str:
                    # Braces inside string values must not move the depth counter.
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : i + 1]
                        try:
                            return json.loads(chunk)
                        except Exception:
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
            sev = str(f.get("severity", "medium")).lower().strip()
            if sev not in SEVERITY_RANK:
                sev = "medium"
            out.append({
                "file": str(f.get("file", "")).strip(),
                "line": int(f.get("line", 0) or 0),
                "severity": sev,
                "category": str(f.get("category", "bug")).lower().strip(),
                "description": str(f.get("description", "")).strip(),
                "confidence": max(0, min(100, int(f.get("confidence", 50) or 50))),
            })
        except Exception:
            continue
    return out


@functools.lru_cache(maxsize=32)
def _which_cached(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """On Windows, npm-installed shims are `.cmd` files that bash finds via PATH
    but Python's subprocess (with shell=False) does not. Use shutil.which to
    resolve the first element to its actual on-disk path.
    """
    if not cmd:
        return cmd
    resolved = _which_cached(cmd[0])
    if resolved:
        return [resolved] + cmd[1:]
    return cmd


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process AND its children. npm .cmd shims spawn a node grandchild
    that survives a plain proc.kill(), holds the captured pipes, and hangs the
    run — the bug that got the gemini reviewer disabled."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


async def run_subprocess(cmd: list[str], stdin_data: str, timeout: int,
                         env: dict | None = None, cwd: str | None = None) -> tuple[int, str, str, float]:
    """Run a subprocess with stdin + timeout. Returns (rc, stdout, stderr, elapsed_sec).

    Runs in a thread for simplicity and Windows compatibility. Resolves argv[0]
    via shutil.which so npm/.cmd shims work. On timeout the whole process TREE
    is killed (POSIX: own session + killpg; Windows: taskkill /T /F).
    """
    resolved_cmd = _resolve_cmd(cmd)

    def _runit() -> tuple[int, str, str, float]:
        t0 = time.monotonic()
        popen_kwargs: dict = {}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                resolved_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cwd,
                shell=False,
                **popen_kwargs,
            )
        except FileNotFoundError as e:
            return 127, "", f"command not found: {e}", time.monotonic() - t0
        except Exception as e:
            return 1, "", f"launch error: {type(e).__name__}: {e}", time.monotonic() - t0
        try:
            out, err = proc.communicate(input=stdin_data.encode("utf-8"), timeout=timeout)
            return (
                proc.returncode,
                out.decode("utf-8", errors="replace"),
                err.decode("utf-8", errors="replace"),
                time.monotonic() - t0,
            )
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            return 124, "", "timeout (process tree killed)", time.monotonic() - t0
        except Exception as e:
            _kill_tree(proc)
            return 1, "", f"launch error: {type(e).__name__}: {e}", time.monotonic() - t0

    return await asyncio.to_thread(_runit)


def resolve_roster(cfg: dict, mode: str, names: list[str] | None, host: str,
                   allow_free: bool = False, allow_logging: bool = False,
                   explicit_custom_only: set[str] | None = None,
                   explicit: bool = False) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (final_roster, drop_reasons).

    explicit=True means the caller passed these exact names by hand
    (dispatch/benchmark --roster): disabled and custom_only gates are waived
    (explicit naming = intent) and host_rules `add` does not inject reviewers
    the caller never asked for. host_rules `skip` and the tier/privacy gates
    still apply — they guard external consequences, not reviewer health.
    """
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
    skipped_by_host = set(host_rules.get("skip", []))
    drops: list[tuple[str, str]] = []
    for n in base:
        if n in skipped_by_host:
            drops.append((n, f"host rule (running inside {host})"))
    base = [n for n in base if n not in skipped_by_host]
    if not explicit:
        for n in host_rules.get("add", []):
            if n not in base:
                base.append(n)

    final = []
    for n in base:
        spec = reviewers.get(n)
        if not spec:
            drops.append((n, "not in registry"))
            continue
        if spec.get("disabled") and not explicit:
            drops.append((n, "disabled in config"))
            continue
        if spec.get("tier") == "free" and not allow_free:
            drops.append((n, "free tier (use --allow-free)"))
            continue
        if spec.get("privacy") == "LOGS" and not allow_logging:
            drops.append((n, "logs prompts (use --allow-logging)"))
            continue
        if spec.get("custom_only") and not explicit and n not in explicit_custom_only:
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


VALID_ROUTE_PREFS = ("openrouter", "direct")


def _route_kind(route_cfg: dict | None) -> str | None:
    """Classify a single route config.

    'openrouter' — aichat via the openrouter client
    'direct'     — aichat via any other (provider-direct) client
    'cli'        — a CLI route (gemini/codex/claude/opencode/copilot)
    """
    if not route_cfg:
        return None
    if route_cfg.get("route") != "aichat":
        return "cli"
    return "openrouter" if route_cfg.get("client") == "openrouter" else "direct"


def resolve_route_preference(cli_value: str | None = None,
                             cfg: dict | None = None) -> str:
    """Resolve the active route preference.

    Precedence: explicit CLI value > ARGUS_ROUTE_PREF env > config default >
    'openrouter'. Unknown values fall back to 'openrouter'.
    """
    val = cli_value or os.environ.get("ARGUS_ROUTE_PREF")
    if not val:
        cfg = cfg or load_config()
        val = cfg.get("defaults", {}).get("route_preference", "openrouter")
    return val if val in VALID_ROUTE_PREFS else "openrouter"


def resolve_routes(spec: dict, preference: str = "openrouter") -> tuple[dict | None, dict | None]:
    """Order a reviewer's two routes into (primary, fallback) by preference.

    Reordering applies ONLY to reviewers whose two routes are exactly the
    {direct-API, OpenRouter} pair (glm-5.2, minimax-m3, deepseek-v4-pro).
    For those, `preference` ('openrouter' | 'direct') decides which is tried
    first; the other becomes the fallback. Every other reviewer — single-route
    reviewers and CLI reviewers that keep OpenRouter as a true fallback —
    retains its declared primary/fallback order untouched.
    """
    primary = spec.get("primary")
    fallback = spec.get("fallback")
    routes = [r for r in (primary, fallback) if r]
    if len(routes) < 2:
        return primary, fallback
    kinds = {_route_kind(r) for r in routes}
    if kinds == {"direct", "openrouter"}:
        pref = preference if preference in VALID_ROUTE_PREFS else "openrouter"
        # stable sort keeps declared order within a class; preferred kind first
        ordered = sorted(routes, key=lambda r: 0 if _route_kind(r) == pref else 1)
        return ordered[0], ordered[1]
    return primary, fallback


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
