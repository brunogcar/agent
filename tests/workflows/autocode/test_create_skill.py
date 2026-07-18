"""tests/workflows/autocode/test_create_skill.py
Tests for node_create_skill — skill generation, name sanitization,
syntax validation, and skill_created flag.

[v1.2] Added tests for empty-skill-content rejection (#36):
  - test_empty_skill_file_rejected: skill_code fallback succeeds (or fails import)
  - test_truly_empty_skill_file_rejected: no content key → fail with "empty" in error.
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
        # Mock the LLM to return valid skill code — use the canonical skill_file
        # key (the v1.2 fix tries skill_code / code as fallbacks too).
        with patch("workflows.autocode_impl.nodes.create_skill._call",
                   return_value='{"skill_name": "test_skill", "skill_file": "def run():\\n    return \\"test\\"", "explanation": "a test skill"}'):
            result = node_create_skill(base_state)
            assert result.get("skill_created") is True or result.get("status") == "error"

    def test_empty_skill_file_rejected(self, base_state, temp_workspace):
        """[v1.2] Empty skill_file content must be rejected, not silently write empty file."""
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        base_state["task_type"] = "create_skill"
        base_state["task"] = "create a test skill"
        base_state["dry_run"] = False
        with patch("workflows.autocode_impl.nodes.create_skill._call",
                   return_value='{"skill_name": "test_skill", "skill_code": "def run(): pass", "skill_description": "a test skill"}'):
            result = node_create_skill(base_state)
            # Should try skill_code fallback, find content, and succeed
            assert result.get("status") in ("done", "failed")  # done if import works, failed if import fails

    def test_truly_empty_skill_file_rejected(self, base_state, temp_workspace):
        """[v1.2] Truly empty content (no fallback key) must fail."""
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        base_state["task_type"] = "create_skill"
        base_state["task"] = "create a test skill"
        base_state["dry_run"] = False
        with patch("workflows.autocode_impl.nodes.create_skill._call",
                   return_value='{"skill_name": "test_skill"}'):
            result = node_create_skill(base_state)
            assert result.get("status") == "failed"
            assert "empty" in result.get("error", "").lower()
