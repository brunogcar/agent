"""
core/sleep_learn/injector.py
Phase 3: Dynamic Rule Injection.
Retrieves relevant learned rules and injects them into the Planner's context.

[v1.2 #7] Symbol offloading — when > 5 rules are injected, offload the full
rule texts to a per-trace file. The injected prompt gets the standard
formatted rules + a note pointing to the symbol file for drill-down. This
keeps the LLM context bounded when many rules match.
"""
from __future__ import annotations
import json
import threading
from typing import List, Dict, Any

import chromadb
from core.sleep_learn.config import (
    _SLEEP_LEARN_DB_PATH,
    SLEEP_LEARN_COLLECTION_NAME,
    SLEEP_LEARN_INJECT_ENABLED,
    SLEEP_LEARN_MIN_CONFIDENCE,
    SLEEP_LEARN_MAX_INJECTED_RULES,
    SLEEP_LEARN_UNIFIED,
)
from core.tracer import tracer, generate_trace_id
from core.config import cfg
from core.symbol_offload import offload_to_file

# Lazy-initialized ChromaDB client (avoid import-time side effects)
_client = None
_collection = None
_init_lock = threading.Lock()

def _ensure_client():
    """Lazy init: create ChromaDB client and collection on first use."""
    global _client, _collection
    if _client is not None:
        return
    with _init_lock:
        if _client is not None:
            return
        _client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
        try:
            _collection = _client.get_collection(name=SLEEP_LEARN_COLLECTION_NAME)
        except Exception:
            _collection = None

def get_relevant_rules(query: str, k: int = SLEEP_LEARN_MAX_INJECTED_RULES) -> List[Dict[str, Any]]:
    """
    Queries the procedural_meta collection for rules relevant to the current task.
    Returns a list of rule dictionaries, sorted by relevance (distance).
    """
    _ensure_client()
    col = _collection  # snapshot: avoids TOCTOU if _collection ever reset
    if not SLEEP_LEARN_INJECT_ENABLED or col is None:
        return []
    if not query or not query.strip():
        return []
    if col.count() == 0:
        return []

    rules = []

    # v1.0 (Commit 4): Split-brain fallback replaced with unified read.
    # When SLEEP_LEARN_UNIFIED=true (default), ONLY the main `procedural`
    # collection is queried. When false (legacy), the old `procedural_meta`
    # collection is queried first for backward compat.
    if not SLEEP_LEARN_UNIFIED:
        try:
            results = col.query(
                query_texts=[query],
                n_results=k,
                where={"confidence": {"$gte": SLEEP_LEARN_MIN_CONFIDENCE}},  # v1.0: unified schema field
                include=["documents", "metadatas", "distances"]
            )
            
            if results and results['ids'] and results['ids'][0]:
                for i, rule_id in enumerate(results['ids'][0]):
                    meta = results['metadatas'][0][i]
                    rules.append({
                        "id": rule_id,
                        "rule": results['documents'][0][i],
                        "confidence": meta.get("confidence", meta.get("confidence_score", 0.0)),
                        "distance": results['distances'][0][i] if results.get('distances') else 0.0,
                        "reasoning": meta.get("reasoning", ""),  # v1.0: include why the rule was learned
                        "source": meta.get("source", "sleep_learn"),
                    })
        except Exception as e:
            tracer.error(generate_trace_id(), "sleep_learn_injector", f"Failed to query rules: {e}")
    
    seen_ids = {r["id"] for r in rules}
    try:
        from core.memory_engine import memory
        main_results = memory.recall(
            query=query,
            collections=["procedural"],
            top_k=k,
            min_score=0.0
        )
        for ex in main_results:
            if ex.get("text"):
                rule_id = ex.get("id", ex.get("text", "")[:30])
                if rule_id not in seen_ids:
                    seen_ids.add(rule_id)
                    ex_meta = ex.get("metadata", {})
                    # v1.0: Use unified schema field 'confidence' (was 'importance' clamped)
                    confidence = ex_meta.get("confidence", 0.5)
                    rules.append({
                        "id": rule_id,
                        "rule": ex["text"],
                        "confidence": confidence,
                        "distance": ex.get("distance", 0.5),
                        "reasoning": ex_meta.get("reasoning", ""),
                        "source": ex_meta.get("source", "meta_learner"),
                    })
    except Exception:
        pass  # Non-fatal: main memory may not be available
    
    return rules

def inject_rules_into_prompt(goal: str, system_prompt: str, trace_id: str = "") -> str:
    """
    Retrieves relevant rules for the goal and appends them to the system prompt.
    If injection is disabled or no rules are found, returns the original prompt.

    [v1.2 #7] When > 5 rules are injected, offloads the full rule list to a
    per-trace symbol file. The injected prompt keeps the formatted rules and
    appends a note pointing to the symbol file for drill-down.
    """
    if not system_prompt:
        return system_prompt
        
    rules = get_relevant_rules(goal)
    if not rules:
        return system_prompt

    # v1.0: Retrieval ranking formula — sort by combined score:
    #   rank_score = similarity * (importance/10)  [or similarity * confidence]
    # This ensures high-similarity + high-confidence rules appear first.
    # (minimax's point: the ranking formula must be defined, not undefined)
    def _rank_score(r):
        similarity = max(0.0, 1.0 - r.get("distance", 0.5))  # distance → similarity
        confidence = r.get("confidence", 0.5)
        return similarity * confidence
    
    rules.sort(key=_rank_score, reverse=True)

    # [v1.2 #7] Offload full rule texts when there are many rules.
    # The injected prompt gets compact summaries; full text is available via
    # the symbol file for drill-down.
    symbol_ref = None
    if len(rules) > 5:
        symbol_ref = offload_to_file(
            trace_id or "sleep_learn",
            "injected_rules",
            rules,
            summary=f"{len(rules)} rules (showing summaries, full text in file)",
        )

    # Format the rules for the LLM — v1.0: include reasoning when available
    rules_text = "\n\n--- RELEVANT LEARNED RULES ---\n"
    rules_text += "The following rules were learned from past experiences. Apply them if applicable:\n"
    for i, r in enumerate(rules, 1):
        rules_text += f"{i}. [Confidence: {r['confidence']:.2f}] {r['rule']}"
        if r.get("reasoning"):
            rules_text += f"\n   Reason: {r['reasoning'][:200]}"
        rules_text += "\n"
    rules_text += "------------------------------"

    if symbol_ref:
        rules_text += f"\n\n[Full rule texts: {symbol_ref['_symbol_file']}]"

    tracer.step(
        trace_id or generate_trace_id(), "sleep_learn_injector", "rules_injected",
        goal_preview=goal[:50],
        rules_count=len(rules),
        rule_ids=[r["id"] for r in rules]
    )

    # Log injection for the Feedback Loop (Path 2)
    if trace_id:
        log_file = cfg.sleep_learn_log_path / "injections.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"trace_id": trace_id, "rule_ids": [r['id'] for r in rules]}) + "\n")

    return system_prompt + rules_text
