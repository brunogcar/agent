"""data_sources/ddm/_base/route_base.py -- Shared route() factory for DDM.

All 7 DDM sub-domain __init__.py files share an identical ~50-line `route()`
function:

    def route(mode="", **kwargs):
        if not mode:
            return {"status": "error", "error": "mode required. ..."}
        if mode not in MANIFEST["modes"]:
            return {"status": "error", "error": "Unknown mode ..."}
        try:
            if mode == "sync_all":
                from ...sync_engine import sync_all as _fn
            elif mode == "sync_index":
                from ...sync_engine import sync_index as _fn
            elif mode == "<src-specific>":
                from ...query_engine import <fn> as _fn
            ...
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)
        except FileNotFoundError as e:
            return {"status": "not_synced", "error": str(e)}
        except Exception as e:
            import traceback
            return {"status": "error", "sub_domain": "<src>",
                    "mode": mode, "error": str(e),
                    "traceback": traceback.format_exc()}

Only two things differ:
  1. The sub_domain string (used in the docstring + the error dict's
     "sub_domain" key).
  2. The mode → (module_path, function_name) mapping table (each source
     has 8 modes; 6 are universal, 2 are source-specific).

This module provides a `make_ddm_route(sub_domain, mode_map)` factory that
takes a `_MODE_MAP: dict[mode_str, (module_path_str, function_name_str)]`
and returns a `route(mode, **kwargs)` function. The mode_map values are
strings (not callables) so the lazy-import happens inside the returned
route() function — preserving the import-time circular-dep avoidance of
the original.

[Phase 3, Commit 1] Extracted from the 7 __init__.py files.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable


def make_ddm_route(
    sub_domain: str,
    mode_map: dict[str, tuple[str, str]],
    manifest: dict,
) -> Callable[..., dict]:
    """Build a route() dispatcher for a DDM sub-domain.

    Args:
        sub_domain: e.g. "inflation" (used in error dicts + docstring).
        mode_map:   {mode_str: (module_path_str, function_name_str)}.
                    module_path_str is a dotted Python path
                    (e.g. "data_sources.ddm.inflation.sync_engine").
                    function_name_str is the attribute to import from
                    that module (e.g. "sync_all"). The import happens
                    lazily inside the returned route() function — NOT at
                    factory-call time — to avoid import-time circular deps.
        manifest:   the per-source MANIFEST dict (used for the
                    "mode required" / "Unknown mode" error messages and
                    to enumerate available modes).

    Returns:
        route(mode="", **kwargs) -> dict -- the dispatcher function.
    """
    modes = manifest.get("modes", {})
    available_modes = list(modes.keys())

    def route(mode: str = "", **kwargs: Any) -> dict:
        """Dispatch {sub_domain} mode call (sgs pattern: lazy-import + filter kwargs)."""
        if not mode:
            return {
                "status": "error",
                "error": f"mode required. Options: {available_modes}",
            }
        if mode not in modes:
            return {
                "status": "error",
                "error": f"Unknown mode '{mode}'. Available: {available_modes}",
            }

        try:
            module_path, fn_name = mode_map[mode]
            import importlib
            _module = importlib.import_module(module_path)
            _fn = getattr(_module, fn_name)

            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        except FileNotFoundError as e:
            return {"status": "not_synced", "error": str(e)}
        except Exception as e:
            import traceback
            return {
                "status":     "error",
                "sub_domain": sub_domain,
                "mode":       mode,
                "error":      str(e),
                "traceback":  traceback.format_exc(),
            }

    route.__doc__ = (
        f"Dispatch {sub_domain} mode call "
        f"(sgs pattern: lazy-import + filter kwargs)."
    )
    return route
