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

def embed_texts(texts: list[str], trace_id: str = "") -> Optional[list[list[float]]]:
    """Embed a list of texts via LM Studio's /v1/embeddings endpoint.

    Returns a list of vectors (one per text), or None on failure.
    None signals the caller to skip vector storage (graceful degradation).

    Uses httpx with a 30s timeout. Batches all texts in one API call
    (OpenAI-compatible endpoints support `"input": [text1, text2, ...]`).
    """
    if not cfg.embedding_enabled:
        return None

    if not texts:
        return []

    import httpx

    url = f"{cfg.embedding_base_url.rstrip('/')}/embeddings"

    try:
        resp = httpx.post(
            url,
            json={
                "model": cfg.embedding_model,
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
    - line_start/line_end: 0/0 (chonkie chunks don't have reliable line numbers)

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
                    "line_start": 0,
                    "line_end": 0,
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
        "line_start": 0,
        "line_end": 0,
    }]
