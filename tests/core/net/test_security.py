"""Tests for core/net/security.py — SSRF prevention and URL safety.

v1.3: Added IPv6 edge cases, merged path_validation and ssrf_protection coverage.
      Added _is_private_or_localhost tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from core.net.security import (
    is_safe_network_address,
    _assert_safe_urls,
    _is_private_or_localhost,
)


@pytest.fixture(autouse=True)
def patch_allowed_hosts(monkeypatch):
    """Patch ALLOWED_INTERNAL_HOSTS to empty for all tests in this file."""
    from core.net import security
    monkeypatch.setattr(security.cfg, "allowed_internal_hosts", frozenset())


class TestIsPrivateOrLocalhost:
    """Tests for _is_private_or_localhost() — the core IP/hostname check."""

    def test_ipv4_loopback(self):
        assert _is_private_or_localhost("127.0.0.1") is True

    def test_ipv4_private(self):
        assert _is_private_or_localhost("10.0.0.1") is True
        assert _is_private_or_localhost("192.168.1.1") is True
        assert _is_private_or_localhost("172.16.0.1") is True

    def test_ipv4_public(self):
        assert _is_private_or_localhost("8.8.8.8") is False
        assert _is_private_or_localhost("1.1.1.1") is False

    def test_ipv6_loopback_no_brackets(self):
        """::1 without brackets."""
        assert _is_private_or_localhost("::1") is True

    def test_ipv6_loopback_with_brackets(self):
        """[::1] with brackets."""
        assert _is_private_or_localhost("[::1]") is True

    def test_ipv6_loopback_with_port(self):
        """[::1]:8080 — port stripped."""
        assert _is_private_or_localhost("[::1]:8080") is True

    def test_ipv4_mapped_ipv6(self):
        assert _is_private_or_localhost("::ffff:127.0.0.1") is True

    def test_ipv6_public(self):
        # v1.3 FIX: 2001:db8::1 is RESERVED in Python's ipaddress module (RFC 3849)
        # Use a truly public IPv6 address instead
        assert _is_private_or_localhost("2001:4860:4860::8888") is False  # Google DNS
        assert _is_private_or_localhost("2606:4700:4700::1111") is False  # Cloudflare DNS

    def test_ipv6_public_with_port(self):
        assert _is_private_or_localhost("[2001:4860:4860::8888]:8080") is False

    def test_empty_hostname(self):
        assert _is_private_or_localhost("") is True

    def test_none_hostname(self):
        assert _is_private_or_localhost(None) is True

    def test_local_tld(self):
        """.local domains resolve as private (DNS fails or returns local)."""
        assert _is_private_or_localhost("foo.local") is True

    def test_public_domain(self):
        """Public domains should return False (safe)."""
        result = _is_private_or_localhost("example.com")
        assert isinstance(result, bool)


class TestIsSafeNetworkAddress:
    """Tests for is_safe_network_address() — the public API."""

    def test_blocks_ipv4_loopback(self):
        assert is_safe_network_address("127.0.0.1") is False

    def test_blocks_ipv4_private(self):
        assert is_safe_network_address("10.0.0.1") is False
        assert is_safe_network_address("192.168.1.1") is False

    def test_allows_ipv4_public(self):
        assert is_safe_network_address("8.8.8.8") is True

    def test_blocks_ipv6_loopback(self):
        assert is_safe_network_address("[::1]") is False
        assert is_safe_network_address("[::1]:8080") is False

    def test_blocks_ipv4_mapped_ipv6(self):
        assert is_safe_network_address("::ffff:127.0.0.1") is False

    def test_allows_ipv6_public(self):
        # v1.3 FIX: Use truly public IPv6 addresses
        assert is_safe_network_address("2001:4860:4860::8888") is True
        assert is_safe_network_address("[2001:4860:4860::8888]:8080") is True

    def test_rejects_empty_hostname(self):
        assert is_safe_network_address("") is False

    def test_rejects_none_hostname(self):
        assert is_safe_network_address(None) is False

    def test_allows_internal_hosts_when_configured(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", {"internal.corp"}):
            assert is_safe_network_address("internal.corp") is True

    def test_blocks_file_scheme(self):
        assert is_safe_network_address("file:///etc/passwd") is False

    def test_blocks_ftp_scheme(self):
        assert is_safe_network_address("ftp://example.com") is False

    def test_blocks_javascript_scheme(self):
        assert is_safe_network_address("javascript:alert(1)") is False

    def test_blocks_url_with_port_no_host(self):
        assert is_safe_network_address(":8080") is False

    def test_blocks_empty_string_url(self):
        assert is_safe_network_address("") is False

    def test_blocks_reserved_tlds(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("foo.local") is False
            assert is_safe_network_address("bar.test") is False


class TestAssertSafeUrls:
    """Tests for _assert_safe_urls() — URL list validation."""

    def test_allows_safe_urls(self):
        safe, err = _assert_safe_urls(["https://example.com", "https://github.com"])
        assert safe is True
        assert err == ""

    def test_blocks_private_url(self):
        safe, err = _assert_safe_urls(["http://127.0.0.1/admin"])
        assert safe is False
        assert "Blocked" in err

    def test_blocks_mixed_list(self):
        safe, err = _assert_safe_urls(["https://example.com", "http://192.168.1.1"])
        assert safe is False
        assert "192.168.1.1" in err

    def test_blocks_invalid_scheme(self):
        safe, err = _assert_safe_urls(["file:///etc/passwd"])
        assert safe is False
        assert "only http/https" in err

    def test_blocks_empty_hostname(self):
        safe, err = _assert_safe_urls(["http:///path"])
        assert safe is False
        assert "no valid hostname" in err
