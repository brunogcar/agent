"""Tests for vision_ops.helpers — shared utilities.

Unit-tests the pure functions in tools/vision_ops/helpers.py in isolation:
  - _validate_vision_inputs() — exactly-one-source + SSRF + size checks
  - _file_to_block() — local file → image_url content block
  - _b64_to_block() — base64 string → content block (with/without data: prefix)
  - _download_image_to_data_uri() — core/net retry_sync adoption
  - _check_vision_available() — kill-switch
  - _build_image_block() — source dispatch
  - _call_vision() — wrapped llm.call() (multimodal)

These tests don't go through the vision facade — they patch the helpers
module's cfg / llm / is_safe_network_address / retry_sync symbols directly.
"""
from __future__ import annotations

import httpx
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.vision_ops import helpers
from tools.vision_ops.helpers import (
    HTTP_TIMEOUT,
    MAX_IMAGE_BYTES,
    MAX_BASE64_LEN,
    _MIME_MAP,
    _validate_vision_inputs,
    _file_to_block,
    _b64_to_block,
    _download_image_to_data_uri,
    _check_vision_available,
    _build_image_block,
    _call_vision,
)


# =============================================================================
# _validate_vision_inputs
# =============================================================================
class TestValidateVisionInputs:
    """_validate_vision_inputs — exactly-one-source + SSRF + size checks."""

    def test_no_sources_provided(self):
        ok, err = _validate_vision_inputs("", "", "")
        assert not ok
        assert "Exactly one image source" in err

    def test_multiple_sources_provided(self):
        ok, err = _validate_vision_inputs("file.png", "base64data", "")
        assert not ok
        assert "exactly ONE" in err

    def test_file_path_and_url_provided(self):
        ok, err = _validate_vision_inputs("file.png", "", "https://example.com/x.png")
        assert not ok
        assert "exactly ONE" in err

    def test_valid_file_path(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_bytes(b"fake image data")
        ok, err = _validate_vision_inputs(str(f), "", "")
        assert ok
        assert err == ""

    def test_file_not_found(self):
        ok, err = _validate_vision_inputs("nonexistent_file.png", "", "")
        assert not ok
        assert "File not found" in err

    def test_file_too_large(self, tmp_path, monkeypatch):
        """File over MAX_IMAGE_BYTES should be rejected."""
        monkeypatch.setattr(helpers, "MAX_IMAGE_BYTES", 10)
        f = tmp_path / "big.png"
        f.write_bytes(b"x" * 100)
        ok, err = _validate_vision_inputs(str(f), "", "")
        assert not ok
        assert "File too large" in err

    def test_base64_too_long(self, monkeypatch):
        """Base64 string over MAX_BASE64_LEN should be rejected."""
        monkeypatch.setattr(helpers, "MAX_BASE64_LEN", 10)
        ok, err = _validate_vision_inputs("", "x" * 100, "")
        assert not ok
        assert "Base64 string too long" in err

    def test_ssrf_localhost_blocked(self):
        with patch.object(helpers, "is_safe_network_address", return_value=False):
            ok, err = _validate_vision_inputs("", "", "http://localhost/secret")
        assert not ok
        assert "SSRF" in err

    def test_ssrf_private_ip_blocked(self):
        with patch.object(helpers, "is_safe_network_address", return_value=False):
            ok, err = _validate_vision_inputs("", "", "http://192.168.1.10/image.png")
        assert not ok
        assert "SSRF" in err

    def test_valid_public_url(self):
        with patch.object(helpers, "is_safe_network_address", return_value=True):
            ok, err = _validate_vision_inputs("", "", "https://example.com/image.png")
        assert ok
        assert err == ""

    def test_invalid_url_scheme(self):
        with patch.object(helpers, "is_safe_network_address", return_value=True):
            ok, err = _validate_vision_inputs("", "", "ftp://example.com/image.png")
        assert not ok
        assert "Invalid URL scheme" in err

    def test_url_missing_hostname(self):
        ok, err = _validate_vision_inputs("", "", "http:///image.png")
        assert not ok
        assert "missing hostname" in err


# =============================================================================
# _file_to_block
# =============================================================================
class TestFileToBlock:
    """_file_to_block — local file → image_url content block."""

    def test_valid_png_file(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        block, err = _file_to_block(str(f))
        assert err == ""
        assert block["type"] == "image_url"
        assert "data:image/png;base64," in block["image_url"]["url"]

    def test_valid_jpeg_file(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff\xe0")
        block, err = _file_to_block(str(f))
        assert err == ""
        assert "data:image/jpeg;base64," in block["image_url"]["url"]

    def test_valid_jpeg_extension_uppercase(self, tmp_path):
        f = tmp_path / "test.JPEG"
        f.write_bytes(b"\xff\xd8\xff\xe0")
        block, err = _file_to_block(str(f))
        assert err == ""
        assert "data:image/jpeg;base64," in block["image_url"]["url"]

    def test_unknown_extension_defaults_to_jpeg(self, tmp_path, capsys):
        f = tmp_path / "test.xyz"
        f.write_bytes(b"unknown")
        block, err = _file_to_block(str(f))
        assert err == ""
        assert "data:image/jpeg;base64," in block["image_url"]["url"]
        # A stderr warning should be emitted
        captured = capsys.readouterr()
        assert "Unknown extension" in captured.err

    def test_read_error_returns_error(self):
        """Passing a directory path should produce a read error."""
        # Use a path that exists but isn't readable as bytes — a directory.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            block, err = _file_to_block(d)
        assert block == {}
        assert "Read error" in err


# =============================================================================
# _b64_to_block
# =============================================================================
class TestB64ToBlock:
    """_b64_to_block — base64 → image_url content block."""

    def test_plain_base64_default_mime(self):
        b64 = "iVBORw0KGgo="
        block, err = _b64_to_block(b64)
        assert err == ""
        assert block["type"] == "image_url"
        assert block["image_url"]["url"] == "data:image/jpeg;base64,iVBORw0KGgo="

    def test_plain_base64_custom_mime(self):
        b64 = "iVBORw0KGgo="
        block, err = _b64_to_block(b64, mime_type="image/png")
        assert err == ""
        assert block["image_url"]["url"] == "data:image/png;base64,iVBORw0KGgo="

    def test_data_uri_passthrough(self):
        """If b64_str starts with 'data:', it should be passed through unchanged."""
        data_uri = "data:image/gif;base64,R0lGODlh="
        block, err = _b64_to_block(data_uri)
        assert err == ""
        assert block["image_url"]["url"] == data_uri


# =============================================================================
# _download_image_to_data_uri (core/net retry_sync adoption)
# =============================================================================
class TestDownloadImageToDataUri:
    """_download_image_to_data_uri — httpx + retry_sync wrapper."""

    def test_successful_download(self):
        """Valid HTTP response should produce a data URI."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG fake bytes"

        with patch.object(helpers, "retry_sync", return_value=mock_response):
            uri, err = _download_image_to_data_uri("https://example.com/img.png")
        assert err == ""
        assert uri.startswith("data:image/png;base64,")

    def test_content_type_with_charset_stripped(self):
        """Content-type 'image/png; charset=utf-8' should be stripped to 'image/png'."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png; charset=utf-8"}
        mock_response.content = b"fake"

        with patch.object(helpers, "retry_sync", return_value=mock_response):
            uri, err = _download_image_to_data_uri("https://example.com/img.png")
        assert err == ""
        assert uri.startswith("data:image/png;base64,")

    def test_non_image_content_type_uses_extension(self):
        """If content-type isn't image/*, fall back to URL extension."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.content = b"fake"

        with patch.object(helpers, "retry_sync", return_value=mock_response):
            uri, err = _download_image_to_data_uri("https://example.com/img.png")
        assert err == ""
        assert uri.startswith("data:image/png;base64,")

    def test_non_image_content_type_unknown_extension_defaults_jpeg(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.content = b"fake"

        with patch.object(helpers, "retry_sync", return_value=mock_response):
            uri, err = _download_image_to_data_uri("https://example.com/img.unknown")
        assert err == ""
        assert uri.startswith("data:image/jpeg;base64,")

    def test_timeout_returns_clean_error(self):
        """httpx.TimeoutException should produce a 'Timeout' error message."""
        with patch.object(helpers, "retry_sync", side_effect=httpx.TimeoutException("timed out")):
            uri, err = _download_image_to_data_uri("https://example.com/slow.png")
        assert uri == ""
        assert "Timeout" in err

    def test_http_status_error_returns_clean_error(self):
        """httpx.HTTPStatusError should produce a clean HTTP error message."""
        request = httpx.Request("GET", "https://example.com/missing.png")
        response = httpx.Response(status_code=404, request=request)
        exc = httpx.HTTPStatusError("Not Found", request=request, response=response)
        with patch.object(helpers, "retry_sync", side_effect=exc):
            uri, err = _download_image_to_data_uri("https://example.com/missing.png")
        assert uri == ""
        assert "HTTP error 404" in err

    def test_other_exception_returns_clean_error(self):
        """Any other exception should produce a 'Download error' message."""
        with patch.object(helpers, "retry_sync", side_effect=RuntimeError("network unreachable")):
            uri, err = _download_image_to_data_uri("https://example.com/img.png")
        assert uri == ""
        assert "Download error" in err
        assert "network unreachable" in err

    def test_retry_sync_called_with_max_retries_two(self):
        """Vision should pass max_retries=2 (one less than web's 3)."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake"

        with patch.object(helpers, "retry_sync", return_value=mock_response) as mock_rs:
            _download_image_to_data_uri("https://example.com/img.png")

        retry_kwargs = mock_rs.call_args[1]
        assert retry_kwargs["max_retries"] == 2
        assert "base_delay" in retry_kwargs
        assert "max_delay" in retry_kwargs
        assert retry_kwargs["jitter"] is True
        assert callable(retry_kwargs["is_retryable"])

    def test_retry_sync_uses_core_net_defaults(self):
        """RETRY_BASE_DELAY and RETRY_MAX_DELAY should come from core/net/default.py."""
        from core.net.default import RETRY_BASE_DELAY, RETRY_MAX_DELAY
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake"

        with patch.object(helpers, "retry_sync", return_value=mock_response) as mock_rs:
            _download_image_to_data_uri("https://example.com/img.png")

        retry_kwargs = mock_rs.call_args[1]
        assert retry_kwargs["base_delay"] == RETRY_BASE_DELAY
        assert retry_kwargs["max_delay"] == RETRY_MAX_DELAY


# =============================================================================
# _check_vision_available
# =============================================================================
class TestCheckVisionAvailable:
    """_check_vision_available — kill-switch."""

    def test_available_when_model_configured(self):
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.vision_model = "gpt-4o"
            ok, err = _check_vision_available()
        assert ok is True
        assert err == {}

    def test_disabled_when_model_empty(self):
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.vision_model = ""
            ok, err = _check_vision_available()
        assert ok is False
        assert err["status"] == "disabled"
        assert "VISION_MODEL" in err["error"]

    def test_disabled_when_model_none(self):
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.vision_model = None
            ok, err = _check_vision_available()
        assert ok is False
        assert err["status"] == "disabled"


# =============================================================================
# _build_image_block
# =============================================================================
class TestBuildImageBlock:
    """_build_image_block — source dispatch helper."""

    def test_dispatches_to_file_to_block(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG fake")
        block, err = _build_image_block(str(f), "", "", "image/jpeg")
        assert err == ""
        assert "data:image/png;base64," in block["image_url"]["url"]

    def test_dispatches_to_b64_to_block(self):
        block, err = _build_image_block("", "iVBORw0KGgo=", "", "image/png")
        assert err == ""
        assert block["image_url"]["url"] == "data:image/png;base64,iVBORw0KGgo="

    def test_dispatches_to_download(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake"
        with patch.object(helpers, "retry_sync", return_value=mock_response):
            block, err = _build_image_block("", "", "https://example.com/img.png", "image/jpeg")
        assert err == ""
        assert "data:image/png;base64," in block["image_url"]["url"]

    def test_no_source_returns_error(self):
        """When no source is provided, returns a clear error (should be unreachable if validation ran)."""
        block, err = _build_image_block("", "", "", "image/jpeg")
        assert block == {}
        assert "No image source" in err


# =============================================================================
# _call_vision
# =============================================================================
class TestCallVision:
    """_call_vision — wrapped llm.call() for multimodal messages."""

    def test_calls_llm_with_vision_role(self):
        mock_response = MagicMock()
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = mock_response
            result = _call_vision(
                system="sys",
                user_content=[{"type": "text", "text": "hi"}],
            )
        mock_llm.call.assert_called_once()
        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["role"] == "vision"
        assert call_kwargs["json_mode"] is False
        assert call_kwargs["json_schema"] is None
        assert call_kwargs["trace_id"] == ""
        assert result is mock_response

    def test_builds_messages_with_system_and_user(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(
                system="my system prompt",
                user_content=[{"type": "image_url", "image_url": {"url": "data:..."}}],
            )
        messages = mock_llm.call.call_args[1]["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "my system prompt"}
        assert messages[1] == {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:..."}}]}

    def test_json_schema_string_parsed_to_dict(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(
                system="sys",
                user_content=[],
                json_schema='{"type": "object", "properties": {"x": {"type": "string"}}}',
            )
        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] == {"type": "object", "properties": {"x": {"type": "string"}}}

    def test_malformed_json_schema_silently_skipped(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(
                system="sys",
                user_content=[],
                json_schema="not valid json {",
            )
        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] is None

    def test_empty_json_schema_treated_as_none(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(system="sys", user_content=[], json_schema="")
        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] is None

    def test_whitespace_json_schema_treated_as_none(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(system="sys", user_content=[], json_schema="   ")
        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] is None

    def test_trace_id_forwarded(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(system="sys", user_content=[], trace_id="trace-xyz")
        assert mock_llm.call.call_args[1]["trace_id"] == "trace-xyz"

    def test_json_mode_forwarded(self):
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.call.return_value = MagicMock()
            _call_vision(system="sys", user_content=[], json_mode=True)
        assert mock_llm.call.call_args[1]["json_mode"] is True


# =============================================================================
# Constants
# =============================================================================
class TestConstants:
    """Module-level constants should match documented defaults."""

    def test_http_timeout_default(self):
        assert HTTP_TIMEOUT == 30.0

    def test_max_image_bytes_default(self):
        assert MAX_IMAGE_BYTES == 20_000_000

    def test_max_base64_len_default(self):
        assert MAX_BASE64_LEN == 10_000_000

    def test_mime_map_has_expected_extensions(self):
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            assert ext in _MIME_MAP
        assert _MIME_MAP[".jpg"] == "image/jpeg"
        assert _MIME_MAP[".png"] == "image/png"
        assert _MIME_MAP[".webp"] == "image/webp"
        assert _MIME_MAP[".gif"] == "image/gif"
        assert _MIME_MAP[".bmp"] == "image/bmp"
