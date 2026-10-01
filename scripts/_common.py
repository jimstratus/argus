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


def canonical_reviewer(cfg: dict, name: str) -> str:
    """Map a possibly-legacy reviewer name to its canonical registry key.

    Reviewer keys went version-free on 2026-09-22 (glm-5.2 -> glm, ...) so that
    bumping a model no longer invalidates saved profiles, --custom rosters, or
    history.db rows keyed by reviewer name. `aliases:` in config.yaml keeps the
    old names working.

    A name that is already a registry key always wins over the alias map, so a
    future reviewer may reuse a retired name without the alias hijacking it.
    Unknown names pass through untouched — callers (estimate_cost, resolve_roster)
    own the "not in registry" error so the message still names what the user typed.
    """
    if name in cfg.get("reviewers", {}):
        return name
    return cfg.get("aliases", {}).get(name, name)


def canonicalize_roster(cfg: dict, names: list[str]) -> list[str]:
    """canonical_reviewer() over a list, preserving order and dropping dupes.

    Deduping matters here: `--custom "glm-5.2,glm"` is two names that resolve to
    one reviewer, and dispatching it twice would double-count it in the
    corroboration boost (merge.py treats each review file as an independent
    voter, so a self-corroborating reviewer could push its own findings over the
    confidence threshold).
    """
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        c = canonical_reviewer(cfg, n)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


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
    # Defensive only: no current caller passes explicit_custom_only (dispatch
    # and benchmark both rely on explicit=True for the custom_only bypass).
    # Normalized anyway so the parameter behaves like every other roster input
    # if a caller ever does use it. No sort — the result is a set, and
    # canonicalize_roster already dedupes.
    explicit_custom_only = set(
        canonicalize_roster(cfg, list(explicit_custom_only or []))
    )
    reviewers = cfg["reviewers"]
    profiles = cfg["profiles"]
    host_rules = cfg.get("host_rules", {}).get(host, {"skip": [], "add": []})

    if mode == "profile":
        base = list(profiles[names[0]]["members"])  # type: ignore
    elif mode in ("custom", "models"):
        base = list(names or [])
    else:
        base = list(profiles[cfg["defaults"]["profile"]]["members"])

    # Resolve legacy version-named reviewers (glm-5.2 -> glm) before any gate
    # runs, so host_rules / disabled / custom_only all match on canonical keys.
    base = canonicalize_roster(cfg, base)

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

    Reordering applies to any reviewer whose two routes are exactly the
    {direct-API, OpenRouter} pair — currently glm, minimax, deepseek, and
    (custom-only) hermes. For those, `preference`
    ('openrouter' | 'direct') decides which is tried first; the other becomes
    the fallback. Every other reviewer — single-route reviewers and CLI
    reviewers that keep OpenRouter as a true fallback — retains its declared
    primary/fallback order untouched.
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


def primary_is_openrouter(spec: dict, preference: str = "openrouter") -> bool:
    """True when OpenRouter is the *resolved primary* route for this reviewer.

    Used by the cost/balance gates: under `direct` preference OpenRouter is only
    a fallback, so its balance is not on the critical path.
    """
    p, _ = resolve_routes(spec or {}, preference)
    return bool(p) and p.get("client") == "openrouter"


def price_tokens(
    input_tokens: int | float,
    output_tokens: int | float,
    rates: dict | None,
) -> float:
    """USD cost at $/M rates. ``rates is None`` / empty (CLI sub) → 0.0.

    Single arithmetic used by ``estimate_roster_cost``, ``bench_cost.py``, and
    any other cost path — do not re-implement the ``/ 1_000_000`` formula.
    """
    if not rates:
        return 0.0
    return (
        (input_tokens / 1_000_000) * float(rates["input"])
        + (output_tokens / 1_000_000) * float(rates["output"])
    )


def rates_for(cfg: dict, name: str, recorded: dict | None = None,
              fallback_calls: int = 0) -> tuple[str, dict | None, str]:
    """Resolve a recorded benchmark reviewer name to its billing rates.

    Returns (canonical_name, cost_per_m_or_None, status) where status is one of:

      'recorded'  rates came from the artifact — what the run was billed at
      'estimated' rates came from the CURRENT registry; the artifact predates
                  rate snapshotting, so this is today's price for an older run
      'mixed'     some calls were served by the FALLBACK route, whose price
                  config.yaml does not carry (it stores one rate per reviewer,
                  the primary's). Returned rates price the primary-served
                  calls only; the fallback calls cannot be priced at all
      'cli-sub'   no per-token price, and no fallback was used — genuinely $0
      'unknown'   not in this registry under any name AND no recorded rates —
                  cannot be priced at all. A reviewer merely deleted from
                  config.yaml still prices from its artifact's own rates

    Benchmark artifacts are historical: their `reviewer` fields hold whatever
    the registry called that reviewer at record time, so a pre-2026-09-22 run
    carries version-named keys like `glm-5.2`. Those are not registry keys any
    more, so a direct lookup misses, `cost_per_m` comes back None, and the row
    would be printed as a $0 paid-CLI subscription — silently understating what
    the run actually cost. Hence the alias resolution here.

    'cli-sub' and 'unknown' both cost $0 but mean opposite things: the first is
    a reviewer that genuinely has no per-token price, the second is a name this
    registry cannot price at all. Collapsing them is how a missing reviewer
    disappears into a total that looks complete.
    """
    canonical = canonical_reviewer(cfg, name)
    spec = cfg["reviewers"].get(canonical)

    # 'unknown' means unpriceable, which is only true when the registry has
    # never heard of this name AND the artifact carries no rates. A reviewer
    # deleted from config.yaml is still fully priceable from its own recorded
    # rates — discarding them on a registry miss would throw away the exact
    # number the snapshot exists to preserve.
    if spec is None and not recorded:
        return canonical, None, "unknown"

    # Rates recorded in the artifact win over the registry: they are what the
    # run was actually billed at. qwen-3.6-plus ran at $0.50/$2.00; today's
    # `qwen` is qwen3.8-max at $2.00/$6.00 — pricing the old run at the new
    # rate is wrong by 4x, in the opposite direction from the $0 it used to
    # report.
    rates = recorded or (spec.get("cost_per_m") if spec else None)

    # Fallback is checked BEFORE the rate source, because no rate in hand
    # describes a fallback call. config.yaml carries one price per reviewer —
    # the PRIMARY's — so a `kimi` run that fell back bills those calls at
    # kimi-k3's $3/$15 when kimi-k2.7-code served them at $0.71/$3.21.
    # Returning 'recorded' there would label a wrong number exact.
    #
    # `rates` still comes back non-None so the caller can price the calls the
    # primary DID serve; only the fallback calls are unpriceable.
    if fallback_calls:
        return canonical, rates, "mixed"

    if recorded:
        return canonical, recorded, "recorded"
    if rates:
        # 'estimated' is deliberately distinct from 'recorded': same
        # arithmetic, weaker claim. Artifacts written before rate snapshotting
        # cannot be costed exactly, and saying so is better than quietly
        # implying they can.
        return canonical, rates, "estimated"
    return canonical, None, "cli-sub"


def estimate_roster_cost(
    cfg: dict,
    roster: list[str],
    *,
    input_tokens_per_unit: int | list[int],
    output_tokens_per_call: int | None = None,
    calls_per_unit: int = 1,
) -> dict:
    """Estimate USD spend for a roster against one or more input-token units.

    Shared by ``estimate_cost.py`` (one shared diff) and ``benchmark.py``'s
    pre-flight gate (per-fixture token counts). Issue #22 slice 2 — the three
    hand-synced copies of the $/M formula lived in estimate_cost, the
    benchmark inline gate, and bench_cost; do not re-implement it.

    ``bench_cost.py`` prices *historical* artifacts (recorded rates, mixed
    fallback) via ``rates_for`` + ``price_tokens`` instead of this helper.

    Parameters
    ----------
    input_tokens_per_unit
        A single int (same prompt for every billed unit — estimate_cost) or a
        list of per-unit input-token estimates (one per fixture — benchmark).
        Each unit is billed ``calls_per_unit`` times.
    output_tokens_per_call
        Defaults to ``defaults.default_output_tokens_est``.
    calls_per_unit
        Multiplier per unit (``runs_per_fixture * fixtures`` collapsed into
        one unit for estimate_cost, or ``runs`` per fixture for benchmark).

    Rates come from the CURRENT registry via ``rates_for`` (so aliases
    resolve). Reviewers with ``cost_per_m: null`` are $0 with note
    ``"paid CLI sub"``. Names missing from the registry are $0 with note
    ``"unknown"`` — callers that treat unknowns as hard errors
    (``estimate_cost.py``) must reject them before calling.

    Returns
    -------
    dict::

        {
          "per_reviewer": [
            {"reviewer": str, "cost_usd": float, "calls": int,
             "per_call_usd": float | None,  # set when a single unit size
             "note": str | None},
            ...
          ],
          "total_usd": float,           # unrounded sum; callers round
          "output_tokens_per_call": int,
          "calls_per_unit": int,
          "n_units": int,
        }
    """
    d = cfg.get("defaults", {})
    out_tok = (
        int(output_tokens_per_call)
        if output_tokens_per_call is not None
        else int(d["default_output_tokens_est"])
    )
    if isinstance(input_tokens_per_unit, (list, tuple)):
        units = [int(u) for u in input_tokens_per_unit]
    else:
        units = [int(input_tokens_per_unit)]
    n_units = len(units)
    calls_per_unit = int(calls_per_unit)
    total_calls = n_units * calls_per_unit

    rows: list[dict] = []
    total = 0.0
    single_unit = n_units == 1

    for name in roster:
        _canonical, rates, status = rates_for(cfg, name)
        if status == "unknown":
            rows.append({
                "reviewer": name,
                "cost_usd": 0.0,
                "calls": total_calls,
                "per_call_usd": None,
                "note": "unknown",
            })
            continue
        if status == "cli-sub":
            rows.append({
                "reviewer": name,
                "cost_usd": 0.0,
                "calls": total_calls,
                "per_call_usd": None,
                "note": "paid CLI sub",
            })
            continue

        cost = 0.0
        per_call: float | None = None
        for u in units:
            pc = price_tokens(u, out_tok, rates)
            cost += pc * calls_per_unit
            if single_unit:
                per_call = pc
        total += cost
        row: dict = {
            "reviewer": name,
            "cost_usd": cost,
            "calls": total_calls,
            "per_call_usd": per_call,
            "note": None,
        }
        rows.append(row)

    return {
        "per_reviewer": rows,
        "total_usd": total,
        "output_tokens_per_call": out_tok,
        "calls_per_unit": calls_per_unit,
        "n_units": n_units,
    }


def score_run(
    *,
    tp: int = 0,
    fp: int = 0,
    fn: int = 0,
    exit_code: int = 0,
    parse_error: bool = False,
    error: Any = None,
) -> dict:
    """Compute tp/fp/fn + precision/recall/F1 for one benchmark run.

    Shared by ``benchmark.py`` (wall-cap stub + exit-code/parse-error branch)
    and ``aggregate_bench._rescore_run`` (issue #22 slice 4). The three
    hand-synced copies of failed-call zero-scoring lived there; do not
    re-implement the clean-baseline / failure gate.

    Rules
    -----
    - Failed calls (non-zero ``exit_code``, an ``error``, or ``parse_error``)
      are zero-scored (P=R=F1=0). ``tp==fp==fn==0`` there means "never ran",
      not "found nothing".
    - Successful call with ``tp==fp==fn==0`` → clean baseline P=R=F1=1.0.
    - Else standard ``P = tp/(tp+fp)``, ``R = tp/(tp+fn)``, ``F1 = 2PR/(P+R)``
      (with ``tp+fp==0 → P=0``, ``tp+fn==0 → R=1``).

    Returned counts are the inputs (coerced to int); only P/R/F1 are derived.
    Matching findings→tp/fp/fn stays in ``benchmark._score``.
    """
    tp_i = int(tp or 0)
    fp_i = int(fp or 0)
    fn_i = int(fn or 0)
    if int(exit_code or 0) != 0 or error or parse_error:
        return {
            "tp": tp_i, "fp": fp_i, "fn": fn_i,
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
        }
    if tp_i == 0 and fp_i == 0 and fn_i == 0:
        return {
            "tp": 0, "fp": 0, "fn": 0,
            "precision": 1.0, "recall": 1.0, "f1": 1.0,
        }
    if tp_i + fp_i == 0:
        prec = 0.0
    else:
        prec = tp_i / (tp_i + fp_i)
    if tp_i + fn_i == 0:
        rec = 1.0
    else:
        rec = tp_i / (tp_i + fn_i)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "tp": tp_i, "fp": fp_i, "fn": fn_i,
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
    }


async def dispatch_with_fallback(
    name: str,
    spec: dict,
    prompt: str,
    timeout: int,
    preference: str = "openrouter",
    *,
    get_adapter: Any = None,
) -> dict:
    """Try primary route; on non-zero exit try fallback. Shared by dispatch.py
    and benchmark.py (issue #22 slice 1).

    These two copies had already drifted twice — exception isolation landed
    only in dispatch, served-model / never-empty-error semantics only in
    benchmark — so every primary→fallback call must go through here.

    `get_adapter` defaults to `adapters.get` (lazy import to avoid a cycle:
    adapters → _common). Tests inject a fake.

    Return schema (superset of both former callers)::

        name, findings, latency_sec, primary_latency_sec, fallback_latency_sec,
        fallback_used, fallback_route, route, model, exit_code,
        primary_exit_code, primary_error, parse_error, error, raw_preview

    Contracts pinned by tests (past-drift regressions):
      - both routes fail → ``model is None`` (do NOT blame the fallback slug);
        ``route`` still names the last-tried (fallback) route — aggregate
        zero-scores by ``model is None``, not by ``route``
      - non-zero exit with empty stderr → ``error`` is still non-empty
      - successful fallback → ``route`` / ``model`` come from the fallback
      - unparseable but exit 0 → ``parse_error=True``, findings=[], exit_code 0
      - unknown route → ``exit_code=1`` (never silently default to 0 in history)
    """
    if get_adapter is None:
        import adapters as _adapters  # local: adapters imports _common
        get_adapter = _adapters.get

    primary_cfg, fallback_cfg = resolve_routes(spec, preference)
    primary_cfg = primary_cfg or {}
    primary_route = primary_cfg.get("route")

    empty = {
        "name": name,
        "findings": [],
        "latency_sec": 0.0,
        "primary_latency_sec": 0.0,
        "fallback_latency_sec": 0.0,
        "fallback_used": False,
        "fallback_route": None,
        "route": primary_route,
        "model": None,
        "exit_code": 1,
        "primary_exit_code": 1,
        "primary_error": "",
        "parse_error": False,
        "error": f"no adapter for {primary_route}",
        "raw_preview": None,
    }

    adapter = get_adapter(primary_route)
    if adapter is None:
        return empty

    r = await adapter.send(prompt, primary_cfg, timeout)
    primary_latency = float(r.get("latency_sec", 0.0) or 0.0)
    primary_exit = int(r.get("exit_code", 0) or 0)
    primary_err = ""
    fallback_latency = 0.0
    fallback_used = False
    fallback_route = None
    # Track which route_cfg produced the final `r` we score/parse.
    served_cfg: dict | None = primary_cfg
    route_label = r.get("route") or primary_route

    if primary_exit != 0:
        primary_err = ((r.get("stderr") or "")[:200])
        if fallback_cfg:
            fb_adapter = get_adapter(fallback_cfg.get("route"))
            if fb_adapter is not None:
                r2 = await fb_adapter.send(prompt, fallback_cfg, timeout)
                fallback_latency = float(r2.get("latency_sec", 0.0) or 0.0)
                fallback_used = True
                fallback_route = r2.get("route") or fallback_cfg.get("route")
                r = r2
                route_label = fallback_route
                # served_cfg only "counts" if this attempt actually succeeded;
                # set provisionally — final model uses exit_code below.
                served_cfg = fallback_cfg

    final_exit = int(r.get("exit_code", 0) or 0)
    findings: list = []
    parse_error = False
    raw_preview = None

    if final_exit == 0:
        parsed = extract_json(r.get("stdout") or "")
        # Require the schema's findings list — extract_json can recover an
        # arbitrary inner object from prose, which is still a failed review.
        if isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
            findings = normalize_findings(parsed["findings"])
        else:
            parse_error = True
            raw_preview = (r.get("stdout") or "")[:2000]

    # Model that served THIS call. Derived from final exit_code, not from
    # which route was tried last: when primary and fallback both fail, no
    # model served the call — recording the fallback slug would attribute a
    # zero score to a model that returned nothing. A parse_error is different:
    # the model did produce output; that belongs on its record.
    if final_exit == 0:
        model = (served_cfg or {}).get("model")
    else:
        model = None
        served_cfg = None  # nothing served

    # Never an empty string for a failure. stats.py distinguishes "this run
    # errored" from "legacy row predates model recording" by non-emptiness.
    if final_exit != 0:
        err = ((r.get("stderr") or "").strip()[:800]
               or f"exit {final_exit} with no stderr")
    else:
        err = None

    return {
        "name": name,
        "findings": findings,
        "latency_sec": round(primary_latency + fallback_latency, 2),
        "primary_latency_sec": round(primary_latency, 2),
        "fallback_latency_sec": round(fallback_latency, 2),
        "fallback_used": fallback_used,
        "fallback_route": fallback_route,
        "route": route_label,
        "model": model,
        "exit_code": final_exit,
        "primary_exit_code": primary_exit,
        "primary_error": primary_err,
        "parse_error": parse_error,
        "error": err,
        "raw_preview": raw_preview,
    }


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
    -- Load-bearing, not diagnostic: stats.py reads emptiness as "this run
    -- succeeded", so a failed run must NEVER store '' (benchmark.py falls
    -- back to "exit <code> with no stderr" when a route dies silently).
    error TEXT,
    -- The model slug this row actually measured -- the route that SERVED it,
    -- which is not necessarily the reviewer's declared primary. A reviewer
    -- KEY is stable across a model bump (gemini-or stayed gemini-or while its
    -- slug moved 2.5-flash -> 3.8-flash), so the name alone cannot tell you
    -- whether a score describes the model the reviewer runs today.
    --
    -- NULL means THREE different things; a consumer that assumes the first
    -- will misreport, which is the exact mistake stats.py now works around:
    --   1. the row predates this column        -> unrecorded, NOT "same"
    --   2. no route served it                  -> wall-cap, crash, both
    --      routes down, or no adapter. `error` is non-empty for these.
    --   3. a route with no `model` field succeeded -> there is no slug to
    --      record, so NULL is simply accurate and current.
    --
    -- (3) is a property of the ROUTE, not of the reviewer, and not of "being
    -- a CLI" either. opencode, opencode-minimax and opencode-glm all use
    -- `opencode-cli` and only the first is model-less; copilot-cli takes
    -- --model too. codex and gemini pair a model-less CLI primary with a
    -- modelled OpenRouter fallback, so the same reviewer writes NULL when the
    -- CLI served and a slug when the fallback did. Only claude and opencode
    -- are model-less on every route today; that is a fact about the current
    -- registry, not a rule. The only reliable test is whether the route dict
    -- has `model`.
    --
    -- Distinguishing 1 from 2 needs `error`; 1 from 3 needs the registry --
    -- specifically whether ANY of the reviewer's routes is model-less.
    -- An explicit run-status column would end this -- see the PR follow-ups.
    model TEXT,
    PRIMARY KEY (ts, reviewer, fixture, run_idx)
);
"""


# Columns added after the initial schema. CREATE TABLE IF NOT EXISTS is a
# no-op on an existing database, so a new column needs an explicit ALTER.
_MIGRATIONS = (
    ("benchmarks", "model", "ALTER TABLE benchmarks ADD COLUMN model TEXT"),
)


def history_conn() -> sqlite3.Connection:
    # The documented benchmark protocol runs one shell per reviewer, so several
    # processes open this database at once. `timeout` makes a contended write
    # wait for the lock instead of raising "database is locked" immediately.
    conn = sqlite3.connect(HISTORY_DB, timeout=30)
    conn.executescript(HISTORY_SCHEMA)
    _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add post-initial-schema columns, tolerating a concurrent migrator.

    Check-then-ALTER races when parallel shells first open an existing
    database: both can observe the column missing, one ALTERs, and the other
    would raise `duplicate column name: <col>` and take down that process's
    history write. The loser of that race has nothing left to do — the column
    it wanted now exists — so the duplicate-column error is swallowed rather
    than serialized against. Any other OperationalError is a real schema
    problem and still propagates.
    """
    for table, column, ddl in _MIGRATIONS:
        try:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)
                conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
            conn.rollback()
