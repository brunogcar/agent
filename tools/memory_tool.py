"""
tools/memory_tool.py — Memory meta-tool.
Exposes core/memory.py to the LLM as a single tool.
The LLM sees ONE tool: memory(action, ...)
Imports are lazy -- chromadb is only loaded on first actual call,
not at module registration time. This keeps server startup fast.
"""
from __future__ import annotations
import re
from registry import tool
from core.config import cfg
from core.contracts import ok, fail
from core.utils import compress_result
from core.memory_backend.janitor import archive_old_episodes
from core.sleep_learn.janitor import purge_stale_rules

def _mem():
    """Lazy import of memory store -- avoids slow chromadb load at startup."""
    from core.memory import memory as _memory
    return _memory

# ── MED-05: Tag Validation (Input Sanitization) ────────────────────────────
TAG_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.\s-]*$')  # Allow hyphens and spaces, but must start with letter

def _validate_tags(tags: str, max_count: int = 6) -> tuple[bool, str]:
    """
    Validate tags to prevent injection/XSS attacks.
    
    Args:
        tags: Comma-separated tag string (may be empty)
        max_count: Maximum tags allowed per entry
        
    Returns:
        Tuple of (is_valid, error_message). Returns (True, "") if valid.
        
    Validation rules:
        - Reject dangerous chars: < > " ' ` | newline
        - Each tag must start with letter, contain only letters/numbers/hyphens/dots/spaces
        - Max N tags (from max_count), max cfg.max_tag_length chars each tag
    """
    if not tags:
        return True, ""  # Empty is fine

    # Reject dangerous characters immediately
    danger_list = ['<', '>', '"', "'", '`', '|']
    for bad_char in danger_list:
        if bad_char in tags:
            return False, f"Tags cannot contain: {bad_char}"

    # Split by comma and validate each tag
    parts = [t.strip() for t in re.split(r'[,\s]+', tags) if t.strip()]

    if not parts:
        return False, "No valid tags found"

    if len(parts) > max_count:
        return False, f"Too many tags (max {max_count})"

    for i, tag in enumerate(parts):
        if len(tag) > cfg.max_tag_length:
            return False, f"Tag exceeds length limit ({len(tag)} > {cfg.max_tag_length})"
        # Tags must match pattern: starts with letter, then alphanumeric/hyphens/dots/spaces
        if not TAG_PATTERN.fullmatch(tag):
            bad_chars = set(tag) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.- ')
            return False, f"Tag contains invalid characters: {bad_chars}"

    return True, ""

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
    action:  "store" | "recall" | "delete" | "prune" | "summarize" | "stats" | "janitor"

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
    """
    action = action.strip().lower()

    # ── JANITOR ACTION ──────────────────────────────────────────────────────
    # Handle this FIRST to avoid loading the memory store (and chromadb) unnecessarily.
    if action == "janitor":
        """
        Run memory compaction: archive old episodic memories and purge stale learned rules.
        This is useful when memory retrieval feels slow or the database is growing too large.
        """
        epi_stats = archive_old_episodes()
        rule_stats = purge_stale_rules()
        
        return compress_result(ok({
            "episodic_archived": epi_stats["archived"],
            "rules_purged": rule_stats["purged"],
            "errors": [e for e in [epi_stats.get("error"), rule_stats.get("error")] if e]
        }, trace_id=trace_id))

    # ONLY load the memory store if we actually need it (prevents chromadb import on janitor action)
    store = _mem()

    if action == "store":
        if not text or not text.strip():
            return fail("text is required for store")
        if importance < 1 or importance > 10:
            return fail(f"importance must be 1-10, got {importance}")
        
        # Guard against storing huge blobs that bloat the vector DB
        text_bytes = len(text.encode("utf-8"))
        if text_bytes > cfg.memory_max_entry_bytes:
            return fail(
                f"text is {text_bytes} bytes -- exceeds {cfg.memory_max_entry_bytes} byte limit.  "
                "Summarise or chunk the content before storing."
            )
        
        # MED-05: Validate tags for store operation (uses cfg.max_tags_per_entry)
        is_valid, err = _validate_tags(tags, max_count=cfg.max_tags_per_entry)
        if not is_valid:
            return fail(err)

        result = store.store(
            text=text, memory_type=memory_type, importance=importance,
            tags=tags, trace_id=trace_id, goal=goal, outcome=outcome,
            tools_used=tools_used, source=source,
        )
        if isinstance(result, dict) and trace_id and "trace_id" not in result:
            result["trace_id"] = trace_id
        return compress_result(result)

    if action == "recall":
        if not query:
            return fail("query is required for recall")
        # MED-05: Validate tags_filter parameter (same validation, relaxed limit)
        is_valid, err = _validate_tags(tags_filter or "", max_count=10)
        if not is_valid:
            return fail(err)

        results = store.recall(
            query=query, top_k=top_k, collections=collections,
            min_score=min_score, tags_filter=tags_filter, trace_id=trace_id,
        )
        return compress_result(ok({"count": len(results), "results": results}, trace_id=trace_id))

    if action == "delete":
        if not query:
            return fail("query is required for delete")
        result = store.delete(
            query=query, collections=collections,
            threshold=threshold or None, confirm_ids=confirm_ids,
        )
        if isinstance(result, dict) and trace_id and "trace_id" not in result:
            result["trace_id"] = trace_id
        return compress_result(result)

    if action == "prune":
        result = store.prune(
            max_age_days=max_age_days, min_importance=min_importance,
            dry_run=dry_run, collections=collections,
        )
        if isinstance(result, dict) and trace_id and "trace_id" not in result:
            result["trace_id"] = trace_id
        return compress_result(result)

    if action == "summarize":
        result = store.summarize(collections=collections, trace_id=trace_id)
        if isinstance(result, dict) and trace_id and "trace_id" not in result:
            result["trace_id"] = trace_id
        return compress_result(result)

    if action == "stats":
        raw   = store.stats()
        total = sum(v.get("count", 0) for v in raw.values())
        return compress_result(ok({"collections": raw, "total": total}, trace_id=trace_id))

    return fail(
        f"Unknown action '{action}'.  "
        "Use: store | recall | delete | prune | summarize | stats | janitor"
    )
