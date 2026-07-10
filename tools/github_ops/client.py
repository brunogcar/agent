"""GitHub API client singleton.

Uses httpx directly (consistent with all other providers in the project).
Auth: Bearer token via GITHUB_TOKEN env var.
Base URL: https://api.github.com (hardcoded — GitHub API is a fixed endpoint).
"""
from __future__ import annotations

import threading
from typing import Optional
import httpx

from core.config import cfg


_client: Optional[httpx.Client] = None
_lock = threading.Lock()

GITHUB_API_BASE = "https://api.github.com"


def get_client() -> httpx.Client:
    """Return singleton httpx.Client with GitHub auth headers."""
    global _client
    if _client is None or _client.is_closed:
        with _lock:
            if _client is None or _client.is_closed:
                _client = httpx.Client(
                    base_url=GITHUB_API_BASE,
                    headers={
                        "Authorization": f"Bearer {cfg.github_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "Content-Type": "application/json",
                    },
                    timeout=None,  # timeout enforced per-request
                )
    return _client


def close_client() -> None:
    """Close the singleton client safely."""
    global _client
    if _client and not _client.is_closed:
        _client.close()
        _client = None


def is_configured() -> bool:
    """Check if GitHub is configured (token + owner + repo all set)."""
    return bool(cfg.github_token and cfg.github_owner and cfg.github_repo)


def repo_path() -> str:
    """Return the repo path segment: /repos/{owner}/{repo}."""
    return f"/repos/{cfg.github_owner}/{cfg.github_repo}"
