"""Browser tool tests — upload action."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
from tools.browser import browser


class TestUpload:
    """Test browser upload action."""

    def test_upload_success(self, mock_browser, tmp_path):
        """Happy path: upload a real file to a file input."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        with patch("tools.browser_core.actions.upload.resolve_path") as mock_resolve:
            mock_resolve.return_value = (test_file, None)
            mock_browser["page"].set_input_files = AsyncMock(return_value=None)
            result = browser(
                action="upload",
                selector="input[type=file]",
                path=str(test_file),
                trace_id="t1",
            )
            assert result["status"] == "success"
            assert result["data"]["uploaded"] is True
            assert result["data"]["selector"] == "input[type=file]"
            assert result["data"]["path"] == str(test_file)
            assert result["data"]["size"] == 11
            mock_browser["page"].set_input_files.assert_called_once_with(
                "input[type=file]", str(test_file)
            )

    def test_upload_path_guard_rejects(self, mock_browser):
        """Path guard must reject paths outside workspace."""
        with patch("tools.browser_core.actions.upload.resolve_path") as mock_resolve:
            mock_resolve.return_value = (None, "Path outside workspace")
            result = browser(
                action="upload",
                selector="input[type=file]",
                path="/etc/passwd",
                trace_id="t1",
            )
            assert result["status"] == "error"
            assert "Upload path error" in result["error"]
            mock_browser["page"].set_input_files.assert_not_called()

    def test_upload_missing_selector(self, mock_browser):
        result = browser(action="upload", path="/tmp/file.txt", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]

    def test_upload_missing_path(self, mock_browser):
        result = browser(
            action="upload", selector="input[type=file]", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "path is required" in result["error"]
