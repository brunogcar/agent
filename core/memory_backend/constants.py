"""
core/memory_backend/constants.py — Memory system constants and thresholds.
"""

# ── Collection Names ──────────────────────────────────────────────────────────
COLLECTION_EPISODIC   = "episodic"
COLLECTION_SEMANTIC   = "semantic"
COLLECTION_PROCEDURAL = "procedural"
ALL_COLLECTIONS       = [COLLECTION_EPISODIC, COLLECTION_SEMANTIC, COLLECTION_PROCEDURAL]

# ── Metadata Fields ───────────────────────────────────────────────────────────
# Fields stored in ChromaDB metadata
META_FIELDS = [
    "type", "importance", "tags", "timestamp",
    "trace_id", "goal", "outcome", "tools_used", "source",
    "text_hash", "reinforcement_count", "workflow_id",  # New fields for Phase 3/6
]

# ── Deduplication Thresholds ──────────────────────────────────────────────────
# Per-collection dedup thresholds (cosine distance, lower is more similar):
#   episodic:   0.05 -- only skip near-identical event logs
#   semantic:   0.15 -- bumped from 0.12 to allow slight variance in report chunks
#   procedural: 0.08 -- skip near-identical fix patterns
DEFAULT_DEDUP_THRESHOLDS = {
    COLLECTION_EPISODIC:    0.05,
    COLLECTION_SEMANTIC:    0.15,
    COLLECTION_PROCEDURAL:  0.08,
}

# ── Contextual Feedback Limits ────────────────────────────────────────────────
MAX_DUPLICATE_PREVIEW_CHARS = 200