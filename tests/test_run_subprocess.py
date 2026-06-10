"""Unit tests for scripts/_common.py::run_subprocess — timeout + tree-kill."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import run_subprocess  # noqa: E402

HAS_BASH = shutil.which("bash") is not None


def test_success_passes_stdin_and_captures_stdout():
    if not HAS_BASH:
        return
    rc, out, err, dt = asyncio.run(run_subprocess(["bash", "-c", "cat"], "hello", 10))
    assert rc == 0
    assert out == "hello"


def test_timeout_returns_124_promptly():
    if not HAS_BASH:
        return
    t0 = time.monotonic()
    rc, out, err, dt = asyncio.run(run_subprocess(["bash", "-c", "sleep 30"], "", 1))
    assert rc == 124
    assert "timeout" in err
    assert time.monotonic() - t0 < 10  # killed, not waited out


def test_timeout_kills_grandchildren():
    """A shell that spawns a sleeping child must not leave the child running
    after timeout — the .cmd-shim hang that got the gemini reviewer disabled."""
    if not HAS_BASH or os.name == "nt":
        return
    import tempfile
    pidfile = tempfile.NamedTemporaryFile(suffix=".pid", delete=False).name
    try:
        rc, out, err, dt = asyncio.run(
            run_subprocess(["bash", "-c", f"sleep 30 & echo $! > {pidfile}; wait"], "", 1)
        )
        assert rc == 124
        child_pid = int(Path(pidfile).read_text().strip())
        time.sleep(0.5)  # let init reap the reparented child
        try:
            os.kill(child_pid, 0)
            alive = Path(f"/proc/{child_pid}/stat").read_text().split()[2] != "Z"
        except (ProcessLookupError, FileNotFoundError):
            alive = False
        assert not alive, f"grandchild {child_pid} survived the tree kill"
    finally:
        os.unlink(pidfile)


def test_command_not_found_returns_127():
    rc, out, err, dt = asyncio.run(run_subprocess(["argus-no-such-binary-xyz"], "", 5))
    assert rc == 127


if __name__ == "__main__":
    import traceback
    tests = [
        test_success_passes_stdin_and_captures_stdout,
        test_timeout_returns_124_promptly,
        test_timeout_kills_grandchildren,
        test_command_not_found_returns_127,
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
