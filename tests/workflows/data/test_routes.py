"""tests/workflows/data/test_routes.py
Tests for the data workflow routing functions.
"""
from __future__ import annotations

from workflows.data_impl.routes import route_after_execute


class TestRouteAfterExecute:
    def test_returns_failed_when_exec_error_set(self):
        """Execution failure (exec_error set) must route to END."""
        assert route_after_execute({"exec_error": "SyntaxError: ..."}) == "failed"

    def test_returns_critique_when_no_exec_error(self):
        """Successful execution must route to critique."""
        assert route_after_execute({"exec_error": ""}) == "critique"
        assert route_after_execute({}) == "critique"

    def test_route_after_critique_removed(self):
        """[Fix #10] route_after_critique was dead code (always returned 'store')."""
        from workflows.data_impl import routes
        assert not hasattr(routes, "route_after_critique"), (
            "route_after_critique must be removed — it always returned 'store' (dead code)"
        )
