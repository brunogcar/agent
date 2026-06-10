"""Test file tool result compression."""
from __future__ import annotations

import pytest
from pathlib import Path

from tools.file import file
from core.utils import compress_result


class TestFileCompressionIntegration:
    """Verify file tool applies compression to large outputs."""

    @pytest.fixture(autouse=True)
    def setup_tmp_dir(self, tmp_path, monkeypatch):
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(exist_ok=True)
        yield tmp_dir

    def test_large_file_read_is_compressed(self, setup_tmp_dir):
        """Reading a file >4000 chars should return compressed output."""
        path = setup_tmp_dir / "large.txt"
        path.write_text("x" * 5000, encoding="utf-8")

        result = file(action="read", path=str(path))
        assert result.get("status") == "success"
        content = result.get("content", "")
        if len(content) > 4000:
            assert "truncated" in content

    def test_small_file_read_uncompressed(self, setup_tmp_dir):
        """Reading a small file should return exact content."""
        path = setup_tmp_dir / "small.txt"
        path.write_text("small content", encoding="utf-8")

        result = file(action="read", path=str(path))
        assert result.get("status") == "success"
        assert result.get("content") == "small content"

    def test_read_many_compression(self, setup_tmp_dir):
        """read_many should compress large individual files."""
        path1 = setup_tmp_dir / "big1.txt"
        path2 = setup_tmp_dir / "small.txt"
        path1.write_text("x" * 5000, encoding="utf-8")
        path2.write_text("small", encoding="utf-8")

        result = file(action="read_many", paths=[str(path1), str(path2)])
        assert result.get("status") == "success"
        files = result.get("files", [])
        assert len(files) == 2
        # Large file should be compressed, small should not
        for f in files:
            if f.get("path") == str(path1):
                assert "truncated" in f.get("content", "")
            elif f.get("path") == str(path2):
                assert f.get("content") == "small"
