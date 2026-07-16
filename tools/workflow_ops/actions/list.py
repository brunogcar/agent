"""tools/workflow_ops/actions/list.py — The `list` action. (v1.1: renamed from list_workflows.py)

Returns metadata for all available workflow types. Useful for the LLM to
discover what workflows exist without reading docs.

Implementation:
  Calls _get_all_workflow_metadata() which lazily imports each workflow
  module's graph.py and reads its WORKFLOW_METADATA attribute. Broken
  modules show up as {"name": <type>, "error": "metadata not available"}.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops._type_registry import TYPE_DISPATCH
from tools.workflow_ops.helpers import _get_all_workflow_metadata


@register_action(
    "workflow", "list",
    help_text="""list — List all available workflows with metadata.
No params required.
Returns: {status, workflows: {<type>: {name, version, description, entry_point}|{error}}, count, trace_id}""",
    examples=[
        'workflow(action="list")',
    ],
)
def _action_list(trace_id: str = "", **kwargs) -> dict:
    """List all available workflows with their metadata."""
    metadata = _get_all_workflow_metadata()

    # Augment with types that exist in TYPE_DISPATCH but not in the static
    # _WORKFLOW_MODULES map (e.g. "auto", which is a router pseudo-type).
    for type_name, info in TYPE_DISPATCH.items():
        if type_name not in metadata:
            metadata[type_name] = {
                "name": type_name,
                "description": info.get("help", ""),
                "version": "?",
                "entry_point": "",
            }

    return {
        "status": "success",
        "workflows": metadata,
        "count": len(metadata),
        "trace_id": trace_id,
    }
