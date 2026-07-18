"""tests/core/observability/test_tracer_engine.py — Comprehensive tracer engine tests.

Covers:
  - generate_trace_id (length, charset, uniqueness)
  - _TraceStore (create, get, update, append_step, all_recent, bounding, thread-safety)
  - _FileWriter (file creation, append, date rollover, error suppression, close)
  - Tracer public API (new_trace, step, error, warning, finish, get, recent, summary)
  - P0 kwargs-spread fix (hardcoded keys cannot be overwritten by caller kwargs)
  - Facade (core.tracer re-exports + shared singleton state)
  - Integration (full lifecycle end-to-end)

The Tracer implementation lives in core/observability/tracer_engine.py.
core/tracer.py is a thin facade that re-exports the same names.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from core.observability.tracer_engine import (
    Tracer,
    _FileWriter,
    _TraceStore,
    _configure_structlog,
    _HAS_STRUCTLOG,
    _store,
    _writer,
    generate_trace_id,
    tracer,
)


# ===========================================================================
# generate_trace_id
# ===========================================================================
class TestGenerateTraceId:
    def test_default_length_is_12(self):
        tid = generate_trace_id()
        assert len(tid) == 12

    def test_custom_length(self):
        for n in (1, 4, 8, 16, 32):
            assert len(generate_trace_id(length=n)) == n

    def test_hex_charset_only(self):
        """Trace IDs must be lowercase hex — safe for filenames and URLs."""
        for _ in range(200):
            tid = generate_trace_id()
            assert all(c in "0123456789abcdef" for c in tid)

    def test_uniqueness(self):
        ids = {generate_trace_id() for _ in range(2000)}
        assert len(ids) == 2000  # collisions astronomically unlikely


# ===========================================================================
# _TraceStore
# ===========================================================================
class TestTraceStore:
    def test_create_and_get(self):
        store = _TraceStore()
        store.create("tid-1", {"workflow": "test", "goal": "g"})
        trace = store.get("tid-1")
        assert trace is not None
        assert trace["workflow"] == "test"

    def test_get_nonexistent_returns_none(self):
        store = _TraceStore()
        assert store.get("nope") is None

    def test_max_traces_bounded_fifo(self):
        """When MAX_TRACES is exceeded, oldest entries are evicted (FIFO)."""
        store = _TraceStore()
        store.MAX_TRACES = 5
        for i in range(10):
            store.create(f"tid-{i}", {"workflow": "test"})
        assert len(store._order) == 5
        # Oldest 5 evicted
        assert store.get("tid-0") is None
        assert store.get("tid-4") is None
        # Newest 5 retained
        assert store.get("tid-5") is not None
        assert store.get("tid-9") is not None

    def test_update_existing(self):
        store = _TraceStore()
        store.create("tid-1", {"status": "running"})
        store.update("tid-1", "status", "success")
        assert store.get("tid-1")["status"] == "success"

    def test_update_nonexistent_is_noop(self):
        store = _TraceStore()
        store.update("ghost", "status", "success")  # must not raise
        assert store.get("ghost") is None

    def test_append_step(self):
        store = _TraceStore()
        store.create("tid-1", {"workflow": "test"})
        store.append_step("tid-1", {"node": "start", "message": "hi"})
        trace = store.get("tid-1")
        assert len(trace["steps"]) == 1
        assert trace["steps"][0]["node"] == "start"

    def test_append_step_nonexistent_is_noop(self):
        store = _TraceStore()
        store.append_step("ghost", {"node": "x"})  # must not raise
        assert store.get("ghost") is None

    def test_all_recent_newest_first(self):
        store = _TraceStore()
        for i in range(5):
            store.create(f"tid-{i}", {"workflow": "w"})
        recent = store.all_recent(n=3)
        # Should be newest-first: tid-4, tid-3, tid-2
        assert len(recent) == 3
        assert recent[0]["workflow"] == "w"

    def test_all_recent_n_larger_than_store(self):
        store = _TraceStore()
        store.create("tid-1", {"workflow": "w"})
        recent = store.all_recent(n=100)
        assert len(recent) == 1

    def test_all_recent_empty_store(self):
        store = _TraceStore()
        assert store.all_recent(n=10) == []

    def test_concurrent_creates_are_thread_safe(self):
        """Rapid concurrent creates must not corrupt the store."""
        store = _TraceStore()
        store.MAX_TRACES = 500

        def worker(start):
            for i in range(100):
                store.create(f"tid-{start}-{i}", {"workflow": "w"})

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 500 creates, MAX_TRACES=500 → all retained
        assert len(store._order) == 500


# ===========================================================================
# _FileWriter
# ===========================================================================
class TestFileWriter:
    def test_write_creates_dated_file(self, tmp_path):
        """_FileWriter creates agent_YYYYMMDD.jsonl under the configured dir."""
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            mock_cfg.autocode_debug = False
            w = _FileWriter()
            w.write({"event": "test", "msg": "hello"})
            files = list(tmp_path.glob("agent_*.jsonl"))
            assert len(files) == 1
            w.close()

    def test_write_appends_to_same_day(self, tmp_path):
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            mock_cfg.autocode_debug = False
            w = _FileWriter()
            w.write({"event": "a"})
            w.write({"event": "b"})
            w.write({"event": "c"})
            files = list(tmp_path.glob("agent_*.jsonl"))
            assert len(files) == 1  # same day → same file
            content = files[0].read_text(encoding="utf-8").strip().split("\n")
            assert len(content) == 3
            w.close()

    def test_write_produces_valid_jsonl(self, tmp_path):
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            mock_cfg.autocode_debug = False
            w = _FileWriter()
            w.write({"event": "test", "unicode": "héllo 世界"})
            w.close()
            files = list(tmp_path.glob("agent_*.jsonl"))
            line = files[0].read_text(encoding="utf-8").strip()
            record = json.loads(line)
            assert record["event"] == "test"
            assert record["unicode"] == "héllo 世界"

    def test_write_swallows_io_errors(self):
        """If the file write fails, the writer must NOT raise — log I/O is
        non-fatal so a disk issue never crashes the agent."""
        w = _FileWriter()
        # Force _get_file to raise by making cfg.agent_log_path a non-dir path
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = MagicMock()
            mock_cfg.agent_log_path.mkdir.side_effect = OSError("disk full")
            # Must not raise
            w.write({"event": "test"})
        w.close()

    def test_close_idempotent(self, tmp_path):
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            mock_cfg.autocode_debug = False
            w = _FileWriter()
            w.write({"event": "a"})
            w.close()
            w.close()  # second close must not raise

    def test_close_then_write_reopens(self, tmp_path):
        """After close(), a subsequent write() must reopen the file."""
        with patch("core.observability.tracer_engine.cfg") as mock_cfg:
            mock_cfg.agent_log_path = tmp_path
            mock_cfg.autocode_debug = False
            w = _FileWriter()
            w.write({"event": "first"})
            w.close()
            w.write({"event": "second"})
            w.close()
            content = list(tmp_path.glob("agent_*.jsonl"))[0].read_text(encoding="utf-8").strip().split("\n")
            assert len(content) == 2
            assert json.loads(content[0])["event"] == "first"
            assert json.loads(content[1])["event"] == "second"


# ===========================================================================
# Tracer — new_trace
# ===========================================================================
class TestTracerNewTrace:
    def test_returns_12char_hex_id(self, isolated_tracer):
        tid = isolated_tracer.new_trace("autocode", goal="fix bug")
        assert len(tid) == 12
        assert all(c in "0123456789abcdef" for c in tid)

    def test_creates_store_record(self, isolated_tracer):
        tid = isolated_tracer.new_trace("autocode", goal="fix bug")
        trace = isolated_tracer.get(tid)
        assert trace is not None
        assert trace["workflow"] == "autocode"
        assert trace["goal"] == "fix bug"
        assert trace["status"] == "running"
        assert trace["steps"] == []

    def test_emits_trace_start_to_writer(self, isolated_tracer, mock_writer):
        tid = isolated_tracer.new_trace("autocode", goal="g")
        mock_writer.write.assert_called_once()
        record = mock_writer.write.call_args[0][0]
        assert record["event"] == "trace_start"
        assert record["trace_id"] == tid
        assert record["workflow"] == "autocode"

    def test_emits_to_stderr(self, isolated_tracer, mock_writer):
        """new_trace must print a JSON line to stderr (never stdout).

        This is the MCP stdio safety guarantee: stdout is the protocol
        channel; any non-JSON-RPC bytes on stdout corrupt the connection.
        """
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            isolated_tracer.new_trace("autocode", goal="g")
        stderr_output = err_buf.getvalue()
        assert stderr_output  # non-empty
        parsed = json.loads(stderr_output.strip())
        assert parsed["event"] == "trace_start"
        assert parsed["workflow"] == "autocode"

    def test_kwargs_preserved_in_record(self, isolated_tracer, mock_writer):
        """Caller kwargs must appear in the trace record."""
        tid = isolated_tracer.new_trace("autocode", goal="g",
                                        custom_field="hello", count=42)
        trace = isolated_tracer.get(tid)
        assert trace["custom_field"] == "hello"
        assert trace["count"] == 42

    def test_p0_kwargs_cannot_overwrite_hardcoded_keys(self, isolated_tracer, mock_writer):
        """[P0 FIX] Caller kwargs must NOT overwrite trace_id, status,
        started_at, started_fmt, steps, or event.

        Note: ``workflow`` and ``goal`` are named parameters of new_trace(),
        so they can't appear in **kwargs — Python raises TypeError. The
        kwargs-spread fix protects the OTHER hardcoded keys (trace_id,
        status, started_at, etc.) which ARE in the record dict but could
        be passed as kwargs if a caller mistakenly includes them.

        Before the fix, ``new_trace("w", trace_id="evil")`` would corrupt
        the trace_id field, breaking all downstream correlation. The fix
        spreads kwargs FIRST, then sets hardcoded keys on top.
        """
        tid = isolated_tracer.new_trace(
            "autocode", goal="g",
            trace_id="EVIL", status="finished",
            started_at=999, started_fmt="hacked", steps=["bad"],
            event="hacked",
        )
        trace = isolated_tracer.get(tid)
        # Hardcoded keys must win
        assert trace["trace_id"] == tid  # not "EVIL"
        assert trace["status"] == "running"  # not "finished"
        assert trace["started_at"] != 999
        assert trace["started_fmt"] != "hacked"
        assert trace["steps"] == []  # not ["bad"]
        # The writer record must also have the correct event
        record = mock_writer.write.call_args[0][0]
        assert record["event"] == "trace_start"  # not "hacked"


# ===========================================================================
# Tracer — step / error / warning
# ===========================================================================
class TestTracerStepErrorWarning:
    def test_step_appends_to_store(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.step(tid, "read", "file loaded", chars=4200)
        trace = isolated_tracer.get(tid)
        assert len(trace["steps"]) == 1
        step = trace["steps"][0]
        assert step["event"] == "step"
        assert step["node"] == "read"
        assert step["message"] == "file loaded"
        assert step["chars"] == 4200

    def test_step_writes_to_file(self, isolated_tracer, mock_writer):
        tid = isolated_tracer.new_trace("wf")
        mock_writer.write.reset_mock()
        isolated_tracer.step(tid, "read", "file loaded")
        mock_writer.write.assert_called_once()
        record = mock_writer.write.call_args[0][0]
        assert record["event"] == "step"

    def test_step_kwargs_cannot_overwrite_hardcoded_keys(self, isolated_tracer):
        """[P0 FIX] kwargs must not overwrite event or ts.

        Note: ``trace_id``, ``node``, and ``message`` are named parameters
        of step(), so they can't appear in **kwargs. The kwargs-spread fix
        protects ``event`` and ``ts`` which ARE in the entry dict but could
        be passed as kwargs if a caller mistakenly includes them.
        """
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.step(
            tid, "read", "msg",
            event="hacked", ts=999,
        )
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["event"] == "step"   # not "hacked"
        assert step["ts"] != 999         # computed from time.time()

    def test_step_latency_ms_passthrough(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.step(tid, "read", "msg", latency_ms=42.5)
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["latency_ms"] == 42.5

    def test_error_appends_to_store(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.error(tid, "apply", "patch failed", error="boom")
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["event"] == "error"
        assert step["node"] == "apply"
        assert step["error"] == "boom"

    def test_error_writes_to_file(self, isolated_tracer, mock_writer):
        tid = isolated_tracer.new_trace("wf")
        mock_writer.write.reset_mock()
        isolated_tracer.error(tid, "apply", "failed")
        mock_writer.write.assert_called_once()
        assert mock_writer.write.call_args[0][0]["event"] == "error"

    def test_error_kwargs_cannot_overwrite_hardcoded_keys(self, isolated_tracer):
        """[P0 FIX] kwargs must not overwrite event or ts.

        Note: ``trace_id``, ``node``, ``message`` are named parameters of
        error(), so they can't appear in **kwargs.
        """
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.error(tid, "n", "m", event="hacked", ts=999)
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["event"] == "error"  # not "hacked"
        assert step["ts"] != 999

    def test_warning_appends_to_store(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.warning(tid, "retry", "transient error", count=3)
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["event"] == "warning"
        assert step["node"] == "retry"
        assert step["count"] == 3

    def test_warning_writes_to_file(self, isolated_tracer, mock_writer):
        tid = isolated_tracer.new_trace("wf")
        mock_writer.write.reset_mock()
        isolated_tracer.warning(tid, "retry", "transient")
        mock_writer.write.assert_called_once()
        assert mock_writer.write.call_args[0][0]["event"] == "warning"

    def test_warning_kwargs_cannot_overwrite_hardcoded_keys(self, isolated_tracer):
        """[P0 FIX] kwargs must not overwrite event or ts.

        Note: ``trace_id``, ``node``, ``message`` are named parameters of
        warning(), so they can't appear in **kwargs.
        """
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.warning(tid, "n", "m", event="hacked", ts=999)
        step = isolated_tracer.get(tid)["steps"][-1]
        assert step["event"] == "warning"  # not "hacked"
        assert step["ts"] != 999

    def test_step_on_nonexistent_trace_does_not_crash(self, isolated_tracer):
        """step() on an unknown trace_id writes to file but doesn't crash.

        The _store.append_step is a no-op for unknown IDs, but the _writer
        still emits the record so the event is visible in JSONL logs.
        """
        isolated_tracer.step("ghost-tid", "read", "msg")  # must not raise


# ===========================================================================
# Tracer — finish
# ===========================================================================
class TestTracerFinish:
    def test_finish_sets_status_success(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.finish(tid, success=True, result="done")
        trace = isolated_tracer.get(tid)
        assert trace["status"] == "success"
        assert trace["result"] == "done"

    def test_finish_sets_status_failed(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.finish(tid, success=False, result="boom")
        trace = isolated_tracer.get(tid)
        assert trace["status"] == "failed"

    def test_finish_computes_elapsed(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        trace = isolated_tracer.get(tid)
        started = trace["started_at"]
        # Patch time so elapsed is deterministic
        with patch("core.observability.tracer_engine.time.time", return_value=started + 5.0):
            isolated_tracer.finish(tid, success=True, result="done")
        trace = isolated_tracer.get(tid)
        assert trace["elapsed"] == 5.0

    def test_finish_truncates_result_to_200(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        long_result = "x" * 500
        isolated_tracer.finish(tid, success=True, result=long_result)
        trace = isolated_tracer.get(tid)
        assert len(trace["result"]) == 200

    def test_finish_kwargs_cannot_overwrite_hardcoded_keys(self, isolated_tracer, mock_writer):
        """[P0 FIX] kwargs must not overwrite event, trace_id, elapsed_s.

        Note: ``trace_id`` and ``success`` are named parameters of finish(),
        so they can't appear in **kwargs — Python would raise TypeError.
        The kwargs-spread fix protects against event/elapsed_s/result which
        ARE in the hardcoded set but could also be passed as kwargs if a
        caller mistakenly includes them.
        """
        tid = isolated_tracer.new_trace("wf")
        mock_writer.write.reset_mock()
        isolated_tracer.finish(
            tid, success=True, result="r",
            event="hacked", elapsed_s=999,
        )
        record = mock_writer.write.call_args[0][0]
        assert record["event"] == "trace_finish"  # not "hacked"
        assert record["trace_id"] == tid           # from positional arg
        assert record["elapsed_s"] != 999            # computed from timestamps

    def test_finish_nonexistent_trace_elapsed_zero(self, isolated_tracer):
        """finish() on an unknown trace_id sets elapsed=0 (no crash)."""
        isolated_tracer.finish("ghost", success=True, result="r")  # must not raise

    def test_finish_appends_finish_event_to_steps(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf")
        isolated_tracer.step(tid, "read", "msg")
        isolated_tracer.finish(tid, success=True, result="done")
        trace = isolated_tracer.get(tid)
        # 1 step + 1 finish event
        assert len(trace["steps"]) == 2
        assert trace["steps"][-1]["event"] == "trace_finish"


# ===========================================================================
# Tracer — get / recent / summary
# ===========================================================================
class TestTracerGetRecentSummary:
    def test_get_returns_trace(self, isolated_tracer):
        tid = isolated_tracer.new_trace("wf", goal="g")
        assert isolated_tracer.get(tid) is not None

    def test_get_nonexistent_returns_none(self, isolated_tracer):
        assert isolated_tracer.get("ghost") is None

    def test_recent_returns_n_traces(self, isolated_tracer):
        for i in range(5):
            isolated_tracer.new_trace(f"wf-{i}")
        recent = isolated_tracer.recent(n=3)
        assert len(recent) == 3

    def test_recent_empty(self, isolated_tracer):
        assert isolated_tracer.recent() == []

    def test_summary_format(self, isolated_tracer):
        tid = isolated_tracer.new_trace("autocode", goal="fix bug")
        isolated_tracer.step(tid, "read", "loaded")
        isolated_tracer.finish(tid, success=True, result="done")
        summary = isolated_tracer.summary(tid)
        assert tid in summary
        assert "autocode" in summary
        assert "success" in summary
        # 1 step + 1 finish event = 2 entries in steps list
        assert "steps=2" in summary
        assert "elapsed=" in summary

    def test_summary_nonexistent(self, isolated_tracer):
        summary = isolated_tracer.summary("ghost")
        assert "not found" in summary


# ===========================================================================
# Facade: core.tracer re-exports the engine's names
# ===========================================================================
class TestFacade:
    def test_facade_reexports_names(self):
        """core.tracer must re-export all public + private names that any
        caller (incl. tests) imports from that path."""
        from core.tracer import (
            _HAS_STRUCTLOG as f_hs,
            _FileWriter as f_fw,
            _TraceStore as f_ts,
            _configure_structlog as f_cs,
            _log as f_log,
            _store as f_store,
            _writer as f_writer,
            Tracer as f_Tracer,
            generate_trace_id as f_gti,
            tracer as f_tracer,
        )
        # The re-exported names must be the SAME objects as the engine's
        from core.observability.tracer_engine import (
            _HAS_STRUCTLOG as e_hs,
            _FileWriter as e_fw,
            _TraceStore as e_ts,
            _configure_structlog as e_cs,
            _log as e_log,
            _store as e_store,
            _writer as e_writer,
            Tracer as e_Tracer,
            generate_trace_id as e_gti,
        )
        assert f_hs is e_hs
        assert f_fw is e_fw
        assert f_ts is e_ts
        assert f_cs is e_cs
        assert f_log is e_log
        assert f_store is e_store      # same _TraceStore singleton
        assert f_writer is e_writer    # same _FileWriter singleton
        assert f_Tracer is e_Tracer
        assert f_gti is e_gti

    def test_facade_tracer_is_Tracer_instance(self):
        from core.tracer import tracer as f_tracer
        assert isinstance(f_tracer, Tracer)

    def test_facade_and_engine_share_store(self, isolated_tracer):
        """Both the facade singleton and engine singleton use the SAME
        module-level _store, so traces created via one are visible via the other."""
        from core.tracer import tracer as facade_tracer
        tid = facade_tracer.new_trace("facade_test")
        # Engine singleton can see it
        assert tracer.get(tid) is not None
        # And vice versa: create via engine, read via facade
        tid2 = tracer.new_trace("engine_test")
        assert facade_tracer.get(tid2) is not None


# ===========================================================================
# Integration: full lifecycle
# ===========================================================================
class TestIntegrationLifecycle:
    def test_full_lifecycle_end_to_end(self, isolated_tracer, mock_writer):
        """new_trace → step → step → error → warning → finish → get."""
        tid = isolated_tracer.new_trace("autocode", goal="fix memory.py")
        isolated_tracer.step(tid, "read", "file loaded", chars=4200)
        isolated_tracer.step(tid, "apply", "patch applied", latency_ms=12.5)
        isolated_tracer.error(tid, "apply", "patch failed", error="context mismatch")
        isolated_tracer.warning(tid, "retry", "transient", attempt=1)
        isolated_tracer.finish(tid, success=True, result="committed abc123")

        trace = isolated_tracer.get(tid)
        assert trace["status"] == "success"
        assert trace["result"] == "committed abc123"
        # 2 steps + 1 error + 1 warning + 1 finish = 5 entries
        assert len(trace["steps"]) == 5
        events = [s["event"] for s in trace["steps"]]
        assert events == ["step", "step", "error", "warning", "trace_finish"]

        # Writer should have received: trace_start + 4 step-like + 1 finish = 6
        assert mock_writer.write.call_count == 6

    def test_multiple_traces_independent(self, isolated_tracer):
        """Concurrent traces must not interfere with each other."""
        t1 = isolated_tracer.new_trace("wf-a")
        t2 = isolated_tracer.new_trace("wf-b")
        isolated_tracer.step(t1, "node-a", "msg-a")
        isolated_tracer.step(t2, "node-b", "msg-b")
        isolated_tracer.finish(t1, success=True)
        isolated_tracer.finish(t2, success=False, result="err")

        a = isolated_tracer.get(t1)
        b = isolated_tracer.get(t2)
        assert a["workflow"] == "wf-a"
        assert b["workflow"] == "wf-b"
        assert a["status"] == "success"
        assert b["status"] == "failed"
        assert len(a["steps"]) == 2  # 1 step + 1 finish
        assert len(b["steps"]) == 2
