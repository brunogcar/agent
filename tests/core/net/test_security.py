"""tests/core/net/test_security.py — Tests for core.net.security helpers.

v1.2: Added IPv6 edge cases, empty hostname, scheme validation.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from core.net.security import is_safe_network_address, _assert_safe_urls


class TestIsSafeNetworkAddress:
    """Test hostname/IP validation for SSRF prevention."""

    def test_blocks_localhost(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("localhost") is False

    def test_blocks_127_0_0_1(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("127.0.0.1") is False

    def test_blocks_private_ip(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("192.168.1.1") is False
            assert is_safe_network_address("10.0.0.1") is False
            assert is_safe_network_address("172.16.0.1") is False

    def test_blocks_link_local(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("169.254.1.1") is False

    def test_allows_public_ip(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("8.8.8.8") is True
            assert is_safe_network_address("1.1.1.1") is True

    def test_allows_public_domain(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("example.com") is True
            assert is_safe_network_address("github.com") is True

    def test_blocks_reserved_tlds(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("foo.local") is False
            assert is_safe_network_address("bar.test") is False

    def test_allows_internal_hosts_when_configured(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", {"myinternal"}):
            assert is_safe_network_address("myinternal") is True

    # v1.2: NEW — IPv6 edge cases
    def test_blocks_ipv6_loopback(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("::1") is False

    def test_blocks_ipv6_with_port(self):
        """[::1]:8080 must be blocked — IPv6 loopback with port."""
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("[::1]:8080") is False

    def test_blocks_ipv4_mapped_ipv6(self):
        """::ffff:127.0.0.1 must be blocked."""
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("::ffff:127.0.0.1") is False

    def test_allows_ipv6_public(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            assert is_safe_network_address("2001:db8::1") is True

    # v1.2: NEW — empty hostname
    def test_rejects_empty_hostname(self):
        assert is_safe_network_address("") is False

    def test_rejects_none_hostname(self):
        assert is_safe_network_address(None) is False  # type: ignore[arg-type]


class TestAssertSafeUrls:
    """Test URL list validation."""

    def test_safe_urls_return_empty(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["https://example.com", "https://github.com"])
            assert safe is True
            assert err == ""

    def test_private_url_blocked(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["http://192.168.1.1/admin"])
            assert safe is False
            assert "Blocked" in err
            assert "192.168.1.1" in err

    def test_mixed_list_blocks_on_first_bad(self):
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
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
        with patch("core.net.security.cfg.allowed_internal_hosts", set()):
            safe, err = _assert_safe_urls(["not-a-url"])
            assert safe is False
            assert "no valid hostname" in err

    # v1.2: NEW — scheme validation
    def test_blocks_file_scheme(self):
        safe, err = _assert_safe_urls(["file:///etc/passwd"])
        assert safe is False
        assert "only http/https" in err

    def test_blocks_ftp_scheme(self):
        safe, err = _assert_safe_urls(["ftp://evil.com/"])
        assert safe is False
        assert "only http/https" in err

    def test_blocks_javascript_scheme(self):
        safe, err = _assert_safe_urls(["javascript:alert(1)"])
        assert safe is False
        assert "only http/https" in err

    # v1.2: NEW — empty hostname edge cases
    def test_blocks_url_with_port_no_host(self):
        """http://:8080/ has no hostname."""
        safe, err = _assert_safe_urls(["http://:8080/admin"])
        assert safe is False
        assert "no valid hostname" in err

    def test_blocks_empty_string_url(self):
        safe, err = _assert_safe_urls([""])
        assert safe is False
        assert "no valid hostname" in err
