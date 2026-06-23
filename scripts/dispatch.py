#!/usr/bin/env python3
"""Dispatch a diff to multiple reviewers in parallel.

Usage:
  dispatch.py --run-dir DIR --roster NAMES --diff PATH [--overlay NAME]

Writes:
  <run-dir>/reviews/<reviewer>.json  (one per reviewer)
  <run-dir>/dispatch_summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    load_config, build_prompt, estimate_tokens, extract_json,
    normalize_findings, resolve_roster, resolve_routes, resolve_route_preference,
)
from detect_host import detect as detect_host
import adapters


async def _dispatch_one(name: str, spec: dict, prompt: str, timeout: int,
                        preference: str = "openrouter") -> dict:
    """Try primary; if primary fails, try fallback. Return structured result.

    Route order is resolved from the reviewer's declared routes by
    `preference` (openrouter|direct) — see _common.resolve_routes.
    """
    result: dict = {"name": name, "findings": []}

    primary_cfg, fallback_cfg = resolve_routes(spec, preference)
    primary_cfg = primary_cfg or {}
    primary_route = primary_cfg.get("route")
    adapter = adapters.get(primary_route)

    if adapter is None:
        result["error"] = f"unknown route: {primary_route}"
        return result

    r = await adapter.send(prompt, primary_cfg, timeout)
    primary_latency = r.get("latency_sec", 0.0)
    primary_exit = r.get("exit_code", 0)
    primary_err = ""
    result["route"] = r["route"]
    result["exit_code"] = primary_exit
    result["primary_exit_code"] = primary_exit
    result["primary_latency_sec"] = round(primary_latency, 2)
    result["fallback_latency_sec"] = 0.0
    result["latency_sec"] = round(primary_latency, 2)
    result["fallback_used"] = False

    stdout = r["stdout"]
    stderr = r["stderr"]

    if r["exit_code"] != 0:
        primary_err = (stderr or "")[:200]
        result["primary_error"] = primary_err
        # Try fallback
        fb_cfg = fallback_cfg
        if fb_cfg:
            fb_route = fb_cfg.get("route")
            fb_adapter = adapters.get(fb_route)
            if fb_adapter is not None:
                r2 = await fb_adapter.send(prompt, fb_cfg, timeout)
                fallback_latency = r2.get("latency_sec", 0.0)
                result["fallback_used"] = True
                result["fallback_route"] = r2["route"]
                result["exit_code"] = r2["exit_code"]
                result["fallback_latency_sec"] = round(fallback_latency, 2)
                result["latency_sec"] = round(primary_latency + fallback_latency, 2)
                stdout, stderr = r2["stdout"], r2["stderr"]

    if result["exit_code"] != 0:
        result["error"] = (stderr or "")[:800].strip() or "non-zero exit"
        return result

    parsed = extract_json(stdout)
    # Require the schema's findings list — extract_json can recover an
    # arbitrary inner object from prose, which is still a failed review.
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        result["parse_error"] = True
        result["raw_preview"] = stdout[:2000]
        return result

    result["findings"] = normalize_findings(parsed["findings"])
    return result


async def _main_async(args) -> int:
    cfg = load_config()
    defaults = cfg["defaults"]
    timeout = int(args.timeout or defaults["reviewer_timeout_sec"])
    max_parallel = int(defaults["max_parallel"])
    ctx_safety = float(defaults["ctx_safety_ratio"])
    preference = resolve_route_preference(args.route_pref, cfg)

    names = [r.strip() for r in args.roster.split(",") if r.strip()]
    host, _ = detect_host()
    # --roster names are explicit: disabled/custom_only are waived and
    # host_rules `add` is not applied; host `skip` and tier/privacy still hold.
    roster, drops = resolve_roster(
        cfg, "custom", names, host,
        allow_free=bool(args.allow_free or defaults.get("allow_free")),
        allow_logging=bool(args.allow_logging or defaults.get("allow_logging")),
        explicit=True,
    )
    for n, reason in drops:
        sys.stderr.write(f"roster: dropped {n} — {reason}\n")
    if not roster:
        sys.stderr.write("roster: empty after policy filtering\n")
        return 1
    diff = Path(args.diff).read_text(encoding="utf-8", errors="replace")
    prompt = build_prompt(diff, overlay=args.overlay)

    run_dir = Path(args.run_dir)
    reviews_dir = run_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    prompt_tokens = estimate_tokens(prompt)

    sem = asyncio.Semaphore(max_parallel)

    async def _bounded(name: str) -> dict:
        async with sem:
            # resolve_roster guarantees roster ⊆ registry
            spec = cfg["reviewers"][name]

            # Context-window pre-check
            ctx = int(spec.get("ctx", 0) or 0)
            if ctx and prompt_tokens > ctx * ctx_safety:
                r = {
                    "name": name,
                    "skipped": True,
                    "skip_reason": f"prompt ~{prompt_tokens} tokens exceeds {int(ctx*ctx_safety)} ({int(ctx_safety*100)}% of {ctx} ctx)",
                    "findings": [],
                }
                (reviews_dir / f"{name}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
                return r

            try:
                r = await _dispatch_one(name, spec, prompt, timeout, preference)
            except Exception as e:
                r = {"name": name, "findings": [], "exit_code": 1,
                     "error": f"{type(e).__name__}: {e}"}
            (reviews_dir / f"{name}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
            return r

    gathered = await asyncio.gather(*[_bounded(n) for n in roster], return_exceptions=True)
    results = []
    for n, r in zip(roster, gathered):
        if isinstance(r, BaseException):
            r = {"name": n, "findings": [], "exit_code": 1,
                 "error": f"{type(r).__name__}: {r}"}
            # Keep the contract that every roster entry produces a
            # reviews/<name>.json — merge.py only reads those files.
            try:
                (reviews_dir / f"{n}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
            except Exception:
                pass
        results.append(r)

    summary = {
        "roster": roster,
        "dropped": {n: reason for n, reason in drops},
        "route_preference": preference,
        "prompt_tokens_est": prompt_tokens,
        "reviewers": {
            r["name"]: {
                "findings": len(r.get("findings", [])),
                "latency_sec": r.get("latency_sec"),
                "skipped": r.get("skipped", False),
                "skip_reason": r.get("skip_reason"),
                "error": r.get("error"),
                "parse_error": r.get("parse_error", False),
                "fallback_used": r.get("fallback_used", False),
                "exit_code": r.get("exit_code"),
                "route": r.get("route"),
            }
            for r in results
        },
    }
    (run_dir / "dispatch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--roster", required=True, help="comma-separated reviewer names")
    ap.add_argument("--diff", required=True)
    ap.add_argument("--overlay", default=None, help="prompt overlay name (security|deep|...)")
    ap.add_argument("--timeout", type=int, default=None, help="override reviewer_timeout_sec for this run")
    ap.add_argument("--allow-free", action="store_true", help="include free-tier reviewers")
    ap.add_argument("--allow-logging", action="store_true", help="include reviewers with privacy: LOGS")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--route-pref", choices=["openrouter", "direct"], default=None,
                     dest="route_pref",
                     help="route preference for dual-route reviewers (overrides config/env)")
    grp.add_argument("--prefer-direct", action="store_const", const="direct", dest="route_pref",
                     help="shorthand for --route-pref direct")
    grp.add_argument("--prefer-openrouter", action="store_const", const="openrouter", dest="route_pref",
                     help="shorthand for --route-pref openrouter")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
