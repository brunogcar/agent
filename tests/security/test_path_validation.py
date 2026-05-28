"""
SSRF Protection Tests — Self-contained, no conftest.py dependencies.
Tests the network-scope blocking logic in tools/vision.py and tools/web.py.
Run with: pytest tests/security/test_ssrf_protection.py -v --tb=short
"""
import os
import pytest
from urllib.parse import urlparse

# Import the function under test directly
from tools.vision import _is_private_or_localhost


class TestSSRFNetworkScopeBlocking:
    """Test that _is_private_or_localhost correctly blocks private/localhost URLs."""
    
    @pytest.mark.parametrize("url,should_block,reason", [
        # Allowed by default allowlist (development)
        ("http://localhost:3000", False, "localhost in default allowlist"),
        ("http://127.0.0.1:1234", False, "127.0.0.1 in default allowlist"),
        ("http://[::1]:8080", False, "IPv6 loopback in default allowlist"),
        
        # Blocked: Private IPv4 ranges
        ("http://10.0.0.5:443", True, "10.0.0.0/8 private range"),
        ("http://192.168.1.100:80", True, "192.168.0.0/16 private range"),
        ("http://172.16.0.1:3000", True, "172.16.0.0/12 private range"),
        ("http://172.31.255.255", True, "172.16-31.x.x private range boundary"),
        
        # Blocked: Link-local and reserved
        ("http://169.254.1.1", True, "169.254.0.0/16 link-local"),
        ("http://192.0.2.1", True, "192.0.2.0/24 documentation range (reserved)"),
        
        # Blocked: Reserved TLDs (RFC 6761/6762)
        ("http://device.local", True, ".local mDNS TLD"),
        ("http://test.test", True, ".test reserved TLD"),
        ("http://example.localhost", True, ".localhost reserved TLD"),
        ("http://invalid.invalid", True, ".invalid reserved TLD"),
        
        # Allowed: Public URLs
        ("https://example.com", False, "Public HTTPS URL"),
        ("http://api.github.com", False, "Public HTTP URL"),
        ("https://1.1.1.1", False, "Public IP address"),
    ])
    def test_ssrf_filter_by_url(self, url: str, should_block: bool, reason: str):
        """Test SSRF filtering with parametrized URLs."""
        hostname = urlparse(url).hostname
        assert hostname is not None, f"Test URL {url} has no hostname"
        
        is_blocked = _is_private_or_localhost(hostname)
        assert is_blocked == should_block, f"{reason}: expected blocked={should_block}, got {is_blocked}"
    
    def test_hostname_with_port_ipv4(self):
        """Test that IPv4 hostnames with ports are parsed correctly."""
        assert _is_private_or_localhost("127.0.0.1:3000") is False  # Allowed by allowlist
        assert _is_private_or_localhost("192.168.1.1:8080") is True  # Blocked private
    
    def test_hostname_with_port_ipv6(self):
        """Test that IPv6 hostnames with ports are parsed correctly."""
        assert _is_private_or_localhost("[::1]:8080") is False  # Allowed by allowlist
        assert _is_private_or_localhost("[fc00::1]:443") is True  # Blocked private IPv6
    
    def test_allowlist_override_via_env(self, monkeypatch):
        """Test that ALLOWED_INTERNAL_HOSTS env var overrides default allowlist."""
        # Temporarily override env var
        monkeypatch.setenv("ALLOWED_INTERNAL_HOSTS", "searxng.internal,local-lm-studio")

        import tools.vision
        new_allowlist = frozenset(
            h.strip().lower() for h in
            os.getenv("ALLOWED_INTERNAL_HOSTS", "").split(",") if h.strip()
        )
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", new_allowlist)

        # New allowlist entries should be allowed
        assert _is_private_or_localhost("searxng.internal") is False
        assert _is_private_or_localhost("local-lm-studio") is False

        # Default entries no longer in allowlist should be blocked
        assert _is_private_or_localhost("localhost") is True
        assert _is_private_or_localhost("127.0.0.1") is True
    
    def test_empty_allowlist_blocks_all_localhost(self, monkeypatch):
        """Test that ALLOWED_INTERNAL_HOSTS='' blocks all localhost/private access."""
        monkeypatch.setenv("ALLOWED_INTERNAL_HOSTS", "")

        import tools.vision
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", frozenset())

        # All localhost variants should be blocked
        assert _is_private_or_localhost("localhost") is True
        assert _is_private_or_localhost("127.0.0.1") is True
        assert _is_private_or_localhost("::1") is True
        assert _is_private_or_localhost("192.168.1.1") is True
    
    def test_invalid_hostname_handling(self):
        """Test that malformed hostnames don't crash the validator."""
        # These should not raise exceptions
        assert _is_private_or_localhost("") is False  # Empty string
        assert _is_private_or_localhost("not:a:valid:hostname") is False  # Too many colons
        assert _is_private_or_localhost(":::invalid") is False  # Malformed IPv6