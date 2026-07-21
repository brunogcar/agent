"""tests/workflows/understand/test_route_after_init.py

[v1.4.1 P0-1] Tests for the route_after_init conditional edge function.

Routes to "discover" on success (status != "failed") and "end" on failure
(status == "failed"). Mirrors the autoresearch route_after_setup pattern.

[v1.4.2] Added test_init_failure_stops_at_init — an integration test that
runs the real graph (no mocking) with a project path that has no `code/`
dir. Verifies that init failure short-circuits to END (discover/parse/report
don't run) — i.e., no kg.db, no files_parsed, no files_to_parse populated.
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


class TestInitFailureStopsAtInit:
    """[v1.4.2] Integration test: real graph + bad project_path → stops at init.

    Runs the full LangGraph (no mocking) with a project_path that has no
    `code/` subdirectory. node_init_project returns status="failed" (source
    root missing), route_after_init routes to END, and discover/parse/report
    don't run.

    Verifies:
      - final state has status="failed"
      - errors mention "Source root does not exist"
      - kg.db file was NOT created (init bailed before GraphStore construction)
      - files_to_parse stays empty (discover_files didn't run)
      - files_parsed stays at 0 (parse_and_store didn't run)
    """

    def test_init_failure_stops_at_init(self, tmp_path):
        from workflows.understand_impl.graph import build_understand_graph
        from workflows.understand_impl.state import _default_state

        # Create a project dir WITHOUT a code/ subdir — init will fail.
        project_path = tmp_path / "no_code_proj"
        project_path.mkdir()
        assert not (project_path / "code").exists()

        graph = build_understand_graph()
        state = _default_state(
            str(project_path),
            is_agent_root=False,
            trace_id="test-init-failure",
        )
        final_state = graph.invoke(state)

        # Init failed cleanly.
        assert final_state["status"] == "failed"
        assert len(final_state["errors"]) > 0
        assert any("Source root does not exist" in e for e in final_state["errors"]), (
            f"errors should mention missing source root, got: {final_state['errors']}"
        )

        # discover_files didn't run — files_to_parse is still the default [].
        assert final_state.get("files_to_parse", []) == [], (
            "discover_files should NOT have run after init failure"
        )

        # parse_and_store didn't run — files_parsed stays at 0.
        assert final_state.get("files_parsed", 0) == 0, (
            "parse_and_store should NOT have run after init failure"
        )

        # kg.db was NOT created — init bailed before GraphStore construction.
        # (init_project checks source_root.exists() BEFORE ensure_initialized +
        # GraphStore creation, so the .understand/ dir + kg.db never get made.)
        assert not (project_path / ".understand").exists(), (
            ".understand/ dir should NOT exist — init bailed before ensure_initialized"
        )
        assert not (project_path / ".understand" / "kg.db").exists(), (
            "kg.db should NOT exist — init bailed before GraphStore construction"
        )

