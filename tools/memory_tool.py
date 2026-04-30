"""
tools/memory_tool.py — Memory meta-tool.

Exposes memory/store.py to the LLM as a single tool.
The LLM sees ONE tool: memory(action, ...)

Actions:
  store     → save a memory to the appropriate collection
  recall    → semantic search across collections with decay scoring
  delete    → remove memories similar to a query
  prune     → sweep old low-importance memories
  summarize → consolidate memories using the planner model
  stats     → collection counts

This file is intentionally thin — all logic lives in memory/store.py.
The tool layer just validates inputs and formats outputs for the LLM.
"""

from __future__ import annotations

from registry import tool
from memory.store import memory as _memory


@tool
def memory(
    action:      str,
    text:        str       = "",
    memory_type: str       = "semantic",
    importance:  int       = 5,
    tags:        str       = "",
    trace_id:    str       = "",
    goal:        str       = "",
    outcome:     str       = "unknown",
    tools_used:  str       = "",
    source:      str       = "",
    query:       str       = "",
    top_k:       int       = 5,
    collections: list      = None,
    min_score:   float     = 0.5,
    tags_filter: str       = "",
    threshold:   float     = 0.0,
    confirm_ids: list      = None,
    max_age_days: int      = 30,
    min_importance: int    = 3,
    dry_run:     bool      = True,
) -> dict:
    """
    Memory tool — store, recall, and manage agent memories.

    action: "store" | "recall" | "delete" | "prune" | "summarize" | "stats"

    ── STORE ────────────────────────────────────────────────────────────────────
    Save a memory to one of three typed collections.

    memory_type : "episodic"   → things that happened (task runs, outcomes)
                  "semantic"   → things you know (facts, research, knowledge)
                  "procedural" → how to do things (fix patterns, solutions)

    importance  : 1-10. High importance = slower decay. Use:
                  9-10 for critical facts, project structure, hard-won fixes
                  7-8  for useful patterns, successful approaches
                  5-6  for general knowledge, research findings
                  1-4  for low-value, transient information

    tags        : comma-separated, e.g. "python,syntax,debug"
    trace_id    : attach to current workflow trace
    goal        : what was being attempted (episodic/procedural)
    outcome     : "success" | "failure" | "partial" | "unknown"
    tools_used  : comma-separated tool names used (episodic)
    source      : where knowledge came from (semantic), e.g. URL or filename

    Examples:
        memory(action="store", memory_type="episodic",
               text="Fixed SyntaxError in tools/web.py line 42 — missing colon after def",
               importance=8, goal="fix scraping bug", outcome="success",
               tools_used="python,git", trace_id="abc123")

        memory(action="store", memory_type="semantic",
               text="ChromaDB get_or_create_collection is idempotent — safe to call on startup",
               importance=7, tags="chromadb,startup", source="https://docs.trychroma.com")

        memory(action="store", memory_type="procedural",
               text="To add a new MCP tool: decorate function with @tool in tools/ directory. "
                    "registry.py auto-discovers it. No changes to server.py needed.",
               importance=9, tags="mcp,tools,howto")

    ── RECALL ───────────────────────────────────────────────────────────────────
    Semantic search across memory collections, ranked by decay score.
    Results are sorted: score = importance × max(0.3, 1 − age/decay_days)

    query       : what to search for (will be rewritten before search)
    top_k       : max results (default 5)
    collections : ["episodic"] | ["semantic"] | ["procedural"] | all three (default)
    min_score   : minimum decay score to include (default 0.5 — filters very old/unimportant)
    tags_filter : comma-separated — only return memories with ANY of these tags

    Returns list of memories sorted by relevance × recency score.

    Examples:
        memory(action="recall", query="how to fix syntax errors in python", top_k=3)
        memory(action="recall", query="ChromaDB", collections=["semantic"])
        memory(action="recall", query="tool registration", tags_filter="mcp,howto")
        memory(action="recall", query="autocode failures", collections=["episodic"],
               min_score=2.0)

    ── DELETE ───────────────────────────────────────────────────────────────────
    Find and remove memories similar to a query.

    Two-step safety pattern:
      Step 1 — call without confirm_ids → returns candidates (dry run)
      Step 2 — call with confirm_ids from step 1 → actually deletes

    threshold   : cosine distance cutoff (default 0.4 — lower = more similar)
    confirm_ids : list of memory IDs to confirm deletion (from step 1 result)

    Examples:
        # Step 1 — preview
        memory(action="delete", query="old test memory", threshold=0.4)
        # Step 2 — confirm (use IDs from step 1 response)
        memory(action="delete", query="old test memory", confirm_ids=["id1", "id2"])

    ── PRUNE ────────────────────────────────────────────────────────────────────
    Remove old, low-importance memories in bulk.
    Procedural collection is always protected — never pruned automatically.
    Memories tagged "summary", "critical", or "protected" are also safe.

    max_age_days   : only considers memories older than this (default 30)
    min_importance : only removes importance BELOW this value (default 3)
    dry_run        : True (default) = preview only. False = actually delete.

    Examples:
        memory(action="prune", dry_run=True)                      # preview
        memory(action="prune", max_age_days=60, min_importance=4,
               dry_run=False)                                      # execute

    ── SUMMARIZE ────────────────────────────────────────────────────────────────
    Consolidate all memories into a dense summary using the planner model.
    The summary is stored as importance=10 semantic memory tagged "summary".
    Call periodically (e.g. after long research sessions) to consolidate knowledge.

    collections : which collections to include (default: all three)
    trace_id    : attach to current trace

    Example:
        memory(action="summarize", trace_id="abc123")

    ── STATS ────────────────────────────────────────────────────────────────────
    Return entry counts per collection. Useful for monitoring.

        memory(action="stats")
    """
    action = action.strip().lower()

    # ── store ─────────────────────────────────────────────────────────────────
    if action == "store":
        if not text or not text.strip():
            return {"status": "error", "error": "text is required for store"}
        if importance < 1 or importance > 10:
            return {"status": "error",
                    "error": f"importance must be 1-10, got {importance}"}

        return _memory.store(
            text        = text,
            memory_type = memory_type,
            importance  = importance,
            tags        = tags,
            trace_id    = trace_id,
            goal        = goal,
            outcome     = outcome,
            tools_used  = tools_used,
            source      = source,
        )

    # ── recall ────────────────────────────────────────────────────────────────
    if action == "recall":
        if not query:
            return {"status": "error", "error": "query is required for recall"}

        results = _memory.recall(
            query       = query,
            top_k       = top_k,
            collections = collections,
            min_score   = min_score,
            tags_filter = tags_filter,
            trace_id    = trace_id,
        )

        return {
            "status":  "success",
            "count":   len(results),
            "results": results,
        }

    # ── delete ────────────────────────────────────────────────────────────────
    if action == "delete":
        if not query:
            return {"status": "error", "error": "query is required for delete"}

        return _memory.delete(
            query       = query,
            collections = collections,
            threshold   = threshold or None,
            confirm_ids = confirm_ids,
        )

    # ── prune ─────────────────────────────────────────────────────────────────
    if action == "prune":
        return _memory.prune(
            max_age_days   = max_age_days,
            min_importance = min_importance,
            dry_run        = dry_run,
            collections    = collections,
        )

    # ── summarize ─────────────────────────────────────────────────────────────
    if action == "summarize":
        return _memory.summarize(
            collections  = collections,
            trace_id     = trace_id,
        )

    # ── stats ─────────────────────────────────────────────────────────────────
    if action == "stats":
        raw = _memory.stats()
        total = sum(v.get("count", 0) for v in raw.values())
        return {
            "status":      "success",
            "collections": raw,
            "total":       total,
        }

    return {
        "status": "error",
        "error":  (
            f"Unknown action '{action}'. "
            "Use: store | recall | delete | prune | summarize | stats"
        ),
    }
