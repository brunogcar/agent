"""Tests for URL path validation via core/net/security.py.

v1.3: Merged from old tests/security/test_path_validation.py.
      Fixed Windows-1252 encoding corruption.
      Rewritten to use is_safe_network_address instead of removed _is_private_or_localhost.
"""
from __future__ import annotations

import pytest

from core.net.security import is_safe_network_address, _assert_safe_urls


@pytest.fixture(autouse=True)
def patch_allowed_hosts(monkeypatch):
    """Patch ALLOWED_INTERNAL_HOSTS to empty for all tests in this file."""
    from core.net import security
    monkeypatch.setattr(security.cfg, "allowed_internal_hosts", frozenset())


class TestPathValidation:
    """Path-specific SSRF validation tests."""

    def test_admin_path_blocked_on_private_ip(self):
        safe, err = _assert_safe_urls(["http://127.0.0.1/admin"])
        assert safe is False
        # Error message contains the full URL, so "admin" will be in it
        assert "127.0.0.1" in err

    def test_api_path_blocked_on_private_ip(self):
        safe, err = _assert_safe_urls(["http://10.0.0.1/api/v1"])
        assert safe is False

    def test_allows_public_path(self):
        safe, err = _assert_safe_urls(["https://example.com/api/v1/users"])
        assert safe is True

    def test_blocks_localhost_with_path(self):
        safe, err = _assert_safe_urls(["http://localhost/config"])
        assert safe is False

    def test_blocks_127_0_0_1_with_query(self):
        safe, err = _assert_safe_urls(["http://127.0.0.1/?debug=true"])
        assert safe is False
