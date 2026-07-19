"""Audit scan node — walks project_root and collects codebase metrics.

[v3.7 F7] Whole-repo scan for task_type="audit". Collects:
- File list with line counts
- Import dependencies (who imports whom)
- Dead code candidates (files not imported by anyone)
- Complexity hotspots (files with many dependents)
- Missing type hints (functions without -> annotation)

Uses core.kgraph.ast_parser + core.kgraph.queries for dependency analysis.
Falls back to basic file walking if kgraph is not available (lazy import).
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.helpers import _should_skip_node
from workflows.autocode_impl.state import AutocodeState


def _walk_python_files(project_root: str, max_files: int = 200) -> list[dict]:
    """Walk project_root and return a list of .py file dicts.
    
    Returns: [{"path": "rel/path.py", "lines": 42, "size": 1234}, ...]
    Sorted by line count descending (biggest files first).
    """
    root = Path(project_root) if project_root else cfg.agent_root
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache", "memory_db",
                 "workspace", ".understand", ".symbols"}
    
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = Path(dirpath) / fname
            try:
                rel = str(fpath.relative_to(root))
                content = fpath.read_text(encoding="utf-8", errors="replace")
                lines = content.count("\n") + 1
                files.append({
                    "path": rel,
                    "lines": lines,
                    "size": len(content),
                })
            except Exception:
                continue
        if len(files) >= max_files:
            break
    
    files.sort(key=lambda f: f["lines"], reverse=True)
    return files[:max_files]


def _find_dead_code(files: list[dict], project_root: str) -> list[str]:
    """Find .py files that are never imported by any other file.
    
    Uses simple grep-style analysis (not kgraph) for speed.
    Returns: ["rel/path.py", ...] — files with no importers.
    """
    root = Path(project_root) if project_root else cfg.agent_root
    imported = set()
    
    for f in files:
        fpath = root / f["path"]
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.replace(".", "/") + ".py")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.replace(".", "/") + ".py")
        except Exception:
            continue
    
    # A file is "dead" if no other file imports it
    # (excluding __init__.py, main entry points, test files)
    dead = []
    for f in files:
        rel = f["path"]
        if rel.endswith("__init__.py"):
            continue
        if rel.startswith("test_") or rel.endswith("_test.py"):
            continue
        if rel in ("main.py", "server.py", "registry.py", "manage.py"):
            continue
        # Check if any import string contains the module name
        module_name = rel.replace("/", ".").replace(".py", "")
        if module_name not in str(imported) and rel not in imported:
            dead.append(rel)
    
    return dead[:20]  # cap at 20


def _find_missing_type_hints(files: list[dict], project_root: str, max_check: int = 50) -> list[dict]:
    """Find functions missing return type annotations.
    
    Returns: [{"file": "rel/path.py", "function": "foo", "line": 42}, ...]
    """
    root = Path(project_root) if project_root else cfg.agent_root
    missing = []
    
    for f in files[:max_check]:
        fpath = root / f["path"]
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns is None:
                        missing.append({
                            "file": f["path"],
                            "function": node.name,
                            "line": node.lineno,
                        })
        except Exception:
            continue
    
    return missing[:30]  # cap at 30


def node_audit_scan(state: AutocodeState) -> dict:
    """[v3.7 F7] Scan the entire project for audit findings.
    
    Walks project_root, collects file metrics, finds dead code candidates,
    finds missing type hints. Results stored in state["impact"]["audit_scan"].
    """
    if _should_skip_node(state):
        return {}
    
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "")
    tracer.step(tid, "audit_scan", "Starting whole-repo audit scan")
    
    # 1. Walk files
    files = _walk_python_files(project_root, max_files=200)
    total_lines = sum(f["lines"] for f in files)
    tracer.step(tid, "audit_scan", f"Found {len(files)} .py files ({total_lines} lines)")
    
    # 2. Find dead code
    dead_code = _find_dead_code(files, project_root)
    tracer.step(tid, "audit_scan", f"Dead code candidates: {len(dead_code)}")
    
    # 3. Find missing type hints
    missing_hints = _find_missing_type_hints(files, project_root, max_check=50)
    tracer.step(tid, "audit_scan", f"Missing type hints: {len(missing_hints)}")
    
    # 4. Complexity hotspots (top 10 by line count)
    hotspots = files[:10]
    
    # 5. Try kgraph for dependency analysis (optional, lazy)
    dependency_map = {}
    try:
        from core.kgraph.project import ProjectManager
        from core.kgraph.queries import get_callers
        is_agent = str(Path(project_root).resolve()) == str(cfg.agent_root.resolve()) if project_root else True
        pm = ProjectManager(project_root or str(cfg.agent_root), is_agent_root=is_agent)
        # Sample top 5 files for caller analysis
        for f in hotspots[:5]:
            callers = get_callers(pm.path, f["path"])
            if callers:
                dependency_map[f["path"]] = callers[:5]
        tracer.step(tid, "audit_scan", f"Dependency map: {len(dependency_map)} files analyzed")
    except Exception as e:
        tracer.warning(tid, "audit_scan", f"KGraph unavailable (non-fatal): {e}")
    
    scan_results = {
        "total_files": len(files),
        "total_lines": total_lines,
        "files": [{"path": f["path"], "lines": f["lines"]} for f in files[:20]],
        "dead_code_candidates": dead_code,
        "missing_type_hints": missing_hints,
        "complexity_hotspots": [{"path": f["path"], "lines": f["lines"]} for f in hotspots],
        "dependency_map": dependency_map,
    }
    
    tracer.step(tid, "audit_scan", f"Audit scan complete: {len(files)} files, {len(dead_code)} dead, {len(missing_hints)} missing hints")
    
    # Store in impact sub-state
    from workflows.autocode_impl.state import _get_impact
    current_impact = dict(state.get("impact", {}))
    current_impact["audit_scan"] = scan_results
    
    return {
        "impact": current_impact,
        "status": "audit_scan_complete",
    }
