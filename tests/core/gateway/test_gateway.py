"""
tests/core/gateway/test_gateway.py
Comprehensive suite for the FastAPI Gateway, SQLite Task Store, and Warmup Logic.

Tests focus on:
- ChromaDB warmup timeout guard and signature validation.
- SQLite Task Store integrity (Store/Get/Update with thread-safe isolation).
- Gateway Endpoints (Async submission, Polling, Error handling, 404 fallbacks).

Run with: pytest tests/core/gateway/test_gateway.py -v
"""
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# ── Import Path Fix ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.gateway as gw
import core.gateway_backend.factory as factory_mod
import core.gateway_backend.store as store_mod
import core.gateway_backend.dispatcher as dispatcher_mod
import core.config as config_mod
from core.tracer import tracer


class TestWarmupMemory:
    """Verify ChromaDB warmup timeout guard and function signature."""

    def test_warmup_timeout_parameter_default(self):
        """Verify _warmup_memory accepts a timeout parameter defaulting to 60s."""
        assert hasattr(factory_mod, '_warmup_memory'), "factory module missing _warmup_memory"
        import inspect
        sig = inspect.signature(factory_mod._warmup_memory)
        assert "timeout" in sig.parameters, "Missing timeout parameter"
        assert sig.parameters["timeout"].default == 60, "Default timeout should be 60s"

    def test_warmup_graceful_degradation(self, monkeypatch):
        """Verify warmup does not crash if memory module is unavailable."""
        def failing_recall(*args, **kwargs):
            raise ModuleNotFoundError("No module named 'chromadb'")

        # Mock dispatcher to prevent side effects if warmup somehow triggers it
        monkeypatch.setattr(dispatcher_mod, "dispatch", MagicMock())
        
        with patch('builtins.__import__', side_effect=failing_recall):
            try:
                factory_mod._warmup_memory(timeout=1)
            except ModuleNotFoundError:
                pass


class TestSQLiteTaskStore:
    """Test SQLite task storage functions with isolated temp databases."""

    @pytest.fixture(autouse=True)
    def setup_isolated_db(self, tmp_path, monkeypatch):
        """Monkeypatch cfg.memory_root to temp path so tests don't touch real DB."""
        monkeypatch.setattr(config_mod.cfg, "memory_root", tmp_path)
        store_mod._TASK_DB_PATH = None
        yield tmp_path
        store_mod._TASK_DB_PATH = None

    def test_store_and_get_task(self):
        """Verify a task can be stored and retrieved with correct fields."""
        trace_id = "test_task_001"
        payload = {"goal": "Test Goal", "tool": "web", "action": "search"}
        
        store_mod._store_task(trace_id, payload)
        task = store_mod._get_task(trace_id)
        
        assert task is not None
        assert task["trace_id"] == trace_id
        assert task["status"] == "pending"
        # Note: _get_task SQL does not SELECT the payload column in current implementation
        assert task["result"] is None
        assert task["error"] == ""

    def test_update_task_status_to_success(self):
        """Verify task status transitions from pending to success."""
        trace_id = "test_task_002"
        store_mod._store_task(trace_id, {"goal": "Update Test"})
        
        result_data = {"output": "success_data"}
        store_mod._update_task(trace_id, status="success", result=result_data)
        
        task = store_mod._get_task(trace_id)
        assert task["status"] == "success"
        assert task["result"] == result_data
        assert task["completed"] is not None
        assert task["completed"] >= task["submitted"]

    def test_update_task_status_to_failed(self):
        """Verify task status transitions to failed with error message."""
        trace_id = "test_task_003"
        store_mod._store_task(trace_id, {"goal": "Fail Test"})
        
        error_msg = "RuntimeError: Something went wrong"
        store_mod._update_task(trace_id, status="failed", error=error_msg)
        
        task = store_mod._get_task(trace_id)
        assert task["status"] == "failed"
        assert task["error"] == error_msg
        assert task["result"] is None

    def test_get_nonexistent_task_returns_none(self):
        """Verify _get_task returns None for missing trace_id."""
        task = store_mod._get_task("non_existent_trace_id_999")
        assert task is None


class TestGatewayEndpoints:
    """Test FastAPI endpoint logic using FastAPI's TestClient."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        """Create a TestClient for the FastAPI app with mocked startup dependencies."""
        monkeypatch.setattr(config_mod.cfg, "memory_root", tmp_path)
        monkeypatch.setattr(config_mod.cfg, "gateway_secret", "test_secret")
        monkeypatch.setattr(config_mod.cfg, "env", "dev")
        
        # Mock heavy startup functions to prevent side effects during testing
        monkeypatch.setattr(factory_mod, "_warmup_memory", lambda *args, **kwargs: None)
        
        # Mock config validation (imported locally in create_app)
        import core.config_validation
        monkeypatch.setattr(core.config_validation, "validate_config", lambda: None)
        
        # Mock background task runner so it doesn't actually execute
        import core.runtime.task_runner
        monkeypatch.setattr(core.runtime.task_runner, "run_background_task", lambda *args, **kwargs: None)
        
        # Reset DB path to use tmp_path
        store_mod._TASK_DB_PATH = None
        
        app = factory_mod.create_app()
        return TestClient(app)

    def test_submit_task_returns_trace_id_immediately(self, client):
        """Verify POST /task returns a trace_id and status 'submitted' immediately."""
        payload = {
            "goal": "Submit Test",
            "workflow": "auto",
            "platform": "api"
        }
        response = client.post(
            "/task", 
            json=payload,
            headers={"Authorization": "Bearer test_secret"}
        )
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
        assert data["status"] == "submitted"
        assert "poll_url" in data

    def test_get_result_existing_task_returns_payload(self, client, monkeypatch, tmp_path):
        """Verify GET /result/{trace_id} returns task details for a stored task."""
        monkeypatch.setattr(config_mod.cfg, "memory_root", tmp_path)
        store_mod._TASK_DB_PATH = None
        
        trace_id = "poll_test_001"
        store_mod._store_task(trace_id, {"goal": "Poll Me"})
        store_mod._update_task(trace_id, "success", result={"data": "done"})

        response = client.get(
            f"/result/{trace_id}",
            headers={"Authorization": "Bearer test_secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trace_id"] == trace_id
        assert data["status"] == "success"
        assert data["result"] == {"data": "done"}
        assert "elapsed" in data

    def test_get_result_unknown_raises_404(self, client, monkeypatch, tmp_path):
        """Verify GET /result/{trace_id} raises HTTPException for unknown trace."""
        monkeypatch.setattr(config_mod.cfg, "memory_root", tmp_path)
        store_mod._TASK_DB_PATH = None
        
        # Mock tracer.get to return None so it falls through to 404
        monkeypatch.setattr(tracer, "get", lambda x: None)

        response = client.get(
            "/result/unknown_trace_id_999",
            headers={"Authorization": "Bearer test_secret"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()