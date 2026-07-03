"""Tests for memory helpers — validation, lazy loading, singleton.
v1.1: NEW file. Covers _validate_collections, _validate_memory_type, _validate_tags,
      and _mem() singleton behavior.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.memory_ops.helpers import _validate_tags, _validate_memory_type, _validate_collections
import tools.memory_ops.state as mem_state


class TestValidateCollections:
    def test_none_is_valid(self):
        is_valid, err = _validate_collections(None)
        assert is_valid is True
        assert err == ""

    def test_empty_list_rejected(self):
        is_valid, err = _validate_collections([])
        assert is_valid is False
        assert "cannot be empty" in err

    def test_non_list_rejected(self):
        """v1.1: Strings and other non-list types must be rejected."""
        is_valid, err = _validate_collections("semantic")
        assert is_valid is False
        assert "must be a list" in err

    def test_valid_list(self):
        is_valid, err = _validate_collections(["semantic", "episodic"])
        assert is_valid is True
        assert err == ""


class TestValidateMemoryType:
    def test_empty_is_valid(self):
        is_valid, err = _validate_memory_type("")
        assert is_valid is True
        assert err == ""

    def test_valid_types(self):
        for t in ["episodic", "semantic", "procedural"]:
            is_valid, err = _validate_memory_type(t)
            assert is_valid is True, f"Should accept: {t}"

    def test_invalid_type_rejected(self):
        is_valid, err = _validate_memory_type("invalid")
        assert is_valid is False
        assert "Invalid memory_type" in err
        assert "episodic" in err
        assert "semantic" in err
        assert "procedural" in err


class TestValidateTags:
    def test_empty_is_valid(self):
        is_valid, err = _validate_tags("")
        assert is_valid is True
        assert err == ""

    def test_dangerous_chars_rejected(self):
        for bad in ["<", ">", "\"", "'", "`", "|"]:
            is_valid, err = _validate_tags(f"tag{bad}bad")
            assert is_valid is False, f"Should reject: {bad}"
            assert "cannot contain" in err

    def test_too_many_tags(self):
        is_valid, err = _validate_tags("a,b,c,d,e,f,g", max_count=6)
        assert is_valid is False
        assert "Too many tags" in err


class TestMemLazyLoading:
    def test_mem_creates_instance(self):
        mem_state.reset_state()
        from tools.memory_ops.helpers import _mem
        store = _mem()
        assert store is not None

    def test_mem_returns_same_instance(self):
        mem_state.reset_state()
        from tools.memory_ops.helpers import _mem
        store1 = _mem()
        store2 = _mem()
        assert store1 is store2
