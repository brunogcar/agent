"""Test directory_tree action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestDirectoryTree:
    def test_directory_tree(self, sample_dir):
        result = file(action="directory_tree", path=sample_dir)
        assert result.get("status") == "success"
        tree = result.get("tree", [])
        assert len(tree) >= 3  # a.txt, b.txt, subdir
        assert result.get("count") >= 3

    def test_directory_tree_max_depth(self, sample_dir):
        result = file(action="directory_tree", path=sample_dir, max_depth=1)
        assert result.get("status") == "success"
        # Should still list top-level items
        assert result.get("count") >= 3

    def test_directory_tree_exclude(self, sample_dir):
        result = file(action="directory_tree", path=sample_dir, exclude_patterns=["*.txt"])
        assert result.get("status") == "success"
        tree = result.get("tree", [])
        names = [e["name"] for e in tree]
        assert "a.txt" not in names
        assert "b.txt" not in names
        assert "subdir" in names
