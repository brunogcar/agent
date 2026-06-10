"""Test git tool result compression."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.git import git
from core.utils import truncate_output, compress_result


class TestTruncateOutput:
    """Unit tests for the truncate_output helper."""

    def test_short_text_unchanged(self):
        text = "short text"
        result = truncate_output(text, max_chars=100)
        assert result == text

    def test_long_text_truncated(self):
        text = "x" * 5000
        result = truncate_output(text, max_chars=4000)
        assert len(result) < len(text)
        assert "truncated" in result
        assert "... 1000 chars truncated" in result

    def test_empty_text(self):
        assert truncate_output("") == ""
        assert truncate_output(None, max_chars=100) is None

    def test_exact_boundary(self):
        text = "x" * 4000
        result = truncate_output(text, max_chars=4000)
        assert result == text  # exactly at boundary, not truncated


class TestCompressResult:
    """Unit tests for compress_result helper."""

    def test_dict_with_large_string(self):
        result = {"status": "ok", "output": "x" * 5000}
        compressed = compress_result(result)
        assert "truncated" in compressed["output"]
        assert len(compressed["output"]) < 5000

    def test_dict_with_small_string(self):
        result = {"status": "ok", "output": "small"}
        assert compress_result(result) == result

    def test_nested_dict_compression(self):
        result = {"data": {"diff": "x" * 5000, "meta": "small"}}
        compressed = compress_result(result)
        assert "truncated" in compressed["data"]["diff"]
        assert compressed["data"]["meta"] == "small"

    def test_list_compression(self):
        result = {"files": [{"content": "x" * 5000}, {"content": "small"}]}
        compressed = compress_result(result)
        assert "truncated" in compressed["files"][0]["content"]
        assert compressed["files"][1]["content"] == "small"

    def test_non_dict_passed_through(self):
        assert compress_result("string") == "string"
        assert compress_result(42) == 42


class TestGitCompressionIntegration:
    """Verify git tool applies compression to large outputs."""

    @pytest.fixture(autouse=True)
    def _use_temp_roots(self, monkeypatch, tmp_path):
        import pathlib
        def _fake_resolve(path, default_root="agent", require_exists=False):
            p = pathlib.Path(str(path))
            return (p, "")
        monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)

    def test_large_diff_is_compressed(self, tmp_path, monkeypatch):
        """A diff with >4000 chars should be truncated by compress_result."""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@agent.local"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo, check=True, capture_output=True)
        # Create a file with lots of content
        (repo / "bigfile.txt").write_text("line\n" * 2000, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
        # Modify it to create a large diff
        (repo / "bigfile.txt").write_text("modified\n" * 2000, encoding="utf-8")

        result = git(action="diff", root=str(repo))
        assert result["status"] == "success"
        assert result["has_changes"] is True
        # The diff should be compressed if >4000 chars
        if len(result["diff"]) > 4000:
            assert "truncated" in result["diff"]
