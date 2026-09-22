"""Unit tests for reviewer-name aliasing in scripts/_common.py.

Reviewer keys went version-free on 2026-09-22 (glm-5.2 -> glm). `aliases:` in
config.yaml keeps every previously-valid roster string working. These tests
pin the behaviour that makes that safe:

  - legacy names resolve to the canonical key
  - a real registry key always beats the alias map
  - unknown names pass through (callers own the error message)
  - mixing a legacy name and its canonical key dispatches ONE reviewer, not two
  - the shipped config.yaml is internally consistent

Run: python -m pytest tests/ -q
Or:  python tests/test_aliases.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import (  # noqa: E402
    canonical_reviewer,
    canonicalize_roster,
    load_config,
    resolve_roster,
)

# Minimal synthetic config — keeps these tests independent of registry churn.
CFG = {
    "defaults": {"profile": "std"},
    "reviewers": {
        "glm": {"tier": "paid", "privacy": "ok"},
        "kimi": {"tier": "paid", "privacy": "ok"},
        "grok-longctx": {"tier": "paid", "privacy": "ok", "custom_only": True},
    },
    "aliases": {"glm-5.2": "glm", "kimi-k2.6": "kimi", "grok-4.20": "grok-longctx"},
    "profiles": {"std": {"members": ["glm", "kimi"]}},
    "host_rules": {"unknown": {"skip": [], "add": []}},
}


def test_legacy_name_resolves_to_canonical():
    assert canonical_reviewer(CFG, "glm-5.2") == "glm"
    assert canonical_reviewer(CFG, "kimi-k2.6") == "kimi"


def test_canonical_name_is_identity():
    assert canonical_reviewer(CFG, "glm") == "glm"


def test_registry_key_beats_alias_map():
    """A name that IS a registry key must never be rewritten by the alias map.

    This lets a future reviewer reuse a retired name without the stale alias
    silently hijacking it.
    """
    cfg = dict(CFG, reviewers={**CFG["reviewers"], "glm-5.2": {"tier": "paid"}})
    assert canonical_reviewer(cfg, "glm-5.2") == "glm-5.2"


def test_unknown_name_passes_through():
    # Callers own the "not in registry" error, so the message names what the
    # user actually typed rather than a mangled version of it.
    assert canonical_reviewer(CFG, "nope") == "nope"


def test_roster_dedupes_alias_and_canonical():
    """glm-5.2 + glm is ONE reviewer.

    Dispatching it twice would make it a self-corroborating voter in merge.py
    and let its solo findings clear the confidence threshold on their own.
    """
    assert canonicalize_roster(CFG, ["glm-5.2", "glm", "kimi"]) == ["glm", "kimi"]


def test_roster_preserves_order():
    assert canonicalize_roster(CFG, ["kimi-k2.6", "glm-5.2"]) == ["kimi", "glm"]


def test_resolve_roster_accepts_legacy_custom_names():
    roster, drops = resolve_roster(
        CFG, "custom", ["glm-5.2", "kimi-k2.6"], "unknown", explicit=True
    )
    assert roster == ["glm", "kimi"]
    assert drops == []


def test_resolve_roster_legacy_name_waives_custom_only_when_explicit():
    """--custom "grok-4.20" must still reach the custom_only reviewer.

    The custom_only gate compares canonical keys, so aliasing has to happen
    before the gate runs or an explicitly-named legacy reviewer gets dropped.
    """
    roster, _ = resolve_roster(
        CFG, "custom", ["grok-4.20"], "unknown", explicit=True
    )
    assert roster == ["grok-longctx"]


def test_host_rules_skip_matches_canonical_key():
    cfg = dict(CFG, host_rules={"claude": {"skip": ["glm"], "add": []}})
    roster, drops = resolve_roster(cfg, "custom", ["glm-5.2", "kimi"], "claude",
                                   explicit=True)
    assert roster == ["kimi"]
    assert [n for n, _ in drops] == ["glm"]


# ── Shipped-config integrity ────────────────────────────────────────────

def test_shipped_config_aliases_and_profiles_resolve():
    cfg = load_config()
    reviewers = cfg["reviewers"]
    for old, new in cfg.get("aliases", {}).items():
        assert old not in reviewers, f"alias {old!r} shadows a real reviewer"
        assert new in reviewers, f"alias {old!r} -> unknown reviewer {new!r}"
    for pname, prof in cfg["profiles"].items():
        for member in prof["members"]:
            assert member in reviewers, f"profile {pname!r}: unknown member {member!r}"


def test_shipped_config_routes_are_wired():
    """Every declared route points at a real CLI command / aichat client."""
    cfg = load_config()
    clients = set(cfg["aichat_clients"])
    commands = set(cfg["cli_commands"])
    for name, spec in cfg["reviewers"].items():
        for slot in ("primary", "fallback"):
            route = spec.get(slot)
            if not route:
                continue
            assert route["route"] in commands, f"{name}.{slot}: bad route"
            if route["route"] == "aichat":
                assert route.get("client") in clients, f"{name}.{slot}: bad client"


def test_bench_cost_prices_legacy_reviewer_names():
    """Historical benchmark artifacts must still price correctly.

    Regression: bench_cost.py reads reviewer names from benchmark artifacts on
    disk, which is the one path that never goes through resolve_roster. A
    pre-rename run carries `glm-5.2`; a direct registry lookup missed, rates
    came back None, and the row printed as a $0 "paid CLI sub" — silently
    understating what the run cost.
    """
    from bench_cost import rates_for
    cfg = load_config()
    for legacy in ("glm-5.2", "kimi-k2.6", "qwen-3.6-plus"):
        canonical, rates, status = rates_for(cfg, legacy)
        # 'estimated' (not 'cli-sub'): the alias resolved and the reviewer is
        # metered. Whether the price is exact is a separate axis, covered by
        # test_bench_cost_prefers_rates_recorded_in_the_artifact.
        assert status == "estimated", f"{legacy} priced as {status}"
        assert rates and rates["input"] > 0, f"{legacy} resolved to no rates"


def test_bench_cost_columns_fit_the_widest_alias_label():
    """The cost table must size its columns to the data, not a fixed width.

    Regression: rows are labelled `recorded->canonical`, and
    `opencode-minimax-m3->opencode-minimax` is 36 chars against a hard-coded
    18-wide field. Python pads but never truncates, so five of the eleven
    aliases shoved every column to their right out of alignment — visible only
    on exactly the historical artifacts the alias fix was written for.
    """
    cfg = load_config()
    widest = max(len(f"{old}\u2192{new}") for old, new in cfg["aliases"].items())
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "bench_cost.py").read_text(encoding="utf-8")
    assert "{name_w}" in src and "len(r[\"reviewer\"]) for r in rows" in src, (
        "bench_cost.py must derive its reviewer column width from the rows; a "
        f"fixed width fails on the widest alias label ({widest} chars)"
    )
    # And the notes column too — it was truncating "paid CLI sub (no per-token
    # cost)" to "paid CLI sub (".
    assert "{note_w}" in src and "note[:14]" not in src


def test_bench_cost_prefers_rates_recorded_in_the_artifact():
    """A historical run must be priced at what it was billed, not today's rate.

    Regression: resolving a legacy name to the current registry fixed the $0
    under-report but introduced a different wrong number. `qwen-3.6-plus` ran
    at $0.50/$2.00; today's `qwen` is qwen3.8-max at $2.00/$6.00, so pricing
    the old run at the new rate overstates it ~3.2x. Rates recorded in the
    artifact take precedence.
    """
    from bench_cost import rates_for
    cfg = load_config()
    recorded = {"input": 0.50, "output": 2.00}
    canonical, rates, status = rates_for(cfg, "qwen-3.6-plus", recorded)
    assert canonical == "qwen"
    assert rates == recorded, "recorded rates must win over the current registry"
    assert status == "recorded"


def test_bench_cost_marks_unrecorded_rates_as_estimated():
    """Same arithmetic, weaker claim — and it must say so.

    Artifacts written before rate snapshotting cannot be costed exactly. They
    still get a number, but it must be distinguishable from an exact one so a
    total is never quoted as actual spend when it is a present-day estimate.
    """
    from bench_cost import rates_for
    cfg = load_config()
    _, rates, status = rates_for(cfg, "qwen-3.6-plus", None)
    assert status == "estimated", "unrecorded rates must not claim to be actuals"
    assert rates  # still priced, just not claimed as exact


def test_benchmark_snapshots_rates_into_new_artifacts():
    """Going forward, artifacts must carry the rates they ran under."""
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "benchmark.py").read_text(encoding="utf-8")
    assert '"rates": spec.get("cost_per_m")' in src, (
        "benchmark.py must record cost_per_m in each per-reviewer artifact so "
        "future cost reports do not depend on a registry that has since moved"
    )


def test_bench_cost_flags_cli_sub_that_fell_back_to_a_metered_route():
    """A CLI sub that fell back to OpenRouter did not cost $0.

    Regression: the artifact snapshot records the reviewer-level cost_per_m,
    which is null for CLI-sub reviewers. But `_dispatch` falls back from a
    failed CLI to the metered OpenRouter route, spending real money that
    config.yaml has no price for. Reporting that run as a $0 "paid CLI sub"
    under-reports spend exactly the way the original null-rate lookup did.
    """
    from bench_cost import rates_for
    cfg = load_config()
    _, _, status = rates_for(cfg, "codex", None, fallback_calls=2)
    assert status == "mixed", "metered fallback on a CLI sub must not read as $0"
    # No fallback: genuinely free, and must still say so.
    _, _, clean = rates_for(cfg, "codex", None, fallback_calls=0)
    assert clean == "cli-sub"


def test_rates_for_docstring_lists_every_status_it_returns():
    """The documented contract must match the values callers can receive."""
    import bench_cost
    doc = bench_cost.rates_for.__doc__ or ""
    for status in ("recorded", "estimated", "mixed", "cli-sub", "unknown"):
        assert f"'{status}'" in doc, f"status {status!r} missing from docstring"
    assert "'metered'" not in doc, "docstring still lists the removed 'metered' status"


def test_bench_cost_separates_unknown_from_free_cli():
    """$0 for a CLI sub and $0 for an unpriceable name must not look alike.

    Both cost nothing in the report, but the first is a real price and the
    second is a missing one. Collapsing them is how a reviewer disappears into
    a total that reads as complete.
    """
    from bench_cost import rates_for
    cfg = load_config()
    assert rates_for(cfg, "codex")[2] == "cli-sub"
    assert rates_for(cfg, "no-such-reviewer-anywhere")[2] == "unknown"


# Reviewer names as recorded in this repo's reference benchmark (README.md
# "Reference benchmark" table and docs/benchmarks.html). These are the
# historical artifact names bench_cost.py must still be able to price.
DOCUMENTED_HISTORICAL_NAMES = [
    "opencode", "qwen-3.6-plus", "glm-5.1", "gemini-or", "minimax-m2.7",
    "mimo-v2-pro", "codex", "deepseek-v3.2", "grok-4.20", "hermes-4.3",
    "kimi-k2.6",
]


def test_every_documented_historical_name_is_priceable():
    """The repo's own documented benchmark must still cost cleanly.

    Regression: `glm-5.1` and `minimax-m2.7` appear in the reference
    leaderboard but had no aliases, so bench_cost.py marked them `unknown`,
    dropped them from the total, and — once unknown names became fatal —
    exited 1. The historical-compatibility promise has to cover at minimum
    the artifacts this repository documents.

    'estimated' is the expected status for most of these: the run predates
    rate snapshotting, so it is priced at current rates and labelled as an
    estimate. What must never happen is 'unknown'.
    """
    from bench_cost import rates_for
    cfg = load_config()
    unknown = [n for n in DOCUMENTED_HISTORICAL_NAMES
               if rates_for(cfg, n)[2] == "unknown"]
    assert not unknown, (
        "documented benchmark reviewers cannot be priced (no alias, not in "
        f"registry): {unknown}"
    )


def test_docs_registry_table_lists_every_reviewer():
    """The generated reviewer table must cover the whole registry.

    Regression: the docs page advertised a reviewer count taken from
    config.yaml while its table still omitted `opencode-minimax` and
    `opencode-glm`, so the generated reference contradicted itself. Adding a
    reviewer without a table row is the easy way to reintroduce that.
    """
    import re
    cfg = load_config()
    src = (Path(__file__).resolve().parent.parent
           / "docs" / "build_content.py").read_text(encoding="utf-8")
    start = src.index("<thead><tr><th>Reviewer</th><th>Route(s)</th>")
    table = src[start:src.index("</tbody>", start)]
    listed = set(re.findall(r"<tr><td><code>([a-z0-9.\-]+)</code>", table))
    missing = sorted(set(cfg["reviewers"]) - listed)
    assert not missing, f"reviewers absent from the docs registry table: {missing}"


def test_grok_legacy_alias_preserves_the_2m_window():
    """grok-4.20 must NOT map to `grok` (Grok 4.7, 500K ctx).

    The old key named the 2M-context model specifically; remapping it to the
    newer-but-smaller flagship would silently shrink an existing roster's
    context window, which is the one thing that reviewer exists to provide.
    """
    cfg = load_config()
    target = cfg["aliases"]["grok-4.20"]
    assert cfg["reviewers"][target]["ctx"] == 2_000_000


# Aliases whose LEGACY reviewer was already custom_only before the version-free
# rename. For these, resolving to a custom_only target preserves the old
# behaviour rather than regressing it, so they're exempt from the check below.
ALREADY_CUSTOM_ONLY = {
    "hermes-4.3", "opencode-minimax-m3", "opencode-glm-5.2", "copilot-gpt5",
}


def test_alias_does_not_newly_gate_a_previously_open_reviewer():
    """An alias must not turn a formerly profile-eligible reviewer custom_only.

    Regression: `grok-4.20` was a normal reviewer before the rename, and its
    alias target `grok-longctx` was briefly marked `custom_only`. Profile
    resolution is non-explicit, so a saved profile (--save-as) holding the
    legacy name resolved the alias and *then* had the reviewer dropped by the
    custom_only gate — silently losing it while advertising backward
    compatibility.

    Aliases in ALREADY_CUSTOM_ONLY are exempt: their legacy reviewers carried
    the same gate, so nothing changed for them.
    """
    cfg = load_config()
    trapped = [
        f"{old} -> {new}"
        for old, new in cfg.get("aliases", {}).items()
        if old not in ALREADY_CUSTOM_ONLY
        and cfg["reviewers"][new].get("custom_only")
    ]
    assert not trapped, (
        "alias newly gates a reviewer behind custom_only, so a saved profile "
        f"using the legacy name silently loses it: {trapped}"
    )


def test_saved_profile_with_legacy_names_keeps_every_reviewer():
    """End-to-end guard for the same regression, via resolve_roster."""
    cfg = load_config()
    cfg = dict(cfg, profiles={**cfg["profiles"],
                              "_saved": {"members": ["glm-5.2", "grok-4.20"]}})
    roster, drops = resolve_roster(cfg, "profile", ["_saved"], "unknown")
    assert roster == ["glm", "grok-longctx"], f"roster={roster} drops={drops}"
    assert drops == []


def test_verify_fails_when_a_name_was_never_verified():
    """An unknown reviewer must fail the run, not merely warn.

    Regression: filtering unknown names out left an all-unknown roster with
    `results == []`, and `any([])` is False — so the exit status was 0 after
    verifying nothing. A caller gating on that exit code (CI, a wrapper
    script) would read it as "all routes reachable", which is the same
    silent-success trap the filter was added to close, one level up.
    """
    source = (Path(__file__).resolve().parent.parent
              / "scripts" / "verify.py").read_text(encoding="utf-8")
    assert 'return 1 if unknown or any(not r["ok"] for r in results) else 0' in source, (
        "verify.py exit status must account for unknown names, not just "
        "failed pings"
    )


def test_verify_canonicalizes_every_roster_source():
    """verify.py must alias profile members too, not just --roster.

    Regression: the --profile branch passed members straight to a
    `if n in reviewers` filter, so a saved profile holding legacy names
    verified *nothing* and still reported success — the same silent-omission
    failure mode that hid a delisted model slug.
    """
    import verify  # noqa: F401  (import guard: module must load cleanly)
    source = (Path(__file__).resolve().parent.parent
              / "scripts" / "verify.py").read_text(encoding="utf-8")
    # Canonicalization must happen after the branch chain, not inside one arm.
    assert "roster = canonicalize_roster(cfg, roster)" in source
    # And unknown names must be reported, never dropped in silence.
    assert "FAIL: not in registry, not verified" in source


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
