"""Browser action: cookies."""
from __future__ import annotations

import json

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "cookies",
    help_text="""cookies — Get, set, or clear browser cookies for the current context.
Required: none
Optional: action_detail, cookies_json, trace_id""",
    examples=[
        'browser(action="cookies")',
        'browser(action="cookies", action_detail="set", cookies_json=\'[{"name":"session","value":"abc","url":"https://example.com"}]\')',
        'browser(action="cookies", action_detail="clear")',
    ],
)
def _action_cookies(
    action_detail: str = "get",
    cookies_json: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Get, set, or clear browser cookies for the current context."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, True), timeout=35)
            context = page.context
            if action_detail == "get":
                cookies = _run_browser_async(context.cookies(), timeout=10)
                return ok({"cookies": cookies, "count": len(cookies)}, trace_id=trace_id)
            elif action_detail == "set":
                cookies = json.loads(cookies_json) if cookies_json else []
                _run_browser_async(context.add_cookies(cookies), timeout=10)
                return ok({"cookies_set": len(cookies)}, trace_id=trace_id)
            elif action_detail == "clear":
                _run_browser_async(context.clear_cookies(), timeout=10)
                return ok({"cookies_cleared": True}, trace_id=trace_id)
            else:
                return fail(f"Unknown cookies action_detail: {action_detail}", trace_id=trace_id)
    except Exception as e:
        return fail(f"Cookies failed: {e}", trace_id=trace_id)
