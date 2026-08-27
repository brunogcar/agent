"""Shared fixtures for core/memory tests.

[fast-tests] Replaces ChromaDB's DefaultEmbeddingFunction (which loads a
~90MB ONNX model of all-MiniLM-L6-v2) with a lightweight dummy that returns
fixed-length zero vectors. This skips the real embedding computation so
tests that call memory.store_procedural() / col.query() / col.add() run
in <1s instead of 30-40s (the one-time model download + load cost).

The dummy is applied to ALL collections (episodic, semantic, procedural,
atomic) on the singleton memory store. It's applied via an autouse fixture
so every test in this directory benefits without needing to opt in.

The dummy preserves the ChromaDB EmbeddingFunction protocol so add/query
work normally — they just use zero vectors instead of real embeddings.
For tests that check clustering behavior (test_diversity_contradiction_guard),
the test itself mocks col.query to return synthetic results, so the dummy
embedding function doesn't affect the assertions.
"""
from __future__ import annotations

import pytest


class _DummyEmbeddingFunction:
    """Drop-in replacement for ChromaDB's DefaultEmbeddingFunction.

    Returns deterministic 384-dim vectors derived from the text's SHA-256
    hash (NOT zero vectors — zero vectors make every document appear
    identical, which breaks the hash guard + dedup tests that expect
    different texts to have different embeddings).

    Using a hash-based vector means:
      - Same text → same vector (dedup works correctly)
      - Different text → different vector (no false semantic matches)
      - No model download/load (instant computation)

    Tests that need specific clustering behavior (test_diversity_contradiction_guard)
    mock col.query directly, so the dummy embedding function doesn't
    affect their assertions.

    [interface] ChromaDB's EmbeddingFunction protocol expects:
      - __call__(input: Documents) -> Embeddings  (batch: list[str] -> list[list[float]])
      - embed_query(input: str) -> Embeddings      (single query -> list[list[float]])
    Note: embed_query must return a LIST of vectors (one per query), NOT a
    single flat vector — the rust bindings iterate over the outer list.
    """

    import hashlib

    @staticmethod
    def _as_list(input) -> list[str]:
        """Normalize input to a list of strings (handles both single str and list)."""
        if isinstance(input, str):
            return [input]
        return list(input)

    def _hash_vec(self, text: str) -> list[float]:
        """Derive a deterministic 384-dim vector from text via SHA-256.

        Text is lowercased + stripped before hashing so that minor query
        rewrites (e.g. _rewrite_query lowercasing + filler removal) still
        produce a similar-enough vector for the delete/recall threshold.
        This mirrors how real embedding models are case-insensitive.
        """
        normalized = text.lower().strip()
        h = self.hashlib.sha256(normalized.encode("utf-8")).digest()
        # Repeat the 32-byte hash to fill 384 dims (32*12=384)
        repeated = (h * 12)[:384]
        return [b / 255.0 for b in repeated]

    def __call__(self, input):
        # input is a list of strings (Documents) — chromadb passes the full batch
        docs = self._as_list(input)
        return [self._hash_vec(text) for text in docs]

    def embed_query(self, input):
        # chromadb passes the full query_texts list here (not a single string).
        # Return one vector per query text.
        docs = self._as_list(input)
        return [self._hash_vec(text) for text in docs]

    def embed_documents(self, input):
        docs = self._as_list(input)
        return [self._hash_vec(text) for text in docs]

    def name(self):
        return "dummy-test-ef"

    # ChromaDB 1.x checks for these attributes on the embedding function
    is_legacy = False
    default_space = "cosine"
    supported_spaces = ["cosine", "l2", "ip"]

    def build_from_config(self, config):
        return self

    def get_config(self):
        return {}

    def validate_config(self, config):
        pass

    def validate_config_update(self, config):
        pass

    def max_tokens(self):
        return 256


@pytest.fixture(autouse=True)
def _fast_embedding_function():
    """Replace ChromaDB's embedding function with a fast dummy + clean state.

    This fixture is autouse so every test in tests/core/memory/ gets the
    fast embedding function. It patches the _embedding_function attribute
    on each collection of the singleton memory store.

    Without this, the first test that calls col.add() or col.query() pays
    a 30-40s one-time cost to download + load the all-MiniLM-L6-v2 ONNX
    model. With the dummy, all embedding operations are instant.

    Also clears all collections + hash cache before each test so tests
    start from a clean state (no leftover data from previous runs in the
    persistent ChromaDB). Without this, test_diversity_contradiction_guard
    fails because procedural memories from test_diversity_dry_run_returns_metrics
    leak through (prune skips the procedural collection by design).
    """
    try:
        import chromadb  # noqa: F401
    except ImportError:
        # chromadb not installed — skip patching (tests that import
        # core.memory_engine will fail at collection time, which is
        # the expected behavior without the optional dependency).
        yield
        return

    fast_ef = _DummyEmbeddingFunction()

    from core.memory_engine import memory

    original_efs = {}
    for col_name, col in memory._collections.items():
        original_efs[col_name] = col._embedding_function
        col._embedding_function = fast_ef

    # Clean slate: delete all documents from every collection + reset the
    # hash cache. This prevents leftover data from previous test runs
    # (stored in the persistent ChromaDB) from causing false duplicates
    # or polluting diversity/clustering assertions.
    for col_name, col in memory._collections.items():
        try:
            data = col.get(include=[])
            ids = data.get("ids", [])
            if ids:
                col.delete(ids=ids)
        except Exception:
            pass
    memory._hash_cache.clear()

    yield

    # Restore original embedding functions
    for col_name, col in memory._collections.items():
        if col_name in original_efs:
            col._embedding_function = original_efs[col_name]
