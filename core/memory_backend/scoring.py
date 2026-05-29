"""
core/memory_backend/scoring.py — Decay scoring, query rewriting, and text normalization.
"""
from __future__ import annotations

import re
import time
import math
import hashlib
import unicodedata

from core.config import cfg

def _decay_score(
    importance: int,
    timestamp: int,
    collection: str = "",
    reinforcement_count: int = 0,
    recall_count: int = 0
) -> float:
    """
    Score = importance * decay_factor * reinforcement_boost * recall_boost
    Procedural memories bypass time-based decay.
    Reinforcement uses a capped logarithmic boost.
    Recall uses a capped linear boost to elevate frequently used memories.
    """
    # 1. Time Decay (Bypassed for procedural)
    if collection == "procedural":
        decay = 1.0
    else:
        age_days = (time.time() - timestamp) / 86400
        decay = max(0.3, 1.0 - (age_days / cfg.memory_decay_days))
        
    # 2. Reinforcement Boost (Capped Logarithmic)
    capped_count = min(reinforcement_count, 10)
    reinforcement_boost = 1.0 + (0.15 * math.log(1 + capped_count))

    # 3. Recall Boost (Capped Linear)
    # +5% max boost for frequently recalled memories (20 recalls * 0.0025)
    capped_recalls = min(recall_count, 20)
    recall_boost = 1.0 + (0.0025 * capped_recalls)

    return round(importance * decay * reinforcement_boost * recall_boost, 3)


def _rewrite_query(query: str) -> str:
    """
    Lightweight query rewriting before hitting ChromaDB.
    Rules (no model call — keeps this fast):
    - Strip filler words that hurt semantic search
    - Expand common abbreviations
    - Lowercase for consistency
    """
    FILLERS = {
        "please", "tell me", "show me",
        "the", "a", "an", "in", "on", "at", "of", "for",
    }
    EXPANSIONS = {
        "py":       "python",
        "fn":       "function",
        "func":     "function",
        "db":       "database",
        "chroma":   "chromadb",
        "mem":      "memory",
        "cfg":      "config",
        "err":      "error",
        "msg":      "message",
        "repo":     "repository",
        "dir":      "directory",
    }

    words   = query.lower().split()
    cleaned = [EXPANSIONS.get(w, w) for w in words if w not in FILLERS]
    result  = " ".join(cleaned).strip()

    if not result or len(result.strip()) < 2:
        return query.lower().strip() or "general"
    return result


def normalize_and_hash(text: str) -> str:
    """
    Normalize text and return SHA256 hex digest.
    Used for O(1) exact-match deduplication guard.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()