"""Regression tests for _common.dispatch_with_fallback (issue #22 slice 1).

dispatch.py:_dispatch_one and benchmark.py:_dispatch were hand-synced copies
that drifted twice (exception isolation → dispatch only; served-model /
never-empty-error → benchmark only). These tests pin the shared contracts
so the two call sites cannot diverge again.

Run: python -m pytest tests/test_dispatch_fallback.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import dispatch_with_fallback  # noqa: E402


class FakeAdapter:
    """Queue of canned send() responses. Popped one per call."""

    def __init__(self, responses: list[dict], *, route: str = "aichat"):
        self.responses = list(responses)
        self.route = route
        self.calls: list[dict] = []

    async def send(self, prompt: str, route_cfg: dict, timeout: int) -> dict:
        self.calls.append({"prompt": prompt, "route_cfg": route_cfg, "timeout": timeout})
        if not self.responses:
            raise AssertionError("FakeAdapter exhausted")
        r = dict(self.responses.pop(0))
        r.setdefault("route", self.route)
        r.setdefault("stdout", "")
        r.setdefault("stderr", "")
        r.setdefault("latency_sec", 0.1)
        r.setdefault("exit_code", 0)
        return r


def _run(coro):
    return asyncio.run(coro)


def _spec(primary: dict, fallback: dict | None = None) -> dict:
    s: dict = {"primary": primary}
    if fallback is not None:
        s["fallback"] = fallback
    return s


DIRECT = {"route": "aichat", "client": "zai", "model": "glm-X"}
OR = {"route": "aichat", "client": "openrouter", "model": "z-ai/glm-X"}
CLI = {"route": "codex-cli", "model": None}
OR_FB = {"route": "aichat", "client": "openrouter", "model": "openai/gpt-fb"}


def test_primary_success_parses_findings():
    ok = {
        "exit_code": 0,
        "stdout": json.dumps({
            "findings": [{"file": "a.py", "line": 1, "severity": "high",
                          "confidence": 90, "description": "bug"}],
        }),
        "stderr": "",
        "latency_sec": 1.5,
        "route": "aichat",
    }
    adapters = {"aichat": FakeAdapter([ok])}
    r = _run(dispatch_with_fallback(
        "glm", _spec(OR), "prompt", 30, "openrouter",
        get_adapter=adapters.get,
    ))
    assert r["exit_code"] == 0
    assert r["parse_error"] is False
    assert r["fallback_used"] is False
    assert r["model"] == "z-ai/glm-X"
    assert r["route"] == "aichat"
    assert len(r["findings"]) == 1
    assert r["findings"][0]["file"] == "a.py"
    assert r["error"] is None
    assert r["latency_sec"] == 1.5
    assert r["name"] == "glm"


def test_primary_fail_fallback_success_attributes_fallback_model():
    """Past drift: a fallback-served score must not be filed under the
    primary model slug."""
    fail = {"exit_code": 1, "stdout": "", "stderr": "primary boom",
            "latency_sec": 0.5, "route": "aichat"}
    ok = {
        "exit_code": 0,
        "stdout": json.dumps({"findings": []}),
        "stderr": "",
        "latency_sec": 2.0,
        "route": "aichat",
    }
    # Single FakeAdapter queued primary-fail then fallback-ok (both aichat).
    both = FakeAdapter([fail, ok], route="aichat")
    r = _run(dispatch_with_fallback(
        "glm", _spec(DIRECT, OR), "prompt", 30, "direct",
        get_adapter=lambda route: both if route == "aichat" else None,
    ))
    assert r["fallback_used"] is True
    assert r["exit_code"] == 0
    # Under direct pref: primary=DIRECT (model glm-X), fallback=OR (z-ai/glm-X).
    # Primary failed → model must be the fallback's slug.
    assert r["model"] == "z-ai/glm-X"
    assert r["primary_exit_code"] == 1
    assert "primary boom" in r["primary_error"]
    assert r["latency_sec"] == 2.5  # 0.5 + 2.0
    assert len(both.calls) == 2


def test_both_fail_model_is_none():
    """Past drift: do NOT attribute a dual-failure zero-score to the fallback slug."""
    fail1 = {"exit_code": 1, "stderr": "p fail", "latency_sec": 0.2, "route": "aichat"}
    fail2 = {"exit_code": 2, "stderr": "fb fail", "latency_sec": 0.3, "route": "aichat"}
    both = FakeAdapter([fail1, fail2])
    r = _run(dispatch_with_fallback(
        "glm", _spec(DIRECT, OR), "prompt", 30, "direct",
        get_adapter=lambda route: both if route == "aichat" else None,
    ))
    assert r["exit_code"] == 2
    assert r["fallback_used"] is True
    assert r["model"] is None
    # route still names the last-tried fallback — do not aggregate zeros by route
    assert r["route"] == "aichat"
    assert r["error"]  # non-empty
    assert "fb fail" in r["error"]
    assert r["findings"] == []


def test_nonzero_empty_stderr_still_has_error():
    """Past drift: empty stderr must not produce error='' (stats.py false legacy)."""
    fail = {"exit_code": 7, "stderr": "", "stdout": "", "latency_sec": 0.1,
            "route": "aichat"}
    ad = FakeAdapter([fail])
    r = _run(dispatch_with_fallback(
        "qwen", _spec(OR), "prompt", 30,
        get_adapter=lambda route: ad if route == "aichat" else None,
    ))
    assert r["exit_code"] == 7
    assert r["error"]
    assert r["error"] != ""
    assert "exit 7" in r["error"]
    assert r["model"] is None


def test_parse_error_keeps_exit_zero_and_model():
    """Unparseable stdout from a successful call is parse_error, not a route fail."""
    bad = {"exit_code": 0, "stdout": "sorry I cannot help", "stderr": "",
           "latency_sec": 1.0, "route": "aichat"}
    ad = FakeAdapter([bad])
    r = _run(dispatch_with_fallback(
        "qwen", _spec(OR), "prompt", 30,
        get_adapter=lambda route: ad if route == "aichat" else None,
    ))
    assert r["exit_code"] == 0
    assert r["parse_error"] is True
    assert r["findings"] == []
    assert r["model"] == "z-ai/glm-X" or r["model"] == OR["model"]
    assert r["raw_preview"]
    assert r["error"] is None


def test_no_adapter_exit_code_one():
    """Past drift: missing adapter used to omit exit_code; merge defaulted to 0."""
    r = _run(dispatch_with_fallback(
        "ghost", _spec({"route": "no-such-route", "model": "x"}), "p", 10,
        get_adapter=lambda route: None,
    ))
    assert r["exit_code"] == 1
    assert r["model"] is None
    assert r["findings"] == []
    assert "no adapter" in r["error"]
    assert r["name"] == "ghost"


def test_cli_primary_or_fallback_updates_route():
    """Successful CLI→OR fallback must record the OR route, not the dead CLI."""
    cli_fail = {"exit_code": 1, "stderr": "cli down", "latency_sec": 0.4,
                "route": "codex-cli"}
    or_ok = {
        "exit_code": 0,
        "stdout": json.dumps({"findings": []}),
        "stderr": "",
        "latency_sec": 1.1,
        "route": "aichat",
    }
    cli_ad = FakeAdapter([cli_fail], route="codex-cli")
    or_ad = FakeAdapter([or_ok], route="aichat")
    table = {"codex-cli": cli_ad, "aichat": or_ad}

    r = _run(dispatch_with_fallback(
        "codex", _spec(CLI, OR_FB), "prompt", 30, "openrouter",
        get_adapter=table.get,
    ))
    assert r["fallback_used"] is True
    assert r["exit_code"] == 0
    assert r["route"] == "aichat"
    assert r["fallback_route"] == "aichat"
    assert r["model"] == "openai/gpt-fb"


def test_prose_object_without_findings_is_parse_error():
    """extract_json can recover {ok:true}; that is still a failed review."""
    prose = {"exit_code": 0, "stdout": 'here you go {"ok": true}',
             "stderr": "", "latency_sec": 0.5, "route": "aichat"}
    ad = FakeAdapter([prose])
    r = _run(dispatch_with_fallback(
        "qwen", _spec(OR), "p", 10,
        get_adapter=lambda route: ad if route == "aichat" else None,
    ))
    assert r["parse_error"] is True
    assert r["findings"] == []


def test_preference_reorders_dual_route_before_dispatch():
    """openrouter preference must try OR first even when declared direct-first."""
    # First call should be OR; make OR succeed so DIRECT is never called.
    or_ok = {
        "exit_code": 0,
        "stdout": json.dumps({"findings": []}),
        "latency_sec": 0.8,
        "route": "aichat",
    }
    calls_models: list[str] = []

    class Tracking(FakeAdapter):
        async def send(self, prompt, route_cfg, timeout):
            calls_models.append(route_cfg.get("model"))
            return await super().send(prompt, route_cfg, timeout)

    ad = Tracking([or_ok])
    r = _run(dispatch_with_fallback(
        "glm", _spec(DIRECT, OR), "p", 10, "openrouter",
        get_adapter=lambda route: ad if route == "aichat" else None,
    ))
    assert calls_models == ["z-ai/glm-X"], f"expected OR first, got {calls_models}"
    assert r["model"] == "z-ai/glm-X"
    assert r["fallback_used"] is False


if __name__ == "__main__":
    failed = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok {name}")
            except Exception as e:
                print(f"FAIL {name}: {e}")
                failed.append(name)
    raise SystemExit(1 if failed else 0)
