"""tests/workflows/understand/test_route_after_init.py

[v1.4.1 P0-1] Tests for the route_after_init conditional edge function.

Routes to "discover" on success (status != "failed") and "end" on failure
(status == "failed"). Mirrors the autoresearch route_after_setup pattern.
"""
from __future__ import annotations

from workflows.understand_impl.routes import route_after_init


class TestRouteAfterInit:
    def test_routes_to_discover_on_running(self):
        """When status is 'running' (or any non-'failed'), route to 'discover'."""
        assert route_after_init({"status": "running"}) == "discover"

    def test_routes_to_end_on_failed(self):
        """When status is 'failed', route to 'end' (short-circuit to END)."""
        assert route_after_init({"status": "failed"}) == "end"

    def test_routes_to_discover_on_completed(self):
        """Defensive: any non-'failed' status should route to 'discover'.

        init_project returns 'running' on success, but the router shouldn't
        care about the specific value — only whether init failed.
        """
        assert route_after_init({"status": "completed"}) == "discover"

    def test_routes_to_discover_on_missing_status(self):
        """Defensive: if status is missing, default to 'discover'.

        The init node always sets a status, so this shouldn't happen in
        practice — but the router should be resilient.
        """
        assert route_after_init({}) == "discover"
