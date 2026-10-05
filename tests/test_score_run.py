"""Regression tests for _common.score_run (issue #22 slice 4).

Failed-call zero-scoring lived in three hand-synced copies:
  1. benchmark.py wall-cap stub
  2. benchmark.py exit-code / parse_error branch
  3. aggregate_bench._rescore_run

These tests pin the shared contracts so the three call sites cannot diverge
again. Matching findings→tp/fp/fn stays in benchmark._score (covered by
test_score.py).

Run: python -m pytest tests/test_score_run.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import score_run  # noqa: E402
from aggregate_bench import _rescore_run  # noqa: E402


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def test_failed_nonzero_exit_zero_scores():
    """Non-zero exit → P=R=F1=0 even when tp/fp/fn look like clean baseline."""
    r = score_run(exit_code=1, tp=0, fp=0, fn=0)
    assert r["precision"] == 0.0
    assert r["recall"] == 0.0
    assert r["f1"] == 0.0
    assert r["tp"] == r["fp"] == r["fn"] == 0


def test_failed_parse_error_zero_scores():
    """Unparseable output is not 'found nothing'."""
    r = score_run(exit_code=0, parse_error=True, tp=0, fp=0, fn=0)
    assert (r["precision"], r["recall"], r["f1"]) == (0.0, 0.0, 0.0)


def test_failed_error_string_zero_scores():
    """Any error string (wall-cap, exception) zero-scores — aggregate rule."""
    r = score_run(exit_code=0, error="wall-cap exceeded", tp=0, fp=0, fn=3)
    assert (r["precision"], r["recall"], r["f1"]) == (0.0, 0.0, 0.0)
    assert r["fn"] == 3  # counts preserved; only P/R/F1 derived


def test_wall_cap_stub_shape():
    """Wall-cap stub: exit 137 + error → zero score, fn = n_issues."""
    r = score_run(exit_code=137, error="wall-cap exceeded", tp=0, fp=0, fn=5)
    assert r == {
        "tp": 0, "fp": 0, "fn": 5,
        "precision": 0.0, "recall": 0.0, "f1": 0.0,
    }


def test_clean_baseline_success():
    """Successful call with tp=fp=fn=0 → perfect (the past F1=1.0 bug fix)."""
    r = score_run(exit_code=0, tp=0, fp=0, fn=0)
    assert r["precision"] == 1.0
    assert r["recall"] == 1.0
    assert r["f1"] == 1.0


def test_standard_prf1_from_counts():
    """1 tp, 0 fp, 1 fn → P=1.0, R=0.5, F1≈0.667."""
    r = score_run(tp=1, fp=0, fn=1)
    assert r["precision"] == 1.0
    assert r["recall"] == 0.5
    assert r["f1"] == 0.667


def test_all_false_positives():
    """tp=0, fp>0, fn=0 → empty-truth FPs: P=R=F1=0 (matches benchmark._score)."""
    r = score_run(tp=0, fp=2, fn=0)
    assert r["precision"] == 0.0
    assert r["recall"] == 0.0
    assert r["f1"] == 0.0


def test_no_predictions_with_truths():
    """tp+fp==0 with fn>0 → P=0, R=0."""
    r = score_run(tp=0, fp=0, fn=3)
    assert r["precision"] == 0.0
    assert r["recall"] == 0.0
    assert r["f1"] == 0.0


def test_rescore_run_delegates_failure():
    """aggregate_bench._rescore_run must apply the shared failure gate."""
    run = {
        "tp": 0, "fp": 0, "fn": 0,
        "exit_code": 137, "error": "wall-cap exceeded", "parse_error": False,
        "precision": 1.0, "recall": 1.0, "f1": 1.0,  # stale pre-fix values
    }
    out = _rescore_run(run)
    assert out["precision"] == 0.0
    assert out["recall"] == 0.0
    assert out["f1"] == 0.0


def test_rescore_run_delegates_clean_baseline():
    run = {
        "tp": 0, "fp": 0, "fn": 0,
        "exit_code": 0, "error": None, "parse_error": False,
        "precision": 0.0, "recall": 0.0, "f1": 0.0,  # stale pre-fix
    }
    out = _rescore_run(run)
    assert out["precision"] == 1.0
    assert out["recall"] == 1.0
    assert out["f1"] == 1.0


def test_call_sites_use_score_run():
    """Both producers of per-run scores must call the shared helper."""
    bench_src = (SCRIPTS / "benchmark.py").read_text(encoding="utf-8")
    agg_src = (SCRIPTS / "aggregate_bench.py").read_text(encoding="utf-8")
    assert "score_run(" in bench_src
    assert "score_run(" in agg_src
    assert "from _common import" in bench_src and "score_run" in bench_src


def test_aggregate_bench_does_not_reimplement_formula():
    """Guard: aggregate_bench must not re-grow the P/R/F1 arithmetic.

    ``_rescore_run`` is a thin wrapper; the clean-baseline / failure gate and
    the ``2 * prec * rec / (prec + rec)`` formula live only in score_run.
    (``benchmark._score`` still matches findings→counts — that is separate.)
    """
    agg_src = (SCRIPTS / "aggregate_bench.py").read_text(encoding="utf-8")
    assert "score_run(" in agg_src
    assert "2 * prec * rec" not in agg_src
    assert "tp == 0 and fp == 0 and fn == 0" not in agg_src
