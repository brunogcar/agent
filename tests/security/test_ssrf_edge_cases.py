"""Edge-case SSRF tests for is_safe_network_address.

[BUGFIX-SECURITY] Covers IPv6, decimal IP, and DNS rebinding bypass attempts.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from core.security import is_safe_network_address

@pytest.fixture(autouse=True)
def block_all_internal_hosts(monkeypatch):
    """Patch ALLOWED_INTERNAL_HOSTS to empty for all tests in this file."""
    from core import security
    monkeypatch.setattr(security.cfg, "allowed_internal_hosts", frozenset())

class TestSSRFIPv6EdgeCases:
    """IPv6 loopback and mapped addresses must be blocked."""

    def test_ipv6_loopback_blocked(self):
        """::1 must be blocked."""
        assert is_safe_network_address("::1") is False

    def test_ipv6_loopback_with_port_blocked(self):
        """[::1]:8080 must be blocked."""
        assert is_safe_network_address("[::1]:8080") is False

    def test_ipv4_mapped_ipv6_loopback_blocked(self):
        """::ffff:127.0.0.1 must be blocked (IPv4-mapped IPv6)."""
        assert is_safe_network_address("::ffff:127.0.0.1") is False

    def test_ipv6_localhost_blocked(self):
        """0:0:0:0:0:0:0:1 must be blocked."""
        assert is_safe_network_address("0:0:0:0:0:0:0:1") is False

    def test_ipv6_private_ula_blocked(self):
        """fd00::1 (Unique Local Address) must be blocked."""
        assert is_safe_network_address("fd00::1") is False

    def test_ipv6_link_local_blocked(self):
        """fe80::1 must be blocked."""
        assert is_safe_network_address("fe80::1") is False

class TestSSRFDecimalIPEdgeCases:
    """Decimal IP representations are NOT valid hostnames.

    is_safe_network_address expects a hostname string. Decimal IPs like
    '2130706433' fail ip_address() parsing and fall through to DNS resolution.
    Since DNS cannot resolve a bare integer string, they are blocked.

    This is defense-in-depth (accidental blocking), not explicit validation.
    The test documents this behavior rather than asserting a security guarantee.
    """

    def test_decimal_ip_127_blocked(self):
        """2130706433 (= 127.0.0.1) is not a valid hostname → DNS fails → blocked."""
        result = is_safe_network_address("2130706433")
        assert result is False

    def test_decimal_ip_192168_blocked(self):
        """3232235521 (= 192.168.0.1) is not a valid hostname → DNS fails → blocked."""
        result = is_safe_network_address("3232235521")
        assert result is False

class TestSSRFReservedTLDs:
    """Reserved TLDs must be blocked."""

    def test_local_tld_blocked(self):
        assert is_safe_network_address("myserver.local") is False

    def test_test_tld_blocked(self):
        assert is_safe_network_address("example.test") is False

    def test_localhost_tld_blocked(self):
        assert is_safe_network_address("app.localhost") is False

    def test_invalid_tld_blocked(self):
        assert is_safe_network_address("foo.invalid") is False

class TestSSRFDNSRebinding:
    """DNS rebinding attacks: hostname resolves to private IP."""

    def test_dns_rebinding_to_private_ip(self, monkeypatch):
        """A public-looking hostname that resolves to 192.168.1.1 must be blocked."""
        import socket
        original_getaddrinfo = socket.getaddrinfo

        def mock_getaddrinfo(host, port, *args, **kwargs):
            # Return a fake resolution to a private IP
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.1.1', 0))]

        monkeypatch.setattr(socket, 'getaddrinfo', mock_getaddrinfo)
        # Must patch the _resolve_safe function which uses ThreadPoolExecutor
        from core import security
        monkeypatch.setattr(security, '_resolve_safe', lambda hostname, timeout=2.0: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.1.1', 0))
        ])

        assert is_safe_network_address("attacker.example.com") is False

    def test_dns_rebinding_to_loopback(self, monkeypatch):
        """A public-looking hostname that resolves to 127.0.0.1 must be blocked."""
        import socket
        from core import security
        monkeypatch.setattr(security, '_resolve_safe', lambda hostname, timeout=2.0: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1', 0))
        ])

        assert is_safe_network_address("evil.com") is False

class TestSSRFAllowedHosts:
    """Explicitly allowed internal hosts must pass."""

    def test_allowed_internal_host(self, monkeypatch):
        """Hosts in ALLOWED_INTERNAL_HOSTS must be permitted."""
        from core import security
        monkeypatch.setattr(security.cfg, 'allowed_internal_hosts', frozenset({'myinternal'}))
        assert is_safe_network_address("myinternal") is True

    def test_allowed_internal_host_case_insensitive(self, monkeypatch):
        """Allowed hosts check must be case-insensitive."""
        from core import security
        monkeypatch.setattr(security.cfg, 'allowed_internal_hosts', frozenset({'myinternal'}))
        assert is_safe_network_address("MYINTERNAL") is True
