#!/usr/bin/env python3
"""Catalog pin diff — catch the mimo-silent-death class of bugs.

Fetches the live OpenRouter model catalog (`GET /api/v1/models`) and diffs
every `client: openrouter` model slug in config.yaml (plus the reviewer-level
`ctx` / `cost_per_m` that pin that slug) against it.

This is the check `verify.py` cannot do: verify only pings routes for
reachability, so a delisted slug or a drifted ctx/price still looks green.

Coverage caveat (same as the PR #26 roster refresh):
  OpenRouter-routed pins ONLY. Direct-provider slugs (zai / minimax /
  deepseek / nous) and CLI-provider slugs (minimax-coding-plan / ollama-cloud
  / copilot) are invisible to this API and are reported as skipped — not
  validated. `opencode-glm` staying on glm-5.2 is the live example.

Usage:
  refresh.py              # human table; exit non-zero on problems
  refresh.py --json       # machine-readable
  refresh.py --tolerance 0.05   # cost $/M absolute slack (default 0.02)

Exit codes:
  0  every OpenRouter pin is listed and metadata matches
  1  mismatches only (ctx / cost_per_m drift; models still listed)
  2  one or more OpenRouter model slugs are delisted / missing
  3  catalog fetch failed
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config  # noqa: E402

OR_MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_COST_TOLERANCE = 0.02  # USD per million tokens


@dataclass
class OrPin:
    """One OpenRouter-routed model reference found in config.yaml."""

    reviewer: str
    which: str  # "primary" | "fallback"
    model: str
    # True when this pin owns the reviewer-level ctx / cost_per_m comparison.
    # Primary OR wins; if primary is not OR, the first OR fallback owns it.
    owns_metadata: bool
    pin_ctx: int | None
    pin_cost: dict | None  # {input, output} or None (CLI / unpaid)


@dataclass
class PinFinding:
    reviewer: str
    which: str
    model: str
    status: str  # ok | delisted | ctx_mismatch | cost_mismatch | both_mismatch
    pin_ctx: int | None = None
    catalog_ctx: int | None = None
    pin_cost: dict | None = None
    catalog_cost: dict | None = None
    note: str = ""


@dataclass
class RefreshReport:
    findings: list[PinFinding] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # non-OR reviewers
    catalog_size: int = 0
    fetch_error: str | None = None

    @property
    def delisted(self) -> list[PinFinding]:
        return [f for f in self.findings if f.status == "delisted"]

    @property
    def mismatched(self) -> list[PinFinding]:
        return [
            f
            for f in self.findings
            if f.status in ("ctx_mismatch", "cost_mismatch", "both_mismatch")
        ]

    @property
    def ok(self) -> list[PinFinding]:
        return [f for f in self.findings if f.status == "ok"]


def collect_or_pins(cfg: dict) -> tuple[list[OrPin], list[dict]]:
    """Return (openrouter_pins, skipped_non_or_reviewers).

    A reviewer with no OpenRouter route at all is skipped (direct/CLI-only).
    Every `client: openrouter` primary/fallback becomes a pin; metadata
    ownership goes to the primary OR route if present, else the first OR
    fallback (so dual-route glm/minimax/deepseek still get their OR-pinned
    ctx/cost checked even when primary is the direct provider).
    """
    pins: list[OrPin] = []
    skipped: list[dict] = []
    for name, spec in (cfg.get("reviewers") or {}).items():
        or_routes: list[tuple[str, dict]] = []
        for which in ("primary", "fallback"):
            route = spec.get(which) or {}
            if route.get("client") == "openrouter" and route.get("model"):
                or_routes.append((which, route))
        if not or_routes:
            reason = "no OpenRouter route (direct/CLI-only — catalog cannot see it)"
            skipped.append({"reviewer": name, "reason": reason})
            continue
        # Metadata ownership: first OR route in declaration order. We append
        # primary before fallback above, so primary wins when it is OR; otherwise
        # the first OR fallback owns the reviewer-level ctx/cost pin.
        owner_which = or_routes[0][0]
        pin_ctx = spec.get("ctx")
        pin_cost = spec.get("cost_per_m")
        if not isinstance(pin_cost, dict):
            pin_cost = None
        for which, route in or_routes:
            pins.append(
                OrPin(
                    reviewer=name,
                    which=which,
                    model=str(route["model"]),
                    owns_metadata=(which == owner_which),
                    pin_ctx=pin_ctx if isinstance(pin_ctx, int) else None,
                    pin_cost=pin_cost,
                )
            )
    return pins, skipped


def catalog_cost_per_m(entry: dict) -> dict | None:
    """Convert OpenRouter per-token pricing to Argus `$ / million tokens`."""
    pricing = entry.get("pricing") or {}
    try:
        inp = round(float(pricing["prompt"]) * 1_000_000, 2)
        out = round(float(pricing["completion"]) * 1_000_000, 2)
    except (KeyError, TypeError, ValueError):
        return None
    return {"input": inp, "output": out}


def fetch_catalog(url: str = OR_MODELS_URL, timeout: float = 30.0) -> dict[str, dict]:
    """Return `{model_id: catalog_entry}` from the live OpenRouter catalog.

    Raises OSError / urllib.error.URLError / ValueError on failure.
    """
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError("OpenRouter /models response missing data[]")
    out: dict[str, dict] = {}
    for entry in data:
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    if not out:
        raise ValueError("OpenRouter /models returned an empty catalog")
    return out


def _cost_matches(pin: dict | None, catalog: dict | None, tolerance: float) -> bool:
    if pin is None:
        # CLI / null cost — nothing to compare; listing check is enough.
        return True
    if catalog is None:
        return False
    try:
        # Quantize to 0.01 $/M before comparing so an exact-tolerance delta
        # (e.g. 0.43 vs 0.45 with tolerance 0.02) is not rejected by binary
        # float noise like 0.020000000000000018.
        def _q(v: float) -> int:
            return round(float(v) * 100)

        slack = _q(tolerance)
        return (
            abs(_q(pin.get("input", 0)) - _q(catalog.get("input", 0))) <= slack
            and abs(_q(pin.get("output", 0)) - _q(catalog.get("output", 0))) <= slack
        )
    except (TypeError, ValueError):
        return False


def diff_pins(
    pins: list[OrPin],
    catalog: dict[str, dict],
    *,
    cost_tolerance: float = DEFAULT_COST_TOLERANCE,
) -> list[PinFinding]:
    """Diff collected pins against a catalog map. Pure — easy to unit-test."""
    findings: list[PinFinding] = []
    for pin in pins:
        entry = catalog.get(pin.model)
        if entry is None:
            findings.append(
                PinFinding(
                    reviewer=pin.reviewer,
                    which=pin.which,
                    model=pin.model,
                    status="delisted",
                    pin_ctx=pin.pin_ctx,
                    pin_cost=pin.pin_cost,
                    note="slug not in OpenRouter catalog — same failure mode as "
                    "xiaomi/mimo-v2-pro (silent death on every dispatch)",
                )
            )
            continue

        cat_ctx = entry.get("context_length")
        if isinstance(cat_ctx, float) and cat_ctx.is_integer():
            cat_ctx = int(cat_ctx)
        cat_cost = catalog_cost_per_m(entry)

        # Non-owner pins (OR fallbacks when primary is also OR): listing only.
        if not pin.owns_metadata:
            findings.append(
                PinFinding(
                    reviewer=pin.reviewer,
                    which=pin.which,
                    model=pin.model,
                    status="ok",
                    pin_ctx=pin.pin_ctx,
                    catalog_ctx=cat_ctx if isinstance(cat_ctx, int) else None,
                    pin_cost=pin.pin_cost,
                    catalog_cost=cat_cost,
                    note="listed (fallback — metadata owned by primary OR pin)",
                )
            )
            continue

        ctx_ok = pin.pin_ctx is None or pin.pin_ctx == cat_ctx
        cost_ok = _cost_matches(pin.pin_cost, cat_cost, cost_tolerance)

        if ctx_ok and cost_ok:
            status = "ok"
            if pin.pin_cost is None and pin.pin_ctx is None:
                note = "listed (no ctx/cost pin to compare)"
            elif pin.pin_cost is None:
                note = "listed; ctx match (cost not pinned — CLI/null)"
            elif pin.pin_ctx is None:
                note = "listed; cost match (ctx not pinned)"
            else:
                note = "listed; ctx/cost match"
        elif not ctx_ok and not cost_ok:
            status = "both_mismatch"
            note = "ctx and cost_per_m differ from catalog"
        elif not ctx_ok:
            status = "ctx_mismatch"
            note = "ctx differs from catalog context_length"
        else:
            status = "cost_mismatch"
            note = "cost_per_m differs from catalog pricing"

        findings.append(
            PinFinding(
                reviewer=pin.reviewer,
                which=pin.which,
                model=pin.model,
                status=status,
                pin_ctx=pin.pin_ctx,
                catalog_ctx=cat_ctx if isinstance(cat_ctx, int) else None,
                pin_cost=pin.pin_cost,
                catalog_cost=cat_cost,
                note=note,
            )
        )
    return findings


def run_refresh(
    cfg: dict | None = None,
    catalog: dict[str, dict] | None = None,
    *,
    cost_tolerance: float = DEFAULT_COST_TOLERANCE,
    catalog_url: str = OR_MODELS_URL,
) -> RefreshReport:
    """Build a full report. Pass `catalog` to skip the network (tests)."""
    report = RefreshReport()
    cfg = cfg or load_config()
    pins, skipped = collect_or_pins(cfg)
    report.skipped = skipped

    if catalog is None:
        try:
            catalog = fetch_catalog(catalog_url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            report.fetch_error = f"{type(e).__name__}: {e}"
            return report

    report.catalog_size = len(catalog)
    report.findings = diff_pins(pins, catalog, cost_tolerance=cost_tolerance)
    return report


def exit_code(report: RefreshReport) -> int:
    if report.fetch_error:
        return 3
    if report.delisted:
        return 2
    if report.mismatched:
        return 1
    return 0


def _fmt_cost(c: dict | None) -> str:
    if not c:
        return "—"
    return f"{c.get('input')}/{c.get('output')}"


def print_human(report: RefreshReport) -> None:
    if report.fetch_error:
        sys.stderr.write(f"FAIL: could not fetch OpenRouter catalog: {report.fetch_error}\n")
        return

    print(
        f"OpenRouter catalog pin diff  (catalog size={report.catalog_size}, "
        f"pins checked={len(report.findings)}, skipped non-OR={len(report.skipped)})"
    )
    print(
        f"{'STATUS':<14} {'REVIEWER':<16} {'WHICH':<9} {'MODEL':<42} "
        f"{'CTX pin→cat':<22} {'COST$/M pin→cat':<24} NOTE"
    )
    for f in report.findings:
        ctx = f"{f.pin_ctx}→{f.catalog_ctx}"
        cost = f"{_fmt_cost(f.pin_cost)}→{_fmt_cost(f.catalog_cost)}"
        label = {
            "ok": "OK",
            "delisted": "DELISTED",
            "ctx_mismatch": "CTX",
            "cost_mismatch": "COST",
            "both_mismatch": "CTX+COST",
        }.get(f.status, f.status.upper())
        print(
            f"{label:<14} {f.reviewer:<16} {f.which:<9} {f.model:<42} "
            f"{ctx:<22} {cost:<24} {f.note}"
        )

    if report.skipped:
        print("\nSkipped (not OpenRouter-routed — catalog cannot see these):")
        for s in report.skipped:
            print(f"  - {s['reviewer']}: {s['reason']}")

    print()
    n_ok, n_mis, n_del = len(report.ok), len(report.mismatched), len(report.delisted)
    print(f"Summary: {n_ok} ok, {n_mis} mismatched, {n_del} delisted")
    if n_del:
        sys.stderr.write(
            "\nDELISTED pins will 404 on every dispatch (mimo-silent-death class). "
            "Update the slug in config.yaml.\n"
        )
    elif n_mis:
        sys.stderr.write(
            "\nMismatched ctx/cost_per_m: update the pin in config.yaml to match "
            "the live catalog (or accept the drift consciously).\n"
        )


def print_json(report: RefreshReport) -> None:
    payload: dict[str, Any] = {
        "catalog_size": report.catalog_size,
        "fetch_error": report.fetch_error,
        "findings": [asdict(f) for f in report.findings],
        "skipped": report.skipped,
        "summary": {
            "ok": len(report.ok),
            "mismatched": len(report.mismatched),
            "delisted": len(report.delisted),
        },
        "exit_code": exit_code(report),
        "coverage": (
            "OpenRouter-routed pins only; direct/CLI-only slugs are skipped "
            "(same caveat as the 2026-09-22 roster refresh)."
        ),
    }
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Diff OpenRouter-routed config.yaml pins against the live catalog."
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_COST_TOLERANCE,
        help=f"absolute $/M slack for cost_per_m (default {DEFAULT_COST_TOLERANCE})",
    )
    ap.add_argument(
        "--url",
        default=OR_MODELS_URL,
        help="catalog URL override (tests / mirrors)",
    )
    args = ap.parse_args(argv)

    report = run_refresh(cost_tolerance=args.tolerance, catalog_url=args.url)
    if args.json:
        print_json(report)
    else:
        print_human(report)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
