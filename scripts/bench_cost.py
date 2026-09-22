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
from _common import load_config, estimate_tokens, canonical_reviewer, ARGUS_HOME


def rates_for(cfg: dict, name: str, recorded: dict | None = None) -> tuple[str, dict | None, str]:
    """Resolve a recorded benchmark reviewer name to its billing rates.

    Returns (canonical_name, cost_per_m_or_None, status) where status is one of
    'metered' | 'cli-sub' | 'unknown'.

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

    # Rates recorded in the artifact win: they are what the run was actually
    # billed at. Anything else is the CURRENT registry's price for a run that
    # happened under a different one, which is a different number wearing the
    # same label. qwen-3.6-plus ran at $0.50/$2.00; today's `qwen` is
    # qwen3.8-max at $2.00/$6.00 — pricing the old run at the new rate is
    # wrong by 4x, in the opposite direction from the $0 it used to report.
    if recorded:
        return canonical, recorded, "recorded"

    spec = cfg["reviewers"].get(canonical)
    if spec is None:
        return canonical, None, "unknown"
    rates = spec.get("cost_per_m")
    # 'estimated' is deliberately distinct from 'recorded': same arithmetic,
    # weaker claim. Artifacts written before rate snapshotting cannot be
    # costed exactly, and saying so is better than quietly implying they can.
    return canonical, rates, "estimated" if rates else "cli-sub"


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
        # Keep the recorded name for display — this is a historical artifact —
        # but price it through the canonical key.
        canonical, rates, status = rates_for(cfg, name, data.get("rates"))
        label = name if canonical == name else f"{name}\u2192{canonical}"
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
                "reviewer": label,
                "calls": total_calls,
                "in_tokens": est_input,
                "out_tokens": est_output,
                "cost_usd": round(cost, 4),
                "rate": (f"${rates['input']}/${rates['output']}"
                         + ("" if status == "recorded" else "  (current rate)")),
                "estimated": status == "estimated",
            })
            total += cost
        else:
            rows.append({
                "reviewer": label,
                "calls": total_calls,
                "cost_usd": 0.0,
                "note": ("paid CLI sub (no per-token cost)" if status == "cli-sub"
                         else "UNKNOWN reviewer - NOT priced"),
                "unpriced": status == "unknown",
            })

    rows.sort(key=lambda r: -r.get("cost_usd", 0))

    # Size the text columns from the data instead of a fixed width. A row label
    # can be `recorded->canonical` (e.g. opencode-minimax-m3->opencode-minimax,
    # 36 chars), which blew past the old hard-coded 18 and shoved every later
    # column right by however much it overflowed. Deriving the width means a
    # future alias chain of any length still lines up, and the notes stop being
    # truncated mid-word ("paid CLI sub (").
    # 18 / 15 are the original fixed widths, kept as floors so the common
    # all-canonical table looks exactly as it did before.
    name_w = max(18, *(len(r["reviewer"]) for r in rows)) if rows else 18
    note_w = max(15, *(len(r.get("note") or r.get("rate") or "") for r in rows)) if rows else 15
    ruler = name_w + note_w + 5 + 8 + 8 + 10 + 5  # +5 for the single spaces between columns

    print(f"{'REVIEWER':<{name_w}} {'CALLS':>5} {'IN tok':>8} {'OUT tok':>8} "
          f"{'RATE in/out':<{note_w}} {'COST USD':>10}")
    print("-" * ruler)
    for r in rows:
        calls = r["calls"]
        cost = r["cost_usd"]
        note = r.get("note", "")
        rate = r.get("rate", "")
        intok = r.get("in_tokens", 0)
        outtok = r.get("out_tokens", 0)
        if note:
            print(f"{r['reviewer']:<{name_w}} {calls:>5} {'-':>8} {'-':>8} "
                  f"{note:<{note_w}} {cost:>10.4f}")
        else:
            print(f"{r['reviewer']:<{name_w}} {calls:>5} {intok:>8} {outtok:>8} "
                  f"{rate:<{note_w}} {cost:>10.4f}")
    print("-" * ruler)
    print(f"{'TOTAL':<{name_w}} {'':>5} {'':>8} {'':>8} {'':<{note_w}} {total:>10.4f}")

    estimated = [r["reviewer"] for r in rows if r.get("estimated")]
    if estimated:
        # Say plainly that these rows are priced at today's rates rather than
        # the ones the run was billed at. The arithmetic is identical; the
        # claim is not, and a total that silently mixes the two invites being
        # quoted as fact.
        sys.stderr.write(
            "NOTE: no rates recorded in the artifact for: "
            f"{', '.join(estimated)}\n"
            "      Priced at CURRENT registry rates, which may differ from "
            "what the run was billed at\n"
            "      (model pins and prices drift). Treat those rows as "
            "estimates, not actuals.\n"
        )

    unpriced = [r["reviewer"] for r in rows if r.get("unpriced")]
    if unpriced:
        # Never let an unpriceable reviewer vanish into a total that reads as
        # complete: say so, and fail, rather than under-reporting in silence.
        sys.stderr.write(
            "WARNING: not in registry, excluded from the total: "
            f"{', '.join(unpriced)}\n"
            "The TOTAL above is therefore a LOWER BOUND, not the run cost.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
