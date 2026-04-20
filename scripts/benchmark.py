#!/usr/bin/env python3
"""Run Argus reviewers against the fixture suite and produce a leaderboard.

Usage:
  benchmark.py [--runs N=3] [--roster NAMES | --profile NAME] [--fixtures N1,N2,...] [--yes-cost]

For each reviewer × fixture × run:
  - dispatch the diff
  - score findings against ground-truth.json (tp/fp/fn → precision/recall/F1)

Produces:
  benchmarks/<ts>.json  — full data
  benchmarks/<ts>.md    — leaderboard + per-fixture detail + agreement matrix
Writes per-row results into history.db (benchmarks table).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    load_config, build_prompt, extract_json, normalize_findings,
    ARGUS_HOME, history_conn,
)
import adapters


FIXTURES_DIR = ARGUS_HOME / "fixtures"
BENCHMARKS_DIR = ARGUS_HOME / "benchmarks"


def _load_fixtures(filter_names: list[str] | None = None) -> list[dict]:
    fixtures = []
    for fdir in sorted(FIXTURES_DIR.iterdir()):
        if not fdir.is_dir():
            continue
        if filter_names and fdir.name not in filter_names:
            continue
        diff = fdir / "diff.patch"
        gt = fdir / "ground-truth.json"
        if not diff.exists() or not gt.exists():
            continue
        try:
            fixtures.append({
                "name": fdir.name,
                "diff": diff.read_text(encoding="utf-8", errors="replace"),
                "ground_truth": json.loads(gt.read_text(encoding="utf-8")),
            })
        except Exception as e:
            sys.stderr.write(f"skip fixture {fdir.name}: {e}\n")
    return fixtures


def _score(findings: list[dict], gt: dict) -> dict:
    """Match findings to ground-truth issues by file + line-within-tolerance."""
    tol = int(gt.get("line_tolerance", 3))
    truths = gt.get("issues", [])
    matched = set()
    tp = 0
    for f in findings:
        for i, t in enumerate(truths):
            if i in matched:
                continue
            if (f.get("file") == t.get("file")
                    and abs(int(f.get("line", 0)) - int(t.get("line", 0))) <= tol):
                matched.add(i)
                tp += 1
                break
    fp = len(findings) - tp
    fn = len(truths) - len(matched)
    prec = tp / len(findings) if findings else 0.0
    rec = tp / len(truths) if truths else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
    }


async def _dispatch(name: str, spec: dict, prompt: str, timeout: int) -> dict:
    primary = spec.get("primary") or {}
    adapter = adapters.get(primary.get("route"))
    if adapter is None:
        return {"findings": [], "latency_sec": 0, "error": f"no adapter for {primary.get('route')}"}
    r = await adapter.send(prompt, primary, timeout)
    if r["exit_code"] != 0:
        fb = spec.get("fallback")
        if fb:
            fba = adapters.get(fb.get("route"))
            if fba is not None:
                r = await fba.send(prompt, fb, timeout)
    findings = []
    if r["exit_code"] == 0:
        parsed = extract_json(r["stdout"])
        if isinstance(parsed, dict):
            findings = normalize_findings(parsed.get("findings", []))
    return {
        "findings": findings,
        "latency_sec": round(r["latency_sec"], 2),
        "exit_code": r["exit_code"],
        "error": (r.get("stderr") or "")[:200] if r["exit_code"] != 0 else None,
    }


async def _bench_reviewer(name: str, spec: dict, fixtures: list[dict],
                          runs: int, timeout: int, sem: asyncio.Semaphore) -> dict:
    per_fixture = []
    findings_keys_per_fixture: list[set[tuple[str, int]]] = []

    for fx in fixtures:
        prompt = build_prompt(fx["diff"])
        run_data = []
        merged_keys: set[tuple[str, int]] = set()
        for idx in range(runs):
            async with sem:
                d = await _dispatch(name, spec, prompt, timeout)
            scored = _score(d["findings"], fx["ground_truth"])
            run_data.append({
                "run_idx": idx,
                "n_findings": len(d["findings"]),
                "latency_sec": d["latency_sec"],
                "exit_code": d["exit_code"],
                "error": d["error"],
                **scored,
            })
            for f in d["findings"]:
                merged_keys.add((f.get("file", ""), int(f.get("line", 0) or 0)))
        findings_keys_per_fixture.append(merged_keys)

        n = len(run_data) or 1
        avg = {
            "precision": round(sum(r["precision"] for r in run_data) / n, 3),
            "recall":    round(sum(r["recall"]    for r in run_data) / n, 3),
            "f1":        round(sum(r["f1"]        for r in run_data) / n, 3),
            "avg_findings": round(sum(r["n_findings"] for r in run_data) / n, 1),
            "avg_latency": round(sum(r["latency_sec"] for r in run_data) / n, 2),
        }
        per_fixture.append({"fixture": fx["name"], "runs": run_data, "avg": avg})

    nf = len(per_fixture) or 1
    overall = {
        "precision": round(sum(fr["avg"]["precision"] for fr in per_fixture) / nf, 3),
        "recall":    round(sum(fr["avg"]["recall"]    for fr in per_fixture) / nf, 3),
        "f1":        round(sum(fr["avg"]["f1"]        for fr in per_fixture) / nf, 3),
        "avg_latency": round(sum(fr["avg"]["avg_latency"] for fr in per_fixture) / nf, 2),
    }
    return {
        "reviewer": name,
        "fixtures": per_fixture,
        "overall": overall,
        "_keys_per_fixture": findings_keys_per_fixture,  # internal; not serialized
    }


def _agreement_matrix(results: list[dict]) -> dict:
    """Jaccard similarity on finding keys, averaged across fixtures."""
    reviewers = sorted(r["reviewer"] for r in results)
    by_name = {r["reviewer"]: r for r in results}
    n_fix = len(next(iter(results), {}).get("_keys_per_fixture", [])) or 0

    matrix: dict[str, dict[str, float]] = {a: {b: 0.0 for b in reviewers} for a in reviewers}
    counts: dict[str, dict[str, int]] = {a: {b: 0 for b in reviewers} for a in reviewers}

    for i in range(n_fix):
        for a in reviewers:
            sa = by_name[a]["_keys_per_fixture"][i]
            for b in reviewers:
                sb = by_name[b]["_keys_per_fixture"][i]
                union = sa | sb
                if not union:
                    continue
                jac = len(sa & sb) / len(union)
                matrix[a][b] += jac
                counts[a][b] += 1
    for a in reviewers:
        for b in reviewers:
            if counts[a][b]:
                matrix[a][b] = round(matrix[a][b] / counts[a][b], 3)
    return matrix


def _write_history(results: list[dict], ts: str) -> None:
    try:
        conn = history_conn()
        for r in results:
            for fr in r["fixtures"]:
                for rd in fr["runs"]:
                    conn.execute(
                        'INSERT OR REPLACE INTO benchmarks (ts, reviewer, fixture, run_idx, "precision", recall, f1, n_findings, latency_sec, error) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (ts, r["reviewer"], fr["fixture"], rd["run_idx"],
                         rd["precision"], rd["recall"], rd["f1"],
                         rd["n_findings"], rd["latency_sec"], (rd["error"] or "")[:400]),
                    )
        conn.commit()
        conn.close()
    except Exception as e:
        sys.stderr.write(f"history write failed: {e}\n")


def _write_outputs(results: list[dict], fixtures: list[dict], runs: int, ts: str, agreement: dict) -> tuple[Path, Path]:
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    json_out = BENCHMARKS_DIR / f"{ts}.json"
    md_out = BENCHMARKS_DIR / f"{ts}.md"

    serializable = []
    for r in results:
        clone = {k: v for k, v in r.items() if k != "_keys_per_fixture"}
        serializable.append(clone)

    json_out.write_text(
        json.dumps({
            "ts": ts,
            "runs_per_fixture": runs,
            "fixtures": [fx["name"] for fx in fixtures],
            "results": serializable,
            "agreement_matrix": agreement,
        }, indent=2),
        encoding="utf-8",
    )

    # Leaderboard markdown
    ranked = sorted(serializable, key=lambda r: -r["overall"]["f1"])
    md = [f"# Argus Benchmark — `{ts}`", ""]
    md.append(f"**Fixtures ({len(fixtures)}):** {', '.join(fx['name'] for fx in fixtures)}  ")
    md.append(f"**Runs per fixture:** {runs}  ")
    md.append(f"**Reviewers tested:** {len(ranked)}  ")
    md.append(f"**Total calls:** {len(fixtures) * runs * len(ranked)}")
    md.append("")
    md.append("## Leaderboard (by F1)")
    md.append("")
    md.append("| Rank | Reviewer | F1 | Precision | Recall | Avg latency (s) |")
    md.append("|------|----------|----|-----------|--------|-----------------|")
    for i, r in enumerate(ranked, 1):
        o = r["overall"]
        md.append(f"| {i} | `{r['reviewer']}` | {o['f1']} | {o['precision']} | {o['recall']} | {o['avg_latency']} |")
    md.append("")

    md.append("## Per-fixture detail")
    md.append("")
    for r in ranked:
        md.append(f"### `{r['reviewer']}` — overall F1 = {r['overall']['f1']}")
        md.append("")
        md.append("| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |")
        md.append("|---------|-----------|--------|----|--------------|-----------------|")
        for fr in r["fixtures"]:
            a = fr["avg"]
            md.append(f"| {fr['fixture']} | {a['precision']} | {a['recall']} | {a['f1']} | {a['avg_findings']} | {a['avg_latency']} |")
        md.append("")

    md.append("## Agreement matrix (Jaccard on finding locations)")
    md.append("")
    md.append("> Values close to 1.0 indicate reviewers find nearly the same issues. Pairs above 0.85 are candidates for demotion (one becomes a fallback/custom).")
    md.append("")
    names = sorted(agreement.keys())
    header = "| | " + " | ".join(f"`{n}`" for n in names) + " |"
    sep = "|" + "---|" * (len(names) + 1)
    md.append(header)
    md.append(sep)
    for a in names:
        row = [f"`{a}`"] + [f"{agreement[a].get(b, 0.0):.2f}" for b in names]
        md.append("| " + " | ".join(row) + " |")
    md.append("")

    # Redundant-pair suggestions
    md.append("### Redundancy suggestions (≥ 0.85 agreement)")
    md.append("")
    suggestions = []
    seen = set()
    for a in names:
        for b in names:
            if a >= b:
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen:
                continue
            seen.add(pair)
            v = agreement[a].get(b, 0.0)
            if v >= 0.85:
                suggestions.append((a, b, v))
    if not suggestions:
        md.append("_No redundant pairs at the 0.85 threshold._")
    else:
        for a, b, v in sorted(suggestions, key=lambda x: -x[2]):
            md.append(f"- `{a}` ↔ `{b}`: {v:.2f} — consider demoting the lower-F1 reviewer to custom/fallback.")
    md.append("")

    md_out.write_text("\n".join(md), encoding="utf-8")
    return md_out, json_out


async def _main_async(args) -> int:
    cfg = load_config()
    defaults = cfg["defaults"]
    timeout = int(defaults["reviewer_timeout_sec"])
    max_parallel = int(defaults["max_parallel"])

    fixture_filter = None
    if args.fixtures:
        fixture_filter = [f.strip() for f in args.fixtures.split(",") if f.strip()]
    fixtures = _load_fixtures(fixture_filter)
    if not fixtures:
        sys.stderr.write("no fixtures found. Seed fixtures/ before running benchmark.\n")
        return 1

    if args.roster:
        roster = [r.strip() for r in args.roster.split(",") if r.strip()]
    elif args.profile:
        roster = list(cfg["profiles"][args.profile]["members"])
    else:
        roster = list(cfg["profiles"]["panel"]["members"])

    # Filter out reviewers not in registry
    roster = [n for n in roster if n in cfg["reviewers"]]

    print(f"Benchmarking {len(roster)} reviewers × {len(fixtures)} fixtures × {args.runs} runs = {len(roster)*len(fixtures)*args.runs} calls", file=sys.stderr)

    sem = asyncio.Semaphore(max_parallel)
    tasks = [_bench_reviewer(n, cfg["reviewers"][n], fixtures, args.runs, timeout, sem) for n in roster]
    results = await asyncio.gather(*tasks)

    agreement = _agreement_matrix(results)
    ts = time.strftime("%Y%m%dT%H%M%S")
    _write_history(results, ts)
    md_out, json_out = _write_outputs(results, fixtures, args.runs, ts, agreement)

    print(f"Leaderboard: {md_out}")
    print(f"Full JSON:   {json_out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="runs per fixture (default 3)")
    ap.add_argument("--roster", help="comma-separated reviewer names")
    ap.add_argument("--profile", help="named profile (default: panel)")
    ap.add_argument("--fixtures", help="comma-separated fixture names to run (default: all)")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
