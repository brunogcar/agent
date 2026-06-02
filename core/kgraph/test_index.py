"""
core/kgraph/test_index.py
Handles persistent storage and hybrid validation (mtime + size + md5) of the test index.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Dict, Any

def _calculate_md5(file_path: Path) -> str:
    """Calculate MD5 hash of a file efficiently."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def load_test_index(project_path: Path) -> Dict[str, Any]:
    """Load the test index from .understand/test_index.json."""
    index_path = project_path / ".understand" / "test_index.json"
    empty_index = {"version": 1, "project_path": str(project_path.resolve()), "entries": {}}
    
    if not index_path.exists():
        return empty_index
        
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        # Validate project path to prevent cross-project contamination
        if data.get("project_path") != str(project_path.resolve()):
            return empty_index
        return data
    except (json.JSONDecodeError, OSError):
        return empty_index

def save_test_index(project_path: Path, index: Dict[str, Any]) -> None:
    """Save the test index atomically to prevent corruption on crash."""
    index_path = project_path / ".understand" / "test_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Atomic write: write to temp file, then replace
    temp_path = index_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    temp_path.replace(index_path)

async def validate_and_update_entry(entry: Dict[str, Any], file_path: Path) -> bool:
    """
    Validates if a cached entry is still valid.
    Uses mtime+size as a fast path, and md5 as the authoritative slow path.
    Returns True if the cached targets are still valid. Updates entry in-place.
    """
    if not file_path.exists():
        return False
        
    stat = file_path.stat()
    current_mtime = stat.st_mtime
    current_size = stat.st_size
    
    # Fast path: mtime and size match
    if entry.get("mtime") == current_mtime and entry.get("size") == current_size:
        return True
        
    # Slow path: content might have changed (or just mtime changed like git checkout)
    current_md5 = _calculate_md5(file_path)
    if entry.get("md5") == current_md5:
        # Content is identical, just update mtime/size to prevent future slow paths
        entry["mtime"] = current_mtime
        entry["size"] = current_size
        return True
        
    # Content actually changed
    entry["mtime"] = current_mtime
    entry["size"] = current_size
    entry["md5"] = current_md5
    return False
