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
from _common import history_conn, load_config, canonical_reviewer, HISTORY_DB


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
        # benchmarks.ts is compact ('20260610T120000'); strip '-' and ':' and
        # truncate both sides to the common YYYYMMDDTHHMMSS prefix so neither
        # a timezone suffix on the row nor one on the cutoff skews the
        # lexical compare at exact-equality boundaries.
        where = "WHERE SUBSTR(REPLACE(REPLACE(ts, '-', ''), ':', ''), 1, 15) >= ?"
        params = [args.since.replace("-", "").replace(":", "")[:15]]

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
    bench_raw = [
        {"reviewer": r[0], "f1": r[1], "prec": r[2], "rec": r[3], "n": r[4]}
        for r in cur.fetchall()
    ]

    # history.db stores whatever the registry called a reviewer at run time, so
    # rows written before the 2026-09-22 version-free rename carry `glm-5.2`
    # while new ones carry `glm`. Grouping by the raw name splits one reviewer
    # into two and stops old benchmark metrics attaching to the canonical name
    # — i.e. the history continuity the alias map exists to preserve.
    #
    # SQL cannot call canonical_reviewer, so the SQL GROUP BY is only a
    # pre-aggregation; the merge below folds the groups by canonical name.
    cfg = load_config()

    def _canon(name: str) -> str:
        return canonical_reviewer(cfg, name)

    # Averages are re-derived from run-weighted totals, never averaged again:
    # 12 runs at 30s and 3 at 5s is 25s, not 17.5s.
    merged: dict[str, dict] = {}
    for reviewer, runs, avg_lat, avg_f, fb, errs in agg:
        m = merged.setdefault(_canon(reviewer), {
            "runs": 0, "lat_total": 0.0, "find_total": 0.0, "fb": 0, "errs": 0,
            "aliased_from": set(),
        })
        n = runs or 0
        m["runs"] += n
        m["lat_total"] += (avg_lat or 0) * n
        m["find_total"] += (avg_f or 0) * n
        m["fb"] += fb or 0
        m["errs"] += errs or 0
        if _canon(reviewer) != reviewer:
            m["aliased_from"].add(reviewer)

    bench: dict[str, dict] = {}
    for b in bench_raw:
        c = bench.setdefault(_canon(b["reviewer"]),
                             {"f1": 0.0, "prec": 0.0, "rec": 0.0, "n": 0})
        n = b["n"] or 0
        c["f1"] += (b["f1"] or 0) * n
        c["prec"] += (b["prec"] or 0) * n
        c["rec"] += (b["rec"] or 0) * n
        c["n"] += n
    for c in bench.values():
        if c["n"]:
            c["f1"] /= c["n"]
            c["prec"] /= c["n"]
            c["rec"] /= c["n"]

    rows = []
    for reviewer, m in sorted(merged.items(), key=lambda kv: -kv[1]["runs"]):
        runs = m["runs"]
        avg_lat = m["lat_total"] / runs if runs else 0
        avg_f = m["find_total"] / runs if runs else 0
        fb, errs = m["fb"], m["errs"]
        b = bench.get(reviewer, {})
        rows.append({
            "reviewer": reviewer,
            "runs": runs,
            "avg_latency_sec": round(avg_lat or 0, 2),
            "avg_findings": round(avg_f or 0, 1),
            "fallback_uses": fb or 0,
            "errors": errs or 0,
            # Names this row absorbed, so a merged history is visible rather
            # than silently presented as one reviewer's unbroken record.
            "merged_from": sorted(m["aliased_from"]) or None,
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
