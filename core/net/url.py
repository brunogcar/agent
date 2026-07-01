"""core/net/url.py — URL normalization and parsing utilities.

v1.2: Added for consistent cache keys and URL comparison.
v1.3: Fixed is_same_domain to consider www.example.com and example.com as same domain.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent cache key generation.

    Rules:
      1. Lowercase scheme and hostname
      2. Strip trailing slash from path
      3. Sort query parameters alphabetically
      4. Strip fragment
      5. Strip default ports (80 for http, 443 for https)
    """
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.hostname.lower() if parsed.hostname else ""

    # Handle port
    if parsed.port:
        if (scheme == "http" and parsed.port != 80) or (scheme == "https" and parsed.port != 443):
            netloc = f"{netloc}:{parsed.port}"

    # Normalize path
    path = parsed.path.rstrip("/") or "/"

    # Sort query params
    query = urlencode(sorted(parse_qsl(parsed.query))) if parsed.query else ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_domain(url: str) -> str:
    """Extract the domain (hostname) from a URL."""
    return urlparse(url).hostname or ""


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs share the same domain.

    v1.3: www.example.com and example.com are considered the same domain.
    """
    d1 = extract_domain(url1).lower()
    d2 = extract_domain(url2).lower()
    # Strip www. prefix for comparison
    d1 = d1.removeprefix("www.")
    d2 = d2.removeprefix("www.")
    return d1 == d2
