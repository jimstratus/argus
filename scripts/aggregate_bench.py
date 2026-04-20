#!/usr/bin/env python3
"""Aggregate per-reviewer benchmark JSONs (produced by parallel-shell runs)
into a single leaderboard markdown + combined JSON.

Usage:
  aggregate_bench.py --ts TS [--fixtures "a,b,c"] [--runs N]

Reads benchmarks/<TS>/per_reviewer/*.json (one per reviewer) and writes
benchmarks/<TS>.md + benchmarks/<TS>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ARGUS_HOME


BENCHMARKS_DIR = ARGUS_HOME / "benchmarks"


def _rescore_run(run: dict) -> dict:
    """Recompute P/R/F1 from tp/fp/fn with the clean-baseline rule (repairs pre-fix data).

    Clean-baseline rule: tp==fp==fn==0 → P=R=F1=1.0 (reviewer correctly found nothing).
    """
    tp = int(run.get("tp", 0) or 0)
    fp = int(run.get("fp", 0) or 0)
    fn = int(run.get("fn", 0) or 0)
    if tp == 0 and fp == 0 and fn == 0:
        run["precision"], run["recall"], run["f1"] = 1.0, 1.0, 1.0
        return run
    if tp + fp == 0:
        prec = 0.0
    else:
        prec = tp / (tp + fp)
    if tp + fn == 0:
        rec = 1.0
    else:
        rec = tp / (tp + fn)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    run["precision"] = round(prec, 3)
    run["recall"] = round(rec, 3)
    run["f1"] = round(f1, 3)
    return run


def _rebuild_fixture_avg(fr: dict) -> dict:
    runs = fr.get("runs", [])
    n = len(runs) or 1
    fr["avg"] = {
        "precision":    round(sum(r["precision"] for r in runs) / n, 3),
        "recall":       round(sum(r["recall"]    for r in runs) / n, 3),
        "f1":           round(sum(r["f1"]        for r in runs) / n, 3),
        "avg_findings": round(sum(r.get("n_findings", 0) for r in runs) / n, 1),
        "avg_latency":  round(sum(r.get("latency_sec", 0) for r in runs) / n, 2),
    }
    return fr


def _collect(ts: str) -> list[dict]:
    per_dir = BENCHMARKS_DIR / ts / "per_reviewer"
    if not per_dir.exists():
        sys.stderr.write(f"no per_reviewer/ dir at {per_dir}\n")
        return []
    results = []
    for p in sorted(per_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # Re-score every run from tp/fp/fn (fixes pre-fix clean-baseline bug)
            for fr in data.get("fixtures", []):
                for run in fr.get("runs", []):
                    _rescore_run(run)
                _rebuild_fixture_avg(fr)
            # Rebuild overall from fixture avgs
            fixtures = data.get("fixtures", [])
            nf = len(fixtures) or 1
            data["overall"] = {
                "precision": round(sum(fr["avg"]["precision"] for fr in fixtures) / nf, 3),
                "recall":    round(sum(fr["avg"]["recall"]    for fr in fixtures) / nf, 3),
                "f1":        round(sum(fr["avg"]["f1"]        for fr in fixtures) / nf, 3),
                "avg_latency": round(sum(fr["avg"]["avg_latency"] for fr in fixtures) / nf, 2),
            }
            # Total wall time (sum of all call latencies — not parallel time)
            data["total_call_latency_sec"] = round(
                sum(r.get("latency_sec", 0) for fr in fixtures for r in fr.get("runs", [])), 2
            )
            results.append(data)
        except Exception as e:
            sys.stderr.write(f"skip {p.name}: {e}\n")
    return results


def _leaderboard_md(ts: str, results: list[dict]) -> str:
    ranked = sorted(results, key=lambda r: -r.get("overall", {}).get("f1", 0.0))
    lines = [f"# Argus Benchmark — `{ts}` (parallel-shell aggregate)", ""]
    lines.append(f"**Reviewers collected:** {len(ranked)}")
    lines.append("")
    lines.append("## Leaderboard (by F1)")
    lines.append("")
    lines.append("| Rank | Reviewer | F1 | Precision | Recall | Avg call (s) | Total calls (s) | Status |")
    lines.append("|------|----------|----|-----------|--------|--------------|-----------------|--------|")
    for i, r in enumerate(ranked, 1):
        o = r.get("overall", {})
        name = r.get("reviewer", "?")
        status = "fatal" if r.get("fatal_error") else ("partial" if not r.get("fixtures") else "ok")
        tot = r.get("total_call_latency_sec", 0.0)
        lines.append(f"| {i} | `{name}` | {o.get('f1', 0):.3f} | {o.get('precision', 0):.3f} | "
                     f"{o.get('recall', 0):.3f} | {o.get('avg_latency', 0):.2f} | {tot:.1f} | {status} |")
    lines.append("")
    lines.append("## Per-fixture detail")
    lines.append("")
    for r in ranked:
        name = r.get("reviewer", "?")
        o = r.get("overall", {})
        fixtures = r.get("fixtures", [])
        lines.append(f"### `{name}` — overall F1 = {o.get('f1', 0):.3f}")
        if r.get("fatal_error"):
            lines.append(f"_Fatal: {r['fatal_error']}_")
            lines.append("")
            continue
        if not fixtures:
            lines.append("_No data._")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |")
        lines.append("|---------|-----------|--------|----|--------------|-----------------|")
        for fr in fixtures:
            a = fr.get("avg", {})
            lines.append(f"| {fr.get('fixture', '?')} | {a.get('precision', 0):.3f} | "
                         f"{a.get('recall', 0):.3f} | {a.get('f1', 0):.3f} | "
                         f"{a.get('avg_findings', 0):.1f} | {a.get('avg_latency', 0):.2f} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", required=True, help="shared benchmark timestamp (dir name under benchmarks/)")
    args = ap.parse_args()

    results = _collect(args.ts)
    if not results:
        return 1

    md = _leaderboard_md(args.ts, results)
    md_out = BENCHMARKS_DIR / f"{args.ts}.md"
    json_out = BENCHMARKS_DIR / f"{args.ts}.json"
    md_out.write_text(md, encoding="utf-8")
    json_out.write_text(json.dumps({"ts": args.ts, "results": results}, indent=2), encoding="utf-8")

    print(f"Leaderboard: {md_out}")
    print(f"Full JSON:   {json_out}")
    print(f"\nReviewers collected: {len(results)}")
    for r in sorted(results, key=lambda x: -x.get('overall', {}).get('f1', 0)):
        o = r.get("overall", {})
        print(f"  {r.get('reviewer', '?'):<16} F1={o.get('f1', 0):.3f}  P={o.get('precision', 0):.3f}  R={o.get('recall', 0):.3f}  {o.get('avg_latency', 0):>6.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
