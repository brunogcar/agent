"""tests/core/router/test_router_autoresearch.py

[v1.1] Regression tests for the autoresearch routing fix.

Background: `autoresearch` was missing from `ROUTER_WORKFLOWS` in
`core/router_backend/constants.py` (only 5 workflows were listed:
research, data, autocode, deep_research, understand). This meant the
router LLM never saw autoresearch as an option, so `workflow(type="auto")`
could never route to it -- even though the autoresearch type handler
existed and `type="autoresearch"` (direct invocation) worked fine.

This file verifies:
  1. `ROUTER_WORKFLOWS` includes "autoresearch" (the bug fix).
  2. `heuristic_route()` routes autoresearch-specific goals
     ("optimize", "hyperparameter", ...) to the autoresearch workflow.
  3. `heuristic_route()` does NOT route plain research goals to
     autoresearch (the new pattern sits before the generic _RE_RESEARCH
     check at step #17, so a regression here would leak autoresearch into
     research requests).
"""
from __future__ import annotations

from core.router import ROUTER_WORKFLOWS, router
from core.router_backend.heuristics import heuristic_route


class TestRouterWorkflowsIncludesAutoresearch:
    """The bug fix: `autoresearch` MUST be in `ROUTER_WORKFLOWS`."""

    def test_router_workflows_includes_autoresearch(self):
        assert "autoresearch" in ROUTER_WORKFLOWS, (
            f"ROUTER_WORKFLOWS is missing 'autoresearch' (got {ROUTER_WORKFLOWS}). "
            "Without it, `workflow(type='auto')` can never route to autoresearch."
        )

    def test_router_workflows_has_six_entries(self):
        # Sanity: 5 (original) + 1 (autoresearch) = 6. Catches silent
        # additions/removals of other workflows at the same time.
        assert len(ROUTER_WORKFLOWS) == 6, (
            f"Expected 6 workflows, got {len(ROUTER_WORKFLOWS)}: {ROUTER_WORKFLOWS}"
        )


class TestHeuristicRoutesAutoresearch:
    """Autoresearch-specific keywords route to the autoresearch workflow."""

    def test_heuristic_routes_optimize(self, force_heuristic):
        decision = heuristic_route("optimize the learning rate of my training script")
        assert decision.workflow == "autoresearch", (
            f"Expected 'autoresearch', got '{decision.workflow}'"
        )
        assert decision.tool == "workflow"

    def test_heuristic_routes_hyperparameter(self, force_heuristic):
        decision = heuristic_route("tune the hyperparameter sweep for the model")
        assert decision.workflow == "autoresearch"
        assert decision.tool == "workflow"

    def test_heuristic_routes_via_router_facade(self, force_heuristic):
        # End-to-end via the public router.route() facade (which calls
        # heuristic_route() when the LLM is unavailable).
        decision = router.route("optimize the learning rate", trace_id="")
        assert decision.workflow == "autoresearch"
        assert decision.tool == "workflow"


class TestHeuristicDoesNotConfuseAutoresearchWithResearch:
    """Plain research goals must NOT route to autoresearch."""

    def test_heuristic_research_not_autoresearch(self, force_heuristic):
        decision = heuristic_route("research LLM frameworks")
        assert decision.workflow == "research", (
            f"Plain research goal leaked into autoresearch (got '{decision.workflow}')"
        )
        assert decision.workflow != "autoresearch"

    def test_heuristic_what_is_not_autoresearch(self, force_heuristic):
        decision = heuristic_route("what is transformer architecture")
        assert decision.workflow == "research"
        assert decision.workflow != "autoresearch"
