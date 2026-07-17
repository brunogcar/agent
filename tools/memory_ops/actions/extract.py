"""tools/memory_ops/actions/extract.py — L1 Atomic Fact Extraction action. [NEW v1.5]

Extracts atomic facts from episodic memories using a router-tier LLM.
Stores in the `atomic` collection (TencentDB L1 layer).

Usage:
  memory(action="extract", text="The autocode workflow runs pytest and commits on success.")
  memory(action="extract", text="...", id="episodic_id_123")  # link to source
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.memory_ops._registry import register_action


@register_action(
    "memory", "extract",
    help_text="""extract — Extract atomic facts from text using a router-tier LLM (v1.5).
Required: text (the episodic memory text to extract facts from)
Optional: id (source episodic ID for provenance tracking), trace_id
Returns: {action_status: "extracted", extracted, stored, skipped_duplicates, errors}

Uses the router-tier LLM (cheap, fast). Facts are stored in the `atomic` collection
with type (config/behavior/dependency/observation) + confidence. Dedup by similarity.""",
    examples=[
        'memory(action="extract", text="The autocode workflow runs pytest and commits on success.")',
    ],
)
def run_extract(
    text: str = "",
    id: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract atomic facts from text and store in the atomic collection."""
    if not text or not text.strip():
        return fail("text is required for extract", trace_id=trace_id, error_code="MISSING_PARAM")

    try:
        from core.memory_backend.atomic_extract import extract_and_store_facts
        result = extract_and_store_facts(
            episodic_text=text,
            episodic_id=id,
            trace_id=trace_id,
        )
    except Exception as e:
        return fail(f"Extraction failed: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    return ok({
        "action_status": "extracted",
        "action": "extract",
        **result,
        "trace_id": trace_id,
    }, trace_id=trace_id)
