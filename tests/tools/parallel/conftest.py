"""Shared fixtures for parallel tool tests.

All parallel infrastructure is fully mocked — no real tool functions are
invoked. Mocks are injected directly into _TOOL_MAP so action handlers
see them via _get_tool_fn().

Patches:
  - tools.parallel_ops.tool_map._TOOL_MAP — inject mock tool callables
  - tools.parallel_ops.tool_map.PARALLEL_SAFE — extend if test needs to
    mark a mock tool as parallel-safe (default fixtures already use names
    that are in the production PARALLEL_SAFE set)
  - core.config.cfg — patch worker_timeout so dispatch resolves a known
    timeout when `timeout=-1` (the default).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_cfg():
    """Patch cfg singleton seen by tools.parallel_ops.executor.

    Default: worker_timeout=60. Tests can mutate to drive timeout paths.
    """
    with patch("tools.parallel_ops.executor.cfg") as mock:
        mock.worker_timeout = 60
        yield mock


@pytest.fixture
def mock_tools():
    """Return mock functions for common parallel-safe tool names.

    Names are chosen from the production PARALLEL_SAFE set so tests don't
    need to also patch PARALLEL_SAFE. Each mock returns a success envelope
    matching the standard ToolResult shape.
    """
    return {
        "web": MagicMock(return_value={"status": "success", "data": "web ok"}),
        "file": MagicMock(return_value={"status": "success", "data": "file ok"}),
        "python": MagicMock(return_value={"status": "success", "data": "python ok"}),
        "notify": MagicMock(return_value={"status": "success", "data": "notify ok"}),
    }


def make_mock_tool(name: str, *, return_value=None, side_effect=None) -> MagicMock:
    """Build a mock tool callable with a ToolResult-shaped default return.

    Convenience factory — tests that need a one-off mock tool can call this
    instead of constructing a MagicMock inline.
    """
    if return_value is None and side_effect is None:
        return_value = {"status": "success", "data": f"{name} ok"}
    m = MagicMock()
    if side_effect is not None:
        m.side_effect = side_effect
    else:
        m.return_value = return_value
    return m
