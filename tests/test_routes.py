"""Unit tests for route-preference resolution in scripts/_common.py.

Covers resolve_routes (direct↔OpenRouter reordering) and
resolve_route_preference (CLI > env > config precedence).

Run: python -m pytest tests/ -q
Or:  python tests/test_routes.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import (  # noqa: E402
    resolve_routes,
    resolve_route_preference,
    _route_kind,
)

DIRECT = {"route": "aichat", "client": "zai", "model": "glm-5.2"}
OR = {"route": "aichat", "client": "openrouter", "model": "z-ai/glm-5.2"}
CLI = {"route": "codex-cli"}
ORFB = {"route": "aichat", "client": "openrouter", "model": "openai/gpt-5.4"}


def test_route_kind():
    assert _route_kind(DIRECT) == "direct"
    assert _route_kind(OR) == "openrouter"
    assert _route_kind(CLI) == "cli"
    assert _route_kind(None) is None


def test_dual_route_openrouter_preference():
    # Declared direct-first, but openrouter preference puts OR first.
    spec = {"primary": DIRECT, "fallback": OR}
    p, f = resolve_routes(spec, "openrouter")
    assert p is OR and f is DIRECT


def test_dual_route_direct_preference():
    spec = {"primary": DIRECT, "fallback": OR}
    p, f = resolve_routes(spec, "direct")
    assert p is DIRECT and f is OR


def test_dual_route_declared_or_first_still_reorders():
    # Declaration order must not matter — preference wins.
    spec = {"primary": OR, "fallback": DIRECT}
    p, f = resolve_routes(spec, "direct")
    assert p is DIRECT and f is OR


def test_cli_reviewer_never_reordered():
    # CLI primary + OR fallback must keep CLI primary under BOTH preferences,
    # so a free CLI sub is never demoted below a paid OpenRouter fallback.
    spec = {"primary": CLI, "fallback": ORFB}
    for pref in ("openrouter", "direct"):
        p, f = resolve_routes(spec, pref)
        assert p is CLI and f is ORFB


def test_single_route_unaffected():
    spec = {"primary": OR}
    p, f = resolve_routes(spec, "direct")
    assert p is OR and f is None


def test_unknown_preference_falls_back_to_openrouter():
    spec = {"primary": DIRECT, "fallback": OR}
    p, f = resolve_routes(spec, "bogus")
    assert p is OR and f is DIRECT


def test_preference_precedence(monkeypatch=None):
    cfg = {"defaults": {"route_preference": "direct"}}
    # config value used when no CLI/env
    os.environ.pop("ARGUS_ROUTE_PREF", None)
    assert resolve_route_preference(None, cfg) == "direct"
    # env overrides config
    os.environ["ARGUS_ROUTE_PREF"] = "openrouter"
    assert resolve_route_preference(None, cfg) == "openrouter"
    # CLI overrides env + config
    assert resolve_route_preference("direct", cfg) == "direct"
    # unknown env value falls back to openrouter
    os.environ["ARGUS_ROUTE_PREF"] = "nonsense"
    assert resolve_route_preference(None, cfg) == "openrouter"
    os.environ.pop("ARGUS_ROUTE_PREF", None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all route tests passed")
