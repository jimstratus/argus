"""Unit tests for scripts/merge.py — clustering + scoring invariants.

Run: python -m pytest tests/ -q
Or:  python tests/test_merge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from merge import _merge, _emit_cluster  # noqa: E402


def _mk(file: str, line: int, reviewer: str, **kw):
    return {
        "file": file,
        "line": line,
        "severity": kw.get("severity", "medium"),
        "category": kw.get("category", "bug"),
        "description": kw.get("description", f"finding at {line}"),
        "confidence": kw.get("confidence", 85),
    }


def _review(name: str, findings: list[dict]) -> dict:
    return {"name": name, "findings": findings}


def test_anchor_splits_chain_drift():
    """Findings at 10, 13, 16, 19 (each +3 from previous) must NOT collapse
    into one cluster — the anchor check rejects C when it's 6 lines from A."""
    r = _merge(
        [
            _review("A", [_mk("f.py", 10, "A")]),
            _review("B", [_mk("f.py", 13, "B")]),
            _review("C", [_mk("f.py", 16, "C")]),
            _review("D", [_mk("f.py", 19, "D")]),
        ],
        threshold=80, boost=15, line_tolerance=3,
    )
    findings = r["findings"]
    # Expect two clusters: [10, 13] and [16, 19]
    assert len(findings) == 2, f"expected 2 clusters, got {len(findings)}: {findings}"
    ranges = sorted(f["line_range"] for f in findings)
    assert ranges == [[10, 13], [16, 19]], f"cluster line_ranges: {ranges}"
    reviewers_per_cluster = sorted(tuple(sorted(f["reviewers"])) for f in findings)
    assert reviewers_per_cluster == [("A", "B"), ("C", "D")]


def test_corroboration_preserved_within_tolerance():
    """Findings at 19, 19, 22 from three different reviewers cluster together
    (all within anchor=19 ± 3)."""
    r = _merge(
        [
            _review("opencode", [_mk("x.py", 19, "opencode", severity="high", category="security")]),
            _review("qwen", [_mk("x.py", 19, "qwen", severity="high", category="security")]),
            _review("gemini-or", [_mk("x.py", 22, "gemini-or", severity="high", category="security")]),
        ],
        threshold=80, boost=15, line_tolerance=3,
    )
    findings = r["findings"]
    assert len(findings) == 1, f"expected 1 cluster, got {len(findings)}"
    assert findings[0]["n_reviewers"] == 3
    # Boost applied: max_conf 85 + 15 = 100 (capped)
    assert findings[0]["confidence"] == 100, f"confidence={findings[0]['confidence']}"


def test_confidence_threshold_drops_low_solo():
    """A solo finding at confidence 70 is dropped (below threshold 80, no boost)."""
    r = _merge(
        [_review("A", [_mk("f.py", 1, "A", confidence=70)])],
        threshold=80, boost=15, line_tolerance=3,
    )
    assert r["findings"] == []


def test_different_files_stay_separate():
    """Same line on different files must not cluster."""
    r = _merge(
        [
            _review("A", [_mk("a.py", 10, "A")]),
            _review("B", [_mk("b.py", 10, "B")]),
        ],
        threshold=80, boost=15, line_tolerance=3,
    )
    assert len(r["findings"]) == 2
    files = sorted(f["file"] for f in r["findings"])
    assert files == ["a.py", "b.py"]


def test_severity_picks_worst_in_cluster():
    """When a cluster spans multiple severities, the worst wins for the merged finding."""
    r = _merge(
        [
            _review("A", [_mk("f.py", 10, "A", severity="low")]),
            _review("B", [_mk("f.py", 12, "B", severity="critical")]),
        ],
        threshold=80, boost=15, line_tolerance=3,
    )
    assert len(r["findings"]) == 1
    assert r["findings"][0]["severity"] == "critical"


def test_solo_finding_above_threshold_kept():
    """A single reviewer finding at confidence 90 (above threshold) is kept as solo."""
    r = _merge(
        [_review("A", [_mk("f.py", 42, "A", confidence=90)])],
        threshold=80, boost=15, line_tolerance=3,
    )
    assert len(r["findings"]) == 1
    assert r["findings"][0]["n_reviewers"] == 1
    assert r["findings"][0]["confidence"] == 90  # no boost, no cap change


if __name__ == "__main__":
    import traceback
    tests = [
        test_anchor_splits_chain_drift,
        test_corroboration_preserved_within_tolerance,
        test_confidence_threshold_drops_low_solo,
        test_different_files_stay_separate,
        test_severity_picks_worst_in_cluster,
        test_solo_finding_above_threshold_kept,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    sys.exit(failed)
