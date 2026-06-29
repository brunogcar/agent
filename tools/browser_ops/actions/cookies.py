"""Browser action: cookies."""
from __future__ import annotations

import json

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "cookies",
    help_text="""cookies — Get, set, or clear browser cookies for the current context.
Required: none
Optional: action_detail, cookies_json, url, trace_id""",
    examples=[
        'browser(action="cookies")',
        'browser(action="cookies", action_detail="get", url="https://example.com")',
        'browser(action="cookies", action_detail="set", cookies_json=\'[{"name":"session","value":"abc","url":"https://example.com"}]\')',
        'browser(action="cookies", action_detail="clear")',
    ],
)
def _action_cookies(
    action_detail: str = "get",
    cookies_json: str = "",
    url: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Get, set, or clear browser cookies for the current context.

    action_detail:
      "get"  — return all cookies (optionally filtered by url).
      "set"  — add cookies from a JSON array (requires name, value, and url or domain+path).
      "clear" — delete all cookies in the current context.
    """
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, True), timeout=35)
            context = page.context

            if action_detail == "get":
                # Optional URL filter: only cookies matching the given URL.
                if url:
                    cookies = _run_browser_async(
                        context.cookies(urls=[url]), timeout=10
                    )
                else:
                    cookies = _run_browser_async(context.cookies(), timeout=10)
                return ok({"cookies": cookies, "count": len(cookies)}, trace_id=trace_id)

            elif action_detail == "set":
                if not cookies_json:
                    return fail(
                        "cookies_json is required for set action", trace_id=trace_id
                    )
                try:
                    cookies = json.loads(cookies_json)
                except (json.JSONDecodeError, TypeError) as e:
                    return fail(f"Invalid cookies JSON: {e}", trace_id=trace_id)

                if not isinstance(cookies, list):
                    return fail(
                        "cookies_json must be a JSON array of cookie objects",
                        trace_id=trace_id,
                    )
                for i, c in enumerate(cookies):
                    if not isinstance(c, dict) or "name" not in c or "value" not in c:
                        return fail(
                            f"Cookie at index {i} missing required 'name' or 'value' field",
                            trace_id=trace_id,
                        )
                    if "url" not in c and ("domain" not in c or "path" not in c):
                        return fail(
                            f"Cookie '{c.get('name', i)}' needs 'url' or 'domain'+'path'",
                            trace_id=trace_id,
                        )
                _run_browser_async(context.add_cookies(cookies), timeout=10)
                return ok({"cookies_set": len(cookies)}, trace_id=trace_id)

            elif action_detail == "clear":
                _run_browser_async(context.clear_cookies(), timeout=10)
                return ok({"cookies_cleared": True}, trace_id=trace_id)

            else:
                return fail(
                    f"Unknown cookies action_detail: {action_detail}", trace_id=trace_id
                )
    except Exception as e:
        return fail(f"Cookies failed: {e}", trace_id=trace_id)
