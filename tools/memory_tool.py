"""
tools/memory_tool.py -- Memory meta-tool.

Exposes memory/store.py to the LLM as a single tool.
The LLM sees ONE tool: memory(action, ...)

Imports are lazy -- chromadb is only loaded on first actual call,
not at module registration time. This keeps server startup fast.
"""

from __future__ import annotations

from registry import tool


def _mem():
    """Lazy import of memory store -- avoids slow chromadb load at startup."""
    from memory.store import memory as _memory
    return _memory


@tool
def memory(
    action:         str,
    text:           str    = "",
    memory_type:    str    = "semantic",
    importance:     int    = 5,
    tags:           str    = "",
    trace_id:       str    = "",
    goal:           str    = "",
    outcome:        str    = "unknown",
    tools_used:     str    = "",
    source:         str    = "",
    query:          str    = "",
    top_k:          int    = 5,
    collections:    list   = None,
    min_score:      float  = 0.5,
    tags_filter:    str    = "",
    threshold:      float  = 0.0,
    confirm_ids:    list   = None,
    max_age_days:   int    = 30,
    min_importance: int    = 3,
    dry_run:        bool   = True,
) -> dict:
    """
    Memory tool -- store, recall, and manage agent memories.

    action: "store" | "recall" | "delete" | "prune" | "summarize" | "stats"

    -- STORE --------------------------------------------------------------------
    Save a memory to one of three typed collections.

    memory_type : "episodic"   -> things that happened (task runs, outcomes)
                  "semantic"   -> things you know (facts, research, knowledge)
                  "procedural" -> how to do things (fix patterns, solutions)

    importance  : 1-10. High importance = slower decay.
                  9-10 critical facts, project structure, hard-won fixes
                  7-8  useful patterns, successful approaches
                  5-6  general knowledge, research findings
                  1-4  low-value, transient information

    tags        : comma-separated, e.g. "python,syntax,debug"
    trace_id    : attach to current workflow trace
    goal        : what was being attempted (episodic/procedural)
    outcome     : "success" | "failure" | "partial" | "unknown"
    tools_used  : comma-separated tool names (episodic)
    source      : where knowledge came from (semantic), e.g. URL

    Examples:
        memory(action="store", memory_type="episodic",
               text="Fixed SyntaxError in tools/web.py -- missing colon after def",
               importance=8, goal="fix scraping bug", outcome="success",
               tools_used="python,git", trace_id="abc123")

        memory(action="store", memory_type="semantic",
               text="ChromaDB get_or_create_collection is idempotent",
               importance=7, tags="chromadb,startup")

        memory(action="store", memory_type="procedural",
               text="To add a new MCP tool: decorate with @tool in tools/ directory. "
                    "registry.py auto-discovers it. No changes to server.py needed.",
               importance=9, tags="mcp,tools,howto")

    -- RECALL -------------------------------------------------------------------
    Semantic search across memory collections, ranked by decay score.
    score = importance * max(0.3, 1 - age/decay_days)

    query       : what to search for
    top_k       : max results (default 5)
    collections : ["episodic"] | ["semantic"] | ["procedural"] | all (default)
    min_score   : minimum decay score (default 0.5)
    tags_filter : comma-separated -- only return memories with ANY of these tags

    Examples:
        memory(action="recall", query="how to fix syntax errors", top_k=3)
        memory(action="recall", query="ChromaDB", collections=["semantic"])
        memory(action="recall", query="tool registration", tags_filter="mcp,howto")

    -- DELETE -------------------------------------------------------------------
    Two-step safety pattern:
      Step 1 -- call without confirm_ids -> returns candidates (dry run)
      Step 2 -- call with confirm_ids from step 1 -> actually deletes

    threshold   : cosine distance cutoff (default 0.4)
    confirm_ids : list of IDs to confirm deletion

    -- PRUNE --------------------------------------------------------------------
    Remove old, low-importance memories in bulk.
    Procedural collection is always protected.
    Memories tagged "summary", "critical", or "protected" are safe.

    dry_run=True (default) -> preview only. dry_run=False -> execute.

    -- SUMMARIZE ----------------------------------------------------------------
    Consolidate all memories into a dense summary using the planner model.
    Stored as importance=10 semantic memory tagged "summary".

    -- STATS --------------------------------------------------------------------
        memory(action="stats")
    """
    action = action.strip().lower()
    store  = _mem()

    if action == "store":
        if not text or not text.strip():
            return {"status": "error", "error": "text is required for store"}
        if importance < 1 or importance > 10:
            return {"status": "error",
                    "error": f"importance must be 1-10, got {importance}"}
        # Guard against storing huge blobs that bloat the vector DB
        MAX_MEMORY_BYTES = 50_000  # 50 KB
        if len(text.encode("utf-8")) > MAX_MEMORY_BYTES:
            return {
                "status": "error",
                "error":  (
                    f"text is {len(text.encode())} bytes -- exceeds 50KB limit. "
                    "Summarise or chunk the content before storing."
                ),
            }
        return store.store(
            text=text, memory_type=memory_type, importance=importance,
            tags=tags, trace_id=trace_id, goal=goal, outcome=outcome,
            tools_used=tools_used, source=source,
        )

    if action == "recall":
        if not query:
            return {"status": "error", "error": "query is required for recall"}
        results = store.recall(
            query=query, top_k=top_k, collections=collections,
            min_score=min_score, tags_filter=tags_filter, trace_id=trace_id,
        )
        return {"status": "success", "count": len(results), "results": results}

    if action == "delete":
        if not query:
            return {"status": "error", "error": "query is required for delete"}
        return store.delete(
            query=query, collections=collections,
            threshold=threshold or None, confirm_ids=confirm_ids,
        )

    if action == "prune":
        return store.prune(
            max_age_days=max_age_days, min_importance=min_importance,
            dry_run=dry_run, collections=collections,
        )

    if action == "summarize":
        return store.summarize(collections=collections, trace_id=trace_id)

    if action == "stats":
        raw   = store.stats()
        total = sum(v.get("count", 0) for v in raw.values())
        return {"status": "success", "collections": raw, "total": total}

    return {
        "status": "error",
        "error":  (
            f"Unknown action '{action}'. "
            "Use: store | recall | delete | prune | summarize | stats"
        ),
    }
