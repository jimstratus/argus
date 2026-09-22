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
