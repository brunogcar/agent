"""Shared utilities for web_ops actions.

_is_safe_url is used by both search (for SearXNG URL validation) and
scrape (for target URL validation). Kept here to avoid duplication.
"""
from __future__ import annotations

from urllib.parse import urlparse

from core.security import is_safe_network_address


def _is_safe_url(url: str) -> bool:
    """Return False if the URL resolves to a private, loopback, or reserved address.

    SSRF protection layer. All URL parameters pass through this before
    any HTTP request is made.
    """
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        return is_safe_network_address(hostname)
    except Exception:
        return False
