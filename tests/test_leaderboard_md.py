"""Golden-output tests for the shared leaderboard renderer (issue #22 slice 5).

``benchmark._write_outputs`` and ``aggregate_bench._leaderboard_md`` each hand-
rolled the same leaderboard + per-fixture Markdown with already-divergent
columns. Both now delegate to ``_common.render_leaderboard_md``. The golden
files under ``tests/golden/`` were captured from the pre-refactor code (master
d9c0cd1) on the fixed inputs below, so any byte-level drift in either report
fails here.

Run: python -m pytest tests/test_leaderboard_md.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import aggregate_bench  # noqa: E402
import benchmark  # noqa: E402
from _common import md_table, render_leaderboard_md  # noqa: E402


GOLDEN = Path(__file__).resolve().parent / "golden"
TS = "20261004T120000"


def _fixture_row(name: str, p, r, f1, findings, lat) -> dict:
    return {
        "fixture": name,
        "runs": [],
        "avg": {"precision": p, "recall": r, "f1": f1,
                "avg_findings": findings, "avg_latency": lat},
    }


def bench_results() -> list[dict]:
    """benchmark.py in-memory results (incl. a fatal stub and an F1 tie)."""
    return [
        {
            "reviewer": "beta",
            "model": "vendor/beta-1",
            "fixtures": [
                _fixture_row("clean-baseline", 1.0, 1.0, 1.0, 0.0, 3.25),
                _fixture_row("sql-injection", 0.5, 1.0, 0.667, 2.0, 11.4),
            ],
            "overall": {"precision": 0.75, "recall": 1.0, "f1": 0.833, "avg_latency": 7.33},
            "_keys_per_fixture": [set(), {("app.py", 10)}],
        },
        {
            "reviewer": "alpha",
            "model": "vendor/alpha-2",
            "fixtures": [
                _fixture_row("clean-baseline", 0.0, 0.0, 0.0, 1.3, 2.0),
                _fixture_row("sql-injection", 1, 1, 1, 1, 9),  # ints render as ints
            ],
            "overall": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "avg_latency": 5.5},
            "_keys_per_fixture": [{("x.py", 1)}, {("app.py", 10)}],
        },
        {
            "reviewer": "gamma",
            "model": None,
            "fixtures": [
                _fixture_row("clean-baseline", 0.0, 0.0, 0.0, 0.0, 0.0),
                _fixture_row("sql-injection", 0.333, 0.5, 0.4, 3.0, 20.12),
            ],
            "overall": {"precision": 0.167, "recall": 0.25, "f1": 0.5, "avg_latency": 10.06},
            "_keys_per_fixture": [set(), {("app.py", 10), ("db.py", 4)}],
        },
        {
            "reviewer": "delta",
            "fixtures": [],
            "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "avg_latency": 0.0},
            "_keys_per_fixture": [set(), set()],
            "fatal_error": "RuntimeError: boom",
        },
    ]


BENCH_FIXTURES = [{"name": "clean-baseline"}, {"name": "sql-injection"}]
BENCH_AGREEMENT = {
    "alpha": {"alpha": 1.0, "beta": 0.9, "delta": 0.0, "gamma": 0.5},
    "beta": {"alpha": 0.9, "beta": 1.0, "delta": 0.0, "gamma": 0.5},
    "delta": {"alpha": 0.0, "beta": 0.0, "delta": 0.0, "gamma": 0.0},
    "gamma": {"alpha": 0.5, "beta": 0.5, "delta": 0.0, "gamma": 1.0},
}


def agg_results() -> list[dict]:
    """aggregate_bench.py collected results (ok / partial / fatal / sparse keys)."""
    return [
        {
            "reviewer": "beta",
            "fixtures": [
                _fixture_row("clean-baseline", 1.0, 1.0, 1.0, 0.0, 3.25),
                _fixture_row("sql-injection", 0.5, 1.0, 0.667, 2.0, 11.4),
            ],
            "overall": {"precision": 0.75, "recall": 1.0, "f1": 0.833, "avg_latency": 7.33},
            "total_call_latency_sec": 43.95,
        },
        {
            "reviewer": "alpha",
            "fixtures": [
                {"fixture": "clean-baseline", "runs": [], "avg": {"precision": 0.25}},
                {"runs": [], "avg": {}},  # missing fixture name + avg keys
            ],
            "overall": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "avg_latency": 5.5},
            "total_call_latency_sec": 22,
        },
        {
            "reviewer": "partial-one",
            "fixtures": [],
            "overall": {"f1": 0.5},
        },
        {
            "reviewer": "delta",
            "fixtures": [],
            "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "avg_latency": 0.0},
            "fatal_error": "RuntimeError: boom",
        },
        {"fixtures": [_fixture_row("x", 0.1, 0.2, 0.3, 0.4, 0.5)]},  # no name, no overall
    ]


def _render_bench(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(benchmark, "BENCHMARKS_DIR", tmp_path)
    md_out, _ = benchmark._write_outputs(bench_results(), BENCH_FIXTURES, 3, TS, BENCH_AGREEMENT)
    return md_out.read_bytes().decode("utf-8")


def test_benchmark_markdown_byte_identical(tmp_path, monkeypatch):
    got = _render_bench(tmp_path, monkeypatch)
    assert got == (GOLDEN / "benchmark_leaderboard.md").read_bytes().decode("utf-8")


def test_aggregate_markdown_byte_identical():
    got = aggregate_bench._leaderboard_md(TS, agg_results())
    assert got == (GOLDEN / "aggregate_leaderboard.md").read_bytes().decode("utf-8")


def test_benchmark_and_aggregate_share_section_skeleton(tmp_path, monkeypatch):
    """Both reports keep the same section order (the thing that used to drift)."""
    bench = _render_bench(tmp_path, monkeypatch).split("\n")
    agg = aggregate_bench._leaderboard_md(TS, agg_results()).split("\n")
    for lines in (bench, agg):
        lb = lines.index("## Leaderboard (by F1)")
        detail = lines.index("## Per-fixture detail")
        assert lines[lb + 1] == ""
        assert lines[lb + 2].startswith("| Rank | Reviewer | F1 | Precision | Recall |")
        assert lb < detail


# ---- md_table -----------------------------------------------------------

def test_md_table_separator_sized_to_headers():
    assert md_table(["Rank", "Avg latency (s)"], []) == [
        "| Rank | Avg latency (s) |",
        "|------|-----------------|",
    ]


def test_md_table_cells_use_str_formatting():
    rows = [[1, "`x`", 0.5, 1.0, 2]]
    assert md_table(["a", "b", "c", "d", "e"], rows)[2] == "| 1 | `x` | 0.5 | 1.0 | 2 |"


# ---- render_leaderboard_md --------------------------------------------------

def _render(results, notice=None):
    return render_leaderboard_md(
        title="# T",
        summary_lines=["s1", "s2"],
        results=results,
        leaderboard_columns=[("Rank", lambda i, r: i), ("Name", lambda i, r: r["n"])],
        fixture_columns=[("Fx", lambda fr: fr["fixture"])],
        detail_heading=lambda r: f"### {r['n']}",
        detail_notice=notice,
    )


def test_render_ranks_by_f1_desc_stable_on_ties():
    results = [
        {"n": "low", "overall": {"f1": 0.1}, "fixtures": []},
        {"n": "tie-a", "overall": {"f1": 0.5}, "fixtures": []},
        {"n": "tie-b", "overall": {"f1": 0.5}, "fixtures": []},
        {"n": "no-overall", "fixtures": []},  # missing overall ranks as F1=0
        {"n": "top", "overall": {"f1": 0.9}, "fixtures": []},
    ]
    lines = _render(results)
    rows = lines[lines.index("| Rank | Name |") + 2:lines.index("## Per-fixture detail") - 1]
    assert rows == [
        "| 1 | top |", "| 2 | tie-a |", "| 3 | tie-b |", "| 4 | low |", "| 5 | no-overall |",
    ]


def test_render_layout_and_trailing_blank():
    lines = _render([{"n": "a", "overall": {"f1": 1.0}, "fixtures": [{"fixture": "f1"}]}])
    assert lines == [
        "# T", "",
        "s1", "s2", "",
        "## Leaderboard (by F1)", "",
        "| Rank | Name |", "|------|------|", "| 1 | a |", "",
        "## Per-fixture detail", "",
        "### a", "",
        "| Fx |", "|----|", "| f1 |", "",
    ]


def test_render_notice_replaces_fixture_table():
    lines = _render(
        [{"n": "a", "overall": {"f1": 1.0}, "fixtures": [{"fixture": "f1"}]}],
        notice=lambda r: "_Fatal: x_",
    )
    assert lines[-3:] == ["### a", "_Fatal: x_", ""]
    assert "| Fx |" not in lines


def test_render_without_notice_emits_empty_table_for_no_fixtures():
    """benchmark.py behaviour for fatal stubs: header-only table (preserved)."""
    lines = _render([{"n": "a", "overall": {"f1": 0.0}, "fixtures": []}])
    assert lines[-5:] == ["### a", "", "| Fx |", "|----|", ""]
