"""
core/gateway_backend/dependencies.py — FastAPI Auth & Rate Limiting dependencies.

EXTRACTION NOTE (Gateway Phase 1): Extracted from core/gateway.py.
These functions are designed to be used with FastAPI's `Depends()` pattern.
"""
from __future__ import annotations

from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import cfg

# ── Dependency Providers (Phase 2 Step 5: Dependency Injection) ─────────
# These allow us to swap out the store, dispatcher, and runner in tests
# using app.dependency_overrides, completely eliminating monkeypatch.
from types import ModuleType

def get_task_store() -> ModuleType:
    from core.gateway_backend import store
    return store

def get_dispatcher() -> ModuleType:
    from core.gateway_backend import dispatcher
    return dispatcher

def get_task_runner() -> ModuleType:
    from core.runtime import task_runner
    return task_runner

_bearer = HTTPBearer(auto_error=False)

def check_auth(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """
    Bearer token auth.

    P0-2 fix: secret is validated at startup (in factory.py). Here we only check
    the incoming token. No print() to stdout -- all warnings go to stderr
    so MCP stdio channel stays clean (P0-1).
    """
    # Touch the activity tracker so background daemons know the agent is active.
    from core.runtime.activity_tracker import tracker
    tracker.touch()
    
    _secret = (getattr(cfg, "gateway_secret", None) or "").strip() or "changeme"
    if _secret != "changeme":
        if not creds or creds.credentials != _secret:
            raise HTTPException(status_code=401, detail="Unauthorized")