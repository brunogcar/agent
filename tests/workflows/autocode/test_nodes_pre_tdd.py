"""tests/workflows/autocode/test_nodes_pre_tdd.py — Phase 1-6 node tests.

Focused per-node tests for the pre-TDD pipeline nodes (the nodes that run
BEFORE the execute/debug/verify loop). Each node gets 2-3 tests covering
the happy path, error path, and skip/early-return condition.

Covers:
  - node_classify_task  (mock _call, assert routing + mode override)
  - node_brainstorm     (mock _call, assert spec + memory_context)
  - node_write_plan     (mock _call, assert plan_state + branch slug)
  - node_write_tests    (mock _call, assert test_code + current_step)

LLM, memory, and KG calls are mocked per-test — no real subprocess/git calls.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# node_classify_task
# ---------------------------------------------------------------------------


class TestNodeClassifyTask:
    def test_returns_task_type_from_llm(self, base_state):
        from workflows.autocode_impl.nodes.classify import node_classify_task
        with patch("workflows.autocode_impl.nodes.classify._call") as mock_call:
            mock_call.return_value = '{"task_type": "fix", "questions": []}'
            result = node_classify_task(base_state)
        assert result["task_type"] == "fix"

    def test_mode_override_fix_error(self, base_state):
        from workflows.autocode_impl.nodes.classify import node_classify_task
        base_state["mode"] = "fix_error"
        with patch("workflows.autocode_impl.nodes.classify._call") as mock_call:
            mock_call.return_value = '{"task_type": "feature", "questions": []}'
            result = node_classify_task(base_state)
        # Mode override must win over LLM classification.
        assert result["task_type"] == "fix"

    def test_unclear_with_questions_returns_needs_clarification(self, base_state):
        from workflows.autocode_impl.nodes.classify import node_classify_task
        with patch("workflows.autocode_impl.nodes.classify._call") as mock_call:
            mock_call.return_value = '{"task_type": "unclear", "questions": ["what scope?"]}'
            result = node_classify_task(base_state)
        assert result["status"] == "needs_clarification"
        assert "what scope?" in result["result"]


# ---------------------------------------------------------------------------
# node_brainstorm
# ---------------------------------------------------------------------------


class TestNodeBrainstorm:
    def test_skips_when_needs_clarification(self, base_state):
        from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
        base_state["status"] = "needs_clarification"
        assert node_brainstorm(base_state) == {}

    def test_skips_for_create_skill_task_type(self, base_state):
        from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
        base_state["task_type"] = "create_skill"
        # _call must NOT be invoked for create_skill path.
        with patch("workflows.autocode_impl.nodes.brainstorm._call") as mock_call:
            result = node_brainstorm(base_state)
            mock_call.assert_not_called()
        assert result == {}

    def test_writes_spec_and_memory_context(self, base_state):
        from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
        spec_payload = {"spec": "refined spec", "acceptance_criteria": ["ac1"]}
        with patch("workflows.autocode_impl.nodes.brainstorm._call") as mock_call, \
             patch("core.memory_engine.memory.recall", return_value=[]), \
             patch("core.sleep_learn.inject_rules_into_prompt", side_effect=lambda system_prompt, **kw: system_prompt):
            mock_call.return_value = json.dumps(spec_payload)
            result = node_brainstorm(base_state)
        assert "memory_context" in result
        assert result["plan_state"]["spec"].startswith("refined spec")
        assert "Acceptance criteria:" in result["plan_state"]["spec"]


# ---------------------------------------------------------------------------
# node_write_plan
# ---------------------------------------------------------------------------


class TestNodeWritePlan:
    def test_skips_when_needs_clarification(self, base_state):
        from workflows.autocode_impl.nodes.plan import node_write_plan
        base_state["status"] = "needs_clarification"
        assert node_write_plan(base_state) == {}

    def test_writes_plan_and_branch_slug(self, base_state):
        from workflows.autocode_impl.nodes.plan import node_write_plan
        base_state["task"] = "Add user login feature"
        plan_payload = [{"id": 1, "label": "write_tests", "description": "tests"}]
        with patch("workflows.autocode_impl.nodes.plan._call") as mock_call, \
             patch("core.sleep_learn.inject_rules_into_prompt", side_effect=lambda system_prompt, **kw: system_prompt):
            mock_call.return_value = json.dumps(plan_payload)
            result = node_write_plan(base_state)
        assert result["plan_state"]["plan"] == plan_payload
        assert result["plan_state"]["current_step"] == 0
        # Branch slug derived from task: "Add user login feature" -> "add-user-login-feature"
        assert "add-user-login-feature" in result["vcs"]["branch"]
        # Trace suffix must be appended (uniqueness).
        assert result["vcs"]["branch"].startswith("autocode/")

    def test_fallback_plan_when_llm_returns_empty(self, base_state):
        from workflows.autocode_impl.nodes.plan import node_write_plan
        with patch("workflows.autocode_impl.nodes.plan._call") as mock_call, \
             patch("core.sleep_learn.inject_rules_into_prompt", side_effect=lambda system_prompt, **kw: system_prompt):
            mock_call.return_value = "[]"
            result = node_write_plan(base_state)
        plan = result["plan_state"]["plan"]
        assert len(plan) == 3  # Fallback 3-step plan (write_tests, implement, verify)
        assert plan[0]["label"] == "write_tests"


# ---------------------------------------------------------------------------
# node_write_tests
# ---------------------------------------------------------------------------


class TestNodeWriteTests:
    def test_skips_when_step_label_not_write_tests(self, base_state):
        from workflows.autocode_impl.nodes.tests import node_write_tests
        # Default base_state plan has label "write_code" — node must early-return {}.
        with patch("workflows.autocode_impl.nodes.tests._call") as mock_call:
            result = node_write_tests(base_state)
            mock_call.assert_not_called()
        assert result == {}

    def test_writes_test_code_and_increments_step(self, base_state):
        from workflows.autocode_impl.nodes.tests import node_write_tests
        base_state["plan_state"]["plan"] = [
            {"id": 1, "label": "write_tests", "description": "write tests", "acceptance": "", "files": []},
        ]
        base_state["plan_state"]["current_step"] = 0
        with patch("workflows.autocode_impl.nodes.tests._call") as mock_call:
            mock_call.return_value = "```python\ndef test_feature(): assert True\n```"
            result = node_write_tests(base_state)
        # test_code is a list[str] from _extract_code.
        assert isinstance(result["test_code"], list)
        assert "assert True" in result["test_code"][0]
        # current_step must be incremented (1 -> 1).
        assert result["plan_state"]["current_step"] == 1

    def test_skips_when_needs_clarification(self, base_state):
        from workflows.autocode_impl.nodes.tests import node_write_tests
        base_state["status"] = "needs_clarification"
        assert node_write_tests(base_state) == {}
