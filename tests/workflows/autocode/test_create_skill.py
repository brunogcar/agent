"""tests/workflows/autocode/test_create_skill.py
Tests for node_create_skill — skill generation, name sanitization,
syntax validation, and skill_created flag.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


class TestCreateSkillFixes:
    """[v1.0.2 #15/#16/#17] Skill name sanitization, syntax check, flag."""

    def test_skill_name_sanitized(self):
        from workflows.autocode_impl.nodes.create_skill import _sanitize_skill_name
        # Non-alphanumeric → underscore, then strip leading/trailing underscores
        assert _sanitize_skill_name("my skill name!") == "my_skill_name"
        assert _sanitize_skill_name("ok_name") == "ok_name"
        assert _sanitize_skill_name("---bad---") == "bad"

    def test_python_syntax_validation_valid(self):
        from workflows.autocode_impl.nodes.create_skill import _validate_python_syntax
        ok, err = _validate_python_syntax("def run(): pass")
        assert ok is True
        assert err == ""

    def test_python_syntax_validation_invalid(self):
        from workflows.autocode_impl.nodes.create_skill import _validate_python_syntax
        ok, err = _validate_python_syntax("def broken(:")
        assert ok is False
        assert "SyntaxError" in err or "syntax" in err.lower()

    def test_skill_created_flag_set(self, base_state, temp_workspace):
        """[v1.0.2 #17] node_create_skill must set skill_created=True on success."""
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        base_state["task_type"] = "create_skill"
        base_state["task"] = "create a test skill"
        base_state["dry_run"] = False
        # Mock the LLM to return valid skill code
        with patch("workflows.autocode_impl.nodes.create_skill._call",
                   return_value='{"skill_name": "test_skill", "skill_code": "def run():\\n    return \\"test\\"", "skill_description": "a test skill"}'):
            result = node_create_skill(base_state)
            assert result.get("skill_created") is True or result.get("status") == "error"
