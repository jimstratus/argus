"""Regression tests for _common.estimate_roster_cost / rates_for / price_tokens
(issue #22 slice 2).

The $/M cost model lived in three hand-synced copies (estimate_cost.py,
benchmark.py's inline gate, bench_cost.py). These tests pin the shared
contracts so the three call sites cannot diverge again.

Run: python -m pytest tests/test_roster_cost.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import (  # noqa: E402
    load_config,
    price_tokens,
    rates_for,
    estimate_roster_cost,
)


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def test_price_tokens_formula():
    """$/M arithmetic: 1M in + 1M out at $1/$2 = $3."""
    assert price_tokens(1_000_000, 1_000_000, {"input": 1.0, "output": 2.0}) == 3.0
    assert price_tokens(500_000, 0, {"input": 2.0, "output": 6.0}) == 1.0


def test_price_tokens_cli_sub_is_zero():
    """Past drift risk: None rates must be $0, not a TypeError / crash."""
    assert price_tokens(10_000, 800, None) == 0.0
    assert price_tokens(10_000, 800, {}) == 0.0


def test_estimate_roster_cost_single_unit_matches_manual_formula():
    """estimate_cost path: one shared diff × calls_per_unit."""
    cfg = load_config()
    # Pick a metered reviewer with known rates.
    rates = cfg["reviewers"]["glm"]["cost_per_m"]
    in_tok, out_tok, calls = 4000, 800, 3
    est = estimate_roster_cost(
        cfg, ["glm"],
        input_tokens_per_unit=in_tok,
        output_tokens_per_call=out_tok,
        calls_per_unit=calls,
    )
    expected_per = price_tokens(in_tok, out_tok, rates)
    assert abs(est["per_reviewer"][0]["per_call_usd"] - expected_per) < 1e-12
    assert abs(est["per_reviewer"][0]["cost_usd"] - expected_per * calls) < 1e-12
    assert abs(est["total_usd"] - expected_per * calls) < 1e-12
    assert est["per_reviewer"][0]["calls"] == calls
    assert est["per_reviewer"][0]["note"] is None


def test_estimate_roster_cost_multi_unit_sums_fixtures():
    """benchmark path: per-fixture token counts × runs."""
    cfg = load_config()
    rates = cfg["reviewers"]["qwen"]["cost_per_m"]
    units = [1000, 2000, 3000]
    runs = 2
    out_tok = 800
    est = estimate_roster_cost(
        cfg, ["qwen"],
        input_tokens_per_unit=units,
        output_tokens_per_call=out_tok,
        calls_per_unit=runs,
    )
    expected = sum(price_tokens(u, out_tok, rates) * runs for u in units)
    assert abs(est["total_usd"] - expected) < 1e-12
    assert est["per_reviewer"][0]["per_call_usd"] is None  # multi-unit
    assert est["per_reviewer"][0]["calls"] == len(units) * runs
    assert est["n_units"] == 3


def test_estimate_roster_cost_cli_sub_zero():
    """codex has cost_per_m: null → $0 with 'paid CLI sub' note."""
    cfg = load_config()
    est = estimate_roster_cost(
        cfg, ["codex"],
        input_tokens_per_unit=5000,
        output_tokens_per_call=800,
        calls_per_unit=1,
    )
    row = est["per_reviewer"][0]
    assert row["cost_usd"] == 0.0
    assert row["note"] == "paid CLI sub"
    assert est["total_usd"] == 0.0


def test_estimate_roster_cost_unknown_zero_not_crash():
    """Unknown names are $0/'unknown'; callers that hard-error check first."""
    cfg = load_config()
    est = estimate_roster_cost(
        cfg, ["no-such-reviewer-xyz"],
        input_tokens_per_unit=1000,
        calls_per_unit=1,
    )
    assert est["per_reviewer"][0]["note"] == "unknown"
    assert est["per_reviewer"][0]["cost_usd"] == 0.0


def test_estimate_roster_cost_resolves_aliases():
    """Aliases must price (same drift that hit bench_cost pre-rename)."""
    cfg = load_config()
    est = estimate_roster_cost(
        cfg, ["glm-5.2"],
        input_tokens_per_unit=2000,
        output_tokens_per_call=800,
        calls_per_unit=1,
    )
    assert est["per_reviewer"][0]["note"] is None
    assert est["per_reviewer"][0]["cost_usd"] > 0


def test_estimate_roster_cost_mixed_roster_sums():
    """Metered + CLI sub: only metered contributes to total."""
    cfg = load_config()
    est = estimate_roster_cost(
        cfg, ["glm", "codex"],
        input_tokens_per_unit=1000,
        output_tokens_per_call=800,
        calls_per_unit=1,
    )
    by_name = {r["reviewer"]: r for r in est["per_reviewer"]}
    assert by_name["codex"]["cost_usd"] == 0.0
    assert by_name["glm"]["cost_usd"] > 0
    assert abs(est["total_usd"] - by_name["glm"]["cost_usd"]) < 1e-12


def test_rates_for_recorded_vs_estimated():
    """Past drift: recorded rates win; absent → estimated (not silent $0)."""
    cfg = load_config()
    recorded = {"input": 0.50, "output": 2.00}
    _, rates, status = rates_for(cfg, "qwen-3.6-plus", recorded)
    assert status == "recorded"
    assert rates == recorded

    _, rates2, status2 = rates_for(cfg, "qwen-3.6-plus", None)
    assert status2 == "estimated"
    assert rates2 and rates2["input"] > 0


def test_rates_for_mixed_and_cli_sub_and_unknown():
    """Past drift: fallback → mixed; clean CLI → cli-sub; missing → unknown."""
    cfg = load_config()
    assert rates_for(cfg, "codex", None, fallback_calls=2)[2] == "mixed"
    assert rates_for(cfg, "codex", None, fallback_calls=0)[2] == "cli-sub"
    assert rates_for(cfg, "no-such-reviewer-anywhere")[2] == "unknown"


def test_rates_for_deleted_reviewer_with_recorded_rates():
    """Past drift: registry miss + recorded rates is still 'recorded'."""
    cfg = load_config()
    recorded = {"input": 0.50, "output": 2.00}
    _, rates, status = rates_for(cfg, "retired-reviewer", recorded)
    assert status == "recorded"
    assert rates == recorded


def test_bench_cost_reexports_rates_for():
    """Thin wrapper: historical `from bench_cost import rates_for` still works."""
    from bench_cost import rates_for as bc_rates_for
    assert bc_rates_for is rates_for


def test_no_inline_cost_formula_in_call_sites():
    """Call sites must not re-implement the /1_000_000 formula in code."""
    import ast

    def _is_million(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value in (1_000_000, 1000000)

    for name in ("estimate_cost.py", "benchmark.py", "bench_cost.py"):
        src = (SCRIPTS / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Inspect BinOp nodes directly — ast.unparse() normalizes 1_000_000 → 1000000
        # and would let a reintroduced division slip past a string check (Copilot #30).
        offenders = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and _is_million(node.right)
        ]
        assert not offenders, (
            f"{name} still has an inline $/M formula — use price_tokens / "
            "estimate_roster_cost"
        )


def test_call_sites_use_shared_helpers():
    est_src = (SCRIPTS / "estimate_cost.py").read_text(encoding="utf-8")
    bench_src = (SCRIPTS / "benchmark.py").read_text(encoding="utf-8")
    bc_src = (SCRIPTS / "bench_cost.py").read_text(encoding="utf-8")
    assert "estimate_roster_cost(" in est_src
    assert "estimate_roster_cost(" in bench_src
    assert "price_tokens(" in bc_src
    assert "rates_for(" in bc_src


def test_estimate_cost_cli_zero_and_exit_ok(tmp_path: Path):
    """End-to-end: CLI-only roster estimates $0 and exits 0."""
    diff = tmp_path / "d.patch"
    diff.write_text("diff --git a/x b/x\n+hello world\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "estimate_cost.py"),
         "--roster", "codex", "--diff", str(diff), "--skip-balance-check"],
        capture_output=True, text=True, cwd=str(SCRIPTS.parent),
        env={**os.environ, "ARGUS_HOME": str(SCRIPTS.parent)},
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["total_estimated_usd"] == 0.0
    assert out["per_reviewer"][0]["note"] == "paid CLI sub"


def test_estimate_cost_invalid_roster_exit_2(tmp_path: Path):
    """Unknown roster is exit 2 (INVALID ROSTER), not a cost block."""
    diff = tmp_path / "d.patch"
    diff.write_text("+x\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "estimate_cost.py"),
         "--roster", "definitely-not-a-reviewer", "--diff", str(diff),
         "--skip-balance-check"],
        capture_output=True, text=True, cwd=str(SCRIPTS.parent),
        env={**os.environ, "ARGUS_HOME": str(SCRIPTS.parent)},
    )
    assert proc.returncode == 2
    assert "INVALID ROSTER" in proc.stderr
