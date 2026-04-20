#!/usr/bin/env python3
"""Route-reachability check. Pings each configured reviewer with a tiny prompt.

Usage:
  verify.py [--all | --profile NAME | --roster NAMES]

Emits a table; exit code 1 if any reviewer fails.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config, extract_json
import adapters


PING = 'You are a health check. Respond with ONLY this JSON and nothing else: {"ok": true}'


async def _try_route(route_cfg: dict, timeout: int) -> tuple[bool, str, dict]:
    route = route_cfg.get("route")
    adapter = adapters.get(route)
    if adapter is None:
        return False, f"no adapter for {route}", {"latency_sec": 0.0, "stdout": ""}
    r = await adapter.send(PING, route_cfg, timeout)
    if r["exit_code"] != 0:
        msg = (r.get("stderr") or "")[:140].strip() or f"rc={r['exit_code']}"
        return False, msg, r
    parsed = extract_json(r["stdout"])
    if isinstance(parsed, dict) and parsed.get("ok"):
        return True, "", r
    return False, "no JSON in response", r


async def _ping(name: str, spec: dict, timeout: int) -> dict:
    primary = spec.get("primary") or {}
    ok, note, r = await _try_route(primary, timeout)
    total_latency = r.get("latency_sec", 0.0)
    route_used = primary.get("route")
    fallback_used = False

    if not ok:
        fb = spec.get("fallback")
        if fb:
            ok2, note2, r2 = await _try_route(fb, timeout)
            total_latency += r2.get("latency_sec", 0.0)
            if ok2:
                ok = True
                note = f"primary failed ({note[:40]}); fallback ok"
                route_used = f"{primary.get('route')}->fb:{fb.get('route')}"
                fallback_used = True
            else:
                note = f"primary: {note[:50]} | fallback: {note2[:50]}"

    return {
        "reviewer": name,
        "route": route_used,
        "ok": ok,
        "latency_sec": round(total_latency, 2),
        "note": note,
        "fallback_used": fallback_used,
        "stdout_preview": r["stdout"][:120].replace("\n", " ").strip(),
    }


async def _main_async(args) -> int:
    cfg = load_config()
    reviewers = cfg["reviewers"]
    if args.all:
        roster = [n for n, spec in reviewers.items() if not spec.get("disabled")]
    elif args.profile:
        roster = cfg["profiles"][args.profile]["members"]
    elif args.roster:
        roster = [r.strip() for r in args.roster.split(",")]
    else:
        roster = cfg["profiles"]["standard"]["members"]

    timeout = 45
    results = await asyncio.gather(*[_ping(n, reviewers[n], timeout) for n in roster if n in reviewers])

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'STATUS':<6} {'LAT(s)':>7}  {'REVIEWER':<16} {'ROUTE':<14} NOTE")
        for r in results:
            status = "OK" if r["ok"] else "FAIL"
            note = r["note"] or r["stdout_preview"][:60]
            print(f"{status:<6} {r['latency_sec']:>7.2f}  {r['reviewer']:<16} {r['route']:<14} {note}")
    return 1 if any(not r["ok"] for r in results) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--profile")
    ap.add_argument("--roster")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
