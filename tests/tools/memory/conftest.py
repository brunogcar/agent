"""Shared fixtures for memory tool tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import tools.memory_ops.state as mem_state


@pytest.fixture(autouse=True)
def reset_memory_state():
    """Reset all memory module state before each test."""
    mem_state.reset_state()
    yield
    mem_state.reset_state()


@pytest.fixture
def mock_cfg():
    """Patch cfg attributes used by memory actions."""
    with patch("tools.memory_ops.helpers.cfg") as mock_cfg:
        mock_cfg.memory_max_entry_bytes = 50000  # 50KB
        mock_cfg.max_tags_per_entry = 6
        mock_cfg.max_tag_length = 50
        yield mock_cfg


@pytest.fixture
def mock_store(request):
    """Mock the lazy-loaded memory store in ALL action modules.
    v1.1: Uses request.addfinalizer for safer cleanup if yield raises.
    """
    store = MagicMock()
    store.store.return_value = {"status": "stored", "id": "test-id"}
    store.recall.return_value = [{"id": "1", "text": "result", "score": 0.9}]
    store.recall_context.return_value = "Formatted memory context for prompt injection."
    store.delete.return_value = {"status": "deleted", "count": 1}
    store.prune.return_value = {"status": "pruned", "would_delete": 5}
    store.summarize.return_value = {"status": "summarized"}
    store.stats.return_value = {
        "episodic": {"count": 10},
        "semantic": {"count": 20},
        "procedural": {"count": 5},
    }

    # Patch _mem in helpers AND all action modules that import it
    patches = [
        patch("tools.memory_ops.helpers._mem", return_value=store),
        patch("tools.memory_ops.actions.store._mem", return_value=store),
        patch("tools.memory_ops.actions.recall._mem", return_value=store),
        patch("tools.memory_ops.actions.recall_context._mem", return_value=store),
        patch("tools.memory_ops.actions.delete._mem", return_value=store),
        patch("tools.memory_ops.actions.prune._mem", return_value=store),
        patch("tools.memory_ops.actions.summarize._mem", return_value=store),
        patch("tools.memory_ops.actions.stats._mem", return_value=store),
    ]
    for p in patches:
        p.start()

    def cleanup():
        for p in patches:
            p.stop()
    request.addfinalizer(cleanup)

    yield store
