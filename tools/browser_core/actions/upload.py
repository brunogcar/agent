"""Browser action: upload."""
from __future__ import annotations

from pathlib import Path

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "upload",
    help_text="""upload — Upload file(s) to a <input type="file"> element.
Required: selector, path
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="upload", selector="input[type=file]", path="data/report.pdf")',
        'browser(action="upload", selector="#avatar", path="photo.png")',
    ],
)
def _action_upload(
    selector: str = "",
    path: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Upload a file to a file input element.

    Playwright's set_input_files bypasses the native file chooser dialog
    by directly injecting the file path into the <input type="file"> DOM node.
    The file must exist on the local filesystem.
    """
    if not selector:
        return fail("selector is required for upload action", trace_id=trace_id)
    if not path:
        return fail("path is required for upload action", trace_id=trace_id)

    file_path = Path(path)
    if not file_path.exists():
        return fail(f"File not found: {path}", trace_id=trace_id)
    if not file_path.is_file():
        return fail(f"Path is not a file: {path}", trace_id=trace_id)

    try:
        with _browser_lock:
            page = _run_browser_async(
                _get_page(trace_id, headless), timeout=timeout + 5
            )
            _run_browser_async(
                page.set_input_files(selector, str(file_path)),
                timeout=timeout + 5,
            )
            return ok(
                {
                    "uploaded": True,
                    "selector": selector,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                },
                trace_id=trace_id,
            )
    except Exception as e:
        return fail(f"Upload failed: {e}", trace_id=trace_id)
