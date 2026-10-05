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
from _common import ARGUS_HOME, render_leaderboard_md, score_run


BENCHMARKS_DIR = ARGUS_HOME / "benchmarks"


def _rescore_run(run: dict) -> dict:
    """Recompute P/R/F1 from tp/fp/fn with the clean-baseline rule (repairs pre-fix data).

    Thin wrapper around ``_common.score_run`` (issue #22 slice 4) so the
    failed-call zero-scoring gate cannot drift from benchmark.py.
    """
    scored = score_run(
        tp=run.get("tp", 0),
        fp=run.get("fp", 0),
        fn=run.get("fn", 0),
        exit_code=run.get("exit_code", 0),
        parse_error=bool(run.get("parse_error")),
        error=run.get("error"),
    )
    run["precision"] = scored["precision"]
    run["recall"] = scored["recall"]
    run["f1"] = scored["f1"]
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


def _status(r: dict) -> str:
    return "fatal" if r.get("fatal_error") else ("partial" if not r.get("fixtures") else "ok")


def _detail_notice(r: dict) -> str | None:
    if r.get("fatal_error"):
        return f"_Fatal: {r['fatal_error']}_"
    if not r.get("fixtures", []):
        return "_No data._"
    return None


def _leaderboard_md(ts: str, results: list[dict]) -> str:
    """Thin wrapper around ``_common.render_leaderboard_md`` (issue #22 slice 5)."""
    def ov(r: dict, key: str) -> float:
        return r.get("overall", {}).get(key, 0)

    def av(fr: dict, key: str) -> float:
        return fr.get("avg", {}).get(key, 0)

    lines = render_leaderboard_md(
        title=f"# Argus Benchmark — `{ts}` (parallel-shell aggregate)",
        summary_lines=[f"**Reviewers collected:** {len(results)}"],
        results=results,
        leaderboard_columns=[
            ("Rank",            lambda i, r: i),
            ("Reviewer",        lambda i, r: f"`{r.get('reviewer', '?')}`"),
            ("F1",              lambda i, r: f"{ov(r, 'f1'):.3f}"),
            ("Precision",       lambda i, r: f"{ov(r, 'precision'):.3f}"),
            ("Recall",          lambda i, r: f"{ov(r, 'recall'):.3f}"),
            ("Avg call (s)",    lambda i, r: f"{ov(r, 'avg_latency'):.2f}"),
            ("Total calls (s)", lambda i, r: f"{r.get('total_call_latency_sec', 0.0):.1f}"),
            ("Status",          lambda i, r: _status(r)),
        ],
        fixture_columns=[
            ("Fixture",         lambda fr: fr.get("fixture", "?")),
            ("Precision",       lambda fr: f"{av(fr, 'precision'):.3f}"),
            ("Recall",          lambda fr: f"{av(fr, 'recall'):.3f}"),
            ("F1",              lambda fr: f"{av(fr, 'f1'):.3f}"),
            ("Avg findings",    lambda fr: f"{av(fr, 'avg_findings'):.1f}"),
            ("Avg latency (s)", lambda fr: f"{av(fr, 'avg_latency'):.2f}"),
        ],
        detail_heading=lambda r: f"### `{r.get('reviewer', '?')}` — overall F1 = {ov(r, 'f1'):.3f}",
        detail_notice=_detail_notice,
    )
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
