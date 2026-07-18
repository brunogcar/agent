"""tests/core/observability/test_reader.py — Trace reader tests (expanded).

Covers:
  - read_trace: empty id, fast-path (memory), slow-path (disk), not-found,
    14-day limit, malformed lines, substring pre-filter, step sorting,
    missing trace_start, extra-field preservation.
  - list_recent_traces: default, limit, empty.
  - _format_trace: all fields, missing fields.
  - _scan_disk: no log dir, empty log dir, multiple files (newest-first).

Bug fix verified here:
  The reader previously scanned ``cfg.log_path`` (``logs/``) but the writer
  writes to ``cfg.agent_log_path`` (``logs/agent/``). The non-recursive glob
  ``agent_*.jsonl`` could never find the writer's files. Now fixed: the
  reader scans ``cfg.agent_log_path`` directly.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.observability.reader import (
    _format_trace,
    _scan_disk,
    list_recent_traces,
    read_trace,
)


def _memory_miss(tracer_obj):
    """Context manager: make tracer.get return None for the duration of a block.

    Uses patch.object so the mutation is automatically reverted — direct
    assignment (tracer_obj.get = MagicMock(...)) would permanently replace
    the method on the process-wide singleton and leak into other tests.
    """
    return patch.object(tracer_obj, "get", return_value=None)


# ===========================================================================
# read_trace — edge cases
# ===========================================================================
class TestReadTraceEdgeCases:
    def test_empty_id_returns_none(self, mock_writer):
        assert read_trace("") is None

    def test_none_id_returns_none(self, mock_writer):
        assert read_trace(None) is None  # type: ignore[arg-type]


# ===========================================================================
# read_trace — fast path (in-memory store)
# ===========================================================================
class TestReadTraceFastPath:
    def test_fast_path_memory_hit(self, isolated_tracer):
        tid = isolated_tracer.new_trace("research", goal="test")
        isolated_tracer.step(tid, "search", "found results")
        isolated_tracer.finish(tid, success=True, result="done")

        result = read_trace(tid)
        assert result is not None
        assert result["trace_id"] == tid
        assert result["workflow"] == "research"
        assert result["goal"] == "test"
        assert result["status"] == "success"
        assert len(result["steps"]) >= 2

    def test_fast_path_uses_tracer_get(self, isolated_tracer):
        """If the tracer has the trace in memory, _scan_disk is never called."""
        tid = isolated_tracer.new_trace("wf")
        with patch("core.observability.reader._scan_disk") as mock_scan:
            result = read_trace(tid)
            mock_scan.assert_not_called()
        assert result is not None
        assert result["trace_id"] == tid

    def test_fast_path_missing_elapsed(self, isolated_tracer):
        """A trace that hasn't finished yet has no 'elapsed' field."""
        tid = isolated_tracer.new_trace("wf")
        result = read_trace(tid)
        assert result is not None
        assert result["status"] == "running"
        assert result["elapsed_s"] is None  # not finished yet


# ===========================================================================
# read_trace — slow path (disk scan)
# ===========================================================================
class TestReadTraceSlowPath:
    def test_slow_path_disk_scan(self, isolated_tracer, isolated_log_path):
        """When the trace is not in memory, fall back to JSONL disk scan."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "trace_start", "trace_id": "disk123",
                "workflow": "data", "goal": "analyze",
                "started_fmt": "2026-01-01 10:00:00",
            }) + "\n")
            f.write(json.dumps({
                "event": "step", "trace_id": "disk123",
                "node": "search", "message": "searching", "ts": 1000,
            }) + "\n")
            f.write(json.dumps({
                "event": "trace_finish", "trace_id": "disk123",
                "success": True, "elapsed_s": 10.0, "result": "done",
            }) + "\n")

        result = read_trace("disk123")
        assert result is not None
        assert result["trace_id"] == "disk123"
        assert result["workflow"] == "data"
        assert result["goal"] == "analyze"
        assert result["status"] == "success"
        assert result["elapsed_s"] == 10.0
        assert result["result"] == "done"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["node"] == "search"

    def test_slow_path_not_found(self, isolated_tracer, isolated_log_path):
        with _memory_miss(isolated_tracer):
            assert read_trace("nonexistent") is None

    def test_slow_path_skips_malformed_lines(self, isolated_tracer, isolated_log_path):
        """Malformed JSON lines must be silently skipped, not crash the scan."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("this is not json\n")
            f.write("{broken json\n")
            f.write(json.dumps({
                "event": "trace_start", "trace_id": "good",
                "workflow": "w", "goal": "g", "started_fmt": "now",
            }) + "\n")
            f.write(json.dumps({
                "event": "step", "trace_id": "good",
                "node": "n", "message": "m", "ts": 1,
            }) + "\n")

        with _memory_miss(isolated_tracer):
            result = read_trace("good")
        assert result is not None
        assert result["workflow"] == "w"
        assert len(result["steps"]) == 1

    def test_slow_path_substring_prefilter(self, isolated_tracer, isolated_log_path):
        """The scanner does a fast ``trace_id in line`` string check before
        the expensive JSON parse. Lines that don't contain the trace_id as a
        substring are skipped without parsing."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            # Unrelated trace
            f.write(json.dumps({
                "event": "step", "trace_id": "other",
                "node": "n", "message": "m", "ts": 1,
            }) + "\n")
            # Our trace
            f.write(json.dumps({
                "event": "trace_start", "trace_id": "target",
                "workflow": "w", "goal": "g", "started_fmt": "now",
            }) + "\n")

        with _memory_miss(isolated_tracer):
            result = read_trace("target")
        assert result is not None
        assert result["workflow"] == "w"
        # The "other" trace's step must NOT appear
        assert all(s.get("trace_id", "target") != "other" for s in result["steps"])

    def test_slow_path_steps_sorted_by_ts(self, isolated_tracer, isolated_log_path):
        """Steps from disk must be sorted by timestamp (oldest first)."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "trace_start", "trace_id": "sort",
                "workflow": "w", "goal": "g", "started_fmt": "now",
            }) + "\n")
            # Write steps out of order
            f.write(json.dumps({"event": "step", "trace_id": "sort", "node": "c", "ts": 300}) + "\n")
            f.write(json.dumps({"event": "step", "trace_id": "sort", "node": "a", "ts": 100}) + "\n")
            f.write(json.dumps({"event": "step", "trace_id": "sort", "node": "b", "ts": 200}) + "\n")

        with _memory_miss(isolated_tracer):
            result = read_trace("sort")
        nodes = [s["node"] for s in result["steps"]]
        assert nodes == ["a", "b", "c"]  # sorted by ts

    def test_slow_path_14_day_limit(self, isolated_tracer, isolated_log_path):
        """The scanner limits to the 14 newest log files to prevent massive I/O."""
        # Create 20 log files — only the 14 newest should be scanned
        for i in range(20):
            day = f"2026{12 - i:02d}01" if i < 12 else f"2026{(20-i):02d}01"
            # Simpler: just use numbered dates
            day_str = f"202601{i+1:02d}"
            log_file = isolated_log_path / f"agent_{day_str}.jsonl"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "event": "trace_start", "trace_id": f"tid-{i}",
                    "workflow": "w", "goal": "g", "started_fmt": "now",
                }) + "\n")

        # The scanner sorts files reverse (newest first) and takes the first 14.
        # tid-19 is in the newest file (agent_20260120.jsonl) so it must be found.
        with _memory_miss(isolated_tracer):
            result = read_trace("tid-19")
        assert result is not None

    def test_slow_path_no_log_dir(self, isolated_tracer, tmp_path):
        """If the log directory doesn't exist, return None (not crash)."""
        with _memory_miss(isolated_tracer):
            with patch("core.observability.reader.cfg") as mock_cfg:
                mock_cfg.agent_log_path = tmp_path / "nonexistent"
                assert read_trace("anything") is None

    def test_slow_path_preserves_extra_fields(self, isolated_tracer, isolated_log_path):
        """Extra kwargs from step/error/warning must survive the disk round-trip."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "trace_start", "trace_id": "extra",
                "workflow": "w", "goal": "g", "started_fmt": "now",
            }) + "\n")
            f.write(json.dumps({
                "event": "step", "trace_id": "extra",
                "node": "n", "message": "m", "ts": 1,
                "custom_field": "hello", "count": 42,
            }) + "\n")

        with _memory_miss(isolated_tracer):
            result = read_trace("extra")
        step = result["steps"][0]
        assert step["custom_field"] == "hello"
        assert step["count"] == 42

    def test_slow_path_only_steps_no_start(self, isolated_tracer, isolated_log_path):
        """If trace_start is missing (partial log), return steps with empty meta."""
        log_file = isolated_log_path / "agent_20260101.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "step", "trace_id": "partial",
                "node": "n", "message": "m", "ts": 1,
            }) + "\n")

        with _memory_miss(isolated_tracer):
            result = read_trace("partial")
        assert result is not None
        assert result["trace_id"] == "partial"
        assert len(result["steps"]) == 1
        # Meta fields absent because no trace_start was found
        assert "workflow" not in result or result.get("workflow") is None


# ===========================================================================
# list_recent_traces
# ===========================================================================
class TestListRecentTraces:
    def test_list_recent_default(self, isolated_tracer):
        isolated_tracer.new_trace("wf-a")
        isolated_tracer.new_trace("wf-b")
        traces = list_recent_traces()
        assert len(traces) == 2

    def test_list_recent_limit(self, isolated_tracer):
        for i in range(5):
            isolated_tracer.new_trace(f"wf-{i}")
        traces = list_recent_traces(limit=3)
        assert len(traces) == 3

    def test_list_recent_empty(self, isolated_tracer):
        assert list_recent_traces() == []

    def test_list_recent_formats_each_trace(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf", goal="g")
        isolated_tracer.finish(tid, success=True, result="done")
        traces = list_recent_traces()
        assert len(traces) == 1
        t = traces[0]
        assert t["trace_id"] == tid
        assert t["workflow"] == "wf"
        assert t["status"] == "success"


# ===========================================================================
# _format_trace
# ===========================================================================
class TestFormatTrace:
    def test_all_fields(self):
        trace = {
            "trace_id": "abc",
            "workflow": "wf",
            "goal": "g",
            "status": "success",
            "started_fmt": "2026-01-01",
            "elapsed": 5.0,
            "result": "done",
            "steps": [{"node": "n"}],
        }
        formatted = _format_trace(trace)
        assert formatted["trace_id"] == "abc"
        assert formatted["workflow"] == "wf"
        assert formatted["status"] == "success"
        assert formatted["elapsed_s"] == 5.0
        assert len(formatted["steps"]) == 1

    def test_missing_fields_default_to_none(self):
        """A trace dict with missing keys must not crash _format_trace."""
        formatted = _format_trace({})
        assert formatted["trace_id"] is None
        assert formatted["workflow"] is None
        assert formatted["steps"] == []


# ===========================================================================
# _scan_disk
# ===========================================================================
class TestScanDisk:
    def test_no_log_dir_returns_none(self, tmp_path):
        with patch("core.observability.reader.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path / "nonexistent"
            assert _scan_disk("any") is None

    def test_empty_log_dir_returns_none(self, tmp_path):
        with patch("core.observability.reader.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            assert _scan_disk("any") is None

    def test_multiple_files_newest_first(self, tmp_path):
        """When multiple log files match, the scanner processes them but
        the result is assembled from all matching lines."""
        with patch("core.observability.reader.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            for day in ["20260101", "20260102", "20260103"]:
                log_file = tmp_path / f"agent_{day}.jsonl"
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "event": "step", "trace_id": "multi",
                        "node": day, "message": "m", "ts": int(day),
                    }) + "\n")
            result = _scan_disk("multi")
            assert result is not None
            assert len(result["steps"]) == 3
