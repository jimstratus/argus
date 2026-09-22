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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
