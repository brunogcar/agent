"""Shared fixtures for core/net tests."""
from __future__ import annotations

import re
import socket
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_budget_tracker():
    """Reset the global budget tracker singleton before each test."""
    from core.net.budget import _budget_tracker
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()
    _budget_tracker._last_reset_date = __import__("datetime").date.today()
    yield
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()


@pytest.fixture(autouse=True)
def mock_dns_resolution():
    """Mock _resolve_safe so SSRF tests don't do real DNS lookups (2s timeout each).

    _resolve_safe uses socket.getaddrinfo with a 2s timeout. Tests that check
    hostnames like "foo.local", "xn--0zwm56d", or decimal IPs ("2130706433")
    all trigger DNS resolution, which times out after 2s on machines where
    these names don't resolve. With 5+ such tests, this adds 10+ seconds.

    Strategy: return a fake PUBLIC IP for valid-looking public domains (so
    they're treated as safe), and [] (unresolvable → unsafe) for:
      - Invalid hostnames (URLs with schemes, ports, slashes, etc.)
      - Reserved TLDs (.local, .test, .localhost, .invalid)
      - Decimal IPs (e.g., "2130706433")
      - IDNA/punycode (xn--...)
    This matches the behavior tests expect: example.com is safe,
    foo.local is blocked, ftp://example.com is blocked.
    """
    _FAKE_PUBLIC_ADDR = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))
    _FAKE_LOOPBACK_ADDR = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
    _RESERVED_TLDS = (".local", ".test", ".localhost", ".invalid", ".example",
                      ".arpa", ".onion")
    # Valid hostname: alphanumeric + dots + hyphens, no scheme/port/path
    _VALID_HOSTNAME = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$')

    def _mock_resolve(hostname, timeout=2.0):
        h = hostname.rstrip(".").lower()
        # Invalid hostname format (URLs with scheme, port, path, etc.) → unresolvable
        if not _VALID_HOSTNAME.match(h):
            return []
        # localhost → loopback (private → blocked)
        if h in ("localhost", "localhost.localdomain"):
            return [_FAKE_LOOPBACK_ADDR]
        # Reserved TLDs → unresolvable (unsafe)
        if any(h.endswith(tld) for tld in _RESERVED_TLDS):
            return []
        # Decimal IP (e.g., "2130706433") → not a valid hostname → unresolvable
        if h.replace(".", "").isdigit():
            return []
        # IDNA/punycode → treat as unresolvable for tests
        if h.startswith("xn--"):
            return []
        # Normal-looking domain → fake public IP (safe)
        return [_FAKE_PUBLIC_ADDR]

    with patch("core.net.security._resolve_safe", side_effect=_mock_resolve):
        yield
