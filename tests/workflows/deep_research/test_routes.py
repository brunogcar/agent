"""tests/workflows/deep_research/test_routes.py
Tests for route_after_synthesize conditional routing.
"""
from __future__ import annotations


class TestRouteAfterSynthesize:
    def test_returns_decompose_for_continuation(self):
        """Below threshold + not converged → 'decompose' (loop back)."""
        from workflows.deep_research_impl.routes import route_after_synthesize
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "completeness": 50.0,
            "completeness_threshold": 85.0,
            "knowledge_base": "Some findings",
            "_prev_knowledge": "",
            "consecutive_empty_iterations": 0,
        }
        assert route_after_synthesize(state) == "decompose"

    def test_returns_report_on_hard_cap(self):
        """iteration >= max_iterations → 'report'."""
        from workflows.deep_research_impl.routes import route_after_synthesize
        state = {
            "iteration": 10,
            "max_iterations": 10,
            "completeness": 20.0,
            "completeness_threshold": 85.0,
            "knowledge_base": "kb",
            "_prev_knowledge": "prev",
            "consecutive_empty_iterations": 0,
        }
        assert route_after_synthesize(state) == "report"

    def test_returns_report_on_stuck_loop(self):
        """consecutive_empty_iterations >= 2 → 'report'."""
        from workflows.deep_research_impl.routes import route_after_synthesize
        state = {
            "iteration": 3,
            "max_iterations": 10,
            "completeness": 20.0,
            "completeness_threshold": 85.0,
            "knowledge_base": "kb",
            "_prev_knowledge": "prev",
            "consecutive_empty_iterations": 2,
        }
        assert route_after_synthesize(state) == "report"

    def test_returns_report_on_dual_gate(self):
        """completeness >= threshold AND converged → 'report'."""
        from workflows.deep_research_impl.routes import route_after_synthesize
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "completeness": 90.0,
            "completeness_threshold": 85.0,
            # v1.1.1 (#11): route now reads state["converged"] instead of recomputing
            "converged": True,
            "consecutive_empty_iterations": 0,
        }
        assert route_after_synthesize(state) == "report"
