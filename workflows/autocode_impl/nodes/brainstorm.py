"""
Brainstorming node.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from workflows.autocode_impl.state import AutocodeState, PLANNER_TIMEOUT, _get_plan  # [v3.0] _get_files removed (files is core flat)
from workflows.autocode_impl.constants import (
    BRAINSTORM_SYSTEM,
    AUDIT_BRAINSTORM_SYSTEM,
    FIX_BRAINSTORM_SYSTEM,
    EDIT_BRAINSTORM_SYSTEM,
    REFACTOR_BRAINSTORM_SYSTEM,
)
from workflows.autocode_impl.helpers import _call, _parse_json, _files_context
from core.tracer import tracer
from core.config import cfg

def node_brainstorm(state: AutocodeState) -> dict:
    """Refine the spec using the appropriate system prompt for the task type."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}
    
    task_type = state.get("task_type", "feature")
    tracer.step(tid, "brainstorm", f"starting for {task_type}")

    if task_type == "create_skill":
        tracer.step(tid, "brainstorm", "create_skill: skipping brainstorm")
        return {}

    # -- Memory recall (all tasks) --
    try:
        from core.memory_engine import memory as _mem
        results = _mem.recall(
            query=state["task"][:150],
            top_k=3,
            collections=["procedural", "episodic"],
        )
        mem_ctx = "\n\n".join(f"[{r['type']}] {r['text']}" for r in results)
    except Exception:
        mem_ctx = ""

    # [Hardening P1.10] Initialize files_update unconditionally — was:
    # `if "files_update" not in dir(): files_update = state.get("files", {})`
    # The dir() check is brittle (inspects locals) and the initialization
    # happened AFTER the KG block, so an exception inside KG could leave
    # files_update undefined. Initialize before KG; KG block updates if found.
    files_update = state.get("files", {})  # [v3.0] files is core flat field

    # -- Knowledge Graph Context Injection (Phase 5) --
    kg_files = {}
    project_root = state.get("project_root", "")
    if project_root:
        try:
            from core.kgraph.project import ProjectManager
            from core.kgraph.queries import find_relevant_files
            
            # Explicitly check if we are working on the agent itself
            is_agent = (str(Path(project_root).resolve()) == str(cfg.agent_root.resolve()))
            pm = ProjectManager(project_root, is_agent_root=is_agent)
            
            # THIS IS THE KEY: source_root is either cfg.agent_root OR cfg.workspace_root/projects/X/code
            source_root = pm.source_root 
            
            # Query the graph for relevant files
            relevant_paths = find_relevant_files(pm.path, state["task"], top_k=5)
            
            if relevant_paths:
                tracer.step(tid, "brainstorm", f"KG found {len(relevant_paths)} relevant files in {source_root}")
                for rel_path in relevant_paths:
                    full_path = source_root / rel_path
                    if full_path.exists() and rel_path not in state.get("files", {}):  # [v3.0] core flat field
                        try:
                            # Read first 8KB to prevent context bloat
                            content = full_path.read_text(encoding="utf-8", errors="replace")[:8000]
                            kg_files[rel_path] = content
                        except Exception:
                            pass
                
                # Merge KG files into files_update (state files take priority)
                if kg_files:
                    files_update = {**kg_files, **files_update}
        except Exception as e:
            tracer.warning(tid, "brainstorm", f"KG query failed: {e}")

    # [Pre-2.0 Fix] Build files context from MERGED files (original + KG-injected).
    # Was: only used state.get("files", {}) — KG files were merged into state
    # AFTER the LLM call, so the brainstorm node never saw them.
    merged_files = {**kg_files, **state.get("files", {})} if kg_files else state.get("files", {})  # [v3.0] core flat field
    files_ctx = _files_context(merged_files)

    # -- Select system prompt based on task type --
    if task_type == "fix":
        system = FIX_BRAINSTORM_SYSTEM
    elif task_type == "edit":
        system = EDIT_BRAINSTORM_SYSTEM
    elif task_type == "refactor":
        system = REFACTOR_BRAINSTORM_SYSTEM
    elif task_type == "audit":
        system = AUDIT_BRAINSTORM_SYSTEM
    else:  # feature / unclear
        system = BRAINSTORM_SYSTEM

    # Phase 3/5: Inject relevant learned rules for the Planner
    from core.sleep_learn import inject_rules_into_prompt
    system = inject_rules_into_prompt(goal=state["task"], system_prompt=system, trace_id=tid)

    user = (
        f"Task:\n{state['task']}\n\n"
        f"Relevant files:\n{files_ctx}"
        + (f"\n\nPast fixes:\n{mem_ctx}" if mem_ctx else "")
    )

    raw = _call(role="planner", system=system, user=user, timeout=PLANNER_TIMEOUT)
    data = _parse_json(raw)

    if data.get("questions"):
        qs = "\n".join(f"- {q}" for q in data["questions"])
        return {
            "memory_context": mem_ctx,
            "status": "needs_clarification",
            "result": qs
        }

    spec = data.get("spec", state["task"])
    ac = data.get("acceptance_criteria", [])
    cons = data.get("constraints", [])
    impact = data.get("impact", [])

    if ac:
        spec += "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in ac)
    if cons:
        spec += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in cons)
    if impact:
        spec += "\n\nImpact review (files/callers to check for regressions):\n" \
                + "\n".join(f"- {i}" for i in impact)

    tracer.step(tid, "brainstorm", f"spec ready ({len(spec)} chars)")

    # [v3.0] memory_context stays flat (ephemeral); spec lives ONLY in plan sub-state.
    updates: dict[str, Any] = {"memory_context": mem_ctx}
    # [v2.2] RMW: write to plan sub-state for spec (sub-state only in v3.0)
    current_plan = dict(state.get("plan_state", {}))
    current_plan["spec"] = spec
    updates["plan_state"] = current_plan
    # [Bug #7] Store the MERGED files (kg_files + original), not the original.
    # Previously: updates["files"] = state["files"] — discarded KG files.
    if kg_files:
        updates["files"] = files_update  # [v3.0] files is core flat field (not sub-state)

    return updates
