"""
workflows/understand.py — LangGraph workflow for building and updating the Codebase Knowledge Graph.

v1.0: Converted from async to sync nodes. Now routes through base.py's standard
graph.invoke() path, giving it checkpoint/resume support and trace_id propagation
like all other workflows.

[ARCHITECTURE CHANGE] Previously used async nodes (async def) + a dangerous
ThreadPoolExecutor + new_event_loop() sync facade. Now uses sync nodes (def)
like research, data, autocode, and deep_research. The async parse_file_dependencies()
is replaced with the sync _parse_dependencies_sync_from_string() directly.

[FUTURE] When multi-language support is added (JavaScript, TypeScript, Go),
the node_parse_and_store node will need to dispatch to language-specific parsers.
The current architecture (sync nodes, batch processing) supports this cleanly.
"""
from __future__ import annotations
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
from core.kgraph.ast_parser import _parse_dependencies_sync_from_string


class UnderstandState(TypedDict, total=False):
    project_path: str
    is_agent_root: bool
    project_id: str
    artifact_dir: str
    trace_id: str  # [Bug #2] Added — was missing, nodes couldn't access trace_id
    status: str
    files_to_parse: list[tuple[str, str, str, float, int]]
    files_parsed: int
    edges_created: int
    errors: list[str]


def _default_state(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> UnderstandState:
    """Create initial state for the understand workflow.

    [Bug #2] Now accepts trace_id and injects it into state.
    """
    pm = ProjectManager(project_path, is_agent_root=is_agent_root)
    return {
        "project_path": str(pm.path),
        "is_agent_root": is_agent_root,
        "project_id": pm.project_id,
        "artifact_dir": str(pm.artifact_root),
        "trace_id": trace_id,  # [Bug #2] Inject trace_id into state
        "status": "running",
        "files_to_parse": [],
        "files_parsed": 0,
        "edges_created": 0,
        "errors": [],
    }


def _chunked_md5(file_path: Path, chunk_size: int = 8192) -> str:
    """[Bug #6] Compute MD5 hash using chunked reading instead of read_bytes().

    Prevents loading entire large files into memory.
    """
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def node_init_project(state: UnderstandState) -> dict:
    """Initialize the project for indexing.

    [Bug #1] Uses state.get("trace_id") instead of hardcoded "understand_init".
    [Bug #3] GraphStore is created and verified here, but not stored in state
             (it's thread-local — each node creates its own connection).
    [Bug #15] Now handles GraphStore init failure gracefully.
    [Architecture] Converted from async def to def (sync).
    """
    tid = state.get("trace_id", "understand")  # [Bug #1]
    tracer.step(tid, "init", f"Initializing project {state['project_path']}")

    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])

    if not pm.is_agent_root and not pm.source_root.exists():
        return {"status": "failed", "errors": [f"Source root does not exist: {pm.source_root}. Did the git clone fail?"]}

    mode = pm.get_indexing_mode()  # [Architecture] Sync — was await asyncio.to_thread()
    if mode == "reject":
        return {"status": "failed", "errors": ["Project too large for indexing."]}

    pm.ensure_initialized()  # [Architecture] Sync

    # [Bug #3] Verify GraphStore can be created (but don't store in state — it's thread-local).
    # [Bug #15] Handle init failure gracefully.
    db_path = pm.artifact_root / "kg.db"
    try:
        store = GraphStore(db_path)
        store.close()  # [Bug #4] Close immediately — just verifying it works.
    except Exception as e:
        return {"status": "failed", "errors": [f"GraphStore init failed: {e}"]}

    return {"status": "running"}


def node_discover_files(state: UnderstandState) -> dict:
    """Discover changed/new files that need parsing.

    [Bug #1] Uses state.get("trace_id") instead of hardcoded "understand_discover".
    [Bug #4] GraphStore connection is now properly closed.
    [Bug #5] os.walk dirs filtered via copy, not in-place mutation.
    [Bug #6] Uses _chunked_md5() instead of read_bytes().
    [Architecture] Converted from async def to def (sync).
    """
    tid = state.get("trace_id", "understand")  # [Bug #1]
    tracer.step(tid, "discover", "Scanning for changed files...")

    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)

    # [Bug #5] Use a frozenset for O(1) lookup instead of in-place mutation.
    skip_dirs = frozenset({"node_modules", "__pycache__", ".git", ".venv", "venv", ".understand", "dist", "build", ".pytest_cache"})

    discovered = []
    try:
        for root, dirs, files in os.walk(pm.source_root):
            # [Bug #5] Filter dirs via list comprehension (creates new list, doesn't mutate in-place)
            dirs[:] = sorted(set(dirs) - skip_dirs)
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

                # Check if file changed since last index
                node = store.read(
                    "SELECT content_hash, last_modified, file_size FROM nodes WHERE project_id = ? AND path = ?",
                    (state["project_id"], rel_path)
                )

                if node:
                    row = node[0]
                    if math.isclose(row["last_modified"], stat.st_mtime, abs_tol=0.001) and row["file_size"] == stat.st_size:
                        continue

                # [Bug #6] Use chunked MD5 instead of read_bytes()
                current_hash = _chunked_md5(full_path)
                stored_hash = store.get_file_hash(state["project_id"], rel_path)

                if current_hash != stored_hash:
                    discovered.append((str(full_path), rel_path, current_hash, stat.st_mtime, stat.st_size))
    finally:
        store.close()  # [Bug #4] Always close connection

    tracer.step(tid, "discover", f"Found {len(discovered)} changed/new files.")
    return {"files_to_parse": discovered}


def node_parse_and_store(state: UnderstandState) -> dict:
    """Parse changed files and store dependency edges in the graph.

    [Bug #1] Uses state.get("trace_id") instead of hardcoded "understand_parse".
    [Bug #4] GraphStore connection is now properly closed.
    [Bug #7] Duplicate target paths eliminated via set.
    [Bug #8] CPU-bound AST parsing now runs synchronously (no asyncio.gather).
             The sync _parse_dependencies_sync_from_string() is used directly.
    [Bug #17] Batch size now configurable via cfg.understand_batch_size.
    [Architecture] Converted from async def to def (sync).
    """
    tid = state.get("trace_id", "understand")  # [Bug #1]
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

    # [Bug #17] Configurable batch size — was hardcoded to 10.
    # Process in batches to avoid memory spikes on large codebases.
    batch_size = getattr(cfg, "understand_batch_size", 10)
    for i in range(0, len(files_to_parse), batch_size):
        batch = files_to_parse[i:i + batch_size]

        for full_path, rel_path, current_hash, mtime, size in batch:
            try:
                # [Bug #8] Use sync parser directly — no asyncio.gather, no event loop blocking.
                # _parse_dependencies_sync_from_string reads the file and parses AST.
                content = Path(full_path).read_text(encoding="utf-8", errors="replace")
                deps = _parse_dependencies_sync_from_string(content)

                # [Bug #7] Deduplicate target paths — was adding both
                # dep.replace(".", "/") + ".py" and dep, causing duplicate edges.
                target_paths = set()
                for dep in deps:
                    target_paths.add(dep)
                    target_paths.add(dep.replace(".", "/") + ".py")

                store.upsert_file_graph(
                    state["project_id"], rel_path, current_hash,
                    list(target_paths), mtime, size
                )
                parsed += 1
                edges += len(target_paths)
            except Exception as e:
                errors.append(f"Failed to parse {rel_path}: {e}")

    store.close()  # [Bug #4] Always close connection

    tracer.step(tid, "parse", f"Completed. Parsed {parsed} files, created {edges} edges.")
    return {
        "files_parsed": parsed,
        "edges_created": edges,
        "errors": errors,
        "status": "completed" if not errors else "completed_with_errors"
    }


def node_report(state: UnderstandState) -> dict:
    """Generate codebase overview report.

    [Bug #11] Exceptions are now logged via tracer.error, not silently swallowed.
    [Architecture] Converted from async def to def (sync).
    """
    from tools.report import report as report_tool

    tid = state.get("trace_id", "understand")  # [Bug #1] Was already correct here
    project_path = state.get("project_path", "")
    files_parsed = state.get("files_parsed", 0)
    edges_created = state.get("edges_created", 0)
    errors = state.get("errors", [])

    sections = [
        {"title": "Project", "content": f"`{project_path}`"},
        {"title": "Indexing Summary", "content": f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}"},
    ]

    if errors:
        sections.append({
            "title": "Errors",
            "content": "\n".join(f"- {e}" for e in errors[:20])
        })

    try:
        report_tool(
            action="report",
            trace_id=tid,
            title=f"Codebase Overview: {Path(project_path).name}",
            data=None,
            config={"sections": sections},
            preset="code_audit",
        )
    except Exception as e:
        # [Bug #11] Was: except Exception: pass — silent failure.
        # Now logs the error so debugging is possible.
        tracer.error(tid, "understand_report", f"Report generation failed: {e}")

    return {}


def build_understand_graph():
    """Build and compile the understand LangGraph StateGraph.

    [Bug #13] Return type annotation removed — returns CompiledGraph, not StateGraph.
    The compile() method returns a different type than the raw StateGraph.
    """
    workflow = StateGraph(UnderstandState)
    workflow.add_node("node_init_project", node_init_project)
    workflow.add_node("node_discover_files", node_discover_files)
    workflow.add_node("node_parse_and_store", node_parse_and_store)
    workflow.add_node("node_report", node_report)
    workflow.set_entry_point("node_init_project")
    workflow.add_edge("node_init_project", "node_discover_files")
    workflow.add_edge("node_discover_files", "node_parse_and_store")
    workflow.add_edge("node_parse_and_store", "node_report")
    workflow.add_edge("node_report", END)
    return workflow.compile()


def run_understand_workflow_sync(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> dict[str, Any]:
    """Synchronous entry point for the understand workflow.

    [Bug #12] Removed dangerous ThreadPoolExecutor + new_event_loop() hack.
    All nodes are now sync, so graph.invoke() works directly.

    [Bug #9] completed_with_errors is now treated as success.
    """
    tid = trace_id or tracer.new_trace("understand", goal=f"Index codebase at {project_path}")
    try:
        # Force is_agent_root=True if path matches agent_root
        if is_same_path(project_path, cfg.agent_root):
            is_agent_root = True

        graph = build_understand_graph()
        # [Bug #2] Inject trace_id into initial state
        initial_state = _default_state(project_path, is_agent_root=is_agent_root, trace_id=tid)
        final_state = graph.invoke(initial_state)

        # [Bug #9] Treat both "completed" and "completed_with_errors" as success
        success = final_state.get("status", "") in ("completed", "completed_with_errors")
        tracer.finish(tid, success=success, result=str(final_state))
        return final_state
    except Exception as e:
        tracer.error(tid, "understand", f"Workflow failed: {e}")
        tracer.finish(tid, success=False, result=str(e))
        return {"status": "failed", "errors": [str(e)]}
