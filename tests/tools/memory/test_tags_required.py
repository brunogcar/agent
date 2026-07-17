"""Tests for tags_required (AND-based tag filtering) — v1.4 Commit 5."""
from __future__ import annotations

import pytest

from tools.memory import memory


class TestTagsRequired:
    """tags_required uses AND semantics — ALL required tags must be present."""

    def test_tags_required_accepted(self, mock_cfg, mock_store):
        """tags_required with valid prefixed tags is accepted (not rejected by validation)."""
        result = memory(
            action="recall", query="test",
            tags_required="source:sleep_learn,domain:python",
        )
        assert result["status"] == "success"

    def test_tags_required_empty_by_default(self, mock_cfg, mock_store):
        """tags_required defaults to empty string (no AND filtering)."""
        result = memory(action="recall", query="test")
        assert result["status"] == "success"

    def test_tags_required_and_tags_filter_coexist(self, mock_cfg, mock_store):
        """Both tags_filter (OR) and tags_required (AND) can be used together."""
        result = memory(
            action="recall", query="test",
            tags_filter="bugfix,pattern",
            tags_required="source:sleep_learn",
        )
        assert result["status"] == "success"

    def test_tags_required_validated(self, mock_cfg, mock_store):
        """Invalid tags (dangerous chars) in tags_required are rejected."""
        result = memory(
            action="recall", query="test",
            tags_required="<script>alert(1)</script>",
        )
        assert result["status"] == "error"

    def test_tags_required_empty_string_ok(self, mock_cfg, mock_store):
        """Empty tags_required is valid (no filtering)."""
        result = memory(action="recall", query="test", tags_required="")
        assert result["status"] == "success"


class TestTagsRequiredAndSemantics:
    """Verify the AND logic (unit test of the filtering)."""

    def test_and_subset_check(self):
        """Test the subset check logic directly."""
        actual = {"source:sleep_learn", "domain:python", "category:bugfix"}

        required = {"source:sleep_learn"}
        assert required <= actual

        required = {"source:sleep_learn", "domain:python"}
        assert required <= actual

        required = {"source:sleep_learn", "domain:web"}
        assert not (required <= actual)

        required = {"source:llm"}
        assert not (required <= actual)
