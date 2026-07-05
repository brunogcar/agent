"""
workflows/autocode_impl/nodes/analyze_impact.py
Analyzes the impact of modified files and determines targeted tests.
Uses the project-scoped core/kgraph/test_mapper for persistent, smart mapping.
Includes Phase 6 Stale Graph Micro-Updates.

[Bug #4] Converted from async to sync — LangGraph StateGraph.add_node expects
sync functions. The async calls (parse_dependencies_from_string, get_targeted_tests)
are now wrapped in asyncio.run() inside the sync function.
"""
from __future__ import annotations
import asyncio
import hashlib
from pathlib import Path
from workflows.autocode_impl.state import AutocodeState
from core.kgraph.test_mapper import get_targeted_tests
from core.config import cfg
from core.tracer import tracer


def _run_async(coro):
    """Run an async coroutine from sync context. Creates a new event loop."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except RuntimeError:
        # Fallback: if there's already a running loop (unlikely in LangGraph sync node)
        return asyncio.run(coro)


def node_analyze_impact(state: AutocodeState) -> dict:
    """Analyze the impact of modified files and determine targeted tests.

    [Bug #4] Was `async def` — LangGraph StateGraph.add_node expects sync.
    Converted to sync, wrapping async calls in _run_async().
    """
    tid = state.get("trace_id", "unknown")
    files_map = state.get("files_map", {})
    project_root = state.get("project_root", "")
    
    if not files_map:
        return {"impact_warnings": [], "targeted_test_cmd": None, "analyze_impact_failed": False}

    tracer.step(tid, "analyze_impact", f"Analyzing impact for {len(files_map)} files")
    modified_files = list(files_map.keys())
    
    # --- Phase 6: Stale Graph Micro-Update ---
    if project_root:
        try:
            from core.kgraph.project import ProjectManager, is_same_path
            from core.kgraph.storage import GraphStore
            from core.kgraph.ast_parser import parse_dependencies_from_string
            
            is_agent = is_same_path(Path(project_root), cfg.agent_root)
            pm = ProjectManager(project_root, is_agent_root=is_agent)
            db_path = pm.artifact_root / "kg.db"
            
            if db_path.exists():
                store = GraphStore(db_path)
                micro_updated = []
                
                for rel_path, snapshot in files_map.items():
                    if isinstance(snapshot, str):
                        current_md5 = hashlib.md5(snapshot.encode("utf-8")).hexdigest()
                        content = snapshot
                    else:
                        current_md5 = snapshot.get("full_md5") or snapshot.get("md5")
                        # 🔴 FIX: Read full file from disk to prevent 8KB AST truncation
                        full_path = pm.source_root / rel_path
                        if full_path.exists():
                            content = full_path.read_text(encoding='utf-8', errors='replace')
                        else:
                            content = snapshot.get("content_preview", "")
                        
                    if not current_md5:
                        continue
                        
                    stored_md5 = store.get_file_hash(pm.project_id, rel_path)
                    
                    if current_md5 != stored_md5:
                        deps = _run_async(parse_dependencies_from_string(pm.project_id, content))
                        target_paths = []
                        for dep in deps:
                            target_paths.append(dep.replace(".", "/") + ".py")
                            target_paths.append(dep)

                        _run_async(store.upsert_file_graph(
                            pm.project_id,
                            rel_path,
                            current_md5,
                            target_paths
                        ))
                        micro_updated.append(rel_path)
                        
                if micro_updated:
                    tracer.step(tid, "analyze_impact", f"Micro-updated {len(micro_updated)} stale graph nodes")
        except Exception as e:
            tracer.warning(tid, "analyze_impact", f"Graph micro-update failed: {e}")
    # --- End Phase 6 Micro-Update ---
    
    try:
        is_agent = (not project_root) or (Path(project_root).resolve() == cfg.agent_root.resolve())
        project_path = Path(project_root) if not is_agent else cfg.agent_root
        
        result = _run_async(get_targeted_tests(
            project_path=project_path,
            modified_files=modified_files,
            project_id=project_path.name
        ))
        
        test_files = result.get("tests", [])
        fallback = result.get("fallback", False)
        raw_warnings = result.get("warnings", [])
        
        impact_warnings = []
        agent_fault = False
        
        for w in raw_warnings:
            is_agent_fault = False
            warning_type = "MAPPING_MISS"
            
            if "Critical path" in w:
                warning_type = "CRITICAL_PATH"
            elif "Zombie test" in w:
                warning_type = "ZOMBIE_TEST"
            elif "No specific tests" in w or "No valid targeted" in w:
                warning_type = "NO_TEST_MAPPING"
                is_agent_fault = True
                agent_fault = True
            
            impact_warnings.append({
                "type": warning_type,
                "message": w,
                "agent_fault": is_agent_fault
            })
        
        targeted_test_cmd = None
        if not fallback and test_files:
            targeted_test_cmd = "pytest " + " ".join(test_files)
        else:
            targeted_test_cmd = "pytest"
            
        tracer.step(
            tid, "analyze_impact", "Impact analysis complete", 
            targeted_cmd=targeted_test_cmd, 
            fallback=fallback,
            has_agent_fault=agent_fault,
            warnings_count=len(impact_warnings)
        )
        
        return {
            "impact_warnings": impact_warnings,
            "targeted_test_cmd": targeted_test_cmd,
            "analyze_impact_failed": False
        }
        
    except Exception as e:
        tracer.error(tid, "analyze_impact", f"AST analysis failed: {e}")
        return {
            "impact_warnings": [{
                "type": "AST_ERROR",
                "message": f"AST analysis crashed: {e}. Running full test suite.",
                "agent_fault": False
            }],
            "targeted_test_cmd": "pytest",
            "analyze_impact_failed": True
        }