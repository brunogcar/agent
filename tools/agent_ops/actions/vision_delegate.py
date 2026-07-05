"""Agent vision action — delegate to tools.vision.vision().

Vision is a special case: it uses a multimodal model, not the text LLM.
All vision parameters are forwarded directly to tools.vision.vision().
"""
from __future__ import annotations

from tools.agent_ops._registry import register_action


HELP_VISION = """
vision_delegate
Delegate image analysis to the vision tool (multimodal model).
Required: task (what to analyze)
Required: context (file_path or public URL to the image)
Optional: content (base64-encoded image string), mime_type, vision_json_mode
Returns: vision tool response
"""


@register_action(
    "agent",
    "vision_delegate",
    help_text=HELP_VISION,
    examples=[
        'agent(action="vision_delegate", task="Describe this image", context="image.png")',
        'agent(action="vision_delegate", task="Extract text", context="https://example.com/img.jpg")',
    ],
)
def run_vision_delegate(
    task: str = "",
    context: str = "",
    content: str = "",
    mime_type: str = "",
    vision_json_mode: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Delegate vision analysis to tools.vision.vision()."""
    try:
        from tools.vision import vision as _vision
    except ImportError:
        return {
            "status": "error",
            "error_code": "MISSING_DEPENDENCY",
            "error": "tools/vision.py not found — ensure it exists and has @tool decorator.",
        }

    file_path = ""
    url = ""
    b64 = ""

    if context:
        if context.startswith(("http://", "https://")):
            url = context
        elif context.startswith("data:"):
            b64 = context
        else:
            file_path = context

    if content and not b64 and not file_path and not url:
        b64 = content

    vision_kwargs: dict = {
        "task": task,
        "file_path": file_path,
        "base64": b64,
        "url": url,
        "trace_id": trace_id,
        # [Bug #13] Forward the caller's context — was hardcoded to "" which
        # prevented passing additional text context (e.g., "What does this
        # diagram show?"). The vision tool accepts context as supplementary
        # text alongside the image.
        "context": context or "",
    }
    if mime_type:
        vision_kwargs["mime_type"] = mime_type
    if vision_json_mode:
        vision_kwargs["json_mode"] = vision_json_mode

    return _vision(**vision_kwargs)
