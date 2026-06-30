"""tests/core/test_security.py — Tests for core.security helpers.

v1.1: Added to verify _assert_safe_urls and is_safe_network_address behavior
after extracting _assert_safe_urls from tavily_ops/errors.py to core/security.py.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from core.security import is_safe_network_address, _assert_safe_urls


class TestIsSafeNetworkAddress:
    """Test hostname/IP validation for SSRF prevention."""

    def test_blocks_localhost(self):
        # localhost is blocked unless in allowed_internal_hosts
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("localhost") is False

    def test_blocks_127_0_0_1(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("127.0.0.1") is False

    def test_blocks_private_ip(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("192.168.1.1") is False
            assert is_safe_network_address("10.0.0.1") is False
            assert is_safe_network_address("172.16.0.1") is False

    def test_blocks_link_local(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("169.254.1.1") is False

    def test_allows_public_ip(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("8.8.8.8") is True
            assert is_safe_network_address("1.1.1.1") is True

    def test_allows_public_domain(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("example.com") is True
            assert is_safe_network_address("github.com") is True

    def test_blocks_reserved_tlds(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("foo.local") is False
            assert is_safe_network_address("bar.test") is False

    def test_allows_internal_hosts_when_configured(self):
        with patch("core.security.cfg.allowed_internal_hosts", {"myinternal"}):
            assert is_safe_network_address("myinternal") is True


class TestAssertSafeUrls:
    """Test URL list validation."""

    def test_safe_urls_return_empty(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["https://example.com", "https://github.com"])
        assert safe is True
        assert err == ""

    def test_private_url_blocked(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["http://192.168.1.1/admin"])
        assert safe is False
        assert "Blocked" in err
        assert "192.168.1.1" in err

    def test_mixed_list_blocks_on_first_bad(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls([
                "https://example.com",
                "http://127.0.0.1/secret",
            ])
        assert safe is False
        assert "127.0.0.1" in err

    def test_empty_list_is_safe(self):
        safe, err = _assert_safe_urls([])
        assert safe is True
        assert err == ""

    def test_malformed_url_blocked(self):
        with patch("core.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["not-a-url"])
        assert safe is False
        assert "Blocked" in err
