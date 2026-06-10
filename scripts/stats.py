#!/usr/bin/env python3
"""Print reviewer stats from history.db.

Usage:
  stats.py [--since ISO] [--format {table,json}]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import history_conn, HISTORY_DB


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="ISO timestamp (inclusive)")
    ap.add_argument("--format", choices=["table", "json"], default="table")
    args = ap.parse_args()

    if not HISTORY_DB.exists():
        print("history.db does not exist yet — run /argus first.")
        return 0

    conn = history_conn()
    cur = conn.cursor()

    where = ""
    params: list = []
    if args.since:
        # runs.ts is dashed ISO-8601 ('2026-06-10T12:00:00+00:00') while
        # benchmarks.ts is compact ('20260610T120000'); strip '-' and ':' from
        # both sides so the lexical compare is valid for either format.
        where = "WHERE REPLACE(REPLACE(ts, '-', ''), ':', '') >= ?"
        params = [args.since.replace("-", "").replace(":", "")]

    # Per-reviewer aggregates from reviewer_runs
    cur.execute(f"""
        SELECT rr.reviewer,
               COUNT(*) AS runs,
               AVG(rr.latency_sec) AS avg_latency,
               AVG(rr.n_findings) AS avg_findings,
               SUM(rr.fallback_used) AS fallback_uses,
               SUM(CASE WHEN rr.exit_code != 0 THEN 1 ELSE 0 END) AS errors
        FROM reviewer_runs rr
        JOIN runs r ON r.run_id = rr.run_id
        {where}
        GROUP BY rr.reviewer
        ORDER BY runs DESC
    """, params)
    agg = cur.fetchall()

    # Benchmark F1
    cur.execute(f"""
        SELECT reviewer, AVG(f1) AS avg_f1, AVG("precision") AS avg_prec, AVG(recall) AS avg_rec, COUNT(*) AS n
        FROM benchmarks
        {where}
        GROUP BY reviewer
    """, params)
    bench = {r[0]: {"f1": r[1], "prec": r[2], "rec": r[3], "n": r[4]} for r in cur.fetchall()}

    rows = []
    for reviewer, runs, avg_lat, avg_f, fb, errs in agg:
        b = bench.get(reviewer, {})
        rows.append({
            "reviewer": reviewer,
            "runs": runs,
            "avg_latency_sec": round(avg_lat or 0, 2),
            "avg_findings": round(avg_f or 0, 1),
            "fallback_uses": fb or 0,
            "errors": errs or 0,
            "bench_f1": round(b.get("f1") or 0, 3) if b else None,
            "bench_precision": round(b.get("prec") or 0, 3) if b else None,
            "bench_recall": round(b.get("rec") or 0, 3) if b else None,
            "bench_samples": b.get("n", 0) if b else 0,
        })

    if args.format == "json":
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'REVIEWER':<18} {'RUNS':>5} {'LAT(s)':>7} {'FIND':>5} {'FB':>3} {'ERR':>3}  {'F1':>5} {'PREC':>5} {'REC':>5} {'N':>3}")
        for r in rows:
            print(f"{r['reviewer']:<18} {r['runs']:>5} {r['avg_latency_sec']:>7.2f} {r['avg_findings']:>5.1f} {r['fallback_uses']:>3} {r['errors']:>3}  "
                  f"{(r['bench_f1'] if r['bench_f1'] is not None else 0):>5.3f} "
                  f"{(r['bench_precision'] if r['bench_precision'] is not None else 0):>5.3f} "
                  f"{(r['bench_recall'] if r['bench_recall'] is not None else 0):>5.3f} "
                  f"{r['bench_samples']:>3}")

    # Last 5 runs
    if args.format == "table":
        cur.execute("SELECT run_id, ts, roster FROM runs ORDER BY ts DESC LIMIT 5")
        print("\nRecent runs:")
        for rid, ts, roster in cur.fetchall():
            print(f"  {ts}  {rid}  [{roster[:80]}]")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
