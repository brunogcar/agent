"""
tests/tools/vision/test_vision.py
Tests for the Vision meta-tool, focusing on P0-2 security hardening 
(input validation, SSRF blocking, timeouts) and core functionality.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import httpx

# Import the functions we want to test from the cleaned-up vision.py
from tools.vision import (
    _validate_vision_inputs,
    _file_to_block,
    _download_image_to_data_uri,
    vision,
)

# =============================================================================
# 1. Input Validation & SSRF Protection Tests
# =============================================================================
class TestVisionValidation:
    def test_no_sources_provided(self):
        is_valid, err = _validate_vision_inputs("", "", "")
        assert not is_valid
        assert "Exactly one image source" in err

    def test_multiple_sources_provided(self):
        is_valid, err = _validate_vision_inputs("file.png", "base64data", "")
        assert not is_valid
        assert "exactly ONE" in err

    def test_valid_file_path(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_bytes(b"fake image data")
        is_valid, err = _validate_vision_inputs(str(f), "", "")
        assert is_valid
        assert err == ""

    def test_file_not_found(self):
        is_valid, err = _validate_vision_inputs("nonexistent_file.png", "", "")
        assert not is_valid
        assert "File not found" in err

class TestVisionSSRF:
    def test_localhost_blocked(self):
        is_valid, err = _validate_vision_inputs("", "", "http://localhost/secret")
        assert not is_valid
        assert "SSRF" in err

    def test_127_0_0_1_blocked(self):
        is_valid, err = _validate_vision_inputs("", "", "http://127.0.0.1:8080/img.png")
        assert not is_valid
        assert "SSRF" in err

    def test_private_ip_blocked(self):
        is_valid, err = _validate_vision_inputs("", "", "http://192.168.1.10/image.png")
        assert not is_valid
        assert "SSRF" in err
        
    def test_valid_public_url(self):
        is_valid, err = _validate_vision_inputs("", "", "https://example.com/image.png")
        assert is_valid
        assert err == ""

# =============================================================================
# 2. Image Helper Tests
# =============================================================================
class TestFileToBlock:
    def test_valid_file_conversion(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff\xe0") # fake jpeg header
        block, err = _file_to_block(str(f))
        
        assert err == ""
        assert block["type"] == "image_url"
        assert "data:image/jpeg;base64," in block["image_url"]["url"]

class TestDownloadImage:
    @patch("tools.vision.httpx.Client")
    def test_timeout_handling(self, mock_client_cls):
        """Ensure httpx timeouts are caught and returned as clean errors."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client_cls.return_value = mock_client
        
        uri, err = _download_image_to_data_uri("https://example.com/slow.png")
        assert uri == ""
        assert "Timeout" in err

    @patch("tools.vision.httpx.Client")
    def test_successful_download(self, mock_client_cls):
        """Ensure valid images are converted to data URIs."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake png data"
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client
        
        uri, err = _download_image_to_data_uri("https://example.com/img.png")
        assert err == ""
        assert uri.startswith("data:image/png;base64,")

# =============================================================================
# 3. Main Tool Integration Tests
# =============================================================================
class TestVisionTool:
    @patch("tools.vision.cfg")
    def test_missing_vision_model(self, mock_cfg):
        """Tool should fail fast if VISION_MODEL is not in .env"""
        mock_cfg.vision_model = ""
        res = vision(task="describe this")
        
        assert res["status"] == "error"
        assert "VISION_MODEL not set" in res["error"]

    @patch("tools.vision.llm")
    @patch("tools.vision.cfg")
    def test_successful_execution(self, mock_cfg, mock_llm, tmp_path):
        """Test a full successful vision call with mocked LLM."""
        mock_cfg.vision_model = "mock-vision-model"
        
        # Create a dummy file
        f = tmp_path / "test.png"
        f.write_bytes(b"fake image")
        
        # Mock the LLM response
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "A fake image description."
        mock_result.model = "mock-vision-model"
        mock_result.elapsed = 1.5
        mock_result.usage = {"prompt": 10, "completion": 20}
        mock_result.parsed = None
        mock_llm.call.return_value = mock_result
        
        res = vision(task="describe", file_path=str(f), trace_id="trace-123")
        
        assert res["status"] == "success"
        assert res["text"] == "A fake image description."
        assert res["trace_id"] == "trace-123"
        mock_llm.call.assert_called_once()

    @patch("tools.vision.llm")
    @patch("tools.vision.cfg")
    def test_llm_failure_handling(self, mock_cfg, mock_llm, tmp_path):
        """Ensure LLM failures return a clean error dict with trace_id."""
        mock_cfg.vision_model = "mock-vision-model"
        
        f = tmp_path / "test.png"
        f.write_bytes(b"fake image")
        
        mock_result = MagicMock()
        mock_result.ok = False
        mock_result.error = "Model context limit exceeded"
        mock_llm.call.return_value = mock_result
        
        res = vision(task="describe", file_path=str(f), trace_id="trace-456")
        
        assert res["status"] == "error"
        assert "Model context limit exceeded" in res["error"]
        assert res["trace_id"] == "trace-456"