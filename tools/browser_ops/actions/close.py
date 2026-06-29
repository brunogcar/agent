"""Browser action: close."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock, _contexts, _pages
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "close",
    help_text="""close — Close the browser context for this trace.
Required: trace_id
Optional: none""",
    examples=[
        'browser(action="close", trace_id="t1")',
    ],
)
def _action_close(
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Close the browser context for this trace.

    trace_id is REQUIRED. Calling close without a trace_id is an error
    because the anonymous key generated at creation time (anon_* UUID)
    cannot be deterministically reconstructed.

    Returns closed: True if a context was found and closed.
    Returns closed: False if no context was found (already closed or never created).
    """
    if not trace_id:
        return fail(
            "trace_id is required for close action — cannot close an anonymous context",
            trace_id=trace_id,
        )

    try:
        with _browser_lock:
            found = False
            if trace_id in _pages:
                del _pages[trace_id]
                found = True
            if trace_id in _contexts:
                ctx, _ = _contexts[trace_id]
                del _contexts[trace_id]
                _run_browser_async(ctx.close(), timeout=30)
                found = True
            if found:
                return ok({"closed": True}, trace_id=trace_id)
            return ok(
                {"closed": False, "reason": "context not found (already closed or never created)"},
                trace_id=trace_id,
            )
    except Exception as e:
        return fail(f"Close failed: {e}", trace_id=trace_id)
