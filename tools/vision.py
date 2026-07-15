"""tools/vision.py — Vision meta-tool (v1.0).

Thin @tool facade. Routes all vision actions to handlers in
vision_ops/actions/ via the DISPATCH dict. Auto-discovered by
registry.py via the @tool decorator.

v1.0 changes (the @meta_tool refactor):
  - Now a meta-tool with 3 actions: describe | extract_text | analyse_ui.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - BREAKING: the old `task` parameter is replaced by `action` + `question`.
    A deprecated `task` alias is kept for backward compat with
    tools/agent_ops/actions/vision_delegate.py — if `action` is empty AND
    `task` is non-empty, it's treated as `action="describe"` + `question=task`.
    A deprecation warning is logged.
  - New params: trace_id (observability), format (markdown|json|bullet_points),
    context_type (screenshot|diagram|photo|document|""), json_schema
    (structured output via llm.call(json_schema=...)).
  - All implementation logic moved to vision_ops/ subpackage.

NOT parallel-safe (uses LLM calls) — do NOT add to PARALLEL_SAFE.
The router already routes to `vision` for image-analysis intents; no
router changes needed for v1.0.

[core/net adoption]:
  - _download_image_to_data_uri() in vision_ops/helpers.py now wraps
    httpx.Client.get() in retry_sync() from core/net/retry.py with
    is_retryable_error() classification. RETRY_BASE_DELAY and
    RETRY_MAX_DELAY come from core/net/default.py.
"""
from __future__ import annotations

import logging
import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import vision_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import vision_ops  # noqa: F401
from tools.vision_ops._registry import DISPATCH

logger = logging.getLogger(__name__)


@tool
@meta_tool(
    DISPATCH.get("vision", {}),
    doc_sections=[
        "VISION TOOL — Multimodal image analysis:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | General image description | vision(describe) | Overview, elements, text, colors, details |",
        " | Extract visible text (OCR) | vision(extract_text) | All readable text, preserve reading order |",
        " | UI/UX analysis | vision(analyse_ui) | Components, layout, accessibility, UX patterns |",
        "",
        "PARAMETERS:",
        " - action (required) — describe | extract_text | analyse_ui.",
        " - question (optional) — specific focus area; defaults to the action's default instruction.",
        " - Provide exactly ONE image source: file_path, base64, or url.",
        " - mime_type (default image/jpeg) — used for base64 sources; ignored for files (extension-based) and URLs (content-type based).",
        " - json_mode (default False) — request JSON output; pairs with the action's JSON prompt variant.",
        " - json_schema (default '') — JSON schema string for structured output (passed to llm.call as json_schema).",
        " - context (default '') — supplementary text shown to the model alongside the image.",
        " - context_type (default '') — screenshot | diagram | photo | document; appends a context-specific modifier to the system prompt.",
        " - format (default markdown) — markdown | json | bullet_points; appends a format instruction to the system prompt (ignored when json_mode/json_schema is set).",
        " - trace_id (optional) — forwarded to llm.call for observability threading.",
        "",
        "DEPRECATED: the `task` parameter is kept as a backward-compat alias.",
        "If `action` is empty AND `task` is non-empty, the call is treated as",
        "action='describe' + question=task. A deprecation warning is logged.",
        "",
        "NOT parallel-safe — uses LLM calls. Kill switch: empty VISION_MODEL in .env.",
    ],
)
def vision(
    action: str = "",
    question: str = "",
    file_path: str = "",
    base64: str = "",
    url: str = "",
    mime_type: str = "image/jpeg",
    json_mode: bool = False,
    json_schema: str = "",
    context: str = "",
    context_type: str = "",
    format: str = "markdown",
    trace_id: str = "",
    task: str = "",
) -> dict:
    """Vision meta-tool — describe | extract_text | analyse_ui.

    Multimodal image analysis via the configured vision model
    (cfg.vision_model). Routes actions to vision_ops/actions/ handlers.

    Args:
        action: Which action to perform. Auto-restricted by @meta_tool to
                the registered action names.
        question: Optional focus question for the model. Defaults to the
                  action's default instruction when empty.
        file_path: Local path to an image file (jpg/jpeg/png/webp/gif/bmp).
        base64: Base64-encoded image data (with or without data: prefix).
        url: Public HTTP(S) URL to an image. SSRF-protected.
        mime_type: MIME type override for base64 sources.
        json_mode: Request JSON-formatted output.
        json_schema: JSON schema string for structured output validation.
        context: Supplementary text shown to the model alongside the image.
        context_type: Image kind modifier (screenshot/diagram/photo/document).
        format: Output format modifier (markdown/json/bullet_points).
        trace_id: Observability threading ID.
        task: DEPRECATED. Backward-compat alias for question when action
              is empty. Mapped to action="describe" + question=task.

    Returns:
        Dict with status="success" or status="error" (or status="disabled"
        when VISION_MODEL is not set). See action handlers for per-action
        response shapes.
    """
    # Backward-compat: legacy `task` parameter → action="describe" + question=task.
    if not action and task and task.strip():
        logger.warning(
            "[vision] DEPRECATED: `task` parameter used. "
            "Use `action='describe' + question=...` instead. "
            "Mapping task=%r → action='describe', question=%r. "
            "The `task` alias will be removed in v2.0.",
            task, task,
        )
        tracer.warning(
            trace_id, "vision", "Deprecated `task` parameter used (mapped to action=describe)",
            deprecated_param="task", mapped_action="describe", task_preview=task[:100],
        )
        action = "describe"
        if not question:
            question = task

    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "vision", f"action={action}")

    if not action:
        return {
            "status": "error",
            "error": "action is required (describe | extract_text | analyse_ui)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("vision", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Use: {valid_actions}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]

    kwargs = {
        "question": question,
        "file_path": file_path,
        "base64": base64,
        "url": url,
        "mime_type": mime_type,
        "json_mode": json_mode,
        "json_schema": json_schema,
        "context": context,
        "context_type": context_type,
        "format": format,
        "trace_id": trace_id,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Vision action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error",
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    if result.get("status") == "error":
        tracer.step(trace_id, "vision", f"action={action}:failed")
    else:
        tracer.step(trace_id, "vision", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
