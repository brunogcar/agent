"""core/net/security.py — SSRF prevention and URL safety checks.

v1.1: Moved from core/security.py; added _assert_safe_urls.
v1.2: Fixed empty hostname bypass, IPv6 port stripping, scheme validation.
v1.3: Restored DNS timeout via ThreadPoolExecutor (socket.getaddrinfo has no timeout kwarg).
      Added _is_private_or_localhost back for cross-tool use.
      FIXED: IPv6 bracket parsing (was broken by split(':') on IPv6 addresses).
v1.4: Added is_unspecified check to block 0.0.0.0 and ::.


[DESIGN] KEY DECISIONS — read before modifying:

  1. socket.getaddrinfo() HAS NO timeout PARAMETER — DO NOT ADD ONE.
     Passing timeout=2.0 raises TypeError. Our except Exception silently swallows it,
     returning [] for every hostname and blocking ALL public URLs with a misleading
     "SSRF blocked" error. The ONLY correct pattern: submit to _DNS_POOL, call
     future.result(timeout=N).

  2. _DNS_POOL max_workers=2. Under parallel tool fan-out, slow DNS pins both workers.
     Raise to 4-6 if parallel tool starts spurious timeouts. Use this shared pool —
     do NOT create per-call ThreadPoolExecutors for DNS resolution.

  3. CGNAT 100.64.0.0/10: ip.is_private=False on Python <3.11.
     NOTE: This file does NOT currently use ip.is_global. It checks is_private,
     is_loopback, is_link_local, is_reserved, is_multicast, is_unspecified.
     On Python <3.11, CGNAT addresses (100.64/10) pass is_private=False and are
     NOT caught by any of the six checks above. If gateway ever faces the internet,
     ADD an explicit is_global check (is_global==False -> block) as a CGNAT safety net.

  4. _is_private_or_localhost() semantics: True=BLOCK, False=ALLOW.
     is_safe_network_address() is the INVERSE: True=safe, False=block.
     Despite the leading underscore, IS exported in __init__.py and used by
     web_ops, tavily_ops, browser_ops. Not internal-only.

  5. TOCTOU WINDOW exists between our DNS check and httpx's actual connection.
     0-TTL DNS rebinding can change the IP after our validation. Accepted risk for
     local-first agent. If gateway ever faces the internet, use a custom httpx
     transport that binds to the pre-validated IP.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
from urllib.parse import urlparse

from core.config import cfg

# v1.3: Dedicated DNS thread pool for timeout-controlled resolution
_DNS_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="dns_resolve"
)


def _resolve_safe(hostname: str, timeout: float = 2.0):
    """Resolve hostname to IPs, returning empty list on any failure.

    Prevents DNS rebinding by resolving before connecting.
    v1.3 FIX: socket.getaddrinfo does NOT accept a timeout keyword argument.
    Use ThreadPoolExecutor + future.result(timeout=) instead.
    """
    future = _DNS_POOL.submit(socket.getaddrinfo, hostname, None)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return []
    except Exception:
        return []


def _is_private_or_localhost(hostname: str) -> bool:
    """Check if a hostname resolves to or is a private, loopback, or reserved address.

    v1.3: Restored for cross-tool use (web_ops, browser, tavily).
    v1.3 FIX: Proper IPv6 bracket parsing (was broken by naive split(':')).
    v1.4 FIX: Block 0.0.0.0 and :: via is_unspecified.
    Handles IP literals directly and resolves domain names for DNS rebinding checks.
    """
    if not hostname or not isinstance(hostname, str):
        return True  # Empty/invalid is treated as unsafe

    hostname = hostname.rstrip(".")

    # ── IPv6 literal with brackets ──────────────────────────────────────────
    if hostname.startswith("["):
        bracket_end = hostname.find("]")
        if bracket_end == -1:
            return True  # Malformed IPv6
        ip_part = hostname[1:bracket_end]
        # Validate: after closing bracket, either end of string or ":port"
        if bracket_end + 1 < len(hostname):
            if not hostname[bracket_end + 1:].startswith(":"):
                return True  # Malformed: unexpected chars after ]
        try:
            ip = ipaddress.ip_address(ip_part)
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            )
        except ValueError:
            return True

    # ── IPv6 literal without brackets ───────────────────────────────────────
    if ":" in hostname:
        try:
            ip = ipaddress.ip_address(hostname)
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            )
        except ValueError:
            pass  # Not an IPv6 literal, might be IPv4 with port

    # ── IPv4 literal with port ─────────────────────────────────────────────
    if ":" in hostname:
        ip_str = hostname.split(":")[0]
    else:
        ip_str = hostname

    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass  # Not an IP literal, fall through to DNS

    # ── DNS resolution ──────────────────────────────────────────────────────
    addrs = _resolve_safe(hostname)
    if not addrs:
        return True  # Cannot resolve — treat as unsafe

    for _, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return True
        except ValueError:
            continue

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

    # Dev mode: allow explicitly configured internal hosts
    allowed = getattr(cfg, "allowed_internal_hosts", set())
    if hostname.lower() in {h.lower() for h in allowed}:
        return True

    # Strip trailing dot (FQDN)
    hostname = hostname.rstrip(".")

    # Delegate to _is_private_or_localhost and invert
    return not _is_private_or_localhost(hostname)


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
