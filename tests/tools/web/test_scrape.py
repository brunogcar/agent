"""Unit tests for web scrape action."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.web import web


class TestScrape:
    def test_scrape_success(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
        assert result["data"]["title"] == "Test"
        assert "Content" in result["data"]["text"]

    def test_scrape_missing_url(self, mock_cfg_for_web):
        result = web(action="scrape", url="")
        assert result["status"] == "error"
        assert "requires url" in result["error"]

    def test_scrape_no_text_content(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "error"
        assert "No text content extracted" in result["error"]

    def test_scrape_max_chars_none_uses_cfg_default(self, mock_cfg_for_web, mock_httpx):
        """When max_chars is omitted (None), cfg.web_max_text_chars is used."""
        mock_cfg_for_web.web_max_text_chars = 100
        long_text = "x" * 500
        mock_response = MagicMock()
        mock_response.text = f"<html><body><p>{long_text}</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_httpx.get.return_value = mock_response
        # Omit max_chars entirely — facade should not pass it
        result = web(action="scrape", url="https://example.com")
        assert result["status"] == "success"
        # Should be truncated to cfg default (100) plus marker
        assert len(result["data"]["text"]) <= 150  # 100 chars + marker
        assert result["data"]["truncated"] is True

    def test_scrape_content_type_pdf_blocked(self, mock_cfg_for_web, mock_httpx):
        """URLs returning application/pdf are rejected before BS4 parsing."""
        mock_response = MagicMock()
        mock_response.text = "%PDF-1.4 garbage"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com/doc.pdf", max_chars=8000)
        assert result["status"] == "error"
        assert "PDF" in result["error"]

    def test_scrape_content_type_image_blocked(self, mock_cfg_for_web, mock_httpx):
        """URLs returning image/* are rejected before BS4 parsing."""
        mock_response = MagicMock()
        mock_response.text = "binary-image-data"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com/pic.png", max_chars=8000)
        assert result["status"] == "error"
        assert "image" in result["error"].lower()

    def test_scrape_pdf_by_extension_blocked(self, mock_cfg_for_web, mock_httpx):
        """URLs ending in .pdf are rejected at pre-flight, before any HTTP request."""
        result = web(action="scrape", url="https://example.com/report.pdf", max_chars=8000)
        assert result["status"] == "error"
        assert "PDF" in result["error"]
        # No HTTP request should have been made
        mock_httpx.get.assert_not_called()

    def test_scrape_response_too_large_blocked(self, mock_cfg_for_web, mock_httpx):
        """Responses with Content-Length > 10MB are rejected."""
        mock_response = MagicMock()
        mock_response.text = "small"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html", "content-length": "20000000"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com/huge", max_chars=8000)
        assert result["status"] == "error"
        assert "too large" in result["error"].lower()

    def test_scrape_retry_on_503(self, mock_cfg_for_web, mock_httpx):
        """Transient 503 triggers retry via retry_sync() with backoff."""
        mock_response_ok = MagicMock()
        mock_response_ok.text = "<html><body>OK</body></html>"
        mock_response_ok.raise_for_status = MagicMock()
        mock_response_ok.headers = {"content-type": "text/html"}

        error_503 = MagicMock()
        error_503.status_code = 503
        import httpx
        exc_503 = httpx.HTTPStatusError("Service Unavailable", request=MagicMock(), response=error_503)

        mock_httpx.get.side_effect = [exc_503, mock_response_ok]
        # [core/net] retry_sync() sleeps in core/net/retry.py, not scrape.py
        with patch("core.net.retry._sleep") as mock_sleep:
            result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
        assert mock_httpx.get.call_count == 2  # 1 fail + 1 success
        mock_sleep.assert_called_once()  # 1 retry = 1 sleep

    def test_scrape_retry_on_timeout(self, mock_cfg_for_web, mock_httpx):
        """Transient timeout triggers retry via retry_sync() with backoff."""
        import httpx
        mock_response_ok = MagicMock()
        mock_response_ok.text = "<html><body>OK</body></html>"
        mock_response_ok.raise_for_status = MagicMock()
        mock_response_ok.headers = {"content-type": "text/html"}

        mock_httpx.get.side_effect = [httpx.TimeoutException("Timeout"), mock_response_ok]
        # [core/net] retry_sync() sleeps in core/net/retry.py, not scrape.py
        with patch("core.net.retry._sleep") as mock_sleep:
            result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
        assert mock_httpx.get.call_count == 2  # 1 fail + 1 success
        mock_sleep.assert_called_once()  # 1 retry = 1 sleep

    def test_scrape_no_retry_on_404(self, mock_cfg_for_web, mock_httpx):
        """404 (client error) does NOT trigger retry — fails immediately."""
        import httpx
        error_404 = MagicMock()
        error_404.status_code = 404
        exc_404 = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=error_404)
        mock_httpx.get.side_effect = exc_404
        # [core/net] retry_sync() uses is_retryable_error() which rejects 4xx
        with patch("core.net.retry._sleep") as mock_sleep:
            result = web(action="scrape", url="https://example.com/notfound", max_chars=8000)
        assert result["status"] == "error"
        assert "404" in result["error"]
        mock_httpx.get.assert_called_once()  # Only one call, no retry
        mock_sleep.assert_not_called()  # No retry = no sleep


class TestSSRFProtection:
    def test_blocks_localhost(self, mock_cfg_for_web, mock_httpx):
        with patch("tools.web_ops.actions.scrape._is_safe_url", return_value=False):
            result = web(action="scrape", url="http://localhost:8080/admin", max_chars=8000)
        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_blocks_private_ip(self, mock_cfg_for_web, mock_httpx):
        with patch("tools.web_ops.actions.scrape._is_safe_url", return_value=False):
            result = web(action="scrape", url="http://192.168.1.1/config", max_chars=8000)
        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_allows_public_url(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "Public content"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
