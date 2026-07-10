"""
tests/core/tracer/test_reader.py
Unit tests for the trace reader (memory + disk fallback).
"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch
from core.observability.reader import read_trace, list_recent_traces

@pytest.fixture
def mock_tracer():
    with patch("core.observability.reader.tracer") as mock:
        yield mock

@pytest.fixture
def mock_config(tmp_path):
    with patch("core.observability.reader.cfg") as mock_cfg:
        mock_cfg.log_path = tmp_path
        yield mock_cfg

class TestReadTrace:
    def test_fast_path_memory_hit(self, mock_tracer):
        mock_tracer.get.return_value = {
            "trace_id": "abc123",
            "workflow": "research",
            "goal": "test",
            "status": "success",
            "started_fmt": "2026-01-01",
            "elapsed": 5.0,
            "result": "done",
            "steps": [{"node": "start"}]
        }
        
        result = read_trace("abc123")
        assert result is not None
        assert result["trace_id"] == "abc123"
        assert result["workflow"] == "research"
        mock_tracer.get.assert_called_once_with("abc123")

    def test_slow_path_disk_scan(self, mock_tracer, mock_config):
        mock_tracer.get.return_value = None
        
        # Create a dummy log file
        log_file = mock_config.log_path / "agent_20260101.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"event": "trace_start", "trace_id": "disk123", "workflow": "data", "goal": "analyze", "started_fmt": "2026-01-01"}) + "\n")
            f.write(json.dumps({"event": "step", "trace_id": "disk123", "node": "search", "message": "searching", "ts": 1000}) + "\n")
            f.write(json.dumps({"event": "trace_finish", "trace_id": "disk123", "success": True, "elapsed_s": 10.0, "result": "done"}) + "\n")
            
        result = read_trace("disk123")
        assert result is not None
        assert result["trace_id"] == "disk123"
        assert result["workflow"] == "data"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["node"] == "search"

    def test_not_found(self, mock_tracer, mock_config):
        mock_tracer.get.return_value = None
        result = read_trace("nonexistent")
        assert result is None

class TestListRecentTraces:
    def test_list_recent(self, mock_tracer):
        mock_tracer.recent.return_value = [
            {"trace_id": "t1", "workflow": "a", "goal": "g1", "status": "success", "started_fmt": "now", "elapsed": 1, "result": "r", "steps": []},
            {"trace_id": "t2", "workflow": "b", "goal": "g2", "status": "failed", "started_fmt": "now", "elapsed": 2, "result": "r", "steps": []}
        ]
        
        traces = list_recent_traces(limit=2)
        assert len(traces) == 2
        assert traces[0]["trace_id"] == "t1"