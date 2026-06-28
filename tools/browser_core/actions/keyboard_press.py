"""Browser action: keyboard_press."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "keyboard_press",
    help_text="""keyboard_press — Press a keyboard key (Enter, Tab, Escape, etc.).
Required: key
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="keyboard_press", key="Enter")',
    ],
)
def _action_keyboard_press(
    key: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Press a keyboard key (Enter, Tab, Escape, etc.)."""
    if not key:
        return fail("key is required for keyboard_press action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(page.keyboard.press(key), timeout=timeout + 5)
        return ok({"pressed": key}, trace_id=trace_id)
    except Exception as e:
        return fail(f"keyboard_press failed: {e}", trace_id=trace_id)
