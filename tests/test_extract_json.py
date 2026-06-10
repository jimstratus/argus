"""Unit tests for scripts/_common.py::extract_json — the tolerant extractor."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import extract_json, normalize_findings  # noqa: E402


def test_direct_json():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_with_think_block():
    """Qwen3 / DeepSeek-R1 style: reasoning in <think> tags before JSON."""
    text = '<think>Let me analyze...</think>\n{"ok": true}'
    assert extract_json(text) == {"ok": True}


def test_fenced_code_block():
    text = """Here is the response:
```json
{"findings": [{"file": "a.py", "line": 1}]}
```
Done.
"""
    r = extract_json(text)
    assert isinstance(r, dict)
    assert "findings" in r
    assert len(r["findings"]) == 1


def test_embedded_in_prose():
    """Finds {...} with 'findings' key even when wrapped in prose."""
    text = 'Prose before. {"findings": [{"file": "x"}]} Prose after.'
    r = extract_json(text)
    assert r == {"findings": [{"file": "x"}]}


def test_empty_input_returns_none():
    assert extract_json("") is None
    assert extract_json(None) is None


def test_malformed_returns_none():
    assert extract_json("not json at all") is None
    assert extract_json("{broken") is None


def test_nested_objects():
    """Handles nested braces correctly when finding the balanced outer object."""
    text = '{"findings": [{"meta": {"nested": true}}]}'
    r = extract_json(text)
    assert isinstance(r, dict)
    assert r["findings"][0]["meta"]["nested"] is True


def test_brace_inside_string_value():
    """Braces inside string values must not break the balanced-brace scan."""
    text = ('Here is my review: {"findings": [{"file": "a.py", "line": 1, '
            '"description": "unmatched } and { braces in a format string"}]}')
    r = extract_json(text)
    assert isinstance(r, dict)
    assert r["findings"][0]["file"] == "a.py"


def test_escaped_quote_inside_string_value():
    text = ('prose {"findings": [{"file": "a.py", '
            '"description": "says \\"x}\\" here"}]}')
    r = extract_json(text)
    assert isinstance(r, dict)
    assert "x}" in r["findings"][0]["description"]


def test_inner_object_recovered_when_outer_braces_invalid():
    """Last-resort span scan finds a nested valid object inside brace garbage."""
    text = 'junk { junk {"a": 1} junk }'
    assert extract_json(text) == {"a": 1}


def test_brace_garbage_returns_none_fast():
    """O(n) span fallback: brace-heavy non-JSON must not take quadratic time."""
    import time
    garbage = ("{ x " * 4000) + ("} y " * 4000)
    t0 = time.monotonic()
    r = extract_json(garbage)
    assert time.monotonic() - t0 < 2.0
    assert r is None


def test_normalize_findings_clamps_unknown_severity():
    """Off-enum severities map to medium so no consumer silently drops them."""
    raw = [
        {"file": "a.py", "line": 1, "severity": "BLOCKER", "description": "x", "confidence": 90},
        {"file": "b.py", "line": 2, "severity": "high", "description": "y", "confidence": 90},
    ]
    out = normalize_findings(raw)
    assert out[0]["severity"] == "medium"
    assert out[1]["severity"] == "high"


if __name__ == "__main__":
    import traceback
    tests = [
        test_direct_json,
        test_with_think_block,
        test_fenced_code_block,
        test_embedded_in_prose,
        test_empty_input_returns_none,
        test_malformed_returns_none,
        test_nested_objects,
        test_brace_inside_string_value,
        test_escaped_quote_inside_string_value,
        test_inner_object_recovered_when_outer_braces_invalid,
        test_brace_garbage_returns_none_fast,
        test_normalize_findings_clamps_unknown_severity,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    sys.exit(failed)
