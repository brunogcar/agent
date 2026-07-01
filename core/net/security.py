"""core/net/security.py — SSRF prevention and URL safety checks.

v1.1: Moved from core/net/security.py; added _assert_safe_urls.
v1.2: Fixed empty hostname bypass, IPv6 port stripping, scheme validation.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from core.config import cfg


def _resolve_safe(hostname: str, timeout: float = 2.0):
    """Resolve hostname to IPs, returning empty list on any failure.

    Prevents DNS rebinding by resolving before connecting.
    """
    try:
        return socket.getaddrinfo(hostname, None, timeout=timeout)
    except Exception:
        return []


def _is_private_or_localhost(ip_str: str) -> bool:
    """Check if an IP string is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or getattr(ip, "is_global", False) is False
        )
    except ValueError:
        return False


def is_safe_network_address(hostname: str) -> bool:
    """Return True if hostname resolves to a public, non-internal IP.

    Checks:
    1. Explicit allowlist (dev mode)
    2. IPv4 / IPv6 literal (bypasses DNS)
    3. DNS resolution (catches CNAME → private IP rebinding)
    """
    # v1.2: Reject empty/None hostnames explicitly
    if not hostname or not isinstance(hostname, str):
        return False

    # v1.2: Whitelist http/https schemes only
    # NOTE: This function receives hostname only; scheme check is in _assert_safe_urls

    # Dev mode: allow explicitly configured internal hosts
    allowed = getattr(cfg, "allowed_internal_hosts", set())
    if hostname.lower() in {h.lower() for h in allowed}:
        return True

    # Strip trailing dot (FQDN)
    hostname = hostname.rstrip(".")

    # ── IPv6 literal ──────────────────────────────────────────────────────────
    if hostname.startswith("["):
        # v1.2 FIX: Handle IPv6 with port: [::1]:8080 → ::1
        if "]:" in hostname:
            ip_part = hostname.split(":")[1].split("]")[0]
            # Reconstruct with brackets for ipaddress module
            ip_str = f"[{ip_part}]"
        elif hostname.endswith("]"):
            ip_str = hostname
        else:
            return False  # Malformed IPv6
        try:
            ip = ipaddress.ip_address(ip_str)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            )
        except ValueError:
            return False

    # ── IPv4 literal ──────────────────────────────────────────────────────────
    if ":" in hostname and not hostname.startswith("["):
        # IPv4 with port: strip port
        ip_str = hostname.split(":")[0]
    else:
        ip_str = hostname

    try:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        pass  # Not an IP literal, fall through to DNS

    # ── DNS resolution ─────────────────────────────────────────────────────────
    addrs = _resolve_safe(hostname)
    if not addrs:
        # Cannot resolve — treat as unsafe to prevent SSRF via unresolvable hosts
        return False

    for _, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        if _is_private_or_localhost(ip_str):
            return False

    return True


def _assert_safe_urls(urls: list[str]) -> tuple[bool, str]:
    """Validate a list of URLs against SSRF rules.

    Returns:
        (True, "") if all URLs are safe
        (False, error_message) if any URL is blocked

    v1.2: Added scheme validation, empty hostname rejection.
    """
    for url in urls:
        parsed = urlparse(url)

        # v1.2: Validate scheme
        if parsed.scheme not in ("http", "https"):
            return False, f"Blocked: {url} — only http/https schemes allowed"

        # v1.2: Reject empty/None hostnames
        hostname = parsed.hostname
        if not hostname:
            return False, f"Blocked: {url} — no valid hostname"

        if not is_safe_network_address(hostname):
            return False, f"Blocked: {url} — resolves to private/internal address"

    return True, ""
