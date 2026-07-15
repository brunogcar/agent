"""tools/vision_ops/actions/describe.py — General image description action.

Preserves the original tools/vision.py behavior (single multimodal LLM call
to the vision role with the _VISION_SYSTEM prompt) but routes through the
vision_ops subpackage so the facade can dispatch via @meta_tool.

New v1.0 capabilities vs. the legacy vision(task="Describe this image"):
  - action: explicit "describe" (vs. free-text task).
  - question: optional focus question (default "" — the system prompt
    handles the instruction).
  - json_mode / json_schema: structured output via JSON variants of the
    system prompt + llm.call(json_schema=...) forwarding.
  - format: markdown (default) | json | bullet_points — appends a format
    suffix to the base system prompt.
  - context_type: screenshot | diagram | photo | document | "" — appends a
    context-type modifier to the system prompt.
  - trace_id: forwarded to llm.call for observability threading.
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
    DESCRIBE_SYSTEM,
    DESCRIBE_JSON_SYSTEM,
    FORMAT_SUFFIXES,
    CONTEXT_TYPE_MODIFIERS,
)


@register_action(
    "vision", "describe",
    help_text="""describe — General image description (default action).
Required: one of (file_path, base64, url)
Optional: question (focus area), mime_type, json_mode, json_schema, context,
          context_type (screenshot|diagram|photo|document), format (markdown|json|bullet_points), trace_id
Returns: {description, model, elapsed, usage, parsed?, trace_id?, duration_ms}""",
    examples=[
        'vision(action="describe", file_path="screenshot.png")',
        'vision(action="describe", url="https://example.com/img.jpg", question="Focus on colors")',
        'vision(action="describe", base64="<b64...>", json_mode=True, context_type="photo")',
    ],
)
def _action_describe(
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
    """General image description. Calls vision role with DESCRIBE_SYSTEM prompt.

    When json_mode=True or json_schema is non-empty, the DESCRIBE_JSON_SYSTEM
    variant is used (it specifies the exact JSON shape and tells the model
    to output JSON only — no markdown fences).
    """
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

    # 4. Build system prompt: JSON variant if json_mode/json_schema, else base + format suffix.
    use_json = json_mode or bool(json_schema and json_schema.strip())
    system_prompt = (
        DESCRIBE_JSON_SYSTEM if use_json else DESCRIBE_SYSTEM
    )
    if not use_json:
        system_prompt = (
            system_prompt
            + FORMAT_SUFFIXES.get(format, "")
            + CONTEXT_TYPE_MODIFIERS.get(context_type, "")
        )
    else:
        # JSON variant: still append context-type modifier (orthogonal to json_mode).
        system_prompt = system_prompt + CONTEXT_TYPE_MODIFIERS.get(context_type, "")

    # 5. Build multimodal user content (text + image).
    user_content: list = []
    if context:
        user_content.append({"type": "text", "text": f"Context: {context}\n\n"})
    user_content.append(img_block)
    # question defaults to "" — the system prompt alone handles the instruction.
    if question and question.strip():
        user_content.append({"type": "text", "text": question})
    else:
        user_content.append({"type": "text", "text": "Describe this image in detail."})

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
        "action": "describe",
        "description": result.text,
        "model": result.model,
        "elapsed": result.elapsed,
        "usage": result.usage,
    }
    if trace_id:
        response["trace_id"] = trace_id

    if use_json:
        response["parsed"] = result.parsed or {}
        if not result.parsed:
            response["parse_warning"] = "LLM response was not valid JSON. Check response.description."

    return response
