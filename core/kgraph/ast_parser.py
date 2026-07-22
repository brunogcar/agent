"""
core/kgraph/ast_parser.py
Dedicated, bounded AST parsing to prevent event loop blocking and memory leaks.

[#4] Now delegates to tree-sitter for multi-language support. The public API
is unchanged — _parse_dependencies_sync_from_string() still works for Python.
New code should use core.kgraph.tree_sitter_parser directly for multi-language.
"""
from __future__ import annotations
import ast
import hashlib
import asyncio
from pathlib import Path
from typing import FrozenSet
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

from core.kgraph.tree_sitter_parser import extract_imports as _ts_extract_imports

# Dedicated thread pool for CPU-bound AST work
_AST_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="ast_parser_"
)

@lru_cache(maxsize=512)
def _parse_file_dependencies_sync(project_id: str, file_path: str, md5_hash: str) -> FrozenSet[str]:
    """
    Synchronous AST parser. 
    Cached by (project_id, path, md5) to prevent cross-project collisions and ensure invalidation.
    Returns only a lightweight frozenset of dependencies, not the AST tree.
    """
    path = Path(file_path)
    if not path.exists():
        return frozenset()
    
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
        
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.add(node.module)
                    
        return frozenset(deps)
    except (SyntaxError, RecursionError, MemoryError, UnicodeDecodeError):
        return frozenset()  # Graceful fallback

async def parse_file_dependencies(project_id: str, file_path: str | Path) -> FrozenSet[str]:
    """Async wrapper that offloads CPU-bound parsing to the dedicated executor.

    v1.0: Uses the ORIGINAL file_path (not resolved) as the cache key.
    This ensures cache hits when the project moves to a different absolute
    path — the relative path + content hash are the same, so the cache
    should hit. The resolved path is still used for file I/O.
    """
    original_path = str(file_path)  # keep original (may be relative) for cache key
    path = Path(file_path).resolve()
    if not path.exists():
        return frozenset()
    
    # Fast hash for cache key
    try:
        content = path.read_bytes()
        md5_hash = hashlib.md5(content).hexdigest()
    except OSError:
        return frozenset()
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _AST_EXECUTOR,
        _parse_file_dependencies_sync,
        project_id,
        original_path,  # v1.0: cache key uses original path (relative if passed)
        md5_hash
    )

def clear_ast_cache() -> None:
    """Clear the LRU cache (useful for testing or major refactors)."""
    _parse_file_dependencies_sync.cache_clear()


# --- Phase 6: Parse from string (for micro-updates from state) ---
def _parse_dependencies_sync_from_string(content: str) -> frozenset[str]:
    """Extract Python imports from source string.

    [#4] Now uses tree-sitter under the hood for consistency with multi-language
    support. Returns the same frozenset of dotted module names as before.
    """
    return _ts_extract_imports(content, "python")

# [v1.9.2] Cache key is (project_id, content_hash) — NOT content.
# Was: content was a param = held in LRU = memory bloat for 512 entries.
# Now: content_hash uniquely identifies content; content passed via closure.
@lru_cache(maxsize=512)
def _parse_dependencies_cached(project_id: str, content_hash: str, content: str = "") -> frozenset[str]:
    return _parse_dependencies_sync_from_string(content)

async def parse_dependencies_from_string(project_id: str, content: str) -> frozenset[str]:
    """Parse dependencies from a string content (used for state-based micro-updates)."""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _AST_EXECUTOR,
        _parse_dependencies_cached,
        project_id,
        content_hash,
        content
    )
