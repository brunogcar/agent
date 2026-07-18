"""Tests for CLI proxy actions (python, memory, notify, lms, skill).

Each proxy is tested by mocking the underlying tool and verifying that
the proxy passes the right parameters. No real execution happens.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.cli_ops.actions.python import _python
from tools.cli_ops.actions.memory import _memory_recall
from tools.cli_ops.actions.lms import _lms_ls, _lms_base_url
from tools.cli_ops.actions.skill import _skill_call
from tools.cli_ops.actions.notify import _notify


class TestPythonProxy:
    """Tests for the python proxy action mapping (P1 #1)."""

    def test_python_proxy_run(self, mock_cfg):
        """CLI action 'run' should call python(action='run')."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"output": "hi"}
            _python(action="run", code="print('hi')")
            mock_py.assert_called_once_with(action="run", code="print('hi')")

    def test_python_proxy_calc(self, mock_cfg):
        """CLI action 'calc' should map to python(action='eval')."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"output": "4"}
            _python(action="calc", code="2+2")
            mock_py.assert_called_once_with(action="eval", code="2+2")

    def test_python_proxy_data(self, mock_cfg):
        """CLI action 'data' should map to python(action='run_data')."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"output": "ok"}
            _python(action="data", code="import pandas")
            mock_py.assert_called_once_with(action="run_data", code="import pandas")

    def test_python_proxy_unknown_action_passes_through(self, mock_cfg):
        """Unknown CLI actions should pass through to the python tool."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"output": "ok"}
            _python(action="profile", code="x = 1")
            mock_py.assert_called_once_with(action="profile", code="x = 1")

    def test_python_proxy_returns_output_field(self, mock_cfg):
        """Proxy should extract the 'output' field from the python tool's dict."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"output": "hello world", "status": "success"}
            result = _python(action="run", code="print('hello world')")
            assert result == "hello world"

    def test_python_proxy_returns_error_field_on_failure(self, mock_cfg):
        """Proxy should extract the 'error' field when output is missing."""
        with patch("tools.python.python") as mock_py:
            mock_py.return_value = {"error": "syntax error", "status": "error"}
            result = _python(action="run", code="invalid syntax")
            assert "syntax error" in result


class TestMemoryProxy:
    """Tests for the memory proxy actions."""

    def test_memory_recall_passes_params(self, mock_cfg):
        """_memory_recall should pass query/top_k to memory.recall."""
        mock_store = MagicMock()
        mock_store.recall.return_value = []
        with patch("tools.cli_ops.actions.memory._mem", return_value=mock_store):
            _memory_recall(action="recall", query="test query", top_k=3)
            mock_store.recall.assert_called_once()
            _, kwargs = mock_store.recall.call_args
            assert kwargs.get("query") == "test query"
            assert kwargs.get("top_k") == 3

    def test_memory_recall_formats_results(self, mock_cfg):
        """_memory_recall should format results as '[col] score=... | text...'."""
        mock_store = MagicMock()
        mock_store.recall.return_value = [
            {"collection": "semantic", "score": 0.9, "text": "hello world"},
        ]
        with patch("tools.cli_ops.actions.memory._mem", return_value=mock_store):
            result = _memory_recall(action="recall", query="test")
            assert "semantic" in result
            assert "0.9" in result
            assert "hello world" in result

    def test_memory_recall_no_results(self, mock_cfg):
        """_memory_recall with no results should return 'No memories found.'."""
        mock_store = MagicMock()
        mock_store.recall.return_value = []
        with patch("tools.cli_ops.actions.memory._mem", return_value=mock_store):
            result = _memory_recall(action="recall", query="nothing")
            assert "No memories found" in result


class TestLmsProxy:
    """Tests for the lms proxy actions."""

    def test_lms_base_url_strips_v1_suffix(self, mock_cfg, monkeypatch):
        """_lms_base_url() should strip the trailing /v1 from cfg.lm_studio_base_url."""
        monkeypatch.setattr(
            "tools.cli_ops.actions.lms.cfg.lm_studio_base_url",
            "http://localhost:1234/v1",
        )
        assert _lms_base_url() == "http://localhost:1234"

    def test_lms_base_url_no_v1_suffix(self, mock_cfg, monkeypatch):
        """_lms_base_url() should pass through URLs without /v1 suffix unchanged."""
        monkeypatch.setattr(
            "tools.cli_ops.actions.lms.cfg.lm_studio_base_url",
            "http://my-lmstudio:9999",
        )
        assert _lms_base_url() == "http://my-lmstudio:9999"

    def test_lms_proxy_ls_hits_api_v0_models(self, mock_cfg, monkeypatch):
        """_lms_ls should GET /api/v0/models on the LM Studio base URL."""
        # Patch cfg.lm_studio_base_url to a non-default value so we can
        # verify the URL is constructed from cfg (not hardcoded).
        monkeypatch.setattr(
            "tools.cli_ops.actions.lms.cfg.lm_studio_base_url",
            "http://my-lmstudio:9999/v1",
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "llama-7b"}, {"id": "mistral-7b"}]
        mock_resp.raise_for_status.return_value = None
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = _lms_ls(action="ls")
            called_url = mock_get.call_args[0][0]
            # /v1 should be stripped, then /api/v0/models appended
            assert called_url == "http://my-lmstudio:9999/api/v0/models"
            assert "llama-7b" in result
            assert "mistral-7b" in result

    def test_lms_proxy_ls_handles_error(self, mock_cfg, monkeypatch):
        """_lms_ls should return 'LM Studio error: ...' on request failure."""
        monkeypatch.setattr(
            "tools.cli_ops.actions.lms.cfg.lm_studio_base_url",
            "http://localhost:1234/v1",
        )
        with patch("requests.get", side_effect=Exception("connection refused")):
            result = _lms_ls(action="ls")
            assert "LM Studio error" in result
            assert "connection refused" in result


class TestSkillProxy:
    """Tests for the skill proxy actions (P1 #8)."""

    def test_skill_call_passes_arg_as_generic_param(self, mock_cfg):
        """_skill_call should pass arg as a generic param to the dispatcher."""
        with patch("skills.dispatcher.skill") as mock_skill:
            mock_skill.return_value = {"status": "ok"}
            _skill_call(action="call", domain="b3", mode="query", arg="PETR4")
            mock_skill.assert_called_once_with(domain="b3", mode="query", arg="PETR4")

    def test_skill_call_passes_extra_kwargs_through(self, mock_cfg):
        """_skill_call should pass extra kwargs through to the dispatcher."""
        with patch("skills.dispatcher.skill") as mock_skill:
            mock_skill.return_value = {"status": "ok"}
            _skill_call(
                action="call", domain="b3", mode="query",
                arg="PETR4", ticker="PETR4",
            )
            _, kwargs = mock_skill.call_args
            assert kwargs.get("arg") == "PETR4"
            assert kwargs.get("ticker") == "PETR4"
            assert kwargs.get("domain") == "b3"
            assert kwargs.get("mode") == "query"

    def test_skill_call_no_arg(self, mock_cfg):
        """_skill_call with no arg should not pass arg= to the dispatcher."""
        with patch("skills.dispatcher.skill") as mock_skill:
            mock_skill.return_value = {"status": "ok"}
            _skill_call(action="call", domain="b3", mode="status")
            mock_skill.assert_called_once_with(domain="b3", mode="status")

    def test_skill_call_returns_json_for_dict(self, mock_cfg):
        """_skill_call should JSON-serialize dict results."""
        import json as _json
        with patch("skills.dispatcher.skill") as mock_skill:
            mock_skill.return_value = {"status": "ok", "data": [1, 2, 3]}
            result = _skill_call(action="call", domain="b3", mode="status")
            # Result should be valid JSON parsing back to the original dict.
            # (indent=2 pretty-prints the list across multiple lines, so we
            # parse rather than substring-match the formatted list.)
            parsed = _json.loads(result)
            assert parsed == {"status": "ok", "data": [1, 2, 3]}

    def test_skill_call_import_error_message(self, mock_cfg):
        """_skill_call should return a friendly error if dispatcher is missing."""
        with patch("skills.dispatcher.skill", side_effect=ImportError("no module")):
            result = _skill_call(action="call", domain="b3", mode="status")
            assert "skills/dispatcher.py not found" in result


class TestNotifyProxy:
    """Tests for the notify proxy."""

    def test_notify_passes_params(self, mock_cfg):
        """_notify should pass action='send' and message to notify()."""
        with patch("tools.notify.notify") as mock_notify:
            mock_notify.return_value = {"message": "ok"}
            _notify(action="send", message="hello")
            mock_notify.assert_called_once_with(action="send", message="hello")

    def test_notify_returns_message_field(self, mock_cfg):
        """_notify should extract the 'message' field from the notify dict."""
        with patch("tools.notify.notify") as mock_notify:
            mock_notify.return_value = {"message": "notification sent", "status": "ok"}
            result = _notify(action="send", message="hello")
            assert "notification sent" in result
