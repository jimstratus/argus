#!/usr/bin/env python3
"""Pre-flight cost estimate for a roster + diff.

Usage:
  estimate_cost.py --roster NAMES --diff PATH [--mode review|benchmark]
                   [--expected-output-tokens N] [--runs-per-fixture N]
                   [--fixtures N]

Exit codes: 0 ok, 1 warn (>= warn threshold), 2 block (>= block threshold).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config, estimate_tokens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--mode", choices=["review", "benchmark"], default="review")
    ap.add_argument("--expected-output-tokens", type=int, default=None)
    ap.add_argument("--runs-per-fixture", type=int, default=1)
    ap.add_argument("--fixtures", type=int, default=1)
    ap.add_argument("--skip-balance-check", action="store_true", help="skip the OpenRouter balance pre-flight")
    ap.add_argument("--yes-cost", action="store_true", help="downgrade a cost block to a warning (exit 1 instead of 2)")
    args = ap.parse_args()

    cfg = load_config()
    d = cfg["defaults"]
    expected_out = args.expected_output_tokens or int(d["default_output_tokens_est"])
    prompt_overhead = int(d["prompt_overhead_tokens"])

    diff_text = Path(args.diff).read_text(encoding="utf-8", errors="replace")
    in_tokens = estimate_tokens(diff_text) + prompt_overhead
    roster = [r.strip() for r in args.roster.split(",") if r.strip()]

    unknown = [n for n in roster if n not in cfg["reviewers"]]
    if unknown:
        sys.stderr.write(
            f"INVALID ROSTER (not a cost block — --yes-cost will not help): "
            f"unknown reviewer(s): {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(cfg['reviewers']))}\n"
        )
        return 2

    rows = []
    total = 0.0
    per_unit_multiplier = args.runs_per_fixture * args.fixtures
    for name in roster:
        spec = cfg["reviewers"].get(name, {})
        rates = spec.get("cost_per_m")
        if not rates:
            rows.append({"reviewer": name, "cost_usd": 0.0, "note": "paid CLI sub"})
            continue
        per_call = (in_tokens / 1_000_000) * rates["input"] + (expected_out / 1_000_000) * rates["output"]
        cost = per_call * per_unit_multiplier
        total += cost
        rows.append({
            "reviewer": name,
            "per_call_usd": round(per_call, 4),
            "calls": per_unit_multiplier,
            "cost_usd": round(cost, 4),
        })

    if args.mode == "benchmark":
        warn = float(d["benchmark_cost_warn_usd"])
        block = float(d["benchmark_cost_block_usd"])
    else:
        warn = float(d["review_cost_warn_usd"])
        block = float(d["review_cost_block_usd"])

    out = {
        "mode": args.mode,
        "input_tokens_est": in_tokens,
        "output_tokens_per_call_est": expected_out,
        "per_reviewer": rows,
        "total_estimated_usd": round(total, 4),
        "warn_threshold_usd": warn,
        "block_threshold_usd": block,
        "runs_per_fixture": args.runs_per_fixture,
        "fixtures": args.fixtures,
    }
    print(json.dumps(out, indent=2))

    rc = 0
    if total >= block:
        if args.yes_cost:
            sys.stderr.write(f"\nWARN: estimated ${total:.2f} exceeds hard cap ${block:.2f} — overridden with --yes-cost.\n")
            rc = 1
        else:
            sys.stderr.write(f"\nBLOCK: estimated ${total:.2f} exceeds hard cap ${block:.2f}. Pass --yes-cost to override.\n")
            return 2
    elif total >= warn:
        sys.stderr.write(f"\nWARN: estimated ${total:.2f} exceeds soft threshold ${warn:.2f}.\n")
        rc = 1

    # OR balance pre-flight for non-dry invocations
    if not args.skip_balance_check:
        uses_openrouter = any(
            (cfg["reviewers"].get(name, {}).get("primary", {}).get("client") == "openrouter")
            or (cfg["reviewers"].get(name, {}).get("fallback", {}).get("client") == "openrouter")
            for name in roster
        )
        if uses_openrouter and os.environ.get("OPENROUTER_API_KEY"):
            try:
                from or_balance import probe
                info = probe(os.environ["OPENROUTER_API_KEY"])
                available = info.get("available_usd")
                safety = float(d.get("or_balance_safety_factor", 2.0))
                if available is not None and available < total * safety:
                    sys.stderr.write(f"\nOR BALANCE WARN: available ${available:.4f} < {safety}× estimate ${total:.4f}. Top up before dispatching.\n")
                    rc = max(rc, 1)
            except Exception as e:
                sys.stderr.write(f"OR balance check failed (non-fatal): {e}\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
