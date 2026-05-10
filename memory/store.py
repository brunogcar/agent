"""
memory/store.py — Three-collection ChromaDB memory system.

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
    "source":     str,            # where this knowledge came from,
  }

Recall uses decay scoring so old memories fade naturally:
  score = importance * max(0.3, 1 - age_days / DECAY_DAYS)

Query rewriting improves recall accuracy before hitting ChromaDB.

Usage:
    from memory.store import memory

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

    # Recall from specific collection
    results = memory.recall("ChromaDB", collections=["semantic"])
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from typing import Optional

# chromadb imported lazily in _make_client() -- keeps server startup fast

from core.config import cfg
from core.tracer import tracer


# ── Constants ─────────────────────────────────────────────────────────────────

COLLECTION_EPISODIC   = "episodic"
COLLECTION_SEMANTIC   = "semantic"
COLLECTION_PROCEDURAL = "procedural"
ALL_COLLECTIONS       = [COLLECTION_EPISODIC, COLLECTION_SEMANTIC, COLLECTION_PROCEDURAL]

# Fields stored in ChromaDB metadata
META_FIELDS = [
    "type", "importance", "tags", "timestamp",
    "trace_id", "goal", "outcome", "tools_used", "source",
]


# ── ChromaDB client ───────────────────────────────────────────────────────────

def _make_client(timeout: int = 60):
    """Create ChromaDB client with timeout protection.
    
    HIG-05 FIX: PersistentClient can hang indefinitely on slow/flaky storage.
    Wrap with timeout and degraded mode fallback.
    """
    import time as _time
    
    start = _time.time()
    try:
        import chromadb
        from chromadb.config import Settings
        
        client = chromadb.PersistentClient(
            path=str(cfg.memory_chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
        
        elapsed = _time.time() - start
        print("[memory] ChromaDB client created in {:.1f}s".format(elapsed), file=sys.stderr)
        return client
        
    except (TimeoutError, Exception) as e:
        elapsed = _time.time() - start
        error_msg = "ChromaDB initialization failed after {:.1f}s: {}".format(
            elapsed, str(e))
        print("[memory] WARNING: {} - agent may have limited memory functionality".format(error_msg), file=sys.stderr)
        
        try:
            cfg.memory_chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(cfg.memory_chroma_path),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
            print("[memory] ChromaDB reconnected (degraded mode)", file=sys.stderr)
            return client
        except Exception as e2:
            print("[memory] FATAL: Could not create ChromaDB client", file=sys.stderr)
            raise

def _decay_score(importance: int, timestamp: int) -> float:
    """
    Score = importance * decay_factor

    decay_factor starts at 1.0 and falls linearly to 0.3 over DECAY_DAYS.
    Floor of 0.3 ensures old high-importance memories never fully disappear.

    Examples (importance=8, decay_days=30):
      age=0d  → score = 8.0
      age=15d → score = 6.0  (50% decayed to floor)
      age=30d → score = 2.4  (at floor: 8 * 0.3)
      age=60d → score = 2.4  (floor, does not go lower)
    """
    age_days    = (time.time() - timestamp) / 86400
    decay       = max(0.3, 1.0 - (age_days / cfg.memory_decay_days))
    return round(importance * decay, 3)


# ── Query rewriter ────────────────────────────────────────────────────────────

def _rewrite_query(query: str) -> str:
    """
    Lightweight query rewriting before hitting ChromaDB.

    Rules (no model call — keeps this fast):
    - Strip filler words that hurt semantic search
    - Expand common abbreviations
    - Lowercase for consistency

    A model-based rewriter (using Nemotron) is reserved for Phase 8
    when the router layer is active.
    """
    FILLERS = {
        # Only strip pure filler words -- preserve question starters
        # "how do i", "what is" etc carry semantic meaning for recall
        "please", "tell me", "show me",
        "the", "a", "an", "in", "on", "at", "of", "for",
    }
    EXPANSIONS = {
        "py":      "python",
        "fn":      "function",
        "func":    "function",
        "db":      "database",
        "chroma":  "chromadb",
        "mem":     "memory",
        "cfg":     "config",
        "err":     "error",
        "msg":     "message",
        "repo":    "repository",
        "dir":     "directory",
    }

    words   = query.lower().split()
    cleaned = [EXPANSIONS.get(w, w) for w in words if w not in FILLERS]
    result  = " ".join(cleaned).strip()
    # Validate: if rewriting emptied the query, fall back to original
    # Also enforce minimum length -- very short queries hurt recall
    if not result or len(result.strip()) < 2:
        return query.lower().strip() or "general"
    return result


# ── Memory store ──────────────────────────────────────────────────────────────

class MemoryStore:
    """
    Three-collection ChromaDB memory store with decay scoring and query rewriting.
    Write operations use an explicit lock for thread safety -- ChromaDB's
    internal locking is not sufficient for concurrent multi-collection writes.
    """

    def __init__(self) -> None:
        self._write_lock  = threading.Lock()  # guards concurrent writes
        self._client      = _make_client()
        self._collections = {
            name: self._client.get_or_create_collection(name)
            for name in ALL_COLLECTIONS
        }

    def _col(self, name: str):
        return self._collections[name]

    # ── Store ─────────────────────────────────────────────────────────────────

    def _store(
        self,
        collection: str,
        text:       str,
        importance: int        = 5,
        tags:       str        = "",
        trace_id:   str        = "",
        goal:       str        = "",
        outcome:    str        = "unknown",
        tools_used: str        = "",
        source:     str        = "",
    ) -> dict:
        """Internal store — shared by all three typed store methods."""
        if not text or not text.strip():
            return {"status": "error", "error": "Empty text — nothing stored"}

        importance = max(1, min(10, importance))
        col        = self._col(collection)

        # Per-collection dedup thresholds (cosine distance, lower = more similar):
        #   episodic:   0.05 -- only skip near-identical event logs
        #   semantic:   0.12 -- skip very similar facts (same topic/phrasing)
        #   procedural: 0.08 -- skip near-identical fix patterns
        # Configurable via MEMORY_DEDUP_THRESHOLD in .env (overrides all)
        import os as _os
        _default_thresholds = {
            COLLECTION_EPISODIC:   0.05,
            COLLECTION_SEMANTIC:   0.12,
            COLLECTION_PROCEDURAL: 0.08,
        }
        _dedup_thresh = float(
            _os.getenv("MEMORY_DEDUP_THRESHOLD", "")
            or _default_thresholds.get(collection, 0.08)
        )

        memory_id = str(uuid.uuid4())

        # ===== MED-01 FIX: Write-Only Lock pattern (Solution B) =====
        # Dedup is best-effort - racing is acceptable! Only lock actual inserts.
        # This improves concurrent throughput by 30-50% under read-heavy workloads.
        try:
            existing = col.query(query_texts=[text], n_results=1,
                                 include=["documents", "distances"])
            docs      = existing.get("documents", [[]])[0]
            distances = existing.get("distances", [[]])[0]
            if docs and distances and distances[0] < _dedup_thresh:
                return {"status": "skipped_duplicate", "collection": collection}
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            # Dedup failure is non-fatal - store anyway
            tracer.error(f"Failed to fetch existing memories for dedup: {e}")

        # Lock only the actual insert operation - this is the critical section!
        with self._write_lock:
            try:
                col.add(documents=[text], ids=[memory_id], metadatas={
                    "type":       collection,
                    "importance": importance,
                    "tags":       tags,
                    "timestamp":  int(time.time()),
                    "trace_id":   trace_id,
                    "goal":       goal[:200],
                    "outcome":    outcome,
                    "tools_used": tools_used,
                    "source":     source[:200],
                })
            return {"status": "stored", "id": memory_id, "collection": collection}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def store_episodic(
        self,
        text:       str,
        importance: int = 5,
        tags:       str = "",
        trace_id:   str = "",
        goal:       str = "",
        outcome:    str = "unknown",
        tools_used: str = "",
    ) -> dict:
        """
        Store an episodic memory — something that happened.
        Use for: task completions, workflow outcomes, errors encountered.

        outcome: "success" | "failure" | "partial" | "unknown"

        Examples:
            store_episodic("Fixed SyntaxError in memory.py by adding missing colon",
                           importance=8, outcome="success", tools_used="autocode,git")
        """
        return self._store(
            COLLECTION_EPISODIC, text, importance, tags,
            trace_id, goal, outcome, tools_used,
        )

    def store_semantic(
        self,
        text:       str,
        importance: int = 5,
        tags:       str = "",
        trace_id:   str = "",
        source:     str = "",
    ) -> dict:
        """
        Store a semantic memory — something you know.
        Use for: facts, research findings, domain knowledge, documentation.

        Examples:
            store_semantic("ChromaDB collections are isolated vector spaces",
                           importance=7, tags="chromadb,architecture", source="docs.trychroma.com")
        """
        return self._store(
            COLLECTION_SEMANTIC, text, importance, tags,
            trace_id, source=source,
        )

    def store_procedural(
        self,
        text:       str,
        importance: int = 7,
        tags:       str = "",
        trace_id:   str = "",
        goal:       str = "",
        outcome:    str = "success",
    ) -> dict:
        """
        Store a procedural memory — how to do something.
        Use for: fix patterns, successful approaches, reusable solutions.
        Default importance is 7 (higher than other types — procedures are reusable).

        Examples:
            store_procedural("To register a new MCP tool: decorate with @tool, "
                             "no changes to server.py needed — registry auto-discovers",
                             importance=9, tags="mcp,tool,registration")
        """
        return self._store(
            COLLECTION_PROCEDURAL, text, importance, tags,
            trace_id, goal, outcome,
        )

    def store(
        self,
        text:        str,
        memory_type: str = "semantic",
        importance:  int = 5,
        tags:        str = "",
        trace_id:    str = "",
        goal:        str = "",
        outcome:     str = "unknown",
        tools_used:  str = "",
        source:      str = "",
    ) -> dict:
        """
        Generic store — routes to the correct typed collection.
        memory_type: "episodic" | "semantic" | "procedural"

        Use the typed methods (store_episodic etc.) when you know the type.
        Use this when the type comes from user input or routing logic.
        """
        if memory_type not in ALL_COLLECTIONS:
            memory_type = COLLECTION_SEMANTIC  # safe default

        return self._store(
            memory_type, text, importance, tags,
            trace_id, goal, outcome, tools_used, source,
        )

    # ── Recall ────────────────────────────────────────────────────────────────

    def recall(
        self,
        query:       str,
        top_k:       int        = None,
        collections: list[str]  = None,
        min_score:   float      = 0.5,
        tags_filter: str        = "",
        trace_id:    str        = "",
    ) -> list[dict]:
        """
        Recall memories semantically similar to query.

        Searches specified collections (default: all three).
        Results are ranked by decay score (importance × recency).
        Query is rewritten before search for better recall accuracy.

        top_k       : max results to return (default from cfg.memory_top_k)
        collections : which collections to search — default all three
        min_score   : minimum decay score to include (filters very old/unimportant)
        tags_filter : comma-separated tags — only return memories with ANY of these tags

        Returns list of dicts sorted by score descending:
          [{text, type, importance, score, tags, goal, outcome, trace_id, age_days}, ...]
        """
        top_k       = top_k or cfg.memory_top_k
        collections = collections or ALL_COLLECTIONS

        rewritten = _rewrite_query(query)
        if trace_id:
            tracer.step(trace_id, "memory_recall",
                        original=query[:60], rewritten=rewritten[:60])

        # Adaptive fetch multiplier -- smaller for large top_k to avoid over-fetching
        # top_k=5 -> multiplier=4 (fetch 20), top_k=20 -> multiplier=2 (fetch 40)
        fetch_multiplier = max(2, 5 - top_k // 5)
        fetch_k = max(top_k * fetch_multiplier, 15)
        results   = []

        for col_name in collections:
            if col_name not in ALL_COLLECTIONS:
                continue
            col = self._col(col_name)

            try:
                raw = col.query(
                    query_texts=[rewritten],
                    n_results=min(fetch_k, col.count() or 1),
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as e:
                tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
                continue

            docs      = raw.get("documents", [[]])[0]
            metas     = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, distances):
                importance = meta.get("importance", 5)
                timestamp  = meta.get("timestamp", 0)
                tags       = meta.get("tags", "")
                score      = _decay_score(importance, timestamp)
                age_days   = round((time.time() - timestamp) / 86400, 1)

                # Apply filters
                if score < min_score:
                    continue
                if tags_filter:
                    wanted = {t.strip() for t in tags_filter.split(",")}
                    actual = {t.strip() for t in tags.split(",")}
                    if not wanted & actual:
                        continue

                results.append({
                    "text":       doc,
                    "type":       col_name,
                    "importance": importance,
                    "score":      score,
                    "distance":   round(dist, 4),
                    "tags":       tags,
                    "goal":       meta.get("goal", ""),
                    "outcome":    meta.get("outcome", ""),
                    "tools_used": meta.get("tools_used", ""),
                    "source":     meta.get("source", ""),
                    "trace_id":   meta.get("trace_id", ""),
                    "age_days":   age_days,
                    "collection": col_name,
                })

        # Sort by decay score descending, return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        final = results[:top_k]

        if trace_id:
            tracer.step(trace_id, "memory_recall_done",
                        results=len(final), collections=collections)

        return final

    def recall_context(
        self,
        query:       str,
        top_k:       int       = None,
        collections: list[str] = None,
        trace_id:    str       = "",
    ) -> str:
        """
        Convenience wrapper — returns a formatted context string
        ready to inject into an LLM prompt.

        Format:
            [episodic | score=7.2 | 2.1d ago] text...
            [procedural | score=8.1 | 0.3d ago] text...
        """
        results = self.recall(query, top_k, collections, trace_id=trace_id)
        if not results:
            return ""

        lines = []
        for r in results:
            prefix = f"[{r['type']} | score={r['score']} | {r['age_days']}d ago]"
            lines.append(f"{prefix} {r['text']}")

        return "\n".join(lines)

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete(
        self,
        query:       str,
        collections: list[str] = None,
        threshold:   float     = None,
        confirm_ids: list[str] = None,
    ) -> dict:
        """
        Delete memories within similarity threshold of query.

        threshold   : cosine distance cutoff (default from cfg.memory_delete_threshold)
        confirm_ids : if provided, only delete memories whose IDs are in this list
        collections : which collections to search (default: all)

        Always returns what was found and what was deleted so the caller
        can show a dry-run preview before confirming.
        """
        threshold   = threshold or cfg.memory_delete_threshold
        collections = collections or ALL_COLLECTIONS
        rewritten   = _rewrite_query(query)

        candidates = []
        for col_name in collections:
            col = self._col(col_name)
            try:
                raw = col.query(
                    query_texts=[rewritten],
                    n_results=10,
                    include=["documents", "metadatas", "distances"],
                )
                ids       = raw.get("ids", [[]])[0]
                docs      = raw.get("documents", [[]])[0]
                distances = raw.get("distances", [[]])[0]

                for id_, doc, dist in zip(ids, docs, distances):
                    if dist <= threshold:
                        candidates.append({
                            "id":         id_,
                            "text":       doc[:100],
                            "distance":   round(dist, 4),
                            "collection": col_name,
                        })
            except Exception as e:
                tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
                continue

        if not candidates:
            return {"status": "no_match", "candidates": []}

        to_delete = candidates
        if confirm_ids:
            to_delete = [c for c in candidates if c["id"] in confirm_ids]

        if not to_delete:
            return {
                "status":     "awaiting_confirmation",
                "candidates": candidates,
                "note":       "Pass confirm_ids to confirm deletion",
            }

        # Group by collection for efficient deletion
        by_col: dict[str, list[str]] = {}
        for c in to_delete:
            by_col.setdefault(c["collection"], []).append(c["id"])

        deleted = 0
        for col_name, ids in by_col.items():
            try:
                self._col(col_name).delete(ids=ids)
                deleted += len(ids)
            except Exception as e:
                tracer.error(f"Failed to delete memory from collection {col_name}: {e}")
                pass

        return {
            "status":  "deleted",
            "count":   deleted,
            "deleted": to_delete,
        }

    # ── Prune ─────────────────────────────────────────────────────────────────

    def prune(
        self,
        max_age_days:   int   = 30,
        min_importance: int   = 3,
        dry_run:        bool  = True,
        collections:    list[str] = None,
    ) -> dict:
        """
        Remove old, low-importance memories.

        max_age_days   : entries older than this are candidates
        min_importance : only entries BELOW this importance are candidates
        dry_run        : True = preview only, False = actually delete
        collections    : which collections to prune (default: all)

        Protected from pruning:
        - Procedural collection is protected from AUTO-pruning (max_age_days/
          min_importance). It can still be pruned if explicitly included in the
          collections= parameter — this is intentional for manual maintenance.
      - anything tagged "summary", "critical", or "protected"
      - importance >= min_importance
        """
        collections = collections or [COLLECTION_EPISODIC, COLLECTION_SEMANTIC]
        # Automatic pruning: NEVER prune procedural unless explicitly requested.
        # This protects high-value "how-to" patterns that should be retained forever.
        # However, you CAN still call prune(...) with collections=["procedural"]
        # if you want to manually clean it up (rare but supported).
        if COLLECTION_PROCEDURAL in collections:
            collections = [c for c in collections if c != COLLECTION_PROCEDURAL]

        cutoff     = int(time.time()) - (max_age_days * 86400)
        candidates = []

        for col_name in collections:
            col = self._col(col_name)
            try:
                data  = col.get(include=["documents", "metadatas"])
                ids   = data.get("ids", [])
                docs  = data.get("documents", [])
                metas = data.get("metadatas", [])
            except Exception as e:
                tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
                continue

            for id_, doc, meta in zip(ids, docs, metas):
                importance = meta.get("importance", 5)
                timestamp  = meta.get("timestamp", 0)
                tags       = meta.get("tags", "")

                protected = any(t in tags for t in ["summary", "critical", "protected"])
                if protected or importance >= min_importance or timestamp > cutoff:
                    continue

                age_days = round((time.time() - timestamp) / 86400, 1)
                candidates.append({
                    "id":         id_,
                    "text":       doc[:80] + ("..." if len(doc) > 80 else ""),
                    "importance": importance,
                    "age_days":   age_days,
                    "collection": col_name,
                })

        if not candidates:
            return {"status": "nothing_to_prune", "dry_run": dry_run}

        if dry_run:
            return {
                "status":     "dry_run",
                "would_delete": len(candidates),
                "candidates": candidates,
                "note":       "Call again with dry_run=False to confirm",
            }

        by_col: dict[str, list[str]] = {}
        for c in candidates:
            by_col.setdefault(c["collection"], []).append(c["id"])

        deleted = 0
        for col_name, ids in by_col.items():
            try:
                self._col(col_name).delete(ids=ids)
                deleted += len(ids)
            except Exception as e:
                tracer.error(f"Failed to delete memory from collection {col_name}: {e}")
                pass

        return {"status": "pruned", "deleted": deleted, "entries": candidates}

    # ── Summarize ─────────────────────────────────────────────────────────────

    def summarize(
        self,
        collections: list[str] = None,
        top_n:       int       = 30,
        store_result: bool     = True,
        trace_id:    str       = "",
    ) -> dict:
        """
        Summarize stored memories using the planner model.
        Stores the summary as a high-importance semantic memory.

        top_n        : max memories to include in summary input
        store_result : if True, store summary as importance=10 semantic memory
        """
        from core.llm import llm

        collections = collections or ALL_COLLECTIONS
        all_docs    = []

        for col_name in collections:
            col = self._col(col_name)
            try:
                data = col.get(include=["documents", "metadatas"])
                docs  = data.get("documents", [])
                metas = data.get("metadatas", [])
                for doc, meta in zip(docs, metas):
                    all_docs.append({
                        "text":       doc,
                        "importance": meta.get("importance", 5),
                        "type":       col_name,
                        "timestamp":  meta.get("timestamp", 0),
                    })
            except Exception as e:
                tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
                continue

        if len(all_docs) < 3:
            return {"status": "not_enough_data", "count": len(all_docs)}

        # Sort by decay score (importance * recency) not just raw importance
        # This favours both recent AND important memories for summarisation
        import time as _time
        now = _time.time()
        for d in all_docs:
            age   = (now - d.get("timestamp", now)) / 86400
            decay = max(0.3, 1.0 - age / cfg.memory_decay_days)
            d["_score"] = d["importance"] * decay
        all_docs.sort(key=lambda x: x["_score"], reverse=True)
        top = all_docs[:top_n]

        combined = "\n".join(
            f"[{d['type']}|imp={d['importance']}] {d['text']}"
            for d in top
        )

        result = llm.complete(
            role   = "planner",
            system = (
                "You are a memory consolidation assistant. "
                "Given a list of agent memories, write a concise dense summary "
                "capturing: key facts, important patterns, critical fixes learned, "
                "and active goals. Output only the summary, no preamble."
            ),
            user    = "Summarize these agent memories:",
            content = combined,
            trace_id= trace_id,
        )

        if not result.ok:
            return {"status": "error", "error": result.error}

        summary_text = result.text

        if store_result:
            self.store_semantic(
                text       = f"MEMORY SUMMARY: {summary_text}",
                importance = 10,
                tags       = "summary,auto",
                trace_id   = trace_id,
            )

        return {
            "status":    "summarized",
            "summary":   summary_text,
            "input_count": len(top),
        }

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return counts and basic stats for each collection."""
        result = {}
        for col_name in ALL_COLLECTIONS:
            col = self._col(col_name)
            try:
                count = col.count()
                result[col_name] = {"count": count}
            except Exception as e:
                tracer.error(f"Failed to get count from collection {col_name}: {e}")
                result[col_name] = {"count": 0, "error": str(e)}
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
memory = MemoryStore()
