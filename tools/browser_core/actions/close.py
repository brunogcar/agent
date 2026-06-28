"""Browser action: close."""
from __future__ import annotations

import uuid

from core.contracts import fail, ok

from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock, _contexts, _pages
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "close",
    help_text="""close — Close the browser context for this trace.
Required: none
Optional: trace_id""",
    examples=[
        'browser(action="close")',
        'browser(action="close", trace_id="t1")',
    ],
)
def _action_close(
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Close the browser context for this trace."""
    try:
        with _browser_lock:
            ctx_key = trace_id or f"anon_{uuid.uuid4().hex[:8]}"
            if ctx_key in _pages:
                del _pages[ctx_key]
            if ctx_key in _contexts:
                ctx, _ = _contexts[ctx_key]
                del _contexts[ctx_key]
                _run_browser_async(ctx.close(), timeout=30)
        return ok({"closed": True}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Close failed: {e}", trace_id=trace_id)
