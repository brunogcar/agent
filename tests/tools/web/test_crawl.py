"""Web tool tests — crawl action (v1.3 prototype).

Tests the web(action="crawl") handler. All tests mock crawl4ai's
AsyncWebCrawler — no real HTTP requests or browser launches.

Test design:
  - crawl4ai is a soft dependency (lazy import). Tests mock the import
    via sys.modules to control which path is exercised.
  - not-installed path: set sys.modules["crawl4ai"] = None (raises ImportError)
  - success path: mock AsyncWebCrawler to return markdown
  - error paths: mock to raise exceptions, return empty content
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from tools.web import web


# ─────────────────────────────────────────────────────────────────────────────
# Soft dependency — crawl4ai not installed
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlNotInstalled:
    """When crawl4ai is not installed, return a clear error (not a crash)."""

    def test_crawl4ai_missing_returns_error(self, mock_cfg_for_web):
        """If crawl4ai is not installed, web(action='crawl') returns fail()."""
        # Mock crawl4ai as not importable by setting it to None in sys.modules.
        # This causes `from crawl4ai import AsyncWebCrawler` to raise ImportError.
        with patch.dict("sys.modules", {"crawl4ai": None}):
            result = web(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "crawl4ai is not installed" in result["error"]
        assert "pip install crawl4ai" in result["error"]

    def test_crawl4ai_missing_does_not_crash(self, mock_cfg_for_web):
        """Missing crawl4ai must not raise — returns structured error."""
        with patch.dict("sys.modules", {"crawl4ai": None}):
            result = web(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        # Must NOT have an unhandled exception traceback
        assert "traceback" not in str(result).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlValidation:
    """Input validation for crawl action."""

    def test_missing_url_returns_error(self, mock_cfg_for_web):
        """url is required for crawl."""
        result = web(action="crawl")
        assert result["status"] == "error"
        assert "url" in result["error"].lower()

    def test_unsafe_url_rejected(self, mock_cfg_for_web):
        """SSRF guard must reject internal/local URLs."""
        # _is_safe_url rejects file://, localhost, private IPs, etc.
        result = web(action="crawl", url="file:///etc/passwd")
        assert result["status"] == "error"
        assert "security" in result["error"].lower() or "blocked" in result["error"].lower()

    def test_http_url_accepted_by_validation(self, mock_cfg_for_web):
        """HTTP/HTTPS URLs pass the SSRF check (may fail later at crawl4ai)."""
        # Mock crawl4ai as not importable so we only test validation
        with patch.dict("sys.modules", {"crawl4ai": None}):
            result = web(action="crawl", url="https://example.com")
        # Should pass validation (not an SSRF error), then fail on import
        assert result["status"] == "error"
        assert "crawl4ai is not installed" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Success path (mocked crawl4ai)
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlSuccess:
    """When crawl4ai succeeds, return clean markdown."""

    def _mock_crawl4ai(self, markdown: str, title: str = "Page"):
        """Build a mock crawl4ai module that returns the given markdown."""
        mock_crawler = MagicMock()
        mock_result = MagicMock()
        mock_result.markdown = markdown
        mock_result.metadata = {"title": title}
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler.arun = AsyncMock(return_value=mock_result)

        mock_module = MagicMock()
        mock_module.AsyncWebCrawler = MagicMock(return_value=mock_crawler)
        return mock_module

    def test_returns_markdown_content(self, mock_cfg_for_web):
        """Successful crawl returns markdown text with metadata."""
        with patch.dict("sys.modules", {"crawl4ai": self._mock_crawl4ai("# Page Title\n\nThis is **markdown** content.", "Example Page")}):
            result = web(action="crawl", url="https://example.com")

        assert result["status"] == "success"
        assert "markdown" in result["data"]["text"]
        assert result["data"]["format"] == "markdown"
        assert result["data"]["crawler"] == "crawl4ai"
        assert result["data"]["title"] == "Example Page"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["word_count"] > 0

    def test_truncation_when_over_max_chars(self, mock_cfg_for_web):
        """Content over max_chars is truncated with a marker."""
        long_markdown = "word " * 5000  # ~25K chars
        with patch.dict("sys.modules", {"crawl4ai": self._mock_crawl4ai(long_markdown, "Long Page")}):
            result = web(action="crawl", url="https://example.com", max_chars=1000)

        assert result["status"] == "success"
        assert result["data"]["truncated"] is True
        assert "[...truncated" in result["data"]["text"]
        assert len(result["data"]["text"]) < len(long_markdown)

    def test_no_truncation_when_under_max_chars(self, mock_cfg_for_web):
        """Content under max_chars is not truncated."""
        short_markdown = "# Short\n\nContent."
        with patch.dict("sys.modules", {"crawl4ai": self._mock_crawl4ai(short_markdown, "Short")}):
            result = web(action="crawl", url="https://example.com", max_chars=8000)

        assert result["status"] == "success"
        assert result["data"]["truncated"] is False
        assert result["data"]["text"] == short_markdown


# ─────────────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlErrors:
    """crawl4ai failures return structured errors (not crashes)."""

    def test_empty_content_returns_error(self, mock_cfg_for_web):
        """If crawl4ai returns empty markdown, return error."""
        mock_crawler = MagicMock()
        mock_result = MagicMock()
        mock_result.markdown = ""
        mock_result.metadata = {}
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler.arun = AsyncMock(return_value=mock_result)

        mock_module = MagicMock()
        mock_module.AsyncWebCrawler = MagicMock(return_value=mock_crawler)

        with patch.dict("sys.modules", {"crawl4ai": mock_module}):
            result = web(action="crawl", url="https://example.com")

        assert result["status"] == "error"
        assert "empty" in result["error"].lower()

    def test_crawl4ai_exception_returns_error(self, mock_cfg_for_web):
        """If crawl4ai raises, return structured error (not crash)."""
        mock_crawler = MagicMock()
        mock_crawler.__aenter__ = AsyncMock(side_effect=RuntimeError("Browser launch failed"))
        mock_crawler.__aexit__ = AsyncMock(return_value=False)

        mock_module = MagicMock()
        mock_module.AsyncWebCrawler = MagicMock(return_value=mock_crawler)

        with patch.dict("sys.modules", {"crawl4ai": mock_module}):
            result = web(action="crawl", url="https://example.com")

        assert result["status"] == "error"
        assert "crawl4ai failed" in result["error"]
