"""Test read_media_file action."""

from __future__ import annotations

import base64
import pytest
from pathlib import Path
from tools.file import file


class TestReadMediaFile:
    def test_read_media_file_png(self, mock_cfg):
        # Create a minimal valid 1x1 PNG
        path = mock_cfg.workspace_root / "test.png"
        # Minimal PNG: 1x1 transparent pixel
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xD8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x05, 0xFE,
            0xD7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
            0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        path.write_bytes(png_data)

        result = file(action="read_media_file", path=str(path))
        assert result.get("status") == "success"
        assert result.get("mime_type") == "image/png"
        assert result.get("type") == "image"
        assert result.get("size") == len(png_data)
        # Verify base64 decodes back correctly
        decoded = base64.b64decode(result.get("data"))
        assert decoded == png_data

    def test_read_media_file_max_bytes(self, mock_cfg):
        path = mock_cfg.workspace_root / "big.bin"
        path.write_bytes(b"x" * 6_000_000)  # 6MB

        result = file(action="read_media_file", path=str(path))
        # Default max_bytes is 5MB, should fail
        assert result.get("status") == "error"
        assert "too large" in result.get("error", "").lower()

    def test_read_media_file_custom_max_bytes(self, mock_cfg):
        path = mock_cfg.workspace_root / "medium.bin"
        path.write_bytes(b"x" * 6_000_000)  # 6MB

        result = file(action="read_media_file", path=str(path), max_bytes=10_000_000)
        assert result.get("status") == "success"
        assert result.get("size") == 6_000_000

    def test_read_media_file_not_found(self, mock_cfg):
        result = file(action="read_media_file", path="nonexistent_12345.png")
        assert result.get("status") == "error"
