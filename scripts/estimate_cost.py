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
    args = ap.parse_args()

    cfg = load_config()
    d = cfg["defaults"]
    expected_out = args.expected_output_tokens or int(d["default_output_tokens_est"])
    prompt_overhead = int(d["prompt_overhead_tokens"])

    diff_text = Path(args.diff).read_text(encoding="utf-8", errors="replace")
    in_tokens = estimate_tokens(diff_text) + prompt_overhead
    roster = [r.strip() for r in args.roster.split(",") if r.strip()]

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

    if total >= block:
        sys.stderr.write(f"\nBLOCK: estimated ${total:.2f} exceeds hard cap ${block:.2f}. Pass --yes-cost to override.\n")
        return 2
    if total >= warn:
        sys.stderr.write(f"\nWARN: estimated ${total:.2f} exceeds soft threshold ${warn:.2f}.\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
