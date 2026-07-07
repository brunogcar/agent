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
