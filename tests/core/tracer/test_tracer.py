"""
tests/core/tracer/test_tracer.py
Unit tests for the core tracer primitive.
"""
import pytest
from unittest.mock import patch
from core.tracer import tracer, _TraceStore, generate_trace_id

class TestTraceStore:
    def test_create_and_get(self):
        store = _TraceStore()
        store.create("tid-1", {"workflow": "test", "goal": "test goal"})
        trace = store.get("tid-1")
        assert trace is not None
        assert trace["workflow"] == "test"

    def test_max_traces_bounded(self):
        store = _TraceStore()
        store.MAX_TRACES = 5
        for i in range(10):
            store.create(f"tid-{i}", {"workflow": "test"})
        
        # Should only keep the last 5
        assert len(store._order) == 5
        assert store.get("tid-0") is None
        assert store.get("tid-9") is not None

    def test_append_step(self):
        store = _TraceStore()
        store.create("tid-1", {"workflow": "test"})
        store.append_step("tid-1", {"node": "start", "message": "hello"})
        
        trace = store.get("tid-1")
        assert len(trace["steps"]) == 1
        assert trace["steps"][0]["node"] == "start"

class TestTracerPublicAPI:
    def test_new_trace_returns_id(self):
        # Mock the file writer to prevent disk I/O during tests
        with patch("core.tracer._writer") as mock_writer:
            tid = tracer.new_trace("autocode", goal="fix bug")
            assert len(tid) == 8
            assert mock_writer.write.called

    def test_generate_trace_id_length(self):
        tid = generate_trace_id(length=12)
        assert len(tid) == 12