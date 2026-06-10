"""Test LLM telemetry and per-role context budgets."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from core.llm_backend.client import LLMClient, _ROLE_BUDGETS
from core.llm_backend.config import RoleConfig


class TestRoleBudgets:
    """Verify per-role context budgets are correctly defined."""

    def test_planner_budget(self):
        assert _ROLE_BUDGETS["planner"] == 32000

    def test_executor_budget(self):
        assert _ROLE_BUDGETS["executor"] == 12000

    def test_router_budget(self):
        assert _ROLE_BUDGETS["router"] == 4000
        assert _ROLE_BUDGETS["route"] == 4000
        assert _ROLE_BUDGETS["classify"] == 4000

    def test_unknown_role_fallback(self):
        """Unknown roles should fall back to cfg.max_context_tokens."""
        assert "unknown_role" not in _ROLE_BUDGETS


class TestTelemetryLogging:
    """Verify telemetry is logged before every LLM call."""

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {},
        }
        return provider

    @pytest.fixture
    def llm_client(self, mock_provider):
        client = LLMClient()
        client._registry.register("lmstudio", mock_provider)
        return client

    def test_telemetry_logs_estimated_tokens(self, llm_client, mock_provider):
        """logger.info should be called with role, message count, estimated tokens, and budget."""
        with patch("core.llm_backend.client.logger") as mock_logger:
            resp = llm_client.call(
                role="executor",
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "Hello"},
                ],
            )
            assert resp.ok
            mock_logger.info.assert_called_once()
            args = mock_logger.info.call_args[0]
            assert args[0] == "LLM call: role=%s messages=%d est_tokens=%d budget=%d"
            assert args[1] == "executor"  # role
            assert args[2] == 2            # message count
            assert args[3] > 0             # estimated tokens
            assert args[4] == 12000        # budget

    def test_telemetry_uses_role_specific_budget(self, llm_client, mock_provider):
        """Planner should use 32K budget, not the global default."""
        with patch("core.llm_backend.client.logger") as mock_logger:
            llm_client.call(role="plan", messages=[{"role": "user", "content": "test"}])
            args = mock_logger.info.call_args[0]
            assert args[4] == 32000  # planner budget

    def test_telemetry_zero_content_messages(self, llm_client, mock_provider):
        """Messages with empty content should estimate 0 tokens."""
        with patch("core.llm_backend.client.logger") as mock_logger:
            llm_client.call(role="router", messages=[{"role": "user", "content": ""}])
            args = mock_logger.info.call_args[0]
            assert args[3] == 0  # est_tokens for empty content

    def test_budget_messages_called_with_role_budget(self, llm_client, mock_provider):
        """budget_messages should receive the role-specific budget, not global."""
        with patch("core.memory_backend.budget.budget_messages") as mock_budget:
            mock_budget.return_value = [{"role": "user", "content": "test"}]
            llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
            mock_budget.assert_called_once()
            _, budget_arg = mock_budget.call_args[0]
            assert budget_arg == 12000  # executor budget, not global 8000
