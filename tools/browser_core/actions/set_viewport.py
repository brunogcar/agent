"""Browser action: set_viewport."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "set_viewport",
    help_text="""set_viewport — Change browser viewport size for responsive testing.
Required: none
Optional: width, height, trace_id""",
    examples=[
        'browser(action="set_viewport", width=1920, height=1080)',
        'browser(action="set_viewport", width=375, height=812)',
    ],
)
def _action_set_viewport(
    width: int = 1280,
    height: int = 720,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Change browser viewport size."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, True), timeout=35)
            _run_browser_async(
                page.set_viewport_size({"width": width, "height": height}),
                timeout=10,
            )
        return ok({"viewport_set": True, "width": width, "height": height}, trace_id=trace_id)
    except Exception as e:
        return fail(f"set_viewport failed: {e}", trace_id=trace_id)
