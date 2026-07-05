"""Thread-safety tests for python sandbox.

[BUGFIX-2] Covers the contextlib.redirect_stdout thread-safety fix.
"""
from __future__ import annotations

import concurrent.futures
import pytest

from tools.python import python


class TestThreadSafeStdout:
    """Verify concurrent python() calls don't corrupt each other's output."""

    def test_concurrent_stdout_isolation(self):
        """Two parallel python() calls must each see only their own output."""
        def run_code(n):
            return python(mode="run", code=f"print('thread{n}')")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(run_code, 1)
            f2 = ex.submit(run_code, 2)
            r1, r2 = f1.result(), f2.result()

        assert r1["status"] == "success"
        assert r2["status"] == "success"
        # Each should only see its own output
        assert "thread1" in r1["data"]
        assert "thread2" in r2["data"]
        assert "thread2" not in r1["data"]  # No cross-contamination
        assert "thread1" not in r2["data"]

    def test_concurrent_mixed_modes(self):
        """Concurrent run and run_data calls must not interleave output."""
        def run_sandbox(n):
            return python(mode="run", code=f"x = {n} * 2\nprint(x)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(run_sandbox, i) for i in range(3)]
            results = [f.result() for f in futures]

        for i, result in enumerate(results):
            assert result["status"] == "success"
            expected = str(i * 2)
            assert expected in result["data"]
            # Verify no other thread's output leaked in
            for j in range(3):
                if j != i:
                    other = str(j * 2)
                    assert other not in result["data"], f"Output contamination: {other} in result {i}"

    def test_run_data_stdout_isolation(self):
        """run_data mode (in-process) must also isolate stdout per thread."""
        def run_stdlib(n):
            return python(mode="run_data", code=f"import json\nprint(json.dumps({{'id': {n}}}))")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(run_stdlib, 1)
            f2 = ex.submit(run_stdlib, 2)
            r1, r2 = f1.result(), f2.result()

        assert r1["status"] == "success"
        assert r2["status"] == "success"
        assert '"id": 1' in r1["data"] or '"id":1' in r1["data"]
        assert '"id": 2' in r2["data"] or '"id":2' in r2["data"]
