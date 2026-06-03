"""
core/kgraph/queries.py
Read-only queries for the Codebase Knowledge Graph.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore

# Common stop words to ignore when searching
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "in", "on", "at", "to", "of", 
    "is", "it", "this", "that", "fix", "bug", "issue", "add", "create", 
    "implement", "write", "update", "change", "modify", "refactor", "code"
}

def find_relevant_files(project_path: str | Path, query: str, top_k: int = 5) -> List[str]:
    """
    Find files in the project graph whose paths match keywords in the query.
    Returns a list of relative file paths (sorted by relevance/match count).
    """
    pm = ProjectManager(project_path)
    db_path = pm.artifact_root / "kg.db"
    
    if not db_path.exists():
        return []
        
    store = GraphStore(db_path)
    project_id = pm.project_id
    
    # Extract meaningful keywords from the query
    words = re.findall(r'\b[a-zA-Z0-9_]{3,}\b', query.lower())
    keywords = [w for w in words if w not in _STOP_WORDS]
    
    if not keywords:
        return []
        
    # Build a SQL query to find files matching any of the keywords
    conditions = []
    params = [project_id]
    for kw in keywords:
        conditions.append("path LIKE ?")
        params.append(f"%{kw}%")
        
    sql = f"""
        SELECT path FROM nodes 
        WHERE project_id = ? AND type = 'file' AND ({' OR '.join(conditions)})
    """
    
    try:
        rows = store.read(sql, tuple(params))
        # Simple relevance scoring: count how many keywords matched
        scored_files = []
        for row in rows:
            path = row["path"]
            score = sum(1 for kw in keywords if kw in path.lower())
            scored_files.append((score, path))
            
        # Sort by score descending, then by path
        scored_files.sort(key=lambda x: (-x[0], x[1]))
        
        return [path for _, path in scored_files[:top_k]]
    except Exception:
        return []


# --- Phase 6: The "On-Demand Librarian" (Internal Queries) ---
def get_dependencies(project_path: str | Path, file_path: str, max_depth: int = 1) -> list[str]:
    """Get files that the given file imports (outgoing edges)."""
    pm = ProjectManager(project_path)
    db_path = pm.artifact_root / "kg.db"
    if not db_path.exists():
        return []
    
    store = GraphStore(db_path)
    node_id = f"file:{file_path}"
    
    rows = store.read(
        "SELECT target_id FROM edges WHERE project_id = ? AND source_id = ?",
        (pm.project_id, node_id)
    )
    deps = [row["target_id"] for row in rows]
    
    # Filter out raw module names, keep only file paths
    return [d for d in deps if d.endswith(".py")]

def get_callers(project_path: str | Path, file_path: str) -> list[str]:
    """Get files that import the given file (incoming edges)."""
    pm = ProjectManager(project_path)
    db_path = pm.artifact_root / "kg.db"
    if not db_path.exists():
        return []
    
    store = GraphStore(db_path)
    
    # Match against file path or module name
    module_name = file_path.replace("/", ".").replace(".py", "")
    
    rows = store.read(
        """SELECT source_id FROM edges 
           WHERE project_id = ? AND (target_id = ? OR target_id = ?)""",
        (pm.project_id, file_path, module_name)
    )
    
    callers = []
    for row in rows:
        source_id = row["source_id"]
        if source_id.startswith("file:"):
            callers.append(source_id[5:]) # strip "file:"
    return callers
