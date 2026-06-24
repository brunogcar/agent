"""Test patch_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestPatchFile:
    def test_patch_file(self, sample_txt):
        result = file(action="patch_file", path=sample_txt, old="Hello World", new="Hello Patched")
        assert result.get("status") == "success"
        content = Path(sample_txt).read_text(encoding="utf-8")
        assert "Hello Patched" in content

    def test_patch_file_not_found(self, mock_cfg):
        result = file(action="patch_file", path="nonexistent_12345.txt", old="a", new="b")
        assert result.get("status") == "error"
