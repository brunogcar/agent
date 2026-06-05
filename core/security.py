"""
core/security.py — Centralized security policies and network validation.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import socket

from core.config import cfg

logger = logging.getLogger(__name__)
_SSRF_WARNED = False

# Dedicated thread pool for DNS resolution to prevent blocking the event loop
_DNS_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="dns_resolver")

def _resolve_safe(hostname: str, timeout: float = 2.0) -> list:
    """Resolve hostname with a strict timeout to prevent DoS via slow DNS."""
    future = _DNS_POOL.submit(socket.getaddrinfo, hostname, None)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return []
    except Exception:
        return []

def is_safe_network_address(hostname: str) -> bool:
    """
    Check if a hostname is safe to connect to (i.e., NOT private, loopback, or reserved).
    Respects the ALLOWED_INTERNAL_HOSTS allowlist in config.
    Returns True if safe, False if blocked.
    
    SECURITY FEATURES:
    - Blocks private, loopback, link-local, and reserved IP ranges.
    - Blocks IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1).
    - Prevents DNS Rebinding attacks by resolving hostnames to IPs and validating ALL returned records.
    - Prevents DNS DoS by enforcing a strict 2-second timeout on resolution.
    """
    global _SSRF_WARNED
    
    if not _SSRF_WARNED and cfg.allowed_internal_hosts:
        logger.warning(
            "SSRF: localhost/internal access allowed by default for development. "
            "Set ALLOWED_INTERNAL_HOSTS='' in .env for production."
        )
        _SSRF_WARNED = True

    hostname = hostname.lower().strip()

    # Handle IPv6 with port: [::1]:8080 -> ::1
    if hostname.startswith("[") and "]:" in hostname:
        hostname = hostname.split("]:")[0].lstrip("[")
    # Handle IPv4 with port: 127.0.0.1:3000 -> 127.0.0.1
    # But NOT IPv6 without brackets (like ::1) - don't strip colons from IPv6
    elif ":" in hostname and not hostname.startswith("[") and "::" not in hostname:
        hostname = hostname.split(":")[0]

    # Allow explicitly permitted hosts FIRST (short-circuit for performance)
    if hostname in cfg.allowed_internal_hosts:
        return True

    # Loopback variants (any port)
    if hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return False

    # Reserved TLDs (mDNS, test domains, RFC 6761/6762)
    if hostname.endswith((".local", ".test", ".localhost", ".invalid")):
        return False

    # 1. Check if it's a bare IP address
    try:
        ip = ipaddress.ip_address(hostname)
        
        # Block IPv4-mapped IPv6 (e.g., ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return False
            
        is_unsafe = bool(
            ip.is_private or      # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
            ip.is_loopback or     # 127.0.0.0/8, ::1
            ip.is_link_local or   # 169.254.0.0/16, fe80::/10
            ip.is_reserved        # 192.0.2.0/24, 2001:db8::/32, etc.
        )
        return not is_unsafe
    except ValueError:
        # Not a bare IP address. It's a domain name.
        # We MUST resolve it to prevent DNS rebinding attacks.
        pass

    # 2. DNS Resolution & Validation (Prevents DNS Rebinding)
    # We use a dedicated thread pool with a strict timeout to prevent DoS.
    infos = _resolve_safe(hostname, timeout=2.0)
    
    # If resolution fails or times out (empty list), we MUST block.
    if not infos:
        return False
        
    for _, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            
            # Block IPv4-mapped IPv6 (e.g., ::ffff:127.0.0.1)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                return False
                
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            # If we can't parse the resolved IP, block it to be safe.
            return False
            
    return True

def _is_private_or_localhost(hostname: str) -> bool:
    """Legacy compatibility alias. Returns True if hostname is private/localhost.
    
    Differs from is_safe_network_address on semantics:
    - True  = hostname IS private/localhost (should be blocked)
    - False = hostname is NOT private/localhost (allowed or unknown)
    
    For invalid/empty hostnames and DNS resolution failures, returns False
    (permissive fallback) to match original behavior.
    
    New code should use is_safe_network_address() which returns True for safe
    addresses and False for blocked/unknown (secure-by-default).
    """
    if not hostname or not isinstance(hostname, str):
        return False
    h = hostname.strip()
    if not h:
        return False
    
    # Handle IPv6 with port: [::1]:8080 -> ::1
    if h.startswith("[") and "]:" in h:
        h = h.split("]:")[0].lstrip("[")
    # Handle IPv4 with port: 127.0.0.1:3000 -> 127.0.0.1
    elif ":" in h and not h.startswith("[") and "::" not in h:
        h = h.split(":")[0]
    
    # Allowlist check (short-circuit)
    if h in cfg.allowed_internal_hosts:
        return False  # Allowed = not private
    
    # Known loopback variants
    if h in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    
    # Reserved TLDs
    if h.endswith((".local", ".test", ".localhost", ".invalid")):
        return True
    
    # IP address check
    try:
        ip = ipaddress.ip_address(h)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return True
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        pass
    
    # DNS resolution — permissive fallback on failure (old behavior)
    infos = _resolve_safe(h, timeout=2.0)
    if not infos:
        return False
    
    for _, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                return True
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except ValueError:
            pass
    
    return False

