"""Tests for MED-05 tag validation.

Tag validation is the primary XSS/injection prevention layer.
These tests must be comprehensive and independent of the store mock.
"""
from __future__ import annotations

import pytest

from tools.memory_ops.helpers import _validate_tags


class TestTagValidationEmpty:
    def test_empty_tags_valid(self):
        is_valid, err = _validate_tags("", max_count=6)
        assert is_valid is True
        assert err == ""


class TestTagValidationSuccess:
    def test_valid_tags(self):
        is_valid, err = _validate_tags("python,debug,mcp", max_count=6)
        assert is_valid is True
        assert err == ""

    def test_valid_tag_with_hyphen_and_underscore(self):
        is_valid, err = _validate_tags("my-tag_name.v2", max_count=6)
        assert is_valid is True

    def test_single_tag(self):
        is_valid, err = _validate_tags("python", max_count=6)
        assert is_valid is True


class TestTagValidationDangerousChars:
    def test_dangerous_chars_rejected(self):
        for bad in ["<", ">", "\"", "'", "`", "|"]:
            is_valid, err = _validate_tags(f"tag{bad}bad", max_count=6)
            assert is_valid is False, f"Should reject: {bad}"
            assert "cannot contain" in err

    def test_newline_rejected(self):
        # Use actual newline character
        is_valid, err = _validate_tags("tag" + chr(10) + "bad", max_count=6)
        assert is_valid is False
        assert "cannot contain" in err


class TestTagValidationLimits:
    def test_too_many_tags(self):
        is_valid, err = _validate_tags("a,b,c,d,e,f,g", max_count=6)
        assert is_valid is False
        assert "Too many tags" in err

    def test_tag_too_long(self, mock_cfg):
        """Uses cfg.max_tag_length (default 50)."""
        long_tag = "a" * 51
        is_valid, err = _validate_tags(long_tag, max_count=6)
        assert is_valid is False
        assert "exceeds length limit" in err

    def test_tag_count_uses_config(self, mock_cfg):
        """Verify max_tags_per_entry is read from config."""
        mock_cfg.max_tags_per_entry = 2
        is_valid, err = _validate_tags("a,b,c", max_count=mock_cfg.max_tags_per_entry)
        assert is_valid is False

    def test_tag_length_uses_config(self, mock_cfg):
        """Verify max_tag_length is read from config."""
        mock_cfg.max_tag_length = 10
        is_valid, err = _validate_tags("verylongtagname", max_count=6)
        assert is_valid is False


class TestTagValidationFormat:
    def test_tag_must_start_with_letter(self):
        is_valid, err = _validate_tags("123invalid", max_count=6)
        assert is_valid is False
        assert "invalid characters" in err.lower()

    def test_tag_cannot_start_with_number(self):
        is_valid, err = _validate_tags("9tags", max_count=6)
        assert is_valid is False

    def test_tag_cannot_start_with_hyphen(self):
        is_valid, err = _validate_tags("-tag", max_count=6)
        assert is_valid is False

    def test_whitespace_only_tags_rejected(self):
        is_valid, err = _validate_tags("   ", max_count=6)
        assert is_valid is False
        assert "No valid tags" in err
