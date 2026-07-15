"""Shared fixtures for workflow tool tests.

All workflow infrastructure is fully mocked — no real LLM calls, no real
workflow execution, no real router calls, no real checkpoint reads.

Patches four surfaces so action handlers + type handlers can be tested in
isolation:
  - tracer — patched in every module that imports it directly:
      tools.workflow.tracer
      tools.workflow_ops.helpers.tracer
      tools.workflow_ops.types.auto.tracer
  - core.router.router.route — auto-routing for type="auto"
  - workflows.base.run_workflow — the actual workflow execution engine
  - core.observability.checkpoint.get_latest — checkpoint lookups for status

[DESIGN] WHY patch tracer in three places: Python's `from x import y`
creates a local binding to the object y refers to AT IMPORT TIME. Patching
`core.tracer.tracer` after import doesn't affect existing bindings. Each
module that did `from core.tracer import tracer` has its own `tracer` name
that must be patched individually. The ExitStack pattern below patches all
of them simultaneously so a single `mock_tracer` fixture covers everything.
"""
from __future__ import annotations

import pytest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch


# Modules that bind `tracer` directly via `from core.tracer import tracer`.
# All of them must be patched simultaneously so any code path that touches
# the tracer gets the mock.
_TRACER_PATCH_TARGETS = (
    "tools.workflow.tracer",
    "tools.workflow_ops.helpers.tracer",
    "tools.workflow_ops.types.auto.tracer",
    # [v1.0-fix] history.py and status.py do lazy `from core.tracer import tracer`
    # inside the function body. Patching the source module ensures those lazy
    # imports get the mock too.
    "core.tracer.tracer",
)


@pytest.fixture
def mock_tracer():
    """Patch the tracer singleton as seen by every workflow module.

    Default: new_trace() returns "test-trace-id"; step/error/warning are
    no-ops. Tests can override return_value or assert on call_args.
    """
    # [v1.0-fix] Use a SINGLE MagicMock shared across all patch targets so
    # tests that override return_value (e.g. new_trace.return_value) affect
    # ALL modules, not just the first one.
    shared_mock = MagicMock()
    shared_mock.new_trace.return_value = "test-trace-id"
    shared_mock.step.return_value = None
    shared_mock.error.return_value = None
    shared_mock.warning.return_value = None
    shared_mock.summary.return_value = {"steps": 0}
    shared_mock.recent.return_value = []

    with ExitStack() as stack:
        for target in _TRACER_PATCH_TARGETS:
            stack.enter_context(patch(target, shared_mock))
        yield shared_mock


@pytest.fixture
def mock_router():
    """Patch core.router.router.route for testing type='auto' routing.

    Default: returns a mock RoutingDecision with workflow="research",
    confidence="high", clarifying_questions=[].

    Tests can override return_value to simulate different routing outcomes:
      - decision.workflow = "direct"  → routed status
      - decision.confidence = "low"   → needs_clarification status
      - side_effect = RuntimeError()  → router failure
    """
    with patch("core.router.router.route") as mock_route:
        decision = make_mock_decision()
        mock_route.return_value = decision
        yield mock_route


@pytest.fixture
def mock_run_workflow():
    """Patch workflows.base.run_workflow — the actual workflow execution.

    Default: returns {"status": "success", "result": "done"}.

    Tests can override return_value or set side_effect to simulate crashes.
    """
    with patch("workflows.base.run_workflow") as mock:
        mock.return_value = {"status": "success", "result": "done"}
        yield mock


@pytest.fixture
def mock_checkpoint():
    """Patch core.observability.checkpoint.get_latest for status action tests.

    Default: returns None (no checkpoint found).

    Tests can override return_value to simulate a checkpoint existing.
    """
    with patch("core.observability.checkpoint.get_latest", return_value=None) as mock:
        yield mock


def make_mock_decision(
    *,
    workflow: str = "research",
    confidence: str = "high",
    clarifying_questions=None,
    tool: str = "",
    reason: str = "",
):
    """Build a mock RoutingDecision-like object for router.route.return_value.

    Mirrors the shape of core.router.RoutingDecision used by the workflow
    tool's auto-routing path.
    """
    mock = MagicMock()
    mock.workflow = workflow
    mock.confidence = confidence
    mock.clarifying_questions = clarifying_questions or []
    mock.tool = tool
    mock.reason = reason
    return mock
