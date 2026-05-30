"""tests/core/memory/test_checkpoint.py — Hardening tests for sanitize_state & checkpointing."""
from __future__ import annotations
from unittest.mock import patch
import json
import time
import os
from decimal import Decimal
from datetime import datetime, timedelta, time as dt_time
from uuid import UUID, uuid4
from workflows.helpers.checkpoint import sanitize_state, CHECKPOINT_DIR

def test_circular_ref_only_on_containers():
    """Interned strings must NOT trigger circular reference detection."""
    state = ["ok", "ok", "ok"]
    result = sanitize_state(state)
    assert result == ["ok", "ok", "ok"], "False positive circular ref on interned strings"
    
def test_genuine_circular_ref_detected():
    """Nested dicts must still be caught."""
    a = {}
    a["self"] = a
    result = sanitize_state(a)
    assert result["self"] == "<circular_reference>", "Genuine circular ref not detected"

def test_decimal_precision_preserved():
    """Decimal must convert to str, not float, to avoid precision loss."""
    state = {"price": Decimal("19.9999999999")}
    result = sanitize_state(state)
    assert result["price"] == "19.9999999999", "Decimal lost precision"

def test_set_determinism():
    """Sets must serialize in sorted order for reproducible checkpoints."""
    state = {"tags": {"zebra", "apple", "mango"}}
    result = sanitize_state(state)
    assert result["tags"] == ["apple", "mango", "zebra"], "Set not sorted deterministically"
    
    # Unorderable types fallback
    state2 = {"mixed": {1, "a"}}
    result2 = sanitize_state(state2)
    assert isinstance(result2["mixed"], list), "Fallback set conversion failed"

def test_datetime_and_uuid_coercion():
    """All edge-case types must serialize to JSON-safe primitives."""
    state = {
        "dt": datetime(2026, 5, 14, 12, 0),
        "t": dt_time(12, 30, 15),
        "delta": timedelta(hours=2, minutes=15),
        "uid": UUID("12345678-1234-5678-1234-567812345678"),
    }
    result = sanitize_state(state)
    assert isinstance(result["dt"], str) and "2026-05-14" in result["dt"]
    assert isinstance(result["t"], str) and "12:30:15" in result["t"]
    assert isinstance(result["delta"], (float, int))
    assert isinstance(result["uid"], str) and "12345678" in result["uid"]

def test_checkpoint_append_with_fsync():
    """Verify save_checkpoint calls os.fsync."""
    trace_id = "fsync_checkpoint_test"
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if path.exists():
        path.unlink()
        
    with patch("workflows.helpers.checkpoint.os.fsync") as mock_fsync:
        from workflows.helpers.checkpoint import save_checkpoint
        save_checkpoint(trace_id, "test_node", {"status": "running"})
        
    assert mock_fsync.called, "os.fsync not called during checkpoint save"
    if path.exists():
        path.unlink()