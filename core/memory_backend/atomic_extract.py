"""core/memory_backend/atomic_extract.py — L1 Atomic Fact Extraction (v1.3).

TencentDB-shaped: extracts atomic facts from episodic entries using a
router-tier LLM (cheap, fast). Stores in the `atomic` collection.

L0 (raw conversation) → L1 (atomic facts) → L2 (procedural rules) → L3 (persona)
This module implements L1. The procedural distiller (sleep_learn/meta_learning)
is L2. L0 and L3 are deferred.

Design (from collective review):
- Router-tier LLM (cheap, fast — 4k context, 15s timeout)
- json_schema enforced: {facts: [{fact, type, confidence}]}
- Dedup: similarity search before insert (same pattern as meta_learning)
- Batch: extract from N episodic entries in one call
- Trigger: called from the memory tool's `extract` action (LLM-initiated)
  OR from a background daemon (future — not in this commit)
"""
from __future__ import annotations

import json
import time
from typing import Any

from core.tracer import tracer
from core.memory_backend.constants import COLLECTION_ATOMIC


# JSON schema for the LLM output
_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "type": {"type": "string", "enum": ["config", "behavior", "dependency", "observation"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["fact", "type", "confidence"],
            },
        },
    },
    "required": ["facts"],
}

_SYSTEM_PROMPT = (
    "You are an atomic fact extractor. Given an episodic memory (a description of "
    "a completed task or event), extract discrete, self-contained atomic facts.\n\n"
    "Rules:\n"
    "1. Each fact must be a single, self-contained statement (no pronouns, no context needed).\n"
    "2. Categorize each fact: config (settings, paths, ports), behavior (how something works), "
    "dependency (requires X), observation (a finding).\n"
    "3. Only extract facts that are USEFUL for future tasks — skip trivial details.\n"
    "4. Assign confidence: 1.0 for explicit facts, 0.7 for inferred, 0.5 for uncertain.\n"
    "5. Return JSON: {facts: [{fact, type, confidence}]}\n"
    "6. Maximum 10 facts per episodic entry."
)


def extract_facts_from_episodic(
    episodic_text: str,
    episodic_id: str = "",
    trace_id: str = "",
) -> list[dict]:
    """Extract atomic facts from a single episodic memory text.
    
    Uses the router-tier LLM (cheap, fast). Returns a list of fact dicts:
        {"fact": str, "type": str, "confidence": float, "source_episodic_id": str}
    
    Returns empty list if the LLM call fails or produces no facts.
    """
    if not episodic_text or not episodic_text.strip():
        return []

    from core.llm import llm

    tid = trace_id or f"atomic_extract_{int(time.time())}"
    tracer.step(tid, "atomic_extract", "extraction_started", episodic_id=episodic_id)

    result = llm.complete(
        role="router",  # cheap, fast tier
        system=_SYSTEM_PROMPT,
        user=f"Extract atomic facts from this episodic memory:\n\n{episodic_text[:4000]}",
        json_schema=_EXTRACT_SCHEMA,
        trace_id=tid,
        timeout=15,  # router-tier: 15s
        max_tokens=512,
    )

    if not result.ok:
        tracer.error(tid, "atomic_extract", f"LLM call failed: {result.error}")
        return []

    parsed = result.parsed
    if not parsed or not isinstance(parsed, dict) or "facts" not in parsed:
        tracer.warning(tid, "atomic_extract", "No facts in LLM response")
        return []

    facts = []
    for f in parsed.get("facts", [])[:10]:  # cap at 10
        fact_text = f.get("fact", "").strip()
        if not fact_text:
            continue
        facts.append({
            "fact": fact_text,
            "type": f.get("type", "observation"),
            "confidence": float(f.get("confidence", 0.7)),
            "source_episodic_id": episodic_id,
        })

    tracer.step(tid, "atomic_extract", f"Extracted {len(facts)} facts", episodic_id=episodic_id)
    return facts


def extract_and_store_facts(
    episodic_text: str,
    episodic_id: str = "",
    trace_id: str = "",
) -> dict:
    """Extract atomic facts from episodic text and store them in the `atomic` collection.
    
    Returns: {"extracted": int, "stored": int, "skipped_duplicates": int, "errors": int}
    """
    from core.memory_engine import memory

    stats = {"extracted": 0, "stored": 0, "skipped_duplicates": 0, "errors": 0}
    tid = trace_id or f"atomic_store_{int(time.time())}"

    facts = extract_facts_from_episodic(episodic_text, episodic_id, tid)
    stats["extracted"] = len(facts)

    if not facts:
        return stats

    for fact in facts:
        try:
            # Dedup: check if a similar fact already exists
            existing = memory.recall(
                query=fact["fact"],
                collections=[COLLECTION_ATOMIC],
                top_k=1,
                min_score=0.0,
            )
            if existing and existing[0].get("score", 0) > 0.92:
                stats["skipped_duplicates"] += 1
                continue

            # Store the fact
            memory.store(
                text=fact["fact"],
                memory_type="atomic",
                importance=max(1, round(fact["confidence"] * 10)),
                tags=f"source:atomic_extract,type:{fact['type']}",
                trace_id=tid,
                source="atomic_extractor",
                source_doc_id=episodic_id or "",
            )
            stats["stored"] += 1
        except Exception as e:
            tracer.error(tid, "atomic_extract", f"Store failed for fact: {e}")
            stats["errors"] += 1

    tracer.step(tid, "atomic_extract", f"Stored {stats['stored']} facts", stats=stats)
    return stats
