"""
core/context_budget.py — Dynamic Cognitive Context Budgeting.
Manages the flow of information into the LLM context window to prevent
OOM crashes and attention dilution.

Architecture:
1. ContextClass Enum: Categorizes messages by cognitive priority.
2. Scoring: Role-Based LIFO + Technical Fingerprinting (Tracebacks/JSON).
3. Budgeting: Greedily selects high-priority messages to fit the token budget.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from core.config import cfg

logger = logging.getLogger(__name__)

# Estimated chars per token (conservative for mixed code/text)
CHARS_PER_TOKEN = 4 

class ContextClass(Enum):
    """Cognitive priority tiers for context assembly."""
    SYSTEM = 0      # Never evict (Rules, Persona)
    USER = 1        # Never evict (Current Intent)
    ERROR = 2       # Critical (Tracebacks, Failures) - Must outrank procedural for debugging
    PROCEDURAL = 3  # High (Recalled Rules)
    RECENT = 4      # Medium (Last N turns)
    OUTPUT = 5      # Low (Tool outputs, Search results)
    ARCHIVE = 6     # Evict First (Old history)

def estimate_tokens(text: str) -> int:
    """Fast heuristic token estimation."""
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN

def _classify_message(msg: dict) -> ContextClass:
    """Deterministically classify a message based on role and content."""
    role = msg.get("role", "")
    content = msg.get("content", "")
    
    if role == "system":
        return ContextClass.SYSTEM
    if role == "user":
        return ContextClass.USER
        
    # Fingerprinting for high-value assistant/tool messages
    content_lower = content.lower()
    if "traceback" in content_lower or "exception" in content_lower or "error:" in content_lower:
        return ContextClass.ERROR
    if "procedural" in content_lower or "rule:" in content_lower:
        return ContextClass.PROCEDURAL
        
    if role == "tool":
        return ContextClass.OUTPUT
        
    return ContextClass.RECENT

def _score_message(msg: dict, index: int, total: int) -> float:
    """
    Score a message for retention. Higher = Keep.
    Formula: (Tier Weight) + (Recency Bonus) + (Fingerprint Bonus)
    """
    cls = _classify_message(msg)
    
    # 1. Tier Weight (Dominant factor)
    # SYSTEM/USER get massive score to ensure they are never dropped.
    tier_weights = {
        ContextClass.SYSTEM: 1000.0,
        ContextClass.USER: 1000.0,
        ContextClass.PROCEDURAL: 50.0,
        ContextClass.ERROR: 40.0,
        ContextClass.RECENT: 20.0,
        ContextClass.OUTPUT: 10.0,
        ContextClass.ARCHIVE: 1.0,
    }
    score = tier_weights.get(cls, 10.0)
    
    # 2. Recency Bonus (0.0 to 10.0)
    # Newer messages (higher index) get more points.
    if total > 0:
        recency = (index / total) * 10.0
        score += recency
        
    # 3. Fingerprint Bonus
    content = msg.get("content", "")
    if "```json" in content or "```python" in content:
        score += 5.0  # Code blocks are usually high signal
        
    return score

def budget_messages(messages: list[dict], max_tokens: int) -> list[dict]:
    """
    Assemble the optimal context window within the token budget.
    1. Scores all messages.
    2. Selects the highest scoring subset that fits.
    3. Re-sorts chronologically to preserve conversation flow.
    """
    if not messages:
        return messages
        
    # Reserve ~20% for output generation safety margin
    input_budget = int(max_tokens * 0.8)
    
    # 1. Score and Tag
    scored = []
    total = len(messages)
    current_tokens = 0
    
    # Always keep System and User messages (P0)
    # We separate them to ensure they are never dropped by the greedy algorithm.
    pinned = []
    candidates = []
    
    for i, msg in enumerate(messages):
        cls = _classify_message(msg)
        tokens = estimate_tokens(msg.get("content", ""))
        
        if cls in (ContextClass.SYSTEM, ContextClass.USER):
            pinned.append((i, msg, tokens))
            current_tokens += tokens
        else:
            score = _score_message(msg, i, total)
            candidates.append((i, msg, tokens, score))
            
    # 2. Greedy Selection with Per-Class Caps
    # Sort by score descending
    candidates.sort(key=lambda x: x[3], reverse=True)
    
    selected = []
    class_token_usage = {cls: 0 for cls in ContextClass}
    
    # Soft cap: No single non-pinned class can exceed 50% of the input budget
    # This prevents a single massive traceback from starving the rest of the context
    CLASS_CAP = int(input_budget * 0.50)
    
    for i, msg, tokens, score in candidates:
        cls = _classify_message(msg)
        
        # Enforce per-class cap
        if class_token_usage[cls] + tokens > CLASS_CAP:
            continue
            
        if current_tokens + tokens <= input_budget:
            selected.append((i, msg, tokens))
            current_tokens += tokens
            class_token_usage[cls] += tokens
            
    # 3. Re-assemble chronologically to preserve conversation flow (User/Assistant alternation).
    # The scoring already determined *which* messages survive; now we just order them by original index.
    final_set = pinned + selected
    final_set.sort(key=lambda x: x[0])
    result = [msg for _, msg, _ in final_set]
    
    # 4. Safety Check: If we still somehow exceeded (e.g. pinned messages were huge),
    # truncate the last user message as a last resort.
    final_tokens = sum(estimate_tokens(m.get("content", "")) for m in result)
    if final_tokens > max_tokens:
        logger.warning(f"[Budget] Pinned messages exceeded budget ({final_tokens} > {max_tokens}). Truncating history.")
        # Keep System + Last User, drop everything else
        result = [m for m in result if _classify_message(m) in (ContextClass.SYSTEM, ContextClass.USER)]
        
    return result