"""Behavioral tests for the ``score_run`` call sites (issue #22 slice 4 follow-up).

PR #33 only pinned these with source-text assertions. These tests drive the
real code paths with a stubbed dispatcher / on-disk fixtures:

  1. benchmark._bench_reviewer wall-cap stub
  2. benchmark._bench_reviewer exit-code / parse_error / exception branch
  3. aggregate_bench._collect → _rescore_run rescoring

and spy on ``score_run`` to prove each path goes through the shared helper.

Run: python -m pytest tests/test_score_run_call_sites.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _common  # noqa: E402
import aggregate_bench  # noqa: E402
import benchmark  # noqa: E402


SPEC = {"primary": {"route": "aichat", "client": "openrouter", "model": "vendor/m-1"}}
CLEAN = {"name": "clean-baseline", "prompt": "P", "ground_truth": {"issues": []}}
BUGGY = {
    "name": "sql-injection", "prompt": "P",
    "ground_truth": {"line_tolerance": 3, "issues": [
        {"file": "app.py", "line": 10}, {"file": "db.py", "line": 40},
    ]},
}


@pytest.fixture
def spy(monkeypatch):
    """Wrap score_run in each consumer module, recording kwargs."""
    calls: list[dict] = []
    real = _common.score_run

    def wrapped(**kw):
        calls.append(kw)
        return real(**kw)

    monkeypatch.setattr(benchmark, "score_run", wrapped)
    monkeypatch.setattr(aggregate_bench, "score_run", wrapped)
    return calls


def _stub_dispatch(monkeypatch, responses):
    """Replace benchmark._dispatch with a queue of canned results/exceptions."""
    queue = list(responses)
    seen: list[str] = []

    async def fake(name, spec, prompt, timeout, preference="openrouter"):
        seen.append(name)
        r = queue.pop(0)
        if isinstance(r, BaseException):
            raise r
        return dict(r)

    monkeypatch.setattr(benchmark, "_dispatch", fake)
    return seen


def _bench(fixtures, runs=1, max_wall_sec=600):
    return asyncio.run(benchmark._bench_reviewer(
        "rev", SPEC, fixtures, runs, timeout=5, sem=asyncio.Semaphore(2),
        ts=None, max_wall_sec=max_wall_sec,
    ))


# ---- 1. wall-cap stub ---------------------------------------------------------

def test_wall_cap_zero_scores_without_dispatch(monkeypatch, spy):
    seen = _stub_dispatch(monkeypatch, [])  # any dispatch would IndexError
    out = _bench([CLEAN, BUGGY], runs=2, max_wall_sec=-1)

    assert seen == []
    for fr, n_issues in zip(out["fixtures"], (0, 2)):
        assert len(fr["runs"]) == 2
        for run in fr["runs"]:
            assert run["exit_code"] == 137
            assert run["error"] == "wall-cap exceeded"
            assert run["model"] is None
            assert (run["tp"], run["fp"], run["fn"]) == (0, 0, n_issues)
            assert (run["precision"], run["recall"], run["f1"]) == (0.0, 0.0, 0.0)
        assert fr["avg"]["f1"] == 0.0
    # Clean baseline must not earn F1=1.0 for a reviewer that never ran.
    assert out["overall"]["f1"] == 0.0
    assert len(spy) == 4
    assert all(c["exit_code"] == 137 and c["error"] == "wall-cap exceeded" for c in spy)
    assert [c["fn"] for c in spy] == [0, 0, 2, 2]


# ---- 2. exit-code / parse_error / exception branch ----------------------------

@pytest.mark.parametrize("resp", [
    {"findings": [], "latency_sec": 1.5, "exit_code": 1, "error": "HTTP 500", "model": "vendor/m-1"},
    {"findings": [], "latency_sec": 1.5, "exit_code": 0, "parse_error": True, "error": None,
     "model": "vendor/m-1"},
    RuntimeError("adapter crashed"),
], ids=["nonzero-exit", "parse-error", "exception"])
def test_failed_call_on_clean_baseline_zero_scores(monkeypatch, spy, resp):
    _stub_dispatch(monkeypatch, [resp])
    run = _bench([CLEAN])["fixtures"][0]["runs"][0]

    assert (run["precision"], run["recall"], run["f1"]) == (0.0, 0.0, 0.0)
    assert (run["tp"], run["fp"], run["fn"]) == (0, 0, 0)
    assert len(spy) == 1
    c = spy[0]
    assert c["exit_code"] != 0 or c["parse_error"]
    assert c["fn"] == 0
    if isinstance(resp, Exception):
        assert run["exit_code"] == 1
        assert c["error"] == "RuntimeError: adapter crashed"


def test_failed_call_with_findings_counts_all_truths_missed(monkeypatch, spy):
    """A failed call's findings are not matched: tp=fp=0, fn=n_issues."""
    _stub_dispatch(monkeypatch, [{
        "findings": [{"file": "app.py", "line": 10}], "latency_sec": 2.0,
        "exit_code": 2, "error": "timeout", "model": "vendor/m-1",
    }])
    run = _bench([BUGGY])["fixtures"][0]["runs"][0]

    assert run["n_findings"] == 1
    assert (run["tp"], run["fp"], run["fn"]) == (0, 0, 2)
    assert run["f1"] == 0.0
    assert spy == [{"exit_code": 2, "parse_error": False, "error": "timeout",
                    "tp": 0, "fp": 0, "fn": 2}]


def test_successful_call_bypasses_score_run(monkeypatch, spy):
    """Success path is scored by _score (findings matching), not the failure gate."""
    _stub_dispatch(monkeypatch, [
        {"findings": [], "latency_sec": 1.0, "exit_code": 0, "model": "vendor/m-1"},
        {"findings": [{"file": "app.py", "line": 11}], "latency_sec": 1.0, "exit_code": 0,
         "model": "vendor/m-1"},
    ])
    out = _bench([CLEAN, BUGGY])

    assert spy == []
    clean, buggy = (fr["runs"][0] for fr in out["fixtures"])
    assert clean["f1"] == 1.0  # genuinely found nothing on a clean diff
    assert (buggy["tp"], buggy["fp"], buggy["fn"]) == (1, 0, 1)
    assert buggy["f1"] == 0.667


# ---- 3. aggregate_bench rescoring ---------------------------------------------

def _write_per_reviewer(root: Path, ts: str, name: str, payload: dict) -> None:
    d = root / ts / "per_reviewer"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_aggregate_collect_rescores_stale_runs(tmp_path, monkeypatch, spy):
    """Pre-fix artifacts carry F1=1.0 for failed clean-baseline runs; _collect
    must rescore every run through score_run and rebuild avg/overall."""
    monkeypatch.setattr(aggregate_bench, "BENCHMARKS_DIR", tmp_path)
    ts = "20261004T000000"
    _write_per_reviewer(tmp_path, ts, "rev", {
        "reviewer": "rev",
        "fixtures": [
            {"fixture": "clean-baseline", "runs": [
                # wall-capped stub with stale perfect score
                {"tp": 0, "fp": 0, "fn": 0, "exit_code": 137, "error": "wall-cap exceeded",
                 "parse_error": False, "n_findings": 0, "latency_sec": 0.0,
                 "precision": 1.0, "recall": 1.0, "f1": 1.0},
                # genuine clean pass with stale zero score
                {"tp": 0, "fp": 0, "fn": 0, "exit_code": 0, "error": None,
                 "parse_error": False, "n_findings": 0, "latency_sec": 4.0,
                 "precision": 0.0, "recall": 0.0, "f1": 0.0},
            ]},
            {"fixture": "sql-injection", "runs": [
                {"tp": 1, "fp": 1, "fn": 1, "exit_code": 0, "error": None,
                 "parse_error": False, "n_findings": 2, "latency_sec": 6.0,
                 "precision": 9.9, "recall": 9.9, "f1": 9.9},
                # parse error; legacy artifact without exit_code key
                {"tp": 0, "fp": 0, "fn": 2, "parse_error": True,
                 "n_findings": 0, "latency_sec": 2.0,
                 "precision": 1.0, "recall": 1.0, "f1": 1.0},
            ]},
        ],
    })

    results = aggregate_bench._collect(ts)

    assert len(results) == 1
    clean, sqli = results[0]["fixtures"]
    assert [r["f1"] for r in clean["runs"]] == [0.0, 1.0]
    assert [r["f1"] for r in sqli["runs"]] == [0.5, 0.0]
    assert clean["avg"]["f1"] == 0.5
    assert sqli["avg"]["f1"] == 0.25
    assert results[0]["overall"]["f1"] == 0.375
    assert results[0]["total_call_latency_sec"] == 12.0

    assert len(spy) == 4
    assert spy[0] == {"tp": 0, "fp": 0, "fn": 0, "exit_code": 137,
                      "parse_error": False, "error": "wall-cap exceeded"}
    assert spy[3] == {"tp": 0, "fp": 0, "fn": 2, "exit_code": 0,
                      "parse_error": True, "error": None}

    # The rescored numbers flow into the rendered leaderboard.
    md = aggregate_bench._leaderboard_md(ts, results)
    assert "| 1 | `rev` | 0.375 |" in md
