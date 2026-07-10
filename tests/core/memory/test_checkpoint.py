"""tests/core/memory/test_checkpoint.py — Hardening tests for sanitize_state & checkpointing."""
from __future__ import annotations
from unittest.mock import patch
import json
import time
import os
from decimal import Decimal
from datetime import datetime, timedelta, time as dt_time
from uuid import UUID, uuid4
from core.observability.checkpoint import sanitize_state, CHECKPOINT_DIR

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

    with patch("core.observability.checkpoint.os.fsync") as mock_fsync:
        from core.observability.checkpoint import save_checkpoint
        save_checkpoint(trace_id, "test_node", {"status": "running"})

    assert mock_fsync.called, "os.fsync not called during checkpoint save"
    if path.exists():
        path.unlink()


# =============================================================================
# Bug #15: Stale docstring path
# =============================================================================
def test_checkpoint_docstring_path_correct():
    """Docstring must reference core/observability/checkpoint.py, not the old path.

    Previously said 'core/workflow_checkpoint.py' — stale from before the
    refactor that moved the file to core/observability/.
    """
    from core.observability import checkpoint
    assert "core/observability/checkpoint.py" in checkpoint.__doc__, (
        "Docstring must reference the current file path (core/observability/checkpoint.py). "
        f"Got: {checkpoint.__doc__!r}"
    )
    assert "core/workflow_checkpoint.py" not in checkpoint.__doc__, (
        "Docstring must NOT reference the stale 'core/workflow_checkpoint.py' path."
    )


# =============================================================================
# Bug #16: Fragile resume counting (string match → JSON parse)
# =============================================================================
def test_resume_count_uses_json_parsing_not_string_match():
    """resume_count must be computed by parsing JSON, not string-matching.

    Previously used `'"node": "resume"' in line` which produces false
    positives if a state field contains that literal string.
    """
    import json
    from core.observability.checkpoint import save_checkpoint, get_latest, CHECKPOINT_DIR

    trace_id = "resume_count_string_match_test"
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if path.exists():
        path.unlink()

    # Write a checkpoint where the STATE contains the literal string
    # '"node": "resume"' — this must NOT be counted as a resume.
    # (The old string-match code would count it; the JSON-parse fix won't.)
    fake_entry = {
        "ts": time.time(),
        "node": "synthesize",  # NOT "resume"
        "status": "running",
        "state": {"note": 'this contains "node": "resume" as a literal string'},
        "resume_count": 0,
        "version": 1,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(fake_entry) + "\n")

    # Now save another checkpoint — save_checkpoint counts existing resumes
    save_checkpoint(trace_id, "test_node", {"status": "running"})

    # Read the last line and check resume_count
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last_entry = json.loads(lines[-1].strip())

    # The state field contained '"node": "resume"' but the actual node was
    # "synthesize". Old string-match would count 1; JSON-parse correctly counts 0.
    assert last_entry["resume_count"] == 0, (
        f"resume_count must be 0 (no actual resume nodes), but got "
        f"{last_entry['resume_count']}. The string-match logic is producing "
        f"false positives from state field content."
    )

    if path.exists():
        path.unlink()


def test_resume_count_counts_actual_resume_nodes():
    """resume_count must correctly count actual 'resume' nodes."""
    import json
    from core.observability.checkpoint import save_checkpoint, CHECKPOINT_DIR

    trace_id = "resume_count_actual_test"
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if path.exists():
        path.unlink()

    # Write 2 actual resume entries + 1 non-resume entry
    for node_name in ["resume", "resume", "synthesize"]:
        fake_entry = {
            "ts": time.time(),
            "node": node_name,
            "status": "running",
            "state": {},
            "resume_count": 0,
            "version": 1,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(fake_entry) + "\n")

    # Now save another checkpoint — should count 2 actual resumes
    save_checkpoint(trace_id, "test_node", {"status": "running"})

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last_entry = json.loads(lines[-1].strip())

    assert last_entry["resume_count"] == 2, (
        f"resume_count must be 2 (two actual 'resume' nodes), got "
        f"{last_entry['resume_count']}."
    )

    if path.exists():
        path.unlink()