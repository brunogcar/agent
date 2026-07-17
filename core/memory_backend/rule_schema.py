"""core/memory_backend/rule_schema.py — Unified procedural rule schema (v1.5).

THE L3 CONTRACT — the keystone of the Memory + Sleep_Learn merge.

Both writers (meta_learning + sleep_learn/distiller) MUST conform to this
schema. The migration (Commit 4) moves all rules into the unified `procedural`
collection with this shape. The split-brain fallback in the injector is
deleted once migration is complete.

[DESIGN] KEY DECISIONS (from 6-LLM collective review):

  1. BOTH `importance` (1-10) AND `confidence` (0.0-1.0) coexist. They measure
     different things:
       - importance: "how critical is this rule?" (LLM-set, used by decay scorer)
       - confidence: "how sure are we it's correct?" (distiller-set, used by injector)
     The normalize_rule_fields() function ensures consistency: if a writer sets
     one, the other is derived. Both fields are always present on every rule.

  2. `version` + `schema_version` for optimistic locking + future migrations.
     version increments on every update (Commit 1's `update` action).
     schema_version is fixed at 1 for this schema; bumped when the schema changes.

  3. `history` is NOT in ChromaDB metadata (collective review: JSON string
     bloats queries + can't be filtered). It lives in the sidecar SQLite
     audit table (memory_db/memory_audit.db, rule_history table) — see
     tools/memory_ops/actions/update.py.

  4. Tag schema is ENFORCED at write time via validate_tags(). Both writers
     must emit tags from the canonical prefix set. This is the prerequisite
     for `tags_required` (Commit 5 — AND-based filtering).

  5. Procedural records are NEVER chunked. State this explicitly — an
     overzealous future contributor might apply chunking uniformly and break
     rule atomicity. (minimax's finding)

  6. `text_hash` is kept as a write-time field (kimi/qwen: needed for dedup
     during migration). It's not in the retrieval schema but IS stored.

FIELD MAPPING (current writers → unified schema):

  write_ops.py (main memory):          →  unified schema:
    type: "procedural"                     type: "procedural"
    importance: 7                          importance: 7
    tags: "meta-learned,auto-distilled"    tags: "source:meta_learner,category:auto-distilled"  (normalized)
    timestamp: 1690000000                  created_at: 1690000000  (renamed)
    trace_id: "abc123"                     source_trace_ids: "abc123"
    goal: "fix the bug"                    goal: "fix the bug"
    outcome: "success"                     outcome: "success"
    tools_used: "file,git"                 tools_used: "file,git"  (kept — mimo's point)
    source: "meta_learner"                 source: "meta_learner"
    text_hash: "a1b2c3"                    text_hash: "a1b2c3"
    reinforcement_count: 0                 reinforcement_count: 0
    last_reinforced: 1690000000            last_reinforced: 1690000000
    (missing)                              confidence: 0.7  (derived: importance/10)
    (missing)                              version: 1
    (missing)                              schema_version: 1
    (missing)                              provenance_count: 1
    (missing)                              updated_at: 0
    (missing)                              reasoning: ""  (Commit 3 adds this)

  sleep_learn/storage.py:               →  unified schema:
    source_memory_id: "abc123"            source_memory_id: "abc123"
    confidence_score: 0.8                 confidence: 0.8  (renamed)
    created_at: 1690000000                created_at: 1690000000
    last_accessed_at: 1690000000          last_accessed_at: 1690000000
    recall_count: 0                       recall_count: 0
    source: "sleep_learn_daemon"          source: "sleep_learn"  (normalized)
    phase: "2_active_distillation"        (dropped — internal, not useful for retrieval)
    (missing)                             importance: 8  (derived: round(confidence * 10))
    (missing)                             tags: "source:sleep_learn"  (generated)
    (missing)                             version: 1
    (missing)                             schema_version: 1
    (missing)                             provenance_count: 1
    (missing)                             updated_at: 0
    (missing)                             text_hash: "..."  (computed)
    (missing)                             source_trace_ids: ""
    (missing)                             goal: ""
    (missing)                             outcome: "unknown"
    (missing)                             tools_used: ""
    (missing)                             reinforcement_count: 0
    (missing)                             last_reinforced: 1690000000
    (missing)                             reasoning: ""
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional, Tuple


# ── Schema Version ───────────────────────────────────────────────────────────

SCHEMA_VERSION = 1  # Bump when the schema changes. Existing records get migrated.


# ── Canonical Tag Schema ─────────────────────────────────────────────────────
# Both writers MUST emit tags from these prefixes. validate_tags() enforces.
# This is the prerequisite for tags_required (Commit 5 — AND-based filtering).

VALID_TAG_PREFIXES = frozenset({
    "source:",        # source:llm | source:meta_learner | source:sleep_learn | source:user
    "domain:",        # domain:python | domain:web | domain:git | domain:config | ...
    "category:",      # category:bugfix | category:pattern | category:warning | category:workflow
    "status:",        # status:active | status:superseded | status:deprecated
    "evidence:",      # evidence:single_trace | evidence:multi_trace | evidence:user_confirmed
})

# Canonical source values (used in the `source` field + `source:*` tags)
VALID_SOURCES = frozenset({"llm", "meta_learner", "sleep_learn", "user", "legacy"})

# Canonical outcome values
VALID_OUTCOMES = frozenset({"success", "failure", "unknown", "abandoned"})


# ── Normalization ────────────────────────────────────────────────────────────

def normalize_rule_fields(
    *,
    importance: Optional[int] = None,
    confidence: Optional[float] = None,
) -> Tuple[int, float]:
    """Ensure both importance (1-10) and confidence (0.0-1.0) are set + consistent.

    Writers set ONE; this function derives the OTHER:
      - importance set → confidence = importance / 10.0
      - confidence set → importance = round(confidence * 10)
      - both set → keep both (writer knows what it's doing)
      - neither set → raise ValueError

    This guarantees every rule has both fields, so the decay scorer (reads
    importance) and the injector (reads confidence) both work regardless of
    which writer produced the rule.

    Returns (importance, confidence) as a tuple.
    """
    if importance is not None and confidence is not None:
        # Both set — trust the writer, but clamp to valid ranges
        return max(1, min(10, int(importance))), max(0.0, min(1.0, float(confidence)))

    if importance is not None:
        imp = max(1, min(10, int(importance)))
        return imp, round(imp / 10.0, 2)

    if confidence is not None:
        conf = max(0.0, min(1.0, float(confidence)))
        return max(1, round(conf * 10)), conf

    raise ValueError("At least one of importance or confidence must be set")


# ── Tag Validation ───────────────────────────────────────────────────────────

def validate_tags(tags: str) -> Tuple[bool, str]:
    """Validate that tags conform to the canonical prefix schema.

    Returns (is_valid, error_message). On success, error_message is "".
    Empty tags are valid (not all rules need tags).
    """
    if not tags or not tags.strip():
        return True, ""

    parts = [t.strip() for t in tags.split(",") if t.strip()]
    if not parts:
        return True, ""

    if len(parts) > 10:
        return False, f"Too many tags ({len(parts)} > 10)"

    for tag in parts:
        if len(tag) > 50:
            return False, f"Tag '{tag[:20]}...' exceeds 50 char limit"
        if not any(tag.startswith(prefix) for prefix in VALID_TAG_PREFIXES):
            return False, (
                f"Tag '{tag}' must start with one of: "
                f"{', '.join(sorted(VALID_TAG_PREFIXES))}"
            )

    return True, ""


def normalize_tags(tags: str, source: str) -> str:
    """Ensure tags include the source:* tag for the given source.

    Writers may pass tags without the source: prefix; this function adds it.
    Also normalizes old-style tags (e.g., "meta-learned" → "source:meta_learner").
    """
    if not tags or not tags.strip():
        return f"source:{source}" if source else ""

    parts = [t.strip() for t in tags.split(",") if t.strip()]

    # Add source: tag if not present
    if source and not any(p.startswith("source:") for p in parts):
        parts.append(f"source:{source}")

    return ",".join(parts)


# ── Text Hash ────────────────────────────────────────────────────────────────

def compute_text_hash(text: str) -> str:
    """Compute a SHA-256 hash of the rule text (for dedup).

    Used at write time to detect exact duplicates. NOT used for retrieval
    (ChromaDB's vector similarity handles that). Kept in metadata so the
    migration script (Commit 4) can dedup by hash.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Unified Metadata Builder ─────────────────────────────────────────────────

def build_unified_metadata(
    *,
    text: str,
    source: str,
    importance: Optional[int] = None,
    confidence: Optional[float] = None,
    tags: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    reasoning: str = "",
    source_trace_ids: str = "",
    source_memory_id: str = "",
    created_at: int = 0,
    last_accessed_at: int = 0,
    recall_count: int = 0,
    reinforcement_count: int = 0,
    last_reinforced: int = 0,
) -> dict:
    """Build a unified-schema metadata dict for a procedural rule.

    Both writers call this to ensure their output conforms to the L3 contract.
    The returned dict is ready to pass to ChromaDB's col.add(metadatas=[...]).

    Args:
        text: The rule text (also stored as the document).
        source: Who wrote it ("llm" | "meta_learner" | "sleep_learn" | "user").
        importance: 1-10 (LLM-set). If None, derived from confidence.
        confidence: 0.0-1.0 (distiller-set). If None, derived from importance.
        tags: Comma-separated tags (will be normalized + validated).
        goal: The goal that was being pursued (truncated to 200 chars).
        outcome: "success" | "failure" | "unknown" | "abandoned".
        tools_used: Comma-separated tool names referenced by the rule.
        reasoning: Why the rule was learned (max 1000 chars — Commit 3 adds this).
        source_trace_ids: Comma-separated trace IDs that originated this rule.
        source_memory_id: Origin memory ID (sleep_learn's existing field).
        created_at: Unix epoch. If 0, set to now.
        last_accessed_at: Unix epoch. If 0, set to created_at.
        recall_count: How many times injected/retrieved.
        reinforcement_count: How many times reinforced.
        last_reinforced: Unix epoch of last reinforcement.

    Returns:
        Dict with all unified-schema fields, ready for ChromaDB.
    """
    import time

    # Normalize importance + confidence (both must be present)
    imp, conf = normalize_rule_fields(importance=importance, confidence=confidence)

    # Validate source
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source {source!r}. Must be one of: {sorted(VALID_SOURCES)}")

    # Validate outcome
    if outcome not in VALID_OUTCOMES:
        outcome = "unknown"  # graceful degradation

    # Normalize + validate tags
    normalized_tags = normalize_tags(tags, source)
    is_valid, err = validate_tags(normalized_tags)
    if not is_valid:
        raise ValueError(f"Tag validation failed: {err}")

    # Truncate fields (ChromaDB metadata has practical size limits)
    now = int(time.time())
    created = created_at or now

    return {
        # ── Identity ──
        "type": "procedural",

        # ── Source ──
        "source": source,
        "source_trace_ids": source_trace_ids[:500],  # cap to prevent bloat (minimax)
        "source_memory_id": source_memory_id[:200],

        # ── Quality / Confidence ──
        "importance": imp,
        "confidence": conf,
        "reinforcement_count": reinforcement_count,
        "last_reinforced": last_reinforced or created,

        # ── Context ──
        "goal": goal[:200],
        "outcome": outcome,
        "reasoning": reasoning[:1000],  # cap (mistral's point)
        "tools_used": tools_used[:200],  # kept (mimo's point — rules reference tools)
        "tags": normalized_tags,

        # ── Lifecycle ──
        "created_at": created,
        "last_accessed_at": last_accessed_at or created,
        "recall_count": recall_count,
        "updated_at": 0,  # set by the update action (Commit 1)

        # ── Schema / Version ──
        "version": 1,  # incremented by update action
        "schema_version": SCHEMA_VERSION,
        "provenance_count": len([t for t in source_trace_ids.split(",") if t.strip()]),

        # ── Dedup (write-time only, not for retrieval) ──
        "text_hash": compute_text_hash(text),
    }
