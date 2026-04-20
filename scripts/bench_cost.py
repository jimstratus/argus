#!/usr/bin/env python3
"""Compute estimated cost of a benchmark run from per-reviewer JSON + config rates.

Usage:
  bench_cost.py --ts TS

Cost model (rough — we don't track exact tokens per call):
  input_tokens_per_call  ≈ prompt_overhead_tokens + avg_diff_tokens (fixture-weighted)
  output_tokens_per_call = 800 (config default_output_tokens_est)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config, estimate_tokens, ARGUS_HOME


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", required=True)
    args = ap.parse_args()

    cfg = load_config()
    d = cfg["defaults"]
    prompt_overhead = int(d["prompt_overhead_tokens"])
    out_tokens = int(d["default_output_tokens_est"])

    # Compute avg input tokens from the actual fixtures
    fixtures_dir = ARGUS_HOME / "fixtures"
    fixture_tokens = {}
    for fdir in fixtures_dir.iterdir():
        if fdir.is_dir():
            diff = fdir / "diff.patch"
            if diff.exists():
                fixture_tokens[fdir.name] = estimate_tokens(diff.read_text(encoding="utf-8", errors="replace")) + prompt_overhead

    per_dir = ARGUS_HOME / "benchmarks" / args.ts / "per_reviewer"
    rows = []
    total = 0.0
    for p in sorted(per_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        name = data.get("reviewer", p.stem)
        spec = cfg["reviewers"].get(name, {})
        rates = spec.get("cost_per_m")
        total_calls = 0
        est_input = 0
        est_output = 0
        for fr in data.get("fixtures", []):
            in_per = fixture_tokens.get(fr["fixture"], prompt_overhead + 400)
            calls = len(fr.get("runs", []))
            total_calls += calls
            est_input += calls * in_per
            est_output += calls * out_tokens
        if rates:
            cost = (est_input / 1_000_000) * rates["input"] + (est_output / 1_000_000) * rates["output"]
            rows.append({
                "reviewer": name,
                "calls": total_calls,
                "in_tokens": est_input,
                "out_tokens": est_output,
                "cost_usd": round(cost, 4),
                "rate": f"${rates['input']}/${rates['output']}",
            })
            total += cost
        else:
            rows.append({
                "reviewer": name,
                "calls": total_calls,
                "cost_usd": 0.0,
                "note": "paid CLI sub (no per-token cost)",
            })

    rows.sort(key=lambda r: -r.get("cost_usd", 0))
    print(f"{'REVIEWER':<18} {'CALLS':>5} {'IN tok':>8} {'OUT tok':>8} {'RATE in/out':<15} {'COST USD':>10}")
    print("-" * 75)
    for r in rows:
        calls = r["calls"]
        cost = r["cost_usd"]
        note = r.get("note", "")
        rate = r.get("rate", "")
        intok = r.get("in_tokens", 0)
        outtok = r.get("out_tokens", 0)
        if note:
            print(f"{r['reviewer']:<18} {calls:>5} {'-':>8} {'-':>8} {note[:14]:<15} {cost:>10.4f}")
        else:
            print(f"{r['reviewer']:<18} {calls:>5} {intok:>8} {outtok:>8} {rate:<15} {cost:>10.4f}")
    print("-" * 75)
    print(f"{'TOTAL':<18} {'':>5} {'':>8} {'':>8} {'':<15} {total:>10.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
