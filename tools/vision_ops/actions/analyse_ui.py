"""tools/vision_ops/actions/analyse_ui.py — UI/UX analysis action.

Routes through the vision role with ANALYSE_UI_SYSTEM, which instructs the
model to act as a senior UI/UX designer: identify components, describe layout,
evaluate accessibility, identify UX patterns, assess the design system, list
strengths/issues with severity, and give actionable recommendations.

Use this action when the caller wants a CRITIQUE of an interface (typically
a screenshot of a web app, mobile app, dashboard, or design mockup). For
general description use describe; for OCR use extract_text.
"""
from __future__ import annotations

from core.tracer import tracer
from tools.vision_ops._registry import register_action
from tools.vision_ops.helpers import (
    _check_vision_available,
    _validate_vision_inputs,
    _build_image_block,
    _call_vision,
)
from tools.vision_ops.prompts import (
    ANALYSE_UI_SYSTEM,
    ANALYSE_UI_JSON_SYSTEM,
    FORMAT_SUFFIXES,
    CONTEXT_TYPE_MODIFIERS,
)


@register_action(
    "vision", "analyse_ui",
    help_text="""analyse_ui — UI/UX analysis (components, layout, accessibility, UX patterns).
Required: one of (file_path, base64, url)
Optional: question (focus area), mime_type, json_mode, json_schema, context,
          context_type (screenshot|diagram|photo|document), format (markdown|json|bullet_points), trace_id
Returns: {analysis, model, elapsed, usage, parsed?, trace_id?, duration_ms}""",
    examples=[
        'vision(action="analyse_ui", file_path="dashboard.png")',
        'vision(action="analyse_ui", url="https://example.com/app.jpg", question="Focus on the nav bar")',
        'vision(action="analyse_ui", base64="<b64...>", json_mode=True, context_type="screenshot")',
    ],
)
def _action_analyse_ui(
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
    **kwargs,
) -> dict:
    """UI/UX analysis. Calls vision role with ANALYSE_UI_SYSTEM prompt."""
    # 1. Pre-flight: vision model configured?
    available, err = _check_vision_available()
    if not available:
        if trace_id:
            err["trace_id"] = trace_id
        return err

    # 2. Input validation & SSRF check.
    is_valid, validation_err = _validate_vision_inputs(file_path, base64, url)
    if not is_valid:
        tracer.error(trace_id, "vision", f"Validation failed: {validation_err}")
        return {"status": "error", "error": validation_err, "trace_id": trace_id}

    # 3. Build image content block.
    img_block, block_err = _build_image_block(file_path, base64, url, mime_type)
    if block_err:
        return {"status": "error", "error": block_err, "trace_id": trace_id}

    # 4. Build system prompt.
    use_json = json_mode or bool(json_schema and json_schema.strip())
    system_prompt = (
        ANALYSE_UI_JSON_SYSTEM if use_json else ANALYSE_UI_SYSTEM
    )
    if not use_json:
        system_prompt = (
            system_prompt
            + FORMAT_SUFFIXES.get(format, "")
            + CONTEXT_TYPE_MODIFIERS.get(context_type, "")
        )
    else:
        system_prompt = system_prompt + CONTEXT_TYPE_MODIFIERS.get(context_type, "")

    # 5. Build multimodal user content (text + image).
    user_content: list = []
    if context:
        user_content.append({"type": "text", "text": f"Context: {context}\n\n"})
    user_content.append(img_block)
    if question and question.strip():
        user_content.append({"type": "text", "text": question})
    else:
        user_content.append({"type": "text", "text": "Analyse this UI in detail."})

    # 6. Call vision role.
    try:
        result = _call_vision(
            system=system_prompt,
            user_content=user_content,
            json_mode=json_mode,
            json_schema=json_schema,
            trace_id=trace_id,
        )
    except Exception as e:
        tracer.error(trace_id, "vision", f"LLM call failed: {e}")
        return {"status": "error", "error": f"Vision model call failed: {e}", "trace_id": trace_id}

    if not result.ok:
        return {
            "status": "error",
            "error": result.error,
            "model": result.model,
            "elapsed": result.elapsed,
            "trace_id": trace_id,
        }

    response: dict = {
        "status": "success",
        "action": "analyse_ui",
        "analysis": result.text,
        "model": result.model,
        "elapsed": result.elapsed,
        "usage": result.usage,
    }
    if trace_id:
        response["trace_id"] = trace_id

    if use_json:
        response["parsed"] = result.parsed or {}
        if not result.parsed:
            response["parse_warning"] = "LLM response was not valid JSON. Check response.analysis."

    return response
