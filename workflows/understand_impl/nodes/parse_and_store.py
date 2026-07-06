"""Node: parse_and_store — Parse changed files and store dependency edges."""
from __future__ import annotations

from workflows.understand_impl.state import UnderstandState
from core.tracer import tracer
from core.config import cfg
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from core.kgraph.ast_parser import _parse_dependencies_sync_from_string


def node_parse_and_store(state: UnderstandState) -> dict:
    """Parse changed files and store dependency edges in the graph."""
    tid = state.get("trace_id", "understand")
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

    batch_size = getattr(cfg, "understand_batch_size", 10)
    for i in range(0, len(files_to_parse), batch_size):
        batch = files_to_parse[i:i + batch_size]

        for full_path, rel_path, current_hash, mtime, size in batch:
            try:
                content = Path(full_path).read_text(encoding="utf-8", errors="replace")
                deps = _parse_dependencies_sync_from_string(content)

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

    store.close()

    tracer.step(tid, "parse", f"Completed. Parsed {parsed} files, created {edges} edges.")
    return {
        "files_parsed": parsed,
        "edges_created": edges,
        "errors": errors,
        "status": "completed" if not errors else "completed_with_errors"
    }
