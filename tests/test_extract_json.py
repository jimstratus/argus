"""Unit tests for scripts/_common.py::extract_json — the tolerant extractor."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import extract_json  # noqa: E402


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
