"""
workflows/understand.py
LangGraph workflow for building and updating the Codebase Knowledge Graph.
"""
from __future__ import annotations
import asyncio
import hashlib
import math
import os
from pathlib import Path
from typing import TypedDict, Any
from langgraph.graph import END, StateGraph
from core.config import cfg
from core.tracer import tracer
from core.kgraph.project import ProjectManager, is_same_path
from core.kgraph.storage import GraphStore
from core.kgraph.ast_parser import parse_file_dependencies

class UnderstandState(TypedDict, total=False):
    project_path: str
    is_agent_root: bool
    project_id: str
    artifact_dir: str
    status: str
    files_to_parse: list[tuple[str, str, str, float, int]]  # (full_path, rel_path, hash, mtime, size)
    files_parsed: int
    edges_created: int
    errors: list[str]

def _default_state(project_path: str, is_agent_root: bool = False) -> UnderstandState:
    pm = ProjectManager(project_path, is_agent_root=is_agent_root)
    return {
        "project_path": str(pm.path),
        "is_agent_root": is_agent_root,
        "project_id": pm.project_id,
        "artifact_dir": str(pm.artifact_root),
        "status": "running",
        "files_to_parse": [],
        "files_parsed": 0,
        "edges_created": 0,
        "errors": [],
    }

async def node_init_project(state: UnderstandState) -> dict:
    tid = "understand_init"
    tracer.step(tid, "init", f"Initializing project {state['project_path']}")
    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    
    # Validate source_root exists to prevent silent empty graphs
    if not pm.is_agent_root and not pm.source_root.exists():
        return {"status": "failed", "errors": [f"Source root does not exist: {pm.source_root}. Did the git clone fail?"]}
    
    mode = await asyncio.to_thread(pm.get_indexing_mode)
    if mode == "reject":
        return {"status": "failed", "errors": [f"Project too large for indexing."]}
    
    await asyncio.to_thread(pm.ensure_initialized)
    
    # Initialize GraphStore (ensures schema is created)
    db_path = pm.artifact_root / "kg.db"
    _ = await asyncio.to_thread(GraphStore, db_path)
    
    return {"status": "running"}

async def node_discover_files(state: UnderstandState) -> dict:
    tid = "understand_discover"
    tracer.step(tid, "discover", "Scanning for changed files...")
    
    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)
    
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".understand", "dist", "build", ".pytest_cache"}
    
    def _scan_disk():
        discovered = []
        for root, dirs, files in os.walk(pm.source_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if not f.endswith(".py"):
                    continue
                full_path = Path(root) / f
                try:
                    stat = full_path.stat()
                    if stat.st_size > ProjectManager.MAX_FILE_SIZE_BYTES:
                        continue
                except OSError:
                    continue
                
                rel_path = full_path.relative_to(pm.source_root).as_posix()
                
                # O(N) I/O BOMB FIX: Fast-path validation using mtime and size
                node = store.read(
                    "SELECT content_hash, last_modified, file_size FROM nodes WHERE project_id = ? AND path = ?",
                    (state["project_id"], rel_path)
                )
                
                if node:
                    row = node[0]
                    # Use math.isclose for float precision safety
                    if math.isclose(row["last_modified"], stat.st_mtime, abs_tol=0.001) and row["file_size"] == stat.st_size:
                        continue
                
                # Only compute MD5 if stats changed or file is new
                current_hash = hashlib.md5(full_path.read_bytes()).hexdigest()
                stored_hash = store.get_file_hash(state["project_id"], rel_path)
                
                if current_hash != stored_hash:
                    discovered.append((str(full_path), rel_path, current_hash, stat.st_mtime, stat.st_size))
        return discovered

    files_to_parse = await asyncio.to_thread(_scan_disk)
    tracer.step(tid, "discover", f"Found {len(files_to_parse)} changed/new files.")
    return {"files_to_parse": files_to_parse}

async def node_parse_and_store(state: UnderstandState) -> dict:
    tid = "understand_parse"
    files_to_parse = state.get("files_to_parse", [])
    if not files_to_parse:
        tracer.step(tid, "parse", "No files changed. Graph is up to date.")
        return {"status": "completed"}
        
    tracer.step(tid, "parse", f"Parsing {len(files_to_parse)} changed files...")
    
    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)
    
    parsed = 0
    edges = 0
    errors = []
    
    # Process in batches to avoid overwhelming the thread pool
    batch_size = 10
    for i in range(0, len(files_to_parse), batch_size):
        batch = files_to_parse[i:i+batch_size]
        tasks = []
        for full_path, rel_path, current_hash, mtime, size in batch:
            tasks.append(parse_file_dependencies(state["project_id"], full_path))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (full_path, rel_path, current_hash, mtime, size), deps in zip(batch, results):
            if isinstance(deps, Exception):
                errors.append(f"Failed to parse {rel_path}: {deps}")
                continue
                
            # deps is a frozenset of module names
            target_paths = []
            for dep in deps:
                target_paths.append(dep.replace(".", "/") + ".py")
                target_paths.append(dep)
                
            await asyncio.to_thread(store.upsert_file_graph, state["project_id"], rel_path, current_hash, target_paths, mtime, size)
            parsed += 1
            edges += len(target_paths)
            
    tracer.step(tid, "parse", f"Completed. Parsed {parsed} files, created {edges} edges.")
    return {
        "files_parsed": parsed,
        "edges_created": edges,
        "errors": errors,
        "status": "completed" if not errors else "completed_with_errors"
    }

def build_understand_graph() -> StateGraph:
    workflow = StateGraph(UnderstandState)
    workflow.add_node("node_init_project", node_init_project)
    workflow.add_node("node_discover_files", node_discover_files)
    workflow.add_node("node_parse_and_store", node_parse_and_store)
    
    workflow.set_entry_point("node_init_project")
    workflow.add_edge("node_init_project", "node_discover_files")
    workflow.add_edge("node_discover_files", "node_parse_and_store")
    workflow.add_edge("node_parse_and_store", END)
    
    return workflow.compile()

async def run_understand_workflow(project_path: str, is_agent_root: bool = False) -> dict[str, Any]:
    tid = tracer.new_trace("understand", goal=f"Index codebase at {project_path}")
    try:
        graph = build_understand_graph()
        initial_state = _default_state(project_path, is_agent_root=is_agent_root)
        final_state = await graph.ainvoke(initial_state)
        
        tracer.finish(tid, success=final_state["status"] == "completed", result=final_state)
        return final_state
    except Exception as e:
        tracer.error(tid, "understand", f"Workflow failed: {e}")
        tracer.finish(tid, success=False, result=str(e))
        return {"status": "failed", "errors": [str(e)]}

def run_understand_workflow_sync(project_path: str, is_agent_root: bool = False) -> dict[str, Any]:
    """
    Synchronous wrapper for run_understand_workflow.
    Prevents RuntimeError when called from an already-running async event loop (e.g., FastMCP).
    """
    import concurrent.futures
    import asyncio
    
    def _run_async():
        graph = build_understand_graph()
        initial_state = _default_state(project_path, is_agent_root=is_agent_root)
        # Create a new event loop for this thread to avoid "event loop is already running"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(graph.ainvoke(initial_state))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_run_async)
        return future.result()