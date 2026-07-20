"""Shared fixtures for autoresearch workflow tests.

[v1.0] Provided 4 fixtures: base_state, mock_subprocess, mock_git, tmp_project.

[v1.3 P2-4] All 4 fixtures removed — they were defined but NEVER imported by
any test file (verified via grep). Each test in test_graph.py and
test_loop_integration.py builds its own state inline (via `_default_state`
or `dict(ar_state)`) or patches the node function directly. The dead
fixtures were misleading future contributors into thinking they were the
"blessed" way to mock autoresearch tests.

This file is intentionally kept (not deleted) so it remains as the natural
attachment point for future shared autoresearch fixtures (e.g. a
`mocked_llm_subagent` fixture once the planner retry path in P1-2 is
exercised by integration tests).
"""
from __future__ import annotations

# Reserved for future shared autoresearch fixtures.
# See test_loop_integration.py for the current per-test fixture pattern
# (each test builds its own state via `_default_state` and patches the
# specific node function it wants to mock).
