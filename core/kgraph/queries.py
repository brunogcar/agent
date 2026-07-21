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
from core.kgraph.tree_sitter_parser import ALL_SUPPORTED_EXTENSIONS

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
    """Get files that the given file imports (outgoing edges).

    [v1.4.1 P1-2] Multi-language fix — was: `d.endswith(".py")` filter,
    which silently dropped every JS/TS/Go/Rust/Java/... dependency edge
    (a regression introduced when v1.2 added multi-language parsing but
    `get_dependencies` was never updated). The graph stores BOTH raw
    module-name forms (e.g. "core.config" for Python, "react" for JS,
    "std::collections::HashMap" for Rust) AND file-path forms (e.g.
    "core/config.py" — added by parse_and_store's
    `dep.replace(".", "/") + ".py"` Python-only path).

    New filter: keep any target_id that (a) looks like a file path (contains
    a `/` or `\\`) OR (b) ends with any of the supported code extensions.
    Raw module names with no path component and no recognized extension
    (rare — only happens when a language's import path doesn't map to a
    file, e.g. Rust `std::collections::HashMap`) are also kept because
    they're useful for cross-language understanding and impact analysis.
    """
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

    # [v1.4.1 P1-2] Keep file-path-like + recognized-extension targets.
    # Drop empty strings + tree-sitter error sentinels (defensive).
    out: list[str] = []
    for d in deps:
        if not d:
            continue
        # File-path form (contains a path separator) — always keep.
        if "/" in d or "\\" in d:
            out.append(d)
            continue
        # Recognized extension — keep (covers "core/config.py" without a slash,
        # "app.ts", "main.go", etc.).
        lowered = d.lower()
        if any(lowered.endswith(ext) for ext in ALL_SUPPORTED_EXTENSIONS):
            out.append(d)
            continue
        # Raw module name (no slash, no recognized extension) — keep too.
        # These are cross-language import strings: "react", "fmt",
        # "std::collections::HashMap", "core.config". Useful for impact
        # analysis even though they don't map 1:1 to a file.
        out.append(d)
    return out

def get_callers(project_path: str | Path, file_path: str) -> list[str]:
    """Get files that import the given file (incoming edges).

    [v1.4.1 P1-2] Multi-language fix — was: `module_name = file_path.replace("/",
    ".").replace(".py", "")` (Python-only). The Python-specific module-name
    form is what `parse_and_store` adds as a target_id when it sees
    `from core.config import cfg` → target_id "core.config". For JS/TS/Go/Rust,
    the import strings are paths (e.g. "./utils", "react", "fmt",
    "std::collections::HashMap") — they don't get a `.replace()`-form twin.

    New approach: query for BOTH the raw `file_path` (covers JS/TS/Go/Rust
    where imports ARE paths) AND a Python-style module-name transformation
    (covers the Python `dep.replace(".", "/") + ".py"` inverse). The
    transformation strips any supported extension from the file_path,
    then converts `/` → `.`. For non-Python files this produces a string
    that just won't match any stored edge (harmless — the SQL OR absorbs
    it). For Python files it produces the canonical dotted module name.
    """
    pm = ProjectManager(project_path)
    db_path = pm.artifact_root / "kg.db"
    if not db_path.exists():
        return []

    store = GraphStore(db_path)

    # [v1.4.1 P1-2] Build candidate target_id forms from the file_path.
    # Different languages store different target_id forms in the edges table:
    #   - Python: "core.config" (module name) AND "core/config.py" (file path)
    #   - JS/TS:  "./utils" (relative import path)
    #   - Go:     "fmt", "myapp/utils" (package path)
    #   - Rust:   "std::collections::HashMap" (crate path)
    #
    # We query for ALL of these forms and let the SQL OR find the match:
    #   1. file_path verbatim ("core/config.py" — matches Python file-path form)
    #   2. module_name ("core.config" — matches Python module-name form)
    #   3. ./module_name ("./utils" — matches JS/TS relative-import form)
    #   4. module_name without leading "./" (catches "utils" from "./utils")
    module_name = file_path
    for ext in ALL_SUPPORTED_EXTENSIONS:
        if module_name.endswith(ext):
            module_name = module_name[: -len(ext)]
            break
    # Python-style: "core/config" → "core.config"
    py_module_name = module_name.replace("/", ".").lstrip(".")
    # JS/TS-style: "./utils" (relative import prefix)
    js_relative_name = "./" + module_name.lstrip("./")

    rows = store.read(
        """SELECT source_id FROM edges 
           WHERE project_id = ? AND (
               target_id = ? OR target_id = ? OR target_id = ? OR target_id = ?
           )""",
        (pm.project_id, file_path, py_module_name, js_relative_name, module_name.lstrip("./"))
    )

    callers = []
    for row in rows:
        source_id = row["source_id"]
        if source_id.startswith("file:"):
            callers.append(source_id[5:]) # strip "file:"
    return callers
