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
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    load_config, build_prompt, extract_json, normalize_findings,
    ARGUS_HOME, history_conn, resolve_roster, resolve_routes, resolve_route_preference,
)
from detect_host import detect as detect_host
import adapters


FIXTURES_DIR = ARGUS_HOME / "fixtures"
BENCHMARKS_DIR = ARGUS_HOME / "benchmarks"

# Set by --progress; when True, log per-run + per-reviewer events to stderr
PROGRESS = False
_PROGRESS_LOCK: asyncio.Lock | None = None
_PROGRESS_COUNTER = {"done": 0, "total": 0}
_PROGRESS_START: float = 0.0


async def _log_progress(msg: str) -> None:
    if not PROGRESS:
        return
    assert _PROGRESS_LOCK is not None
    async with _PROGRESS_LOCK:
        elapsed = time.monotonic() - _PROGRESS_START
        done = _PROGRESS_COUNTER["done"]
        total = _PROGRESS_COUNTER["total"]
        sys.stderr.write(f"[{elapsed:6.1f}s {done:>3}/{total}] {msg}\n")
        sys.stderr.flush()


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
    """Match findings to ground-truth issues by file + line-within-tolerance.

    Edge case: clean baseline (truths empty).
      - findings empty → perfect (P=R=F1=1.0)
      - findings present → all false positives (P=R=F1=0.0)
    """
    tol = int(gt.get("line_tolerance", 3))
    truths = gt.get("issues", [])

    if not truths:
        if not findings:
            return {"tp": 0, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}
        return {"tp": 0, "fp": len(findings), "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

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


async def _dispatch(name: str, spec: dict, prompt: str, timeout: int,
                    preference: str = "openrouter") -> dict:
    primary, fb = resolve_routes(spec, preference)
    primary = primary or {}
    adapter = adapters.get(primary.get("route"))
    if adapter is None:
        return {"findings": [], "latency_sec": 0.0, "primary_latency_sec": 0.0,
                "fallback_latency_sec": 0.0, "fallback_used": False,
                "exit_code": 1, "primary_exit_code": 1, "primary_error": "",
                "parse_error": False,
                "error": f"no adapter for {primary.get('route')}"}
    r = await adapter.send(prompt, primary, timeout)
    primary_latency = r.get("latency_sec", 0.0)
    primary_exit = r.get("exit_code", 0)
    primary_err = ""
    fallback_latency = 0.0
    fallback_used = False
    if r["exit_code"] != 0:
        primary_err = (r.get("stderr") or "")[:200]
        if fb:
            fba = adapters.get(fb.get("route"))
            if fba is not None:
                r2 = await fba.send(prompt, fb, timeout)
                fallback_latency = r2.get("latency_sec", 0.0)
                fallback_used = True
                r = r2
    findings = []
    parse_error = False
    if r["exit_code"] == 0:
        parsed = extract_json(r["stdout"])
        # Require the schema's findings list — extract_json can recover an
        # arbitrary inner object from prose, which is still a failed review.
        if isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
            findings = normalize_findings(parsed["findings"])
        else:
            parse_error = True
    total_latency = primary_latency + fallback_latency
    return {
        "findings": findings,
        "latency_sec": round(total_latency, 2),
        "primary_latency_sec": round(primary_latency, 2),
        "fallback_latency_sec": round(fallback_latency, 2),
        "fallback_used": fallback_used,
        "exit_code": r["exit_code"],
        "primary_exit_code": primary_exit,
        "primary_error": primary_err,
        "parse_error": parse_error,
        "error": (r.get("stderr") or "")[:200] if r["exit_code"] != 0 else None,
    }


async def _bench_reviewer(name: str, spec: dict, fixtures: list[dict],
                          runs: int, timeout: int, sem: asyncio.Semaphore,
                          ts: str | None = None, max_wall_sec: int = 600,
                          preference: str = "openrouter") -> dict:
    per_fixture = []
    findings_keys_per_fixture: list[set[tuple[str, int]]] = []
    wall_start = time.monotonic()

    for fx in fixtures:
        prompt = fx["prompt"]
        run_data = []
        merged_keys: set[tuple[str, int]] = set()
        for idx in range(runs):
            if time.monotonic() - wall_start > max_wall_sec:
                await _log_progress(f"{name:<16} WALL-CAP HIT at {int(time.monotonic()-wall_start)}s — skipping remaining runs")
                run_data.append({
                    "run_idx": idx, "n_findings": 0, "latency_sec": 0.0,
                    "exit_code": 137, "parse_error": False, "error": "wall-cap exceeded",
                    "tp": 0, "fp": 0, "fn": len(fx["ground_truth"].get("issues", [])),
                    "precision": 0.0, "recall": 0.0, "f1": 0.0,
                })
                _PROGRESS_COUNTER["done"] += 1
                continue
            try:
                async with sem:
                    d = await _dispatch(name, spec, prompt, timeout, preference)
            except Exception as e:
                await _log_progress(f"{name:<16} {fx['name']:<18} run {idx+1}/{runs}  EXCEPTION: {type(e).__name__}: {str(e)[:80]}")
                d = {"findings": [], "latency_sec": 0.0, "exit_code": 1,
                     "parse_error": False, "error": f"{type(e).__name__}: {e}"}
            if d.get("exit_code", 1) != 0 or d.get("parse_error"):
                # A failed or unparseable call is not "correctly found nothing" —
                # zero-score it so broken reviewers can't earn F1=1.0 on clean-baseline.
                scored = {"tp": 0, "fp": 0, "fn": len(fx["ground_truth"].get("issues", [])),
                          "precision": 0.0, "recall": 0.0, "f1": 0.0}
            else:
                scored = _score(d["findings"], fx["ground_truth"])
            run_data.append({
                "run_idx": idx,
                "n_findings": len(d["findings"]),
                "latency_sec": d["latency_sec"],
                "exit_code": d.get("exit_code", 1),
                "parse_error": d.get("parse_error", False),
                "error": d.get("error"),
                **scored,
            })
            for f in d["findings"]:
                merged_keys.add((f.get("file", ""), int(f.get("line", 0) or 0)))
            _PROGRESS_COUNTER["done"] += 1
            status = "err" if d["exit_code"] != 0 else f"F1={scored['f1']:.2f}"
            await _log_progress(f"{name:<16} {fx['name']:<18} run {idx+1}/{runs}  {d['latency_sec']:>5.1f}s  {status}")
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
    await _log_progress(f"{name:<16} *** reviewer complete ({nf} fixtures × {runs} runs)")
    # Incremental per-reviewer JSON (tailable) if ts provided
    if ts:
        try:
            reviewer_dir = BENCHMARKS_DIR / ts / "per_reviewer"
            reviewer_dir.mkdir(parents=True, exist_ok=True)
            (reviewer_dir / f"{name}.json").write_text(
                json.dumps({"reviewer": name, "fixtures": per_fixture}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            sys.stderr.write(f"incremental write failed for {name}: {e}\n")
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
    conn = None
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
    except Exception as e:
        sys.stderr.write(f"history write failed: {e}\n")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


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
    preference = resolve_route_preference(args.route_pref, cfg)

    fixture_filter = None
    if args.fixtures:
        fixture_filter = [f.strip() for f in args.fixtures.split(",") if f.strip()]
    fixtures = _load_fixtures(fixture_filter)
    if not fixtures:
        sys.stderr.write("no fixtures found. Seed fixtures/ before running benchmark.\n")
        return 1

    # Same policy engine as dispatch.py: --roster names are explicit (disabled/
    # custom_only waived, no host_rules add); profiles get full policy.
    host, _ = detect_host()
    if args.roster:
        names = [r.strip() for r in args.roster.split(",") if r.strip()]
        roster, drops = resolve_roster(
            cfg, "custom", names, host,
            allow_free=args.allow_free, allow_logging=args.allow_logging,
            explicit=True,
        )
    else:
        profile = args.profile or "panel"
        roster, drops = resolve_roster(
            cfg, "profile", [profile], host,
            allow_free=args.allow_free, allow_logging=args.allow_logging,
        )
    for n, reason in drops:
        print(f"skip {n}: {reason}", file=sys.stderr)

    total_calls = len(roster) * len(fixtures) * args.runs
    print(f"Benchmarking {len(roster)} reviewers × {len(fixtures)} fixtures × {args.runs} runs = {total_calls} calls", file=sys.stderr)

    # Cost gate: estimate spend and enforce benchmark thresholds
    from _common import estimate_tokens
    default_out_tokens = int(defaults["default_output_tokens_est"])
    prompt_overhead = int(defaults["prompt_overhead_tokens"])
    warn_thresh = float(defaults["benchmark_cost_warn_usd"])
    block_thresh = float(defaults["benchmark_cost_block_usd"])
    est_total = 0.0
    per_reviewer_cost: list[dict] = []
    for name in roster:
        spec = cfg["reviewers"][name]
        rates = spec.get("cost_per_m")
        if not rates:
            per_reviewer_cost.append({"reviewer": name, "cost": 0.0, "note": "paid CLI"})
            continue
        reviewer_cost = 0.0
        for fx in fixtures:
            in_tokens = estimate_tokens(fx["diff"]) + prompt_overhead
            per_call = (in_tokens / 1_000_000) * rates["input"] + (default_out_tokens / 1_000_000) * rates["output"]
            reviewer_cost += per_call * args.runs
        per_reviewer_cost.append({"reviewer": name, "cost": round(reviewer_cost, 4)})
        est_total += reviewer_cost

    est_total = round(est_total, 4)
    print(f"Estimated benchmark spend: ${est_total:.4f} (warn=${warn_thresh}, block=${block_thresh})", file=sys.stderr)
    yes_cost_override = bool(args.yes_cost) or (os.environ.get("ARGUS_YES_COST") == "1")
    if est_total >= block_thresh and not yes_cost_override:
        print(f"BLOCKED: estimate ${est_total:.4f} >= block threshold ${block_thresh}. Pass --yes-cost (or ARGUS_YES_COST=1) to override.", file=sys.stderr)
        for row in per_reviewer_cost:
            note = row.get("note", "")
            print(f"  {row['reviewer']:<18} ${row['cost']:>8.4f}  {note}", file=sys.stderr)
        return 2
    if est_total >= warn_thresh:
        print(f"WARNING: estimate ${est_total:.4f} >= warn threshold ${warn_thresh}. Proceeding.", file=sys.stderr)

    # OR balance pre-flight: only matters when OpenRouter is the *resolved
    # primary* for some reviewer (under direct preference OR is a fallback and
    # its balance is not on the critical path).
    def _primary_is_or(n: str) -> bool:
        p, _ = resolve_routes(cfg["reviewers"][n], preference)
        return bool(p) and p.get("client") == "openrouter"
    uses_openrouter = any(_primary_is_or(n) for n in roster)
    if uses_openrouter and not args.skip_balance_check and os.environ.get("OPENROUTER_API_KEY"):
        try:
            from or_balance import probe
            info = probe(os.environ["OPENROUTER_API_KEY"])
            available = info.get("available_usd")
            safety = float(defaults.get("or_balance_safety_factor", 2.0))
            if available is not None:
                required = est_total * safety
                print(f"OpenRouter available: ${available:.4f}  (required ≥ {safety}× estimate = ${required:.4f})", file=sys.stderr)
                if available < required and not yes_cost_override:
                    print(f"BLOCKED: OR balance ${available:.4f} < required ${required:.4f}. Top up or use --yes-cost.", file=sys.stderr)
                    return 2
        except Exception as e:
            sys.stderr.write(f"OR balance check failed (non-fatal): {e}\n")

    global PROGRESS, _PROGRESS_LOCK, _PROGRESS_START
    PROGRESS = bool(args.progress)
    _PROGRESS_LOCK = asyncio.Lock()
    _PROGRESS_COUNTER["total"] = total_calls
    _PROGRESS_COUNTER["done"] = 0
    _PROGRESS_START = time.monotonic()

    # UTC so benchmarks.ts and runs.ts (also UTC) share one --since timeline.
    ts = args.benchmark_ts or time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    # Prompts are reviewer-independent — build each fixture's once.
    for fx in fixtures:
        fx["prompt"] = build_prompt(fx["diff"])
    sem = asyncio.Semaphore(max_parallel)
    tasks = [_bench_reviewer(n, cfg["reviewers"][n], fixtures, args.runs, timeout, sem,
                              ts=ts, max_wall_sec=args.max_wall_sec, preference=preference)
             for n in roster]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    # Replace exceptions with error stubs so we never lose everything
    results = []
    for n, r in zip(roster, gathered):
        if isinstance(r, Exception):
            sys.stderr.write(f"FATAL in {n}: {type(r).__name__}: {r}\n")
            results.append({
                "reviewer": n,
                "fixtures": [],
                "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "avg_latency": 0.0},
                "_keys_per_fixture": [set() for _ in fixtures],
                "fatal_error": f"{type(r).__name__}: {r}",
            })
        else:
            results.append(r)

    agreement = _agreement_matrix(results)
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
    ap.add_argument("--progress", action="store_true", help="log per-run progress to stderr")
    ap.add_argument("--benchmark-ts", default=None, help="shared timestamp for parallel-shell runs (same TS = merged output dir)")
    ap.add_argument("--max-wall-sec", type=int, default=600, help="hard wall-time cap per reviewer (default 600s)")
    ap.add_argument("--yes-cost", action="store_true", help="bypass benchmark cost block + OR balance gate (env: ARGUS_YES_COST=1)")
    ap.add_argument("--skip-balance-check", action="store_true", help="skip the OpenRouter balance pre-flight")
    ap.add_argument("--allow-free", action="store_true", help="include free-tier reviewers")
    ap.add_argument("--allow-logging", action="store_true", help="include reviewers with privacy: LOGS")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--route-pref", choices=["openrouter", "direct"], default=None,
                     dest="route_pref", help="route preference for dual-route reviewers")
    grp.add_argument("--prefer-direct", action="store_const", const="direct", dest="route_pref")
    grp.add_argument("--prefer-openrouter", action="store_const", const="openrouter", dest="route_pref")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
