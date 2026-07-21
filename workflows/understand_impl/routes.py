"""Routing functions for the understand workflow.

[v1.4.1 P0-1] Mirrors the autoresearch pattern (workflows/autoresearch_impl/
routes.py): one router sits between init and discover so that init failures
route to END instead of falling through to discover_files.

Without this router, a `node_init_project` failure (missing source root,
project too large, GraphStore init crash) was followed by `node_discover_files`
running anyway — discovering 0 files (because the source_root is invalid or
the project hasn't been initialized), `node_parse_and_store` returning
"completed", and `node_report` emitting "✅ up to date". The user saw a
green checkmark on a workflow that never actually indexed anything.

Now: `route_after_init` checks `state["status"] == "failed"` and routes
to END. The downstream nodes also have a belt-and-suspenders defensive bail
(P1-1) so that even if a future graph refactor accidentally adds a direct
edge, the nodes themselves short-circuit cleanly.
"""
from __future__ import annotations

from workflows.understand_impl.state import UnderstandState


def route_after_init(state: UnderstandState) -> str:
    """After init: proceed to discover on success, END on failure.

    Returns:
        "discover" — init succeeded (status="running" or any non-"failed").
        "end"      — init failed (status="failed"); short-circuit to END so
                     discover/parse/report don't run on a half-initialized
                     project (no source_root, no artifact_root, no GraphStore).
    """
    if state.get("status") == "failed":
        return "end"
    return "discover"
