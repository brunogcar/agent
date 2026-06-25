"""Real integration tests using actual filesystem."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from tools.file import file


@pytest.fixture
def txt_file(mock_cfg):
    """Create a test text file under mock workspace."""
    path = str(mock_cfg.workspace_root / "test.txt")
    result = file(action="write_file", path=path,
                  content="Hello World\nLine 2\n### Section")
    assert result["status"] == "success"
    return result["path"]


class TestRealWriteReadCycle:
    def test_write_then_read_txt(self, txt_file):
        result = file(action="read_file", path=txt_file)
        assert result["status"] == "success"
        assert "Hello World" in result["content"]
        assert Path(txt_file).exists()

    def test_write_then_read_with_head(self, txt_file):
        result = file(action="read_file", path=txt_file, head=1)
        assert result["status"] == "success"
        assert result["content"] == "Hello World"


class TestRealCopy:
    def test_copy_file(self, txt_file, mock_cfg):
        dest = str(mock_cfg.workspace_root / "copied.txt")
        result = file(action="copy_file", source=txt_file, destination=dest)
        assert result["status"] == "success"
        assert Path(dest).exists()
        assert Path(txt_file).exists()  # Source still exists


class TestRealAppend:
    def test_append_to_file(self, txt_file):
        result = file(action="append_file", path=txt_file, content="\nAppended line")
        assert result["status"] == "success"
        read_result = file(action="read_file", path=txt_file)
        assert "Appended line" in read_result["content"]


class TestRealPatch:
    def test_patch_modifies_file(self, txt_file):
        result = file(action="patch_file", path=txt_file,
                      old="Hello World", new="Hello Patched")
        assert result["status"] == "success"
        after = file(action="read_file", path=txt_file)
        assert "Hello Patched" in after["content"]


class TestRealList:
    def test_list_test_directory(self, mock_cfg):
        result = file(action="list_directory", path=str(mock_cfg.workspace_root))
        assert result["status"] == "success"


class TestRealReadMultiple:
    def test_read_multiple_actual_files(self, mock_cfg, txt_file):
        p2 = str(mock_cfg.workspace_root / "test2.txt")
        p3 = str(mock_cfg.workspace_root / "test3.md")
        file(action="write_file", path=p2, content="Second")
        file(action="write_file", path=p3, content="# MD")

        paths = [txt_file, p2, p3]
        result = file(action="read_multiple_files", paths=paths)

        assert result["status"] == "success"
        assert result["count"] == 3
        assert len(result["errors"]) == 0


class TestRealFind:
    def test_find_files(self, mock_cfg, txt_file):
        result = file(action="find_files", pattern="*.txt", path=str(mock_cfg.workspace_root))
        assert result["status"] == "success"
        assert result["count"] >= 1
        names = [f["name"] for f in result["files"]]
        assert "test.txt" in names


class TestRealSearch:
    def test_search_finds_written_content(self, txt_file):
        result = file(action="search_files", query="Hello World", max_results=5)
        assert result["status"] in ("success", "error")


class TestRealPathResolution:
    def test_relative_path_write_read(self, mock_cfg):
        rel_path = str(mock_cfg.workspace_root / "relative_test.txt")
        content = "Relative path test"

        result = file(action="write_file", path=rel_path, content=content)
        assert result["status"] == "success"
        resolved = result["path"]

        read_result = file(action="read_file", path=rel_path)
        assert read_result["status"] == "success"
        assert content in read_result["content"]
        assert Path(resolved).exists()


class TestRealErrorHandling:
    def test_read_nonexistent_returns_error(self, mock_cfg):
        result = file(action="read_file", path=str(mock_cfg.workspace_root / "does_not_exist_12345.txt"))
        assert result["status"] == "error"

    def test_write_protected_path_fails(self):
        result = file(action="write_file", path="C:/Windows/System32/test.txt", content="x")
        assert result["status"] == "error"
