"""skills/_base/route.py — Route factory + sync-guarded dispatch.

Provides:
  - make_route() — generates the route() dispatcher function for a skill
  - _route_with_sync_guard() — runs sync guard + dispatch with re-entrancy
    protection (via the _SYNC_CHECKED ContextVar defined here)
  - _dispatch() — internal dispatch (filters kwargs by signature)

The re-entrancy guard wraps the ENTIRE route() call (sync check + dispatch):
if a mode function (e.g., dashboard()) internally calls another route()
(e.g., annual()), the inner route() skips the sync check — it's already
been done by the outer route().

Part of the skills/_base/ package split (was originally in skills/_base.py).
"""
from __future__ import annotations

import inspect
from contextvars import ContextVar
from typing import Callable

from .registry import ModeSpec
from .html_gen import _auto_generate_html
from .sync_guard import ensure_fresh


# Re-entrancy guard: ensures ensure_fresh() runs at most once per top-level
# route() call. Without this, dashboard() → annual() → quarterly() would
# each trigger ensure_fresh() separately.
_SYNC_CHECKED: ContextVar[bool] = ContextVar("_sync_checked", default=False)


def make_route(
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    accept_sub_domain: bool = False,
    required_sources: list[str] | None = None,
) -> Callable:
    """Create a route() dispatcher function for a skill.

    Args:
        manifest_key:    "sub_domain" for CVM skills, "domain" for top-level
                         flat domains like investsite. Used in error responses.
        skill_name:      Skill name (e.g. "governance", "investsite"). Used in
                         error responses.
        MODES:           The skill's MODES dict (from make_registry()).
        accept_sub_domain: If True, route() accepts a sub_domain param (ignored)
                         for dispatcher compatibility. investsite needs this;
                         CVM skills don't (their dispatcher resolves sub_domain
                         before calling route()).
        required_sources: [v1.14] List of data sources this skill needs (e.g.
                         ["dfp", "itr", "bridge"]). The route() wrapper checks
                         freshness before each dispatch and triggers force-sync
                         if any source is older than 24h (or missing). Set to
                         None or [] to disable. Tests use CVM_SKIP_SYNC=1.

    Returns:
        A route(mode="", **kwargs) function (or route(sub_domain="", mode="")
        if accept_sub_domain=True) that dispatches to the registered mode.

    Usage in __init__.py:
        # CVM skill with sync guard:
        route = make_route("sub_domain", "governance", MODES,
                           required_sources=["dfp", "itr", "bridge"])
        # CVM skill without sync guard:
        route = make_route("sub_domain", "governance", MODES)
        # Top-level flat domain:
        route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
    """
    srcs = required_sources or []

    if accept_sub_domain:
        def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
            # sub_domain is intentionally ignored (flat domain compat).
            _ = sub_domain
            return _route_with_sync_guard(srcs, manifest_key, skill_name, MODES, mode, kwargs)
        return route
    else:
        def route(mode: str = "", **kwargs) -> dict:
            return _route_with_sync_guard(srcs, manifest_key, skill_name, MODES, mode, kwargs)
        return route


def _route_with_sync_guard(
    srcs: list[str],
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    mode: str,
    kwargs: dict,
) -> dict:
    """Run sync guard + dispatch with re-entrancy protection.

    [v1.14] The re-entrancy guard wraps the ENTIRE route() call (sync check
    + dispatch), not just the sync check. This ensures that if a mode
    function (e.g., dashboard()) internally calls another route() (e.g.,
    annual()), the inner route() skips the sync check — it's already been
    done by the outer route().

    [v5] The outer route() call also auto-generates HTML for dashboard mode.
    Inner route() calls (re-entrancy) skip HTML generation because they
    return early from the _SYNC_CHECKED guard above.
    """
    # Re-entrancy guard: if we're already inside a route() call, skip sync.
    if _SYNC_CHECKED.get():
        # Inner call — just dispatch, no sync check, no HTML
        kwargs.pop("skip_sync", False)
        return _dispatch(manifest_key, skill_name, MODES, mode, kwargs)

    # Outer call — set guard, run sync check, dispatch, then reset guard
    token = _SYNC_CHECKED.set(True)
    try:
        skip_sync = kwargs.pop("skip_sync", False)
        sync_report = None
        if srcs:
            company = kwargs.get("company")
            sync_report = ensure_fresh(srcs, company=company, skip_sync=skip_sync)
        result = _dispatch(manifest_key, skill_name, MODES, mode, kwargs)
        if sync_report is not None:
            result["_sync"] = sync_report
        # [v5] Auto-generate HTML for dashboard mode (outer call only —
        # inner calls return early from the _SYNC_CHECKED guard above).
        _auto_generate_html(skill_name, mode, kwargs, result)
        return result
    finally:
        _SYNC_CHECKED.reset(token)


def _dispatch(
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    mode: str,
    kwargs: dict,
) -> dict:
    """Internal: dispatch a mode call (shared by both route() variants)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MODES.keys())}"}
    if mode not in MODES:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MODES.keys())}"}

    spec = MODES[mode]
    fn = spec.fn
    # [v1.1] Use cached params_set instead of re-calling inspect.signature
    # on every dispatch (Qwen's performance finding).
    accepted = spec.params_set
    if not accepted:
        # Fallback: compute on first use if cache wasn't populated
        accepted = set(inspect.signature(fn).parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", manifest_key: skill_name,
                "mode": mode, "error": str(e)}
