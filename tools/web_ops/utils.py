"""Shared utilities for web_ops actions.

_is_safe_url is used by both search (for SearXNG URL validation) and
scrape (for target URL validation). Kept here to avoid duplication.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Allowed URL schemes. Anything else (file://, ftp://, etc.) is rejected.
_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> bool:
    """Return False if the URL resolves to a private, loopback, or reserved address.

    SSRF protection layer. All URL parameters pass through this before
    any HTTP request is made.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Lazy import to avoid loading core.net.security at web_ops import time
        from core.net.security import is_safe_network_address
        return is_safe_network_address(hostname)
    except Exception:
        return False
