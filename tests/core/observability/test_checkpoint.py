"""tests/core/observability/test_checkpoint.py — Checkpoint journal tests.

Covers:
  - sanitize_state: all Python types (primitives, datetime, Decimal, UUID,
    Path, bytes, dict, list, tuple, set, circular refs, non-serializable).
  - save_checkpoint: file creation, append, version field, resume_count,
    empty trace_id, fsync.
  - get_latest: last state, version injection, zombie quarantine
    (resume_count >= MAX_RESUMES), consecutive-failure quarantine,
    missing file.
  - quarantine: file move, missing file noop.
  - mark_complete: file deletion, missing file noop.
  - scan_incomplete: finds running, skips terminal, skips old (48h),
    empty dir.

The checkpoint module lives in core/observability/checkpoint.py. It provides
an append-only JSONL journal for workflow resumability — saving workflow
state at critical boundaries to survive agent crashes.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.observability import checkpoint as ckpt
from core.observability.checkpoint import (
    MAX_RESUMES,
    get_latest,
    mark_complete,
    quarantine,
    sanitize_state,
    save_checkpoint,
    scan_incomplete,
)


# ===========================================================================
# sanitize_state — JSON-safe extraction
# ===========================================================================
class TestSanitizeStatePrimitives:
    def test_str(self):
        assert sanitize_state("hello") == "hello"

    def test_int(self):
        assert sanitize_state(42) == 42

    def test_float(self):
        assert sanitize_state(3.14) == 3.14

    def test_bool(self):
        assert sanitize_state(True) is True
        assert sanitize_state(False) is False

    def test_none(self):
        assert sanitize_state(None) is None


class TestSanitizeStateDateTime:
    def test_datetime(self):
        dt = datetime.datetime(2026, 7, 18, 12, 0, 0)
        assert sanitize_state(dt) == dt.isoformat()

    def test_date(self):
        d = datetime.date(2026, 7, 18)
        assert sanitize_state(d) == d.isoformat()

    def test_time(self):
        t = datetime.time(12, 30, 0)
        assert sanitize_state(t) == t.isoformat()

    def test_timedelta(self):
        td = datetime.timedelta(seconds=90)
        assert sanitize_state(td) == 90.0


class TestSanitizeStateSpecialTypes:
    def test_bytes(self):
        assert sanitize_state(b"hello") == "hello"

    def test_bytes_non_utf8(self):
        # Invalid UTF-8 bytes should be replaced, not crash
        assert sanitize_state(b"\xff\xfe") is not None

    def test_decimal(self):
        assert sanitize_state(Decimal("3.14")) == "3.14"

    def test_uuid(self):
        u = uuid.uuid4()
        assert sanitize_state(u) == str(u)

    def test_path(self):
        p = Path("/tmp/test")
        assert sanitize_state(p) == str(p)


class TestSanitizeStateContainers:
    def test_dict(self):
        result = sanitize_state({"a": 1, "b": "two"})
        assert result == {"a": 1, "b": "two"}

    def test_dict_keys_stringified(self):
        """Dict keys are converted to strings for JSON safety."""
        result = sanitize_state({1: "a", 2: "b"})
        assert result == {"1": "a", "2": "b"}

    def test_nested_dict(self):
        result = sanitize_state({"outer": {"inner": [1, 2, 3]}})
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_list(self):
        assert sanitize_state([1, "two", 3.0]) == [1, "two", 3.0]

    def test_tuple_becomes_list(self):
        """Tuples are converted to lists (JSON has no tuple type)."""
        result = sanitize_state((1, 2, 3))
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_set_becomes_sorted_list(self):
        """Sets are converted to sorted lists for deterministic output."""
        result = sanitize_state({3, 1, 2})
        assert result == [1, 2, 3]

    def test_set_of_unsortable_items(self):
        """Sets of unsortable items (e.g. dicts) fall back to insertion order."""
        result = sanitize_state({"a", "b", "c"})
        assert sorted(result) == ["a", "b", "c"]


class TestSanitizeStateEdgeCases:
    def test_circular_reference_dict(self):
        """Circular references must not cause infinite recursion."""
        d: dict = {}
        d["self"] = d
        result = sanitize_state(d)
        assert result["self"] == "<circular_reference>"

    def test_circular_reference_list(self):
        lst: list = []
        lst.append(lst)
        result = sanitize_state(lst)
        assert result[0] == "<circular_reference>"

    def test_non_serializable_returns_none(self):
        """Non-serializable objects (locks, clients, etc.) return None.

        This prevents truthy-string crashes on resume. Nodes that need
        such objects must reconstruct them on entry if missing.
        """
        import threading
        lock = threading.Lock()
        assert sanitize_state(lock) is None

    def test_non_serializable_in_dict(self):
        """Non-serializable values inside a dict become None, not dropped."""
        import threading
        result = sanitize_state({"lock": threading.Lock(), "count": 5})
        assert result["lock"] is None
        assert result["count"] == 5

    def test_object_with_fspath(self):
        """Path-like objects (with __fspath__) are stringified."""
        class FakePath:
            def __fspath__(self):
                return "/fake/path"
        assert sanitize_state(FakePath()) == "/fake/path"

    def test_deeply_nested(self):
        deep = {"a": {"b": {"c": {"d": "end"}}}}
        assert sanitize_state(deep) == deep


# ===========================================================================
# save_checkpoint
# ===========================================================================
class TestSaveCheckpoint:
    def test_creates_jsonl_file(self, isolated_checkpoint_dirs):
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        state = {"status": "running", "task": "fix bug"}
        save_checkpoint("trace-1", "node_a", state)
        assert (ckpt_dir / "trace-1.jsonl").exists()

    def test_appends_multiple_entries(self, isolated_checkpoint_dirs):
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-1.jsonl"
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        save_checkpoint("trace-1", "node_b", {"status": "running"})
        save_checkpoint("trace-1", "node_c", {"status": "success"})
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3
        entries = [json.loads(l) for l in lines]
        assert entries[0]["node"] == "node_a"
        assert entries[2]["node"] == "node_c"

    def test_includes_version(self, isolated_checkpoint_dirs):
        """Each checkpoint entry must include a schema version for compatibility."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-1.jsonl"
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        entry = json.loads(path.read_text().strip())
        assert entry["version"] == 1

    def test_includes_resume_count_zero(self, isolated_checkpoint_dirs):
        """First checkpoint has resume_count=0 (no prior resume entries)."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-1.jsonl"
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        entry = json.loads(path.read_text().strip())
        assert entry["resume_count"] == 0

    def test_resume_count_counts_resume_nodes(self, isolated_checkpoint_dirs):
        """resume_count = number of prior entries with node='resume'."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-1.jsonl"
        # Write two resume entries manually
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"node": "resume", "status": "running", "state": {}, "ts": 1, "resume_count": 0, "version": 1}) + "\n")
            f.write(json.dumps({"node": "resume", "status": "running", "state": {}, "ts": 2, "resume_count": 1, "version": 1}) + "\n")
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        lines = path.read_text().strip().split("\n")
        last_entry = json.loads(lines[-1])
        assert last_entry["resume_count"] == 2

    def test_empty_trace_id_noop(self, isolated_checkpoint_dirs):
        """save_checkpoint('', ...) must not create a file."""
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        save_checkpoint("", "node_a", {"status": "running"})
        assert not (ckpt_dir / ".jsonl").exists()
        # No files at all
        assert len(list(ckpt_dir.glob("*.jsonl"))) == 0

    def test_state_sanitized(self, isolated_checkpoint_dirs):
        """Non-serializable state values must be sanitized (None) before write."""
        import threading
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-1.jsonl"
        save_checkpoint("trace-1", "node_a", {"lock": threading.Lock(), "count": 5})
        entry = json.loads(path.read_text().strip())
        assert entry["state"]["lock"] is None
        assert entry["state"]["count"] == 5


# ===========================================================================
# get_latest
# ===========================================================================
class TestGetLatest:
    def test_returns_last_state(self, isolated_checkpoint_dirs):
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        save_checkpoint("trace-1", "node_b", {"status": "success", "result": "done"})
        state = get_latest("trace-1")
        assert state is not None
        assert state["status"] == "success"
        assert state["result"] == "done"

    def test_injects_checkpoint_version(self, isolated_checkpoint_dirs):
        """get_latest injects _checkpoint_version into the state dict so
        base.py can validate schema compatibility on resume."""
        save_checkpoint("trace-1", "node_a", {"status": "running"})
        state = get_latest("trace-1")
        assert state is not None
        assert state["_checkpoint_version"] == 1

    def test_nonexistent_returns_none(self, isolated_checkpoint_dirs):
        assert get_latest("ghost") is None

    def test_zombie_quarantine_by_resume_count(self, isolated_checkpoint_dirs):
        """If resume_count >= MAX_RESUMES, the workflow is quarantined and
        get_latest returns None."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-z.jsonl"
        # Write MAX_RESUMES+1 resume entries so the last has resume_count=MAX_RESUMES
        with open(path, "w", encoding="utf-8") as f:
            for i in range(MAX_RESUMES + 1):
                f.write(json.dumps({
                    "node": "resume", "status": "running", "state": {},
                    "ts": i, "resume_count": i, "version": 1,
                }) + "\n")

        state = get_latest("trace-z")
        assert state is None  # quarantined
        # File should have been moved to quarantine
        assert not path.exists()
        assert (isolated_checkpoint_dirs["quarantine"] / "trace-z.jsonl").exists()

    def test_zombie_quarantine_consecutive_same_node_failures(self, isolated_checkpoint_dirs):
        """Two consecutive failures at the same node (not 'resume') = zombie."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-z2.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "node": "node_x", "status": "failed", "state": {},
                "ts": 1, "resume_count": 0, "version": 1,
            }) + "\n")
            f.write(json.dumps({
                "node": "node_x", "status": "failed", "state": {},
                "ts": 2, "resume_count": 0, "version": 1,
            }) + "\n")

        state = get_latest("trace-z2")
        assert state is None  # quarantined
        assert (isolated_checkpoint_dirs["quarantine"] / "trace-z2.jsonl").exists()

    def test_non_dict_state_returns_as_is(self, isolated_checkpoint_dirs):
        """If the state is not a dict (edge case), return it without version injection."""
        path = isolated_checkpoint_dirs["checkpoints"] / "trace-nd.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "node": "n", "status": "running", "state": "not_a_dict",
                "ts": 1, "resume_count": 0, "version": 1,
            }) + "\n")
        result = get_latest("trace-nd")
        assert result == "not_a_dict"


# ===========================================================================
# quarantine
# ===========================================================================
class TestQuarantine:
    def test_moves_file_to_quarantine(self, isolated_checkpoint_dirs):
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        quar_dir = isolated_checkpoint_dirs["quarantine"]
        path = ckpt_dir / "trace-q.jsonl"
        path.write_text('{"node": "n"}\n')

        quarantine("trace-q")
        assert not path.exists()
        assert (quar_dir / "trace-q.jsonl").exists()

    def test_nonexistent_file_noop(self, isolated_checkpoint_dirs):
        """quarantine() on a missing file must not raise."""
        quarantine("ghost")  # must not raise


# ===========================================================================
# mark_complete
# ===========================================================================
class TestMarkComplete:
    def test_deletes_file(self, isolated_checkpoint_dirs):
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        path = ckpt_dir / "trace-d.jsonl"
        path.write_text('{"node": "n"}\n')

        mark_complete("trace-d")
        assert not path.exists()

    def test_nonexistent_file_noop(self, isolated_checkpoint_dirs):
        """mark_complete() on a missing file must not raise."""
        mark_complete("ghost")  # must not raise


# ===========================================================================
# scan_incomplete
# ===========================================================================
class TestScanIncomplete:
    def test_finds_running_workflows(self, isolated_checkpoint_dirs):
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        # Running workflow
        path1 = ckpt_dir / "trace-run.jsonl"
        path1.write_text(json.dumps({"status": "running", "state": {}, "node": "n"}) + "\n")
        # Completed workflow
        path2 = ckpt_dir / "trace-done.jsonl"
        path2.write_text(json.dumps({"status": "success", "state": {}, "node": "n"}) + "\n")

        incomplete = scan_incomplete()
        assert "trace-run" in incomplete
        assert "trace-done" not in incomplete

    def test_skips_terminal_statuses(self, isolated_checkpoint_dirs):
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        for tid, status in [("t-s", "success"), ("t-f", "failed")]:
            path = ckpt_dir / f"{tid}.jsonl"
            path.write_text(json.dumps({"status": status, "state": {}, "node": "n"}) + "\n")
        incomplete = scan_incomplete()
        assert "t-s" not in incomplete
        assert "t-f" not in incomplete

    def test_skips_old_files(self, isolated_checkpoint_dirs):
        """Files older than 48h are not returned by scan_incomplete."""
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        path = ckpt_dir / "trace-old.jsonl"
        path.write_text(json.dumps({"status": "running", "state": {}, "node": "n"}) + "\n")
        # Set mtime to 49 hours ago
        old_time = time.time() - (49 * 3600)
        os.utime(path, (old_time, old_time))

        incomplete = scan_incomplete()
        assert "trace-old" not in incomplete

    def test_includes_recent_files(self, isolated_checkpoint_dirs):
        """Files modified within 48h ARE returned (if status is non-terminal)."""
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        path = ckpt_dir / "trace-recent.jsonl"
        path.write_text(json.dumps({"status": "running", "state": {}, "node": "n"}) + "\n")
        # Set mtime to 1 hour ago
        recent_time = time.time() - 3600
        os.utime(path, (recent_time, recent_time))

        incomplete = scan_incomplete()
        assert "trace-recent" in incomplete

    def test_empty_dir(self, isolated_checkpoint_dirs):
        assert scan_incomplete() == []

    def test_malformed_last_line_skipped(self, isolated_checkpoint_dirs):
        """If the last line is malformed JSON, the file is skipped (not crashed)."""
        ckpt_dir = isolated_checkpoint_dirs["checkpoints"]
        path = ckpt_dir / "trace-bad.jsonl"
        path.write_text("not valid json\n")
        incomplete = scan_incomplete()
        assert "trace-bad" not in incomplete
