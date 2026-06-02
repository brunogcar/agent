"""
core/sleep_learn/injector.py
Phase 3: Dynamic Rule Injection.
Retrieves relevant learned rules and injects them into the Planner's context.
"""
from __future__ import annotations
from typing import List, Dict, Any

import chromadb
from core.sleep_learn.config import (
    _SLEEP_LEARN_DB_PATH,
    SLEEP_LEARN_COLLECTION_NAME,
    SLEEP_LEARN_INJECT_ENABLED,
    SLEEP_LEARN_MIN_CONFIDENCE,
    SLEEP_LEARN_MAX_INJECTED_RULES,
)
from core.tracer import tracer

# Connect to the isolated sleep_learn ChromaDB
_client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))

# Safely get the collection (might not exist if Phase 2 hasn't populated it yet)
try:
    _collection = _client.get_collection(name=SLEEP_LEARN_COLLECTION_NAME)
except Exception:
    _collection = None

def get_relevant_rules(query: str, k: int = SLEEP_LEARN_MAX_INJECTED_RULES) -> List[Dict[str, Any]]:
    """
    Queries the procedural_meta collection for rules relevant to the current task.
    Returns a list of rule dictionaries, sorted by relevance (distance).
    """
    if not SLEEP_LEARN_INJECT_ENABLED or _collection is None:
        return []
    if not query or not query.strip():
        return []
    if _collection.count() == 0:
        return []

    try:
        results = _collection.query(
            query_texts=[query],
            n_results=k,
            where={"confidence_score": {"$gte": SLEEP_LEARN_MIN_CONFIDENCE}},
            include=["documents", "metadatas", "distances"]
        )
        
        rules = []
        if results and results['ids'] and results['ids'][0]:
            for i, rule_id in enumerate(results['ids'][0]):
                rules.append({
                    "id": rule_id,
                    "rule": results['documents'][0][i],
                    "confidence": results['metadatas'][0][i].get("confidence_score", 0.0),
                    "distance": results['distances'][0][i] if results.get('distances') else 0.0
                })
        return rules
    except Exception as e:
        tracer.error("daemon", "sleep_learn_injector", f"Failed to query rules: {e}")
        return []

def inject_rules_into_prompt(goal: str, system_prompt: str) -> str:
    """
    Retrieves relevant rules for the goal and appends them to the system prompt.
    If injection is disabled or no rules are found, returns the original prompt.
    """
    if not system_prompt:
        return system_prompt
        
    rules = get_relevant_rules(goal)
    if not rules:
        return system_prompt

    # Format the rules for the LLM
    rules_text = "\n\n--- RELEVANT LEARNED RULES ---\n"
    rules_text += "The following rules were learned from past experiences. Apply them if applicable:\n"
    for i, r in enumerate(rules, 1):
        rules_text += f"{i}. [Confidence: {r['confidence']:.2f}] {r['rule']}\n"
    rules_text += "------------------------------"

    tracer.step(
        "daemon", "sleep_learn_injector", "rules_injected",
        goal_preview=goal[:50],
        rules_count=len(rules),
        rule_ids=[r['id'] for r in rules]
    )

    return system_prompt + rules_text
