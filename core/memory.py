"""
core/memory.py — Three-collection ChromaDB memory system.

Collections:
  episodic   → what happened  (task runs, workflow outcomes, errors)
  semantic   → what you know  (facts, research, domain knowledge)
  procedural → how to do it   (autocode learnings, fix patterns, solutions)

Every memory entry has a structured format:
{
  "text":       str,            # the main content
  "type":       str,            # episodic | semantic | procedural
  "importance": int,            # 1-10
  "tags":       str,            # comma-separated
  "timestamp":  int,            # unix epoch
  "trace_id":   str,            # links memory to the workflow that created it
  "goal":       str,            # what was being attempted
  "outcome":    str,            # success | failure | partial | unknown
  "tools_used": str,            # comma-separated tool names,
  "source":     str,            # where this knowledge comes from,
}

Recall uses decay scoring so old memories fade naturally:
  score = importance * max(0.3, 1 - age_days / DECAY_DAYS)
  (Procedural memories bypass time-decay and use reinforcement boosting).

Query rewriting improves recall accuracy before hitting ChromaDB.

Usage:
  from core.memory import memory

  # Store
  memory.store_episodic("Fixed bug in memory.py", importance=8,
                        trace_id=tid, goal="fix import error", outcome="success")

  memory.store_semantic("ChromaDB supports persistent local storage",
                        importance=6, tags="chromadb,vector,storage", source="docs.trychroma.com")

  memory.store_procedural("To fix SyntaxError: always check line N-2 for unclosed bracket",
                          importance=9, tags="syntax,debug")

  # Recall (searches all collections by default)
  results = memory.recall("how to fix syntax errors", top_k=5)
  for r in results:
      print(r["text"], r["score"])
"""
from __future__ import annotations

# The entire memory engine is now located in core/memory_backend/.
# This file serves purely as a stable public facade to maintain 
# the `from core.memory import memory` import pattern across the codebase.

from core.memory_backend.store import MemoryStore

# ── Singleton ─────────────────────────────────────────────────────────────────
memory = MemoryStore()