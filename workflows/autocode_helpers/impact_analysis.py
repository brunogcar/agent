"""
workflows/autocode_helpers/impact_analysis.py
AST-based dependency mapper for impact analysis.
Runs in a separate thread to avoid blocking the async event loop.
"""
from __future__ import annotations
import ast
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any
from functools import lru_cache

def _compute_file_hash(file_path: str) -> str:
    """Compute MD5 hash of file contents for cache invalidation."""
    try:
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""

@lru_cache(maxsize=1024)
def _parse_ast_sync(file_path: str, file_hash: str) -> Dict[str, Any]:
    """
    Synchronous AST parsing logic, to be run in a thread.
    Cached via LRU to prevent memory leaks. Keyed by path + hash for auto-invalidation.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return {"status": "failed", "reason": "File not found", "imports": [], "defines": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(path))
        imports = []
        defines = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defines.append(node.name)
                
        return {
            "status": "success",
            "imports": list(set(imports)),
            "defines": list(set(defines))
        }
    except SyntaxError as e:
        return {"status": "failed", "reason": f"SyntaxError: {e}", "imports": [], "defines": []}
    except (RecursionError, MemoryError) as e:
        return {"status": "failed", "reason": f"ResourceError: {e}", "imports": [], "defines": []}
    except Exception as e:
        return {"status": "failed", "reason": str(e), "imports": [], "defines": []}

async def get_file_dependencies(file_path: str) -> Dict[str, Any]:
    """Parse a Python file and extract its imports and defined symbols."""
    path = str(Path(file_path).resolve())
    current_hash = _compute_file_hash(path)
    
    # Run CPU-bound AST parsing in a separate thread
    # The lru_cache inside _parse_ast_sync handles memory bounds and invalidation
    result = await asyncio.to_thread(_parse_ast_sync, path, current_hash)
    return result

def clear_ast_cache():
    """Utility to clear cache if needed."""
    _parse_ast_sync.cache_clear()
