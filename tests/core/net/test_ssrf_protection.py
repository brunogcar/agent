"""Tests for SSRF protection via core/net/security.py.

v1.3: Merged from old tests/security/test_ssrf_protection.py.
      Fixed Windows-1252 encoding corruption.
      Rewritten to use current security API.
"""
from __future__ import annotations

import pytest

from core.net.security import is_safe_network_address, _assert_safe_urls


@pytest.fixture(autouse=True)
def patch_allowed_hosts(monkeypatch):
    """Patch ALLOWED_INTERNAL_HOSTS to empty for all tests in this file."""
    from core.net import security
    monkeypatch.setattr(security.cfg, "allowed_internal_hosts", frozenset())


class TestSSRFProtection:
    """SSRF protection tests."""

    def test_blocks_loopback(self):
        assert is_safe_network_address("127.0.0.1") is False
        assert is_safe_network_address("localhost") is False

    def test_blocks_private_ranges(self):
        assert is_safe_network_address("10.0.0.1") is False
        assert is_safe_network_address("172.16.0.1") is False
        assert is_safe_network_address("192.168.1.1") is False

    def test_blocks_link_local(self):
        assert is_safe_network_address("169.254.1.1") is False

    def test_allows_public_ips(self):
        assert is_safe_network_address("8.8.8.8") is True
        assert is_safe_network_address("1.1.1.1") is True

    def test_blocks_ipv6_loopback(self):
        assert is_safe_network_address("::1") is False
        assert is_safe_network_address("[::1]") is False

    def test_allows_ipv6_public(self):
        # v1.3 FIX: Use truly public IPv6 address
        assert is_safe_network_address("2001:4860:4860::8888") is True

    def test_url_list_mixed(self):
        safe, err = _assert_safe_urls([
            "https://example.com",
            "http://127.0.0.1/secret",
        ])
        assert safe is False
        assert "127.0.0.1" in err
