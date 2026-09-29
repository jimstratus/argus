"""Unit tests for scripts/refresh.py — OpenRouter catalog pin diff.

Pins the mimo-silent-death regression: a delisted OpenRouter slug must be
reported as DELISTED (exit 2), not quietly OK. Also covers ctx/cost mismatch
reporting and the direct/CLI-only skip caveat.

Run: python -m pytest tests/test_refresh.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from refresh import (  # noqa: E402
    OrPin,
    catalog_cost_per_m,
    collect_or_pins,
    diff_pins,
    exit_code,
    run_refresh,
)


# Minimal synthetic config — independent of registry churn.
CFG = {
    "reviewers": {
        # Dual-route: direct primary + OR fallback. Metadata owned by fallback.
        "glm": {
            "ctx": 1000,
            "cost_per_m": {"input": 1.0, "output": 2.0},
            "primary": {"route": "aichat", "client": "zai", "model": "glm-X"},
            "fallback": {"route": "aichat", "client": "openrouter", "model": "z-ai/glm-X"},
        },
        # OR primary + OR fallback. Metadata owned by primary only.
        "mimo": {
            "ctx": 1048576,
            "cost_per_m": {"input": 0.43, "output": 0.87},
            "primary": {
                "route": "aichat",
                "client": "openrouter",
                "model": "xiaomi/mimo-v2.6-pro",
            },
            "fallback": {
                "route": "aichat",
                "client": "openrouter",
                "model": "xiaomi/mimo-v2.6-flash",
            },
        },
        # Delisted slug (the bug class).
        "dead": {
            "ctx": 100,
            "cost_per_m": {"input": 0.1, "output": 0.2},
            "primary": {
                "route": "aichat",
                "client": "openrouter",
                "model": "xiaomi/mimo-v2-pro",
            },
        },
        # CLI-only — must be skipped, not validated.
        "opencode-glm": {
            "ctx": 200000,
            "cost_per_m": None,
            "primary": {"route": "opencode-cli", "model": "ollama-cloud/glm-5.2"},
        },
        # CLI primary + OR fallback, null cost — listing check only on OR.
        "codex": {
            "ctx": 400000,
            "cost_per_m": None,
            "primary": {"route": "codex-cli"},
            "fallback": {
                "route": "aichat",
                "client": "openrouter",
                "model": "openai/gpt-5.3-codex",
            },
        },
    }
}


def _entry(model_id: str, ctx: int, prompt: str, completion: str) -> dict:
    return {
        "id": model_id,
        "context_length": ctx,
        "pricing": {"prompt": prompt, "completion": completion},
    }


CATALOG = {
    "z-ai/glm-X": _entry("z-ai/glm-X", 1000, "0.000001", "0.000002"),  # $1/$2
    "xiaomi/mimo-v2.6-pro": _entry(
        "xiaomi/mimo-v2.6-pro", 1048576, "0.000000435", "0.00000087"
    ),
    "xiaomi/mimo-v2.6-flash": _entry(
        "xiaomi/mimo-v2.6-flash", 1048576, "0.00000014", "0.00000028"
    ),
    # intentionally NO xiaomi/mimo-v2-pro
    "openai/gpt-5.3-codex": _entry(
        "openai/gpt-5.3-codex", 400000, "0.00000175", "0.000014"
    ),
}


def test_catalog_cost_per_m_converts_per_token():
    c = catalog_cost_per_m(
        {"pricing": {"prompt": "0.000000435", "completion": "0.00000087"}}
    )
    assert c == {"input": 0.43, "output": 0.87}


def test_collect_skips_direct_cli_only():
    pins, skipped = collect_or_pins(CFG)
    skipped_names = {s["reviewer"] for s in skipped}
    assert "opencode-glm" in skipped_names
    pin_reviewers = {p.reviewer for p in pins}
    assert "opencode-glm" not in pin_reviewers
    assert "mimo" in pin_reviewers
    assert "dead" in pin_reviewers
    assert "glm" in pin_reviewers
    assert "codex" in pin_reviewers


def test_metadata_ownership_primary_or_wins():
    pins, _ = collect_or_pins(CFG)
    mimo = [p for p in pins if p.reviewer == "mimo"]
    assert len(mimo) == 2
    owners = {(p.which, p.owns_metadata) for p in mimo}
    assert ("primary", True) in owners
    assert ("fallback", False) in owners


def test_metadata_ownership_fallback_when_primary_direct():
    pins, _ = collect_or_pins(CFG)
    glm = [p for p in pins if p.reviewer == "glm"]
    assert len(glm) == 1
    assert glm[0].which == "fallback" and glm[0].owns_metadata is True


def test_delisted_slug_reported():
    """Regression: xiaomi/mimo-v2-pro class — must be DELISTED, not ok."""
    pins, _ = collect_or_pins(CFG)
    findings = diff_pins(pins, CATALOG)
    dead = [f for f in findings if f.reviewer == "dead"]
    assert len(dead) == 1
    assert dead[0].status == "delisted"
    assert "mimo-v2-pro" in dead[0].model


def test_matching_pins_ok():
    pins, _ = collect_or_pins(CFG)
    findings = diff_pins(pins, CATALOG)
    by = {(f.reviewer, f.which): f for f in findings}
    assert by[("mimo", "primary")].status == "ok"
    assert by[("glm", "fallback")].status == "ok"
    # fallback OR when primary is also OR: listing-only, always ok if present
    assert by[("mimo", "fallback")].status == "ok"
    assert by[("codex", "fallback")].status == "ok"


def test_ctx_mismatch():
    pins = [
        OrPin(
            reviewer="mimo",
            which="primary",
            model="xiaomi/mimo-v2.6-pro",
            owns_metadata=True,
            pin_ctx=999,
            pin_cost={"input": 0.43, "output": 0.87},
        )
    ]
    findings = diff_pins(pins, CATALOG)
    assert findings[0].status == "ctx_mismatch"
    assert findings[0].catalog_ctx == 1048576


def test_cost_mismatch():
    pins = [
        OrPin(
            reviewer="mimo",
            which="primary",
            model="xiaomi/mimo-v2.6-pro",
            owns_metadata=True,
            pin_ctx=1048576,
            pin_cost={"input": 9.99, "output": 9.99},
        )
    ]
    findings = diff_pins(pins, CATALOG)
    assert findings[0].status == "cost_mismatch"


def test_both_mismatch():
    pins = [
        OrPin(
            reviewer="mimo",
            which="primary",
            model="xiaomi/mimo-v2.6-pro",
            owns_metadata=True,
            pin_ctx=1,
            pin_cost={"input": 9.99, "output": 9.99},
        )
    ]
    assert diff_pins(pins, CATALOG)[0].status == "both_mismatch"


def test_fallback_does_not_compare_primary_cost_against_fallback_price():
    """mimo fallback has different catalog price than the reviewer pin;
    because it does not own_metadata, that must not be a cost_mismatch."""
    pins, _ = collect_or_pins(CFG)
    findings = diff_pins(pins, CATALOG)
    fb = next(f for f in findings if f.reviewer == "mimo" and f.which == "fallback")
    assert fb.status == "ok"


def test_exit_codes():
    pins, skipped = collect_or_pins(CFG)
    findings = diff_pins(pins, CATALOG)
    from refresh import RefreshReport

    r = RefreshReport(findings=findings, skipped=skipped, catalog_size=len(CATALOG))
    assert exit_code(r) == 2  # delisted 'dead'

    # strip delisted → should be 0 (all remaining match)
    r2 = RefreshReport(
        findings=[f for f in findings if f.status != "delisted"],
        catalog_size=len(CATALOG),
    )
    assert exit_code(r2) == 0

    # force a mismatch
    bad = diff_pins(
        [
            OrPin(
                "x",
                "primary",
                "xiaomi/mimo-v2.6-pro",
                True,
                1,
                {"input": 0.43, "output": 0.87},
            )
        ],
        CATALOG,
    )
    assert exit_code(RefreshReport(findings=bad, catalog_size=1)) == 1

    assert exit_code(RefreshReport(fetch_error="boom")) == 3


def test_run_refresh_with_injected_catalog():
    report = run_refresh(cfg=CFG, catalog=CATALOG)
    assert report.fetch_error is None
    assert any(f.status == "delisted" for f in report.findings)
    assert any(s["reviewer"] == "opencode-glm" for s in report.skipped)
    assert exit_code(report) == 2


def test_cost_tolerance():
    # pin off by 0.01 — within default 0.02 tolerance
    pins = [
        OrPin(
            "mimo",
            "primary",
            "xiaomi/mimo-v2.6-pro",
            True,
            1048576,
            {"input": 0.44, "output": 0.88},
        )
    ]
    assert diff_pins(pins, CATALOG)[0].status == "ok"
    assert diff_pins(pins, CATALOG, cost_tolerance=0.005)[0].status == "cost_mismatch"


def test_cost_tolerance_exact_boundary_accepted():
    """0.43 vs 0.45 with tolerance 0.02 must be OK despite float noise."""
    pins = [
        OrPin(
            "mimo",
            "primary",
            "xiaomi/mimo-v2.6-pro",
            True,
            1048576,
            {"input": 0.45, "output": 0.89},  # +0.02 / +0.02 vs catalog 0.43/0.87
        )
    ]
    assert diff_pins(pins, CATALOG, cost_tolerance=0.02)[0].status == "ok"


def test_null_cost_ok_note_does_not_claim_cost_match():
    pins = [
        OrPin(
            "codex",
            "fallback",
            "openai/gpt-5.3-codex",
            True,
            400000,
            None,
        )
    ]
    f = diff_pins(pins, CATALOG)[0]
    assert f.status == "ok"
    assert "cost match" not in f.note
    assert "cost not pinned" in f.note


def test_shipped_config_collects_without_error():
    """Smoke: real config.yaml is parseable and yields at least one OR pin."""
    from _common import load_config

    cfg = load_config()
    pins, skipped = collect_or_pins(cfg)
    assert pins, "expected at least one OpenRouter pin in shipped config"
    assert any(s["reviewer"] == "opencode-glm" for s in skipped)


if __name__ == "__main__":
    # Allow `python tests/test_refresh.py` without pytest for quick checks.
    import_failed = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok {name}")
            except Exception as e:
                print(f"FAIL {name}: {e}")
                import_failed.append(name)
    if import_failed:
        sys.exit(1)
    print("all refresh tests passed")
