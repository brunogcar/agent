"""Browser action: screenshot."""
from __future__ import annotations

import base64
import time
from pathlib import Path

from core.config import cfg
from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "screenshot",
    help_text="""screenshot — Capture page or element screenshot.
Required: none
Optional: selector, path, return_base64, timeout, headless, trace_id""",
    examples=[
        'browser(action="screenshot")',
        'browser(action="screenshot", selector="div.chart")',
        'browser(action="screenshot", return_base64=True)',
    ],
)
def _action_screenshot(
    selector: str = "",
    path: str = "",
    timeout: int = 30,
    headless: bool = True,
    return_base64: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Capture a screenshot of the page or a specific element."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            screenshot_dir = cfg.workspace_root / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            if path:
                save_path = Path(path)
            else:
                save_path = screenshot_dir / f"{trace_id or 'notrace'}_{int(time.time())}.png"

            if selector:
                element = _run_browser_async(
                    page.query_selector(selector), timeout=timeout + 5
                )
                if not element:
                    return fail(f"Element not found: {selector}", trace_id=trace_id)
                _run_browser_async(
                    element.screenshot(path=str(save_path)), timeout=timeout + 5
                )
            else:
                _run_browser_async(
                    page.screenshot(path=str(save_path), full_page=True),
                    timeout=timeout + 5,
                )

            result = {"path": str(save_path)}
            if return_base64:
                try:
                    with open(save_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    result["base64"] = b64
                except Exception:
                    pass
            return ok(result, trace_id=trace_id)
    except Exception as e:
        return fail(f"Screenshot failed: {e}", trace_id=trace_id)
