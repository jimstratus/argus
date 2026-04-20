#!/usr/bin/env python3
"""Merge per-reviewer findings with confidence filter + corroboration boost.

Usage:
  merge.py --run-dir DIR [--threshold N] [--boost N] [--output {md,json,gsd}]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    load_config, history_conn, SEVERITY_RANK, ARGUS_HOME,
)


def _emit_cluster(file_path: str, cluster: list[dict], threshold: int, boost: int) -> dict | None:
    """Collapse a cluster of same-file, nearby-line findings into one."""
    reviewers = sorted({it["_reviewer"] for it in cluster})
    max_conf = max(int(it.get("confidence", 0) or 0) for it in cluster)
    effective = min(100, max_conf + boost) if len(reviewers) >= 2 else max_conf
    if effective < threshold:
        return None
    worst = max(cluster, key=lambda it: -SEVERITY_RANK.get(it.get("severity", "medium"), 3))
    lines = sorted(int(it.get("line", 0) or 0) for it in cluster)
    anchor_line = lines[len(lines) // 2]  # median
    # Aggregate descriptions (cluster may merge independently-found issues)
    unique_descs = []
    seen_descs = set()
    for it in sorted(cluster, key=lambda x: -int(x.get("confidence", 0) or 0)):
        d = it.get("description", "").strip()
        if d and d not in seen_descs:
            seen_descs.add(d)
            unique_descs.append(f"[{it['_reviewer']}] {d}")
    return {
        "file": file_path,
        "line": anchor_line,
        "line_range": [lines[0], lines[-1]] if lines[0] != lines[-1] else [lines[0]],
        "severity": worst.get("severity", "medium"),
        "category": worst.get("category", "bug"),
        "description": "\n\n".join(unique_descs),
        "confidence": effective,
        "reviewers": reviewers,
        "n_reviewers": len(reviewers),
    }


def _load_reviewer_results(reviews_dir: Path) -> list[dict]:
    out = []
    for p in sorted(reviews_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(data)
        except Exception:
            continue
    return out


def _merge(reviewer_results: list[dict], threshold: int, boost: int, line_tolerance: int = 3) -> dict:
    """Cluster findings by file + line-within-tolerance (not exact line).

    Algorithm: per file, sort findings by line. Walk forward, growing a cluster
    as long as the next finding's line is within `line_tolerance` of the max
    line already in the cluster. Reset cluster when the gap exceeds tolerance.
    Each cluster becomes one merged finding; the anchor line is the median.
    """
    per_reviewer_counts: dict[str, int] = {}
    by_file: dict[str, list[dict]] = defaultdict(list)

    for data in reviewer_results:
        name = data.get("name", "?")
        findings = data.get("findings", [])
        per_reviewer_counts[name] = len(findings)
        for f in findings:
            by_file[f.get("file", "")].append({**f, "_reviewer": name})

    merged = []
    for file_path, items in by_file.items():
        items.sort(key=lambda it: int(it.get("line", 0) or 0))
        cluster: list[dict] = []
        cluster_max_line = -10_000
        for it in items:
            ln = int(it.get("line", 0) or 0)
            if cluster and (ln - cluster_max_line) > line_tolerance:
                merged_item = _emit_cluster(file_path, cluster, threshold, boost)
                if merged_item is not None:
                    merged.append(merged_item)
                cluster = []
                cluster_max_line = -10_000
            cluster.append(it)
            cluster_max_line = max(cluster_max_line, ln)
        if cluster:
            merged_item = _emit_cluster(file_path, cluster, threshold, boost)
            if merged_item is not None:
                merged.append(merged_item)

    merged.sort(key=lambda f: (
        SEVERITY_RANK.get(f["severity"], 3),
        -f["confidence"],
        f["file"],
        f["line"],
    ))

    return {
        "findings": merged,
        "per_reviewer_counts": per_reviewer_counts,
        "reviewer_results": reviewer_results,
    }


def _to_markdown(result: dict, run_dir: Path) -> str:
    findings = result["findings"]
    counts = result["per_reviewer_counts"]
    reviewer_results = result["reviewer_results"]

    lines = [f"# Argus Review — `{run_dir.name}`", ""]

    by_sev: dict[str, int] = defaultdict(int)
    for f in findings:
        by_sev[f["severity"]] += 1
    corr = sum(1 for f in findings if f["n_reviewers"] >= 2)

    total = len(findings)
    sev_summary = " / ".join(f"{n} {s}" for s, n in sorted(by_sev.items(), key=lambda x: SEVERITY_RANK.get(x[0], 3)))
    lines.append(f"**Findings:** {total}  ({sev_summary})" if sev_summary else f"**Findings:** {total}")
    lines.append(f"**Corroborated (2+ reviewers):** {corr}  /  **Solo:** {total - corr}")
    lines.append("")
    lines.append("**Reviewers:**")
    for name, n in counts.items():
        meta = next((r for r in reviewer_results if r.get("name") == name), {})
        status = ""
        if meta.get("skipped"):
            status = f" — skipped ({meta.get('skip_reason')})"
        elif meta.get("error"):
            status = f" — error: {meta.get('error')[:80]}"
        elif meta.get("parse_error"):
            status = " — parse error"
        elif meta.get("fallback_used"):
            status = f" — fallback"
        lines.append(f"- `{name}`: {n} raw finding(s){status}")
    lines.append("")

    if not findings:
        lines.append("_No findings passed the confidence + corroboration filter._")
        return "\n".join(lines)

    lines.append("---")
    lines.append("")
    for i, f in enumerate(findings, 1):
        corr_tag = " **[corroborated]**" if f["n_reviewers"] >= 2 else ""
        lines.append(f"## {i}. {f['severity'].upper()} · `{f['category']}` · confidence {f['confidence']}{corr_tag}")
        lines.append(f"**Location:** `{f['file']}:{f['line']}`  ")
        lines.append(f"**Flagged by:** {', '.join('`'+r+'`' for r in f['reviewers'])}")
        lines.append("")
        lines.append(f["description"])
        lines.append("")
    return "\n".join(lines)


def _to_gsd(result: dict, run_dir: Path) -> str:
    """Emit REVIEW.md in the gsd-code-review schema for downstream consumption."""
    findings = result["findings"]
    lines = [f"# REVIEW.md", "", f"Generated by Argus run `{run_dir.name}`", ""]
    by_sev: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_sev[f["severity"]].append(f)
    for sev in ("critical", "high", "medium", "low"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        lines.append(f"## {sev.capitalize()} ({len(items)})")
        lines.append("")
        for f in items:
            lines.append(f"### {f['file']}:{f['line']}")
            lines.append(f"- category: {f['category']}")
            lines.append(f"- confidence: {f['confidence']}")
            lines.append(f"- reviewers: {', '.join(f['reviewers'])}")
            lines.append("")
            lines.append(f["description"])
            lines.append("")
    return "\n".join(lines)


def _record_history(result: dict, run_dir: Path, cfg: dict) -> None:
    """Append the run and its findings to history.db."""
    conn = None
    try:
        conn = history_conn()
        run_id = run_dir.name
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        reviewer_results = result["reviewer_results"]
        roster = ",".join(sorted(r.get("name", "?") for r in reviewer_results))
        latencies = [r.get("latency_sec", 0) or 0 for r in reviewer_results]
        total_latency = round(max(latencies) if latencies else 0, 2)  # parallel wall time ≈ max

        # diff hash
        diff_path = run_dir / "diff.patch"
        diff_sha = ""
        diff_bytes = 0
        if diff_path.exists():
            b = diff_path.read_bytes()
            diff_sha = hashlib.sha256(b).hexdigest()
            diff_bytes = len(b)

        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, ts, host, profile, roster, diff_sha256, diff_bytes, cost_est_usd, latency_sec) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, ts, None, None, roster, diff_sha, diff_bytes, None, total_latency),
        )
        for r in reviewer_results:
            conn.execute(
                "INSERT OR REPLACE INTO reviewer_runs (run_id, reviewer, route, exit_code, fallback_used, latency_sec, n_findings, error) VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    r.get("name", "?"),
                    r.get("route") or "",
                    int(r.get("exit_code", 0) or 0),
                    1 if r.get("fallback_used") else 0,
                    float(r.get("latency_sec", 0) or 0),
                    len(r.get("findings", [])),
                    (r.get("error") or "")[:400],
                ),
            )
        for i, f in enumerate(result["findings"]):
            conn.execute(
                "INSERT OR REPLACE INTO findings (run_id, idx, file, line, severity, category, confidence, n_reviewers, reviewers, description) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, i, f["file"], f["line"], f["severity"], f["category"],
                    f["confidence"], f["n_reviewers"], ",".join(f["reviewers"]),
                    f["description"][:1000],
                ),
            )
        conn.commit()
    except Exception as e:
        sys.stderr.write(f"history write failed (non-fatal): {e}\n")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--threshold", type=int, default=None)
    ap.add_argument("--boost", type=int, default=None)
    ap.add_argument("--output", default="md", choices=["md", "json", "gsd"])
    args = ap.parse_args()

    cfg = load_config()
    threshold = args.threshold if args.threshold is not None else cfg["defaults"]["confidence_threshold"]
    boost = args.boost if args.boost is not None else cfg["defaults"]["corroboration_boost"]

    run_dir = Path(args.run_dir)
    reviews_dir = run_dir / "reviews"
    if not reviews_dir.exists():
        sys.stderr.write(f"no reviews/ dir in {run_dir}\n")
        return 1

    reviewer_results = _load_reviewer_results(reviews_dir)
    result = _merge(reviewer_results, threshold, boost)

    # Always write metrics.json + merged.md; honor --output for stdout
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {"findings": result["findings"], "per_reviewer_counts": result["per_reviewer_counts"]},
            indent=2,
        ),
        encoding="utf-8",
    )
    md = _to_markdown(result, run_dir)
    (run_dir / "merged.md").write_text(md, encoding="utf-8")
    if args.output == "gsd":
        gsd_text = _to_gsd(result, run_dir)
        (run_dir / "REVIEW.md").write_text(gsd_text, encoding="utf-8")
        print(gsd_text)
    elif args.output == "json":
        print(json.dumps({"findings": result["findings"], "per_reviewer_counts": result["per_reviewer_counts"]}, indent=2))
    else:
        print(md)

    _record_history(result, run_dir, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
