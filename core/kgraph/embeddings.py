"""core/kgraph/embeddings.py — Code embedding via LM Studio + AST-based chunking.

[#3] ChromaDB vector indexing for the understand workflow.

Two responsibilities:
  1. extract_definitions(content) — AST-based chunking: split Python source
     into top-level definitions (functions, classes, module docstring).
     Each definition becomes one vector with metadata (file, name, type, lines).

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

import ast
from typing import Optional

from core.config import cfg
from core.tracer import tracer


# ─── AST-based chunking ─────────────────────────────────────────────────────

def extract_definitions(content: str) -> list[dict]:
    """Split Python source into top-level definitions for embedding.

    Each definition is a dict:
      {name, type, source, line_start, line_end}

    Types: "module" (docstring), "function", "class".

    Falls back to a single "module" chunk with the full content if the file
    has no top-level definitions (e.g. scripts, __init__.py).
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Can't parse — return the whole file as one chunk so it's still searchable
        return [{
            "name": "<module>",
            "type": "module",
            "source": content,
            "line_start": 1,
            "line_end": len(content.splitlines()),
        }]

    definitions = []

    # Module-level docstring as a "module" chunk
    if (tree.body and isinstance(tree.body[0], ast.Expr) and
        isinstance(tree.body[0].value, ast.Constant) and
        isinstance(tree.body[0].value.value, str)):
        doc = tree.body[0].value.value
        if doc.strip():
            definitions.append({
                "name": "<module>",
                "type": "module",
                "source": doc,
                "line_start": 1,
                "line_end": len(doc.splitlines()),
            })

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            source = ast.get_source_segment(content, node) or ""
            if source.strip():
                definitions.append({
                    "name": node.name,
                    "type": "function",
                    "source": source,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno) or node.lineno,
                })
        elif isinstance(node, ast.ClassDef):
            source = ast.get_source_segment(content, node) or ""
            if source.strip():
                definitions.append({
                    "name": node.name,
                    "type": "class",
                    "source": source,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno) or node.lineno,
                })

    # Fallback: if no definitions found, embed the whole file
    if not definitions:
        definitions.append({
            "name": "<module>",
            "type": "module",
            "source": content[:4000],  # cap to prevent oversized embeddings
            "line_start": 1,
            "line_end": len(content.splitlines()),
        })

    return definitions


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
