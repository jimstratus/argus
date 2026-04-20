"""Unit tests for scripts/benchmark.py::_score — the precision/recall/F1 scorer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from benchmark import _score  # noqa: E402


def test_clean_baseline_perfect():
    """When truths is empty AND findings is empty, reviewer correctly flagged
    nothing — must score 1.0 across the board (previously scored 0.0, pre-fix)."""
    r = _score(findings=[], gt={"line_tolerance": 3, "issues": []})
    assert r["precision"] == 1.0
    assert r["recall"] == 1.0
    assert r["f1"] == 1.0
    assert r["tp"] == 0 and r["fp"] == 0 and r["fn"] == 0


def test_clean_baseline_with_phantom_findings():
    """Truths empty, findings non-empty — all phantoms; F1=0."""
    r = _score(
        findings=[{"file": "a.py", "line": 1}, {"file": "b.py", "line": 2}],
        gt={"line_tolerance": 3, "issues": []},
    )
    assert r["tp"] == 0
    assert r["fp"] == 2
    assert r["fn"] == 0
    assert r["precision"] == 0.0
    assert r["recall"] == 0.0
    assert r["f1"] == 0.0


def test_perfect_match():
    """All findings match all truths."""
    r = _score(
        findings=[
            {"file": "a.py", "line": 10},
            {"file": "a.py", "line": 20},
        ],
        gt={"line_tolerance": 3, "issues": [
            {"file": "a.py", "line": 10},
            {"file": "a.py", "line": 20},
        ]},
    )
    assert r["precision"] == 1.0
    assert r["recall"] == 1.0
    assert r["f1"] == 1.0


def test_line_tolerance():
    """Finding at line 12 matches truth at line 10 within tolerance=3."""
    r = _score(
        findings=[{"file": "a.py", "line": 12}],
        gt={"line_tolerance": 3, "issues": [{"file": "a.py", "line": 10}]},
    )
    assert r["tp"] == 1
    assert r["precision"] == 1.0


def test_line_tolerance_boundary_miss():
    """Finding at line 14 is outside tolerance=3 of truth at 10 (distance 4)."""
    r = _score(
        findings=[{"file": "a.py", "line": 14}],
        gt={"line_tolerance": 3, "issues": [{"file": "a.py", "line": 10}]},
    )
    assert r["tp"] == 0
    assert r["fp"] == 1
    assert r["fn"] == 1


def test_partial_recall():
    """1 tp, 0 fp, 1 fn → precision=1.0, recall=0.5, f1=0.667"""
    r = _score(
        findings=[{"file": "a.py", "line": 10}],
        gt={"line_tolerance": 3, "issues": [
            {"file": "a.py", "line": 10},
            {"file": "a.py", "line": 30},
        ]},
    )
    assert r["tp"] == 1
    assert r["fn"] == 1
    assert r["precision"] == 1.0
    assert r["recall"] == 0.5
    assert round(r["f1"], 3) == 0.667


def test_each_truth_matches_at_most_once():
    """Two findings at the same line should only count as 1 tp when there's 1 truth there."""
    r = _score(
        findings=[
            {"file": "a.py", "line": 10},
            {"file": "a.py", "line": 10},  # duplicate
        ],
        gt={"line_tolerance": 3, "issues": [{"file": "a.py", "line": 10}]},
    )
    assert r["tp"] == 1
    assert r["fp"] == 1  # second finding is a phantom


if __name__ == "__main__":
    import traceback
    tests = [
        test_clean_baseline_perfect,
        test_clean_baseline_with_phantom_findings,
        test_perfect_match,
        test_line_tolerance,
        test_line_tolerance_boundary_miss,
        test_partial_recall,
        test_each_truth_matches_at_most_once,
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
