"""Shared fixtures for autoresearch workflow tests.

[v1.0] Provided 4 fixtures: base_state, mock_subprocess, mock_git, tmp_project.

[v1.3 P2-4] All 4 fixtures removed — they were defined but NEVER imported by
any test file (verified via grep). Each test in test_graph.py and
test_loop_integration.py builds its own state inline (via `_default_state`
or `dict(ar_state)`) or patches the node function directly. The dead
fixtures were misleading future contributors into thinking they were the
"blessed" way to mock autoresearch tests.

[v1.3 tests] Added `ar_state` — a minimal autoresearch state pointing at a
tmp project dir. This is the single shared fixture every per-node test
file (test_nodes_setup / test_nodes_propose / test_nodes_decide /
test_nodes_run) builds on. Tests override only the fields they need by
calling `dict(ar_state)` and `state.update({...})`.

This file remains the natural attachment point for future shared
autoresearch fixtures.
"""
from __future__ import annotations

import pytest

from workflows.autoresearch_impl.state import _default_state


@pytest.fixture
def ar_state(tmp_path):
    """A default autoresearch state pointing at a temp project dir.

    Tests override only the fields they need by calling `dict(ar_state)`
    and `state.update({...})`. The fixture uses `_default_state()` so sane
    cfg defaults (metric_name="val_bpb", direction="lower", time_budget=300,
    target_file="train.py") are pulled in automatically.
    """
    return _default_state(
        goal="minimize val_bpb",
        trace_id="test-ar",
        project_root=str(tmp_path),
        target_file="train.py",
        metric_name="val_bpb",
        metric_direction="lower",
        time_budget=10,
        branch="autoresearch/test",
        results_path=str(tmp_path / "results.tsv"),
    )
