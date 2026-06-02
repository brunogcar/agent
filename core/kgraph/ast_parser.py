"""
core/kgraph/ast_parser.py
Dedicated, bounded AST parsing to prevent event loop blocking and memory leaks.
"""
from __future__ import annotations
import ast
import hashlib
import asyncio
from pathlib import Path
from typing import FrozenSet
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

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
    """Async wrapper that offloads CPU-bound parsing to the dedicated executor."""
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
        str(path),
        md5_hash
    )

def clear_ast_cache() -> None:
    """Clear the LRU cache (useful for testing or major refactors)."""
    _parse_file_dependencies_sync.cache_clear()
