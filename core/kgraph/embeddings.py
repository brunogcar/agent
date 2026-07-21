"""core/kgraph/embeddings.py — Code embedding via LM Studio + tree-sitter chunking.

[#3] ChromaDB vector indexing for the understand workflow.
[#4] Multi-language support via tree-sitter (Python, JS/TS, Go, Rust).

Two responsibilities:
  1. extract_definitions(content, language) — tree-sitter chunking: split source
     into top-level definitions (functions, classes). Each definition becomes
     one vector with metadata (file, name, type, lines).

  2. embed_texts(texts) — call LM Studio's /v1/embeddings endpoint
     (OpenAI-compatible) to generate vectors. Returns None on failure
     so the caller can degrade gracefully (skip vectors, keep graph edges).

Config (via .env):
  EMBEDDING_MODEL    — model name as shown in LM Studio (default: all-MiniLM-L6-v2-GGUF)
  EMBEDDING_BASE_URL — endpoint URL (default: same as LM_STUDIO_BASE_URL)
  EMBEDDING_ENABLED  — "false" to disable entirely (default: "true")

Recommended GGUF model: https://huggingface.co/second-state/All-MiniLM-L6-v2-Embedding-GGUF
  (q8 = 25MB, loads in LM Studio under Models → Embeddings)
"""
from __future__ import annotations

import hashlib
from typing import Optional

from core.config import cfg
from core.tracer import tracer
from core.kgraph.tree_sitter_parser import extract_definitions_ts


# ─── Definition extraction (delegates to tree-sitter) ──────────────────────

def extract_definitions(content: str, language: str = "python") -> list[dict]:
    """Split source code into top-level definitions for embedding.

    [#4] Now uses tree-sitter for multi-language support. Defaults to Python
    for backward compatibility — callers should pass the language explicitly
    when parsing non-Python files.

    Each definition is a dict: {name, type, source, line_start, line_end}
    Types: "function", "class", "type", "module" (fallback for files with no defs).

    Falls back to a single "module" chunk if the file has no parseable definitions.
    """
    return extract_definitions_ts(content, language)


# ─── LM Studio embedding client ─────────────────────────────────────────────

# v1.4: Module-level flag — once embedding fails, skip all subsequent calls
# in this session (avoids 965 × 30s timeouts when LM Studio is down).
_embedding_available: Optional[bool] = None

# [v1.7] Module-level embedding cache. Keyed by md5(text) so identical texts
# (same source code chunk seen in two files, or re-embeds after a metadata
# change) don't re-hit LM Studio. The cache is process-local — it doesn't
# persist across restarts, and it's not shared between worker processes.
#
# Cache cap: 10000 entries (an arbitrary ceiling to prevent unbounded growth
# on huge codebases). When the cap is exceeded, the entire cache is cleared
# (simplest correct behavior — an LRU would be more precise but adds
# complexity for ~rare benefit, since the cap is hit only on codebases with
# >10k unique definitions, which re-walk from scratch in ~30s anyway).
_embedding_cache: dict[str, list[float]] = {}
_EMBEDDING_CACHE_CAP = 10000


def clear_embedding_cache() -> None:
    """[v1.7] Clear the embedding cache. For testing + memory management.

    Tests call this between cases so cached embeddings from one test don't
    affect the next. Operators with very long-running processes could call
    this (via the MCP introspect API) to free memory.
    """
    _embedding_cache.clear()


def _maybe_evict_cache() -> None:
    """[v1.7] Clear the cache if it has exceeded the cap.

    Called after every successful embed. The check is O(1) (dict.__len__);
    the clear is O(n) but only happens at the cap (rare).
    """
    if len(_embedding_cache) > _EMBEDDING_CACHE_CAP:
        _embedding_cache.clear()


def is_embedding_available() -> bool:
    """v1.4: Check if LM Studio embedding endpoint is reachable.

    Caches the result — once it returns False, all subsequent embed_texts()
    calls skip the HTTP request and return None immediately. This prevents
    965 × 30s timeouts when indexing a large project with LM Studio down.

    Resets on process restart (module reload).
    """
    global _embedding_available
    if _embedding_available is not None:
        return _embedding_available

    if not cfg.embedding_enabled:
        _embedding_available = False
        return False

    import httpx
    try:
        resp = httpx.get(
            f"{cfg.embedding_base_url.rstrip('/')}/models",
            timeout=5.0,
        )
        _embedding_available = resp.status_code == 200
    except Exception:
        _embedding_available = False

    return _embedding_available


def reset_embedding_check() -> None:
    """Reset the cached embedding availability (for testing)."""
    global _embedding_available
    _embedding_available = None


def embed_texts(
    texts: list[str],
    trace_id: str = "",
    model: str = "",
) -> Optional[list[list[float]]]:
    """Embed a list of texts via LM Studio's /v1/embeddings endpoint.

    Returns a list of vectors (one per text), or None on failure.
    None signals the caller to skip vector storage (graceful degradation).

    Uses httpx with a 30s timeout. Batches all texts in one API call
    (OpenAI-compatible endpoints support `"input": [text1, text2, ...]`).

    [v1.7] Embedding cache — keyed by md5(text). Cache hits skip the HTTP
    call entirely. If SOME texts are cached and others aren't, only the
    uncached ones hit LM Studio (the cached ones are merged back into the
    result list in their original positions). The cache is process-local
    + capped at 10000 entries (clear when exceeded).

    [v1.7] Per-project model — the optional `model` parameter overrides
    cfg.embedding_model. When empty (default), uses cfg.embedding_model
    (backward compat). Callers with a per-project config (ProjectManager.
    get_embedding_model()) should pass it here.
    """
    if not cfg.embedding_enabled:
        return None

    # [v1.4.1] Empty-list short-circuit BEFORE the availability check.
    # Was: the availability check ran first, so embed_texts([]) returned None
    # when LM Studio was down — but an empty input should always succeed
    # (there's nothing to embed). Tests that assert embed_texts([]) == []
    # now pass regardless of LM Studio availability.
    if not texts:
        return []

    # v1.4: Skip if embedding service is known to be unavailable (cached check)
    if not is_embedding_available():
        return None

    # [v1.7] Resolve the model — explicit parameter wins, else cfg default.
    effective_model = model or cfg.embedding_model

    # [v1.7] Cache lookup. Compute md5(text) for each text; collect cached
    # vectors + the indices of texts that still need embedding. The cache key
    # is md5(text) (not text itself) so very long source chunks don't bloat
    # the dict keys.
    cache_keys = [hashlib.md5(t.encode("utf-8")).hexdigest() for t in texts]
    cached: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    for i, key in enumerate(cache_keys):
        if key in _embedding_cache:
            cached[i] = _embedding_cache[key]
        else:
            uncached_indices.append(i)

    # All cache hits — return early without hitting LM Studio.
    if not uncached_indices:
        # All entries are non-None here (cache stores only successful embeds).
        return cached  # type: ignore[return-value]

    # Embed only the uncached texts.
    uncached_texts = [texts[i] for i in uncached_indices]
    new_embeddings = _embed_via_http(uncached_texts, effective_model, trace_id)
    if new_embeddings is None:
        # HTTP failure — don't return partial cache. Callers expect either
        # the full list or None (graceful degradation). Returning partial
        # results would let a stale-cache hit mask a real LM Studio outage.
        return None

    # Merge new embeddings back into the cached list + store in the cache.
    for idx, emb in zip(uncached_indices, new_embeddings):
        cached[idx] = emb
        _embedding_cache[cache_keys[idx]] = emb

    # Evict if the cache has grown past the cap.
    _maybe_evict_cache()

    return cached  # type: ignore[return-value]


def _embed_via_http(
    texts: list[str],
    model: str,
    trace_id: str,
) -> Optional[list[list[float]]]:
    """[v1.7] Pure HTTP call — extracted from embed_texts() so the cache layer
    can wrap it cleanly.

    Returns the list of embeddings (one per text) or None on failure.
    Does NOT interact with the cache — the caller handles cache reads/writes.
    """
    import httpx

    url = f"{cfg.embedding_base_url.rstrip('/')}/embeddings"

    try:
        resp = httpx.post(
            url,
            json={
                "model": model,
                "input": texts,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI-compatible response: {"data": [{"embedding": [...]}, ...]}
        embeddings = [item["embedding"] for item in data["data"]]
        return embeddings
    except Exception as e:
        tracer.warning(
            trace_id, "embeddings",
            f"Embedding failed (LM Studio not running or model not loaded?): {e}"
        )
        return None


# ─── Document chunking (v1.3 — chonkie for prose) ──────────────────────────

def extract_doc_chunks(content: str, file_path: str = "", trace_id: str = "") -> list[dict]:
    """v1.3: Split a document (.md/.txt/.rst) into sentence-aware chunks for embedding.

    Uses chonkie SentenceChunker (lazy import — soft dependency). Falls back to
    a single "doc" chunk containing the whole file if chonkie is not installed
    or chunking fails. This mirrors the extract_definitions() fallback pattern
    for code files with no parseable definitions.

    Returns the same dict shape as extract_definitions() so upsert_file_vectors()
    can consume it without modification:
      {name, type, source, line_start, line_end}
    - name: "doc_chunk_N_of_M" (N=0-based, M=total chunks)
    - type: "doc" (vs "function"/"class"/"module" for code)
    - source: the chunk text
    - line_start/line_end: 1-based line range of the chunk in the original file
      (v1.4.1 P2-3 — was: 0/0 because chonkie chunks don't expose line numbers
      directly. Now computed by scanning the original content for the chunk's
      first character. Falls back to 0/0 if the chunk text isn't found, e.g.
      when chonkie normalizes whitespace.)

    Args:
        content: The document text.
        file_path: Relative file path (for logging only).
        trace_id: For trace logging.
    """
    if not content or not content.strip():
        return [{
            "name": "doc_chunk_0_of_1",
            "type": "doc",
            "source": content or "",
            "line_start": 0,
            "line_end": 0,
        }]

    # Try chonkie sentence chunking
    try:
        from tools.file_ops.actions.read_file import _chunk_text
        chunks = _chunk_text(content, "sentence", 512)
        if chunks and len(chunks) > 0:
            total = len(chunks)
            return [
                {
                    "name": f"doc_chunk_{i}_of_{total}",
                    "type": "doc",
                    "source": chunk,
                    "line_start": _line_start_for_chunk(content, chunk),
                    "line_end": _line_end_for_chunk(content, chunk),
                }
                for i, chunk in enumerate(chunks)
            ]
    except Exception as e:
        if trace_id:
            tracer.warning(
                trace_id, "embeddings",
                f"Chonkie chunking failed for {file_path} — using single doc chunk: {e}"
            )

    # Fallback: single chunk with the whole doc
    return [{
        "name": "doc_chunk_0_of_1",
        "type": "doc",
        "source": content,
        "line_start": 1,
        "line_end": len(content.splitlines()) or 1,
    }]


def _line_start_for_chunk(content: str, chunk_text: str) -> int:
    """[v1.4.1 P2-3] Compute the 1-based line number where a chunk begins.

    Scans the original content for the chunk's first character. Returns 0
    if the chunk text isn't found (chonkie may normalize whitespace).
    """
    if not chunk_text:
        return 0
    idx = content.find(chunk_text)
    if idx == -1:
        # Chonkie normalized whitespace — try matching just the first non-empty
        # line of the chunk. Worst case we fall back to 0.
        first_line = next((ln for ln in chunk_text.splitlines() if ln.strip()), "")
        if not first_line:
            return 0
        idx = content.find(first_line)
        if idx == -1:
            return 0
    return content[:idx].count("\n") + 1


def _line_end_for_chunk(content: str, chunk_text: str) -> int:
    """[v1.4.1 P2-3] Compute the 1-based line number where a chunk ends.

    = line_start + (newlines inside the chunk). Falls back to line_start
    when the chunk can't be located.
    """
    if not chunk_text:
        return 0
    start = _line_start_for_chunk(content, chunk_text)
    if start == 0:
        return 0
    return start + chunk_text.count("\n")
