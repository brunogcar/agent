"""tools/workflow_ops/actions/templates.py — The `templates` action.

Lists available workflow templates from tools/workflow_ops/templates/.
Templates are pre-configured parameter sets for common tasks (bug-fix,
refactor, index-codebase, index-quick). They reduce call-site verbosity:
instead of `workflow(action="run", type="autocode", mode="fix_error",
goal="Fix the bug...", target_file=..., error_msg=...)`, the caller can do
`workflow(action="run", template="bug-fix", target_file=..., error_msg=...)`.

[DESIGN] Why list templates as a separate action?
  The `list` action returns workflow TYPES (research, data, autocode, ...).
  Templates are a different axis — pre-set PARAMETER BUNDLES for specific
  use cases. A separate action keeps the two concepts from polluting each
  other's response shape.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action


@register_action(
    "workflow", "templates",
    help_text="""templates — List available workflow templates.
No params required.
Returns: {status, templates: [{name, type, description, params, required, _source_file}], count}""",
    examples=[
        'workflow(action="templates")',
    ],
)
def _action_templates(trace_id: str = "", **kwargs) -> dict:
    """List available workflow templates from tools/workflow_ops/templates/."""
    try:
        from tools.workflow_ops.templates._registry import list_templates
    except ImportError as e:
        return {
            "status": "error",
            "error": f"Templates module unavailable: {e}",
            "trace_id": trace_id,
        }

    try:
        templates = list_templates()
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to list templates: {e}",
            "trace_id": trace_id,
        }

    # Strip the internal _source_file key from the public response — it's
    # for debugging, not for the LLM/operator.
    public_templates = [
        {
            "name": t.get("name", ""),
            "type": t.get("type", ""),
            "description": t.get("description", ""),
            "params": t.get("params", {}),
            "required": t.get("required", []),
        }
        for t in templates
    ]

    return {
        "status": "success",
        "templates": public_templates,
        "count": len(public_templates),
        "trace_id": trace_id,
    }
