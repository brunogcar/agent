"""Agent tool tests — autonomous model escalation on parse failure."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestModelEscalation:
    """Test auto-retry with planner model when JSON parsing fails."""

    def setup_method(self):
        _clear_cache()

    def test_escalation_triggered_on_parse_failure(self, mock_llm_result):
        """When primary model returns invalid JSON, planner model retries."""
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result["status"] == "success"
            assert "parsed" in result
            assert result.get("escalated") is True
            assert mock_llm.call_count == 2

    def test_no_escalation_when_json_valid(self, mock_llm_result):
        mock_llm_result.text = '{"workflow": "research"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert "parsed" in result
            assert mock_llm.call_count == 1

    def test_escalation_failure_keeps_parse_warning(self, mock_llm_result):
        """If escalation also fails, original parse_warning is preserved."""
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = "also not json"
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result["status"] == "success"
            assert "parse_warning" in result

    def test_escalation_updates_response_fields(self, mock_llm_result):
        """Escalation success should update text, model, and usage from escalation result."""
        mock_llm_result.text = "bad json"
        mock_llm_result.parsed = None
        mock_llm_result.model = "primary-model"
        mock_llm_result.usage = {"total": 10}

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner-model"
        escalation_result.usage = {"total": 25}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result["status"] == "success"
            assert result["model"] == "planner-model"
            assert result["usage"]["total"] == 25
            assert result.get("escalated") is True

    # ─── Escalation prompt + json_mode (Bug #7) ──────────────────────────────

    def test_escalation_uses_plan_role_system_prompt(self, mock_llm_result):
        """Escalation must use the plan role's system prompt, not the original role's.

        The plan role is designed for structured output; using the original
        role's prompt (often a binary classifier or code generator) produced
        worse JSON. NOTE: ROLES['plan'] configures the prompt, while
        llm.complete is called with role='planner' (the model registry key).
        """
        from tools.agent_ops import ROLES

        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            agent(action="dispatch", role="route", task="test")

            assert mock_llm.call_count == 2
            escalation_kwargs = mock_llm.call_args_list[1].kwargs
            plan_prompt = ROLES["plan"]["system_prompt"]
            assert escalation_kwargs["system"] == plan_prompt, (
                "Escalation must use the plan role's system prompt, not the original role's."
            )

    def test_escalation_respects_plan_role_json_mode(self, mock_llm_result):
        """Escalation json_mode must match the plan role's config, not be hardcoded False."""
        from tools.agent_ops import ROLES

        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            agent(action="dispatch", role="route", task="test")

            escalation_kwargs = mock_llm.call_args_list[1].kwargs
            plan_cfg = ROLES["plan"]["role_config"]
            expected_json_mode = plan_cfg.get("json_mode") == "api"
            assert escalation_kwargs["json_mode"] == expected_json_mode, (
                "Escalation json_mode must match plan role's config, not be hardcoded False."
            )

    # ─── escalated_from origin tracking (Bug #8) ─────────────────────────────

    def test_escalation_records_escalated_from(self, mock_llm_result):
        """Escalation must record the origin role+model in 'escalated_from'.

        Without this field, callers can't tell the primary model failed —
        useful for debugging and metrics.
        """
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None
        mock_llm_result.model = "primary-model"

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner-model"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result.get("escalated") is True
            assert "escalated_from" in result, (
                "escalated_from must be set to track the origin model."
            )
            assert result["escalated_from"]["model"] == "primary-model"
            assert result["escalated_from"]["role"] == "route"
