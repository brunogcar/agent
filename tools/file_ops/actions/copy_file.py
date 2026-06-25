"""Copy file action handler."""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "copy_file",
    help_text="""Copy a file or directory. Both source and destination must be within allowed roots.
Required: source, destination
Optional: force (default False) — overwrite if destination exists
Returns: {source, destination}""",
    examples=[
        'file(action="copy_file", source="old.txt", destination="new.txt")',
        'file(action="copy_file", source="tmp/a", destination="tmp/b", force=True)',
    ],
)
def _handle_copy_file(
    source: str = "",
    destination: str = "",
    force: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Copy a file or directory."""
    if not source:
        return {"status": "error", "error": "source is required for copy_file"}
    if not destination:
        return {"status": "error", "error": "destination is required for copy_file"}

    src, err = _safe_resolve(source)
    if err:
        return {"status": "error", "error": err}
    if not src.exists():
        return {"status": "error", "error": f"Source not found: {src}"}

    dst, err = _safe_resolve(destination)
    if err:
        return {"status": "error", "error": err}

    if dst.exists() and not force:
        return {"status": "error", "error": f"Destination already exists: {dst}. Use force=True to overwrite."}

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists() and force:
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {
            "status": "success",
            "source": str(src),
            "destination": str(dst),
        }
    except Exception as e:
        return {"status": "error", "error": f"Copy failed: {e}"}
