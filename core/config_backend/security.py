"""core/config_backend/security.py — Initialize protected files, SSRF allowlist, gateway, environment.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    SSRF Protection:
        ALLOWED_INTERNAL_HOSTS  — default "localhost,127.0.0.1,::1"
                                  (comma-separated; "" = block ALL private/localhost)

    Gateway:
        GATEWAY_HOST    — default "127.0.0.1"
        GATEWAY_PORT    — default 8000
        GATEWAY_SECRET  — default "changeme"

    Environment:
        ENV  — default "development" (cfg.is_dev = (ENV == "development"))

Non-env-derived:
    protected_files  — frozenset of paths that may never be written by autocode:
        server.py, registry.py, core/config.py, core/tracer.py,
        core/llm.py, core/memory.py, core/gateway.py
"""

from __future__ import annotations

import os


def _init_security(cfg) -> None:
    """Initialize protected files, SSRF allowlist, gateway, and environment flags."""

    # -- Protected files ---------------------------------------------------
    cfg.protected_files: frozenset[str] = frozenset({
        "server.py", "registry.py",
        "core/config.py", "core/tracer.py",
        "core/llm.py", "core/memory.py", "core/gateway.py",
    })

    # -- SSRF Protection ---------------------------------------------------
    # Allowlist for trusted internal services (comma-separated hostnames)
    # Default: permissive for development (localhost, LM Studio, SearXNG)
    # Production: set ALLOWED_INTERNAL_HOSTS="" to block ALL private/localhost
    cfg.allowed_internal_hosts: frozenset[str] = frozenset(
        h.strip().lower()
        for h in os.getenv("ALLOWED_INTERNAL_HOSTS", "localhost,127.0.0.1,::1").split(",")
        if h.strip()
    )

    # -- Gateway -----------------------------------------------------------
    cfg.gateway_host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    cfg.gateway_port = int(os.getenv("GATEWAY_PORT", "8000"))
    cfg.gateway_secret = os.getenv("GATEWAY_SECRET", "changeme")

    # -- Environment -------------------------------------------------------
    cfg.env = os.getenv("ENV", "development")
    cfg.is_dev = cfg.env == "development"
    cfg.is_windows = os.name == "nt"
