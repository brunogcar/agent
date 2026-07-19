"""
State machine construction for autocode workflow.

v1.1: Added WORKFLOW_METADATA for MCP client introspection. Includes
explicit loops array (debug loop) and branches array (create_skill bypass)
so MCP clients can render the graph correctly.

[v1.4 P2] get_graph() now uses double-checked locking with a module-level
threading.Lock — prevents two concurrent callers from each compiling the
graph (was: race condition where both saw _COMPILED_GRAPH=None and both
called build_graph() + workflow.compile()).
"""
from __future__ import annotations
import threading
from langgraph.graph import END, StateGraph
from workflows.autocode_impl.state import AutocodeState, _get_tdd  # [v3.1 #48] _get_tdd for swarm_fallback routing
# [v1.2 #36] Module-level imports so test patches like
# `patch("workflows.autocode_impl.graph.request_cancellation")` resolve.
from workflows.autocode_impl.helpers import request_cancellation, clear_cancellation
from workflows.autocode_impl.nodes.classify import node_classify_task
from workflows.autocode_impl.nodes.validate import node_validate_input
from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
from workflows.autocode_impl.nodes.plan import node_write_plan
from workflows.autocode_impl.nodes.branch import node_git_branch
from workflows.autocode_impl.nodes.tests import node_write_tests
from workflows.autocode_impl.nodes.execute import node_execute_step
from workflows.autocode_impl.nodes.run_tests import node_run_tests
from workflows.autocode_impl.nodes.analyze_impact import node_analyze_impact
from workflows.autocode_impl.nodes.debug import node_systematic_debug
from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback  # [v3.1 #48] swarm fallback
from workflows.autocode_impl.nodes.summarize_context import node_summarize_context  # [v2.0] Phase 4
from workflows.autocode_impl.nodes.write_files import node_write_files  # [v2.0] backward-compat wrapper
from workflows.autocode_impl.nodes.apply_patches import node_apply_patches  # [v2.0] Phase 3.1 split
from workflows.autocode_impl.nodes.write_new_files import node_write_new_files  # [v2.0] Phase 3.1 split
from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts  # [v2.0] Phase 3.1 split
from workflows.autocode_impl.nodes.verify import node_verify  # [v2.0] backward-compat wrapper
from workflows.autocode_impl.nodes.run_pytest import node_run_pytest  # [v2.0] Phase 3.2 split
from workflows.autocode_impl.nodes.run_lint import node_run_lint  # [v2.0] Phase 3.2 split
from workflows.autocode_impl.nodes.llm_review import node_llm_review  # [v2.0] Phase 3.2 split
from workflows.autocode_impl.nodes.verify_decision import node_verify_decision  # [v2.0] Phase 3.2 split
from workflows.autocode_impl.nodes.commit import node_commit
from workflows.autocode_impl.nodes.publish import node_publish  # [v2.0] backward-compat wrapper
from workflows.autocode_impl.nodes.push import node_push  # [v2.0] Phase 3.3 split
from workflows.autocode_impl.nodes.create_pr import node_create_pr  # [v2.0] Phase 3.3 split
from workflows.autocode_impl.nodes.merge_pr import node_merge_pr  # [v2.0] Phase 3.3 split
from workflows.autocode_impl.nodes.memory import node_distill_memory
from workflows.autocode_impl.nodes.create_skill import node_create_skill
from workflows.autocode_impl.nodes.report import node_report
from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate  # [v3.4 #38] HiTL approval gate
from workflows.autocode_impl.routes import (
    route_after_classify,
    route_after_run_tests,
    route_after_swarm_fallback,  # [v1.4 P2] named function replaces inline lambda
    route_after_write_files,
    route_after_verify,
    route_after_hitl_gate,  # [v3.4 #38] HiTL gate routing
)
# [Pre-2.0 Fix] Removed route_after_analyze_impact import — was always constant,
# replaced with direct edge.


# [v1.1] WORKFLOW_METADATA for MCP client introspection.
# Pragmatic schema: nodes (with type), edges (with condition + loop flag),
# explicit loops array, explicit branches array. Mirrors the pattern in
# research/understand/data/deep_research but extended for autocode's
# complexity (30 nodes: 26 active + 3 backward-compat wrappers + 1 hitl_gate,
# debug loop, create_skill bypass).
WORKFLOW_METADATA = {
    "name": "autocode",
    "version": "3.4",  # [v3.4] HiTL approval gate; [v3.1] Debug loop improvements: goal sanitization, AST pre-check, debug_summary in verify, swarm fallback
    "description": "Autonomous coding with TDD, debug loops, impact analysis, git integration, and procedural memory",
    "entry_point": "node_classify_task",
    "nodes": [
        {"name": "node_classify_task", "type": "llm", "role": "router", "description": "Classify task type from goal"},
        {"name": "node_validate_input", "type": "logic", "description": "Validate input files and path safety"},
        {"name": "node_brainstorm", "type": "llm", "role": "planner", "description": "Brainstorm spec tailored to task type"},
        {"name": "node_write_plan", "type": "llm", "role": "planner", "description": "Write structured plan with acceptance criteria"},
        {"name": "node_git_branch", "type": "tool", "tool": "git", "description": "Create git branch for the task"},
        {"name": "node_write_tests", "type": "llm", "role": "executor", "description": "Write TDD tests before implementation"},
        {"name": "node_execute_step", "type": "llm", "role": "executor", "description": "Generate implementation code from plan"},
        {"name": "node_apply_patches", "type": "tool", "tool": "file", "description": "[v2.0] Apply str_replace patches to existing files"},
        {"name": "node_write_new_files", "type": "tool", "tool": "file", "description": "[v2.0] Write new/overwrite files atomically + build files_map"},
        {"name": "node_persist_artifacts", "type": "tool", "tool": "file", "description": "[v2.0] Persist test file + generated code + debug log to run_dir"},
        {"name": "node_analyze_impact", "type": "llm", "role": "analyze", "description": "Blast radius analysis using dependency graph"},
        {"name": "node_run_tests", "type": "tool", "tool": "pytest", "description": "Run TDD tests via pytest subprocess"},
        {"name": "node_systematic_debug", "type": "llm", "role": "executor", "description": "[v2.0] 4-phase debug: investigation → pattern → hypothesis → fix"},
        {"name": "node_swarm_fallback", "type": "llm", "role": "executor", "description": "[v3.1] Swarm consensus when debug retries exhausted (HIGH confidence → retry, LOW → verify)"},
        {"name": "node_summarize_context", "type": "logic", "description": "[v2.0] Compress debug_history before re-entering loop"},
        {"name": "node_verify", "type": "composite", "description": "[v2.0] Backward-compat wrapper (not wired)"},
        {"name": "node_run_pytest", "type": "tool", "tool": "pytest", "description": "[v2.0] Fresh pytest on autocode test files"},
        {"name": "node_run_lint", "type": "tool", "tool": "ruff", "description": "[v2.0] Ruff lint on modified files only"},
        {"name": "node_llm_review", "type": "llm", "role": "executor", "description": "[v2.0] LLM spec coverage + cleanliness review"},
        {"name": "node_verify_decision", "type": "logic", "description": "[v2.0] Compose results + hallucination guard"},
        {"name": "node_report", "type": "llm", "role": "summarize", "description": "Generate structured report of what was done"},
        {"name": "node_commit", "type": "tool", "tool": "git", "description": "Commit changes to the git branch"},
        {"name": "node_publish", "type": "tool", "tool": "github", "description": "[v2.0] Backward-compat wrapper (not wired)"},
        {"name": "node_push", "type": "tool", "tool": "github", "description": "[v2.0] Push branch to remote"},
        {"name": "node_create_pr", "type": "tool", "tool": "github", "description": "[v2.0] Create pull request from branch"},
        {"name": "node_merge_pr", "type": "tool", "tool": "github", "description": "[v2.0] Auto-merge PR (if enabled)"},
        {"name": "node_distill_memory", "type": "llm", "role": "planner", "description": "Distill procedural memory for future runs"},
        {"name": "node_create_skill", "type": "tool", "tool": "file", "description": "Generate a new skill file (bypasses TDD, has AST validation)"},
        {"name": "node_hitl_gate", "type": "logic", "description": "[v3.4] Human-in-the-Loop approval gate (opt-in via AUTOCODE_HITL_ENABLED=1)"},
    ],
    "edges": [
        {"from": "node_classify_task", "to": "node_brainstorm", "condition": "route_after_classify: feature/fix/refactor/edit/audit"},
        {"from": "node_classify_task", "to": "node_create_skill", "condition": "route_after_classify: create_skill"},
        {"from": "node_classify_task", "to": "node_validate_input", "condition": "route_after_classify: validate first"},
        {"from": "node_classify_task", "to": "END", "condition": "route_after_classify: unclear"},
        {"from": "node_validate_input", "to": "node_brainstorm"},
        {"from": "node_create_skill", "to": "END", "condition": "create_skill bypass (skips TDD)"},
        {"from": "node_brainstorm", "to": "node_write_plan"},
        {"from": "node_write_plan", "to": "node_git_branch"},
        {"from": "node_git_branch", "to": "node_write_tests"},
        {"from": "node_write_tests", "to": "node_execute_step"},
        {"from": "node_execute_step", "to": "node_apply_patches"},
        {"from": "node_apply_patches", "to": "node_write_new_files"},
        {"from": "node_write_new_files", "to": "node_persist_artifacts"},
        {"from": "node_persist_artifacts", "to": "node_analyze_impact", "condition": "route_after_write_files: fix/refactor/improve/feature/audit/edit"},
        {"from": "node_persist_artifacts", "to": "node_run_pytest", "condition": "route_after_write_files: other"},
        {"from": "node_analyze_impact", "to": "node_run_tests"},
        {"from": "node_run_tests", "to": "node_run_pytest", "condition": "route_after_run_tests: passed or max_retries"},
        {"from": "node_run_tests", "to": "node_systematic_debug", "condition": "route_after_run_tests: failed"},
        {"from": "node_systematic_debug", "to": "node_summarize_context", "condition": "debug loop entry"},
        {"from": "node_summarize_context", "to": "node_apply_patches", "condition": "debug loop (type: loop)", "type": "loop"},
        {"from": "node_verify_decision", "to": "node_report", "condition": "route_after_verify: verification_passed"},
        {"from": "node_verify_decision", "to": "END", "condition": "route_after_verify: failed"},
        {"from": "node_report", "to": "node_hitl_gate"},
        {"from": "node_hitl_gate", "to": "node_commit", "condition": "route_after_hitl_gate: approved"},
        {"from": "node_hitl_gate", "to": "END", "condition": "route_after_hitl_gate: awaiting_approval"},
        {"from": "node_commit", "to": "node_push"},  # [v2.0] Phase 3.3 split
        {"from": "node_push", "to": "node_create_pr"},  # [v2.0] Phase 3.3 split
        {"from": "node_create_pr", "to": "node_merge_pr"},  # [v2.0] Phase 3.3 split
        {"from": "node_merge_pr", "to": "node_distill_memory"},  # [v2.0] Phase 3.3 split
        {"from": "node_distill_memory", "to": "END"},
    ],
    "loops": [
        {
            "name": "debug_loop",
            "nodes": ["node_apply_patches", "node_write_new_files", "node_persist_artifacts", "node_analyze_impact", "node_run_tests", "node_systematic_debug", "node_summarize_context"],
            "exit_condition": "tdd_status == passed OR tdd_status == max_retries_exceeded",
            "max_iterations": "cfg.autocode_max_retries (default from .env)",
        },
    ],
    "branches": [
        {
            "name": "create_skill",
            "trigger": "task_type == create_skill",
            "path": ["node_classify_task", "node_create_skill", "END"],
            "skips": ["validate", "brainstorm", "plan", "branch", "tests", "execute", "write_files", "analyze_impact", "run_tests", "debug", "verify", "report", "commit", "distill_memory"],
            "note": "Bypasses TDD but has AST syntax validation (v1.0.2 #16) before writing the skill file.",
        },
    ],
    "safety_features": ["protected_files", "git_branch", "atomic_writes", "test_verification", "path_traversal_guard"],
}

# Global compiled graph instance
_COMPILED_GRAPH = None
# [v1.4 P2] Module-level lock for double-checked locking in get_graph().
_graph_lock = threading.Lock()

def build_graph() -> StateGraph:
    """
    Build the LangGraph state machine for the autocode workflow.
    """
    workflow = StateGraph(AutocodeState)

    # Add all nodes
    workflow.add_node("node_classify_task", node_classify_task)
    workflow.add_node("node_validate_input", node_validate_input)
    workflow.add_node("node_brainstorm", node_brainstorm)
    workflow.add_node("node_write_plan", node_write_plan)
    workflow.add_node("node_git_branch", node_git_branch)
    workflow.add_node("node_write_tests", node_write_tests)
    workflow.add_node("node_execute_step", node_execute_step)
    workflow.add_node("node_run_tests", node_run_tests)
    workflow.add_node("node_analyze_impact", node_analyze_impact)
    workflow.add_node("node_systematic_debug", node_systematic_debug)
    workflow.add_node("node_swarm_fallback", node_swarm_fallback)  # [v3.1 #48] swarm fallback
    workflow.add_node("node_summarize_context", node_summarize_context)  # [v2.0] Phase 4
    # [v2.0] Phase 3.1: node_write_files split into 3 nodes
    workflow.add_node("node_apply_patches", node_apply_patches)
    workflow.add_node("node_write_new_files", node_write_new_files)
    workflow.add_node("node_persist_artifacts", node_persist_artifacts)
    workflow.add_node("node_write_files", node_write_files)  # backward-compat wrapper (not wired)
    workflow.add_node("node_verify", node_verify)  # backward-compat wrapper (not wired)
    # [v2.0] Phase 3.2: node_verify split into 4 nodes
    workflow.add_node("node_run_pytest", node_run_pytest)
    workflow.add_node("node_run_lint", node_run_lint)
    workflow.add_node("node_llm_review", node_llm_review)
    workflow.add_node("node_verify_decision", node_verify_decision)
    workflow.add_node("node_commit", node_commit)
    workflow.add_node("node_publish", node_publish)  # backward-compat wrapper (not wired)
    # [v2.0] Phase 3.3: node_publish split into 3 nodes
    workflow.add_node("node_push", node_push)
    workflow.add_node("node_create_pr", node_create_pr)
    workflow.add_node("node_merge_pr", node_merge_pr)
    workflow.add_node("node_distill_memory", node_distill_memory)
    workflow.add_node("node_create_skill", node_create_skill)
    workflow.add_node("node_report", node_report)
    workflow.add_node("node_hitl_gate", node_hitl_gate)  # [v3.4 #38] HiTL approval gate

    # Set entry point
    workflow.set_entry_point("node_classify_task")

    # Route after classification
    workflow.add_conditional_edges(
        "node_classify_task",
        route_after_classify,
        {
            # [Pre-2.0 Fix] Removed dead "node_brainstorm" mapping —
            # route_after_classify never returns "node_brainstorm" (always
            # goes through validate_input first).
            "node_create_skill": "node_create_skill",
            "node_validate_input": "node_validate_input",
            "END": END,
        },
    )

    # Input validation
    workflow.add_edge("node_validate_input", "node_brainstorm")

    # Direct edges for main flow
    workflow.add_edge("node_create_skill", END)
    workflow.add_edge("node_brainstorm", "node_write_plan")
    workflow.add_edge("node_write_plan", "node_git_branch")
    workflow.add_edge("node_git_branch", "node_write_tests")
    workflow.add_edge("node_write_tests", "node_execute_step")
    # [v2.0] Phase 3.1: execute → apply_patches → write_new_files → persist_artifacts
    workflow.add_edge("node_execute_step", "node_apply_patches")
    workflow.add_edge("node_apply_patches", "node_write_new_files")
    workflow.add_edge("node_write_new_files", "node_persist_artifacts")

    # Route after persist_artifacts (TDD loop vs verification)
    # [v2.0] Was: route_after_write_files from node_write_files → node_verify.
    # Now routes from node_persist_artifacts → node_run_pytest (Phase 3.2 split).
    workflow.add_conditional_edges(
        "node_persist_artifacts",
        route_after_write_files,
        {
            "node_analyze_impact": "node_analyze_impact",
            "node_verify": "node_run_pytest",  # [v2.0] route to first verify sub-node
        },
    )

    # [Pre-2.0 Fix] Replaced conditional_edges with direct edge —
    # route_after_analyze_impact was always constant ("node_run_tests").
    workflow.add_edge("node_analyze_impact", "node_run_tests")

    # Route after run_tests (pass vs debug vs swarm fallback)
    # [v2.0] Phase 3.2: "node_verify" now maps to node_run_pytest (first sub-node)
    # [v3.1 #48]: "node_swarm_fallback" — when debug retries exhausted + flag on
    workflow.add_conditional_edges(
        "node_run_tests",
        route_after_run_tests,
        {
            "node_verify": "node_run_pytest",  # [v2.0] route to first verify sub-node
            "node_systematic_debug": "node_systematic_debug",
            "node_swarm_fallback": "node_swarm_fallback",  # [v3.1 #48]
        },
    )

    # Debug loop [v2.0] Phase 4: debug → summarize_context → apply_patches
    workflow.add_edge("node_systematic_debug", "node_summarize_context")
    workflow.add_edge("node_summarize_context", "node_apply_patches")

    # [v3.1 #48] Swarm fallback edges:
    #   HIGH confidence → node_systematic_debug (one more debug cycle with swarm verdict)
    #   LOW/unavailable → node_run_pytest (proceed to verify chain, will fail)
    # [v1.4 P2] Inline lambda replaced with named route_after_swarm_fallback()
    # so it can be tested directly + documented in routes.py.
    workflow.add_conditional_edges(
        "node_swarm_fallback",
        route_after_swarm_fallback,
        {
            "node_systematic_debug": "node_systematic_debug",
            "node_verify": "node_run_pytest",
        },
    )

    # [v2.0] Phase 3.2: verify chain — run_pytest → run_lint → llm_review → verify_decision
    workflow.add_edge("node_run_pytest", "node_run_lint")
    workflow.add_edge("node_run_lint", "node_llm_review")
    workflow.add_edge("node_llm_review", "node_verify_decision")

    # Route after verification [v2.0] Phase 3.2: from node_verify_decision (was: node_verify)
    workflow.add_conditional_edges(
        "node_verify_decision",
        route_after_verify,
        {
            "report": "node_report",
            "END": END,
        },
    )

    # Report -> hitl_gate -> commit -> push -> create_pr -> merge_pr -> distill -> END  [v3.4: HiTL gate]
    # [v3.4 #38] HiTL gate between report and commit
    workflow.add_edge("node_report", "node_hitl_gate")
    workflow.add_conditional_edges(
        "node_hitl_gate",
        route_after_hitl_gate,
        {"node_commit": "node_commit", "END": END},
    )
    workflow.add_edge("node_commit", "node_push")  # [v2.0] Phase 3.3
    workflow.add_edge("node_push", "node_create_pr")  # [v2.0] Phase 3.3
    workflow.add_edge("node_create_pr", "node_merge_pr")  # [v2.0] Phase 3.3
    workflow.add_edge("node_merge_pr", "node_distill_memory")  # [v2.0] Phase 3.3
    workflow.add_edge("node_distill_memory", END)

    return workflow

def get_graph():
    """
    Get the singleton compiled graph instance.

    [v1.4 P2] Uses double-checked locking with a module-level threading.Lock
    to prevent two concurrent callers from each compiling the graph. The
    first caller acquires the lock and compiles; the second sees the
    populated _COMPILED_GRAPH and skips compilation.
    """
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        with _graph_lock:
            if _COMPILED_GRAPH is None:
                workflow = build_graph()
                _COMPILED_GRAPH = workflow.compile()
    return _COMPILED_GRAPH


def invoke_with_timeout(initial_state: dict) -> dict:
    """Invoke the autocode graph with the configured AUTOCODE_GRAPH_TIMEOUT.

    [P2 #30] cfg.autocode_graph_timeout was defined but never used.
    Now wraps graph.invoke() with a threading-based timeout to prevent
    hung workflows from blocking forever.

    [v2.0] Now sets the cancellation flag on timeout — _call() checks this
    between retries, so pending LLM retry backoffs bail immediately instead
    of sleeping through the timeout. The daemon thread still can't be killed
    (Python limitation), but it will exit on the next _call() check.
    TODO(2.0-later): Consider process-level termination (#35) for true cancellation.
    """
    import threading
    from core.config import cfg
    # [v1.2 #36] request_cancellation, clear_cancellation now imported at
    # module level (above) so test patches can target
    # `workflows.autocode_impl.graph.request_cancellation` directly.

    # [v2.0] Clear any stale cancellation flag from a previous run
    clear_cancellation()

    # [v3.6 #35] Record the graph start time so _remaining_timeout() can
    # cap subprocess timeouts at the remaining graph budget. Prevents
    # subprocess.run() from lingering past the graph deadline.
    from workflows.autocode_impl.helpers import set_graph_start_time
    set_graph_start_time()

    # [v1.4 P2] Best-effort cleanup of old autocode run folders before
    # starting a new run. Non-fatal — cleanup failure must not block the
    # workflow (the new run's folder will still be created on demand).
    try:
        from workflows.autocode_impl.helpers import _cleanup_old_autocode_runs
        _cleanup_old_autocode_runs()
    except Exception:
        pass  # Non-fatal: cleanup failure shouldn't block the workflow

    graph = get_graph()
    result = {"status": "failed", "error": "Graph invocation timed out"}
    # [v1.2 #40] Adaptive timeout by task_type — create_skill=120s, audit=300s,
    # feature=900s, fix/refactor/edit=600s. Falls back to cfg.autocode_graph_timeout.
    # Opt-in via AUTOCODE_ADAPTIVE_TIMEOUT=1 (default OFF — uses static timeout).
    timeout = getattr(cfg, "autocode_graph_timeout", 300)
    if getattr(cfg, "autocode_adaptive_timeout", False):
        _TASK_TYPE_TIMEOUTS = {
            "create_skill": 120,
            "audit": 300,
            "feature": 900,
            "fix": 600,
            "refactor": 600,
            "edit": 600,
        }
        task_type = initial_state.get("task_type", "")
        timeout = _TASK_TYPE_TIMEOUTS.get(task_type, timeout)

    # [Hardening P0.3] Capture exceptions inside the daemon thread — without
    # this, any node crash kills the thread silently and is reported as a
    # "timeout" because result stays at the default "Graph invocation timed out".
    _invoke_error: Exception | None = None

    def _invoke():
        nonlocal result, _invoke_error
        try:
            result = graph.invoke(initial_state)
        except Exception as e:
            _invoke_error = e

    thread = threading.Thread(target=_invoke, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    # [Hardening P0.3] If the thread died with an exception, surface that as
    # the failure reason instead of misreporting it as a timeout.
    if _invoke_error is not None:
        return {
            "status": "failed",
            "error": f"Autocode graph crashed: {_invoke_error}",
            "trace_id": initial_state.get("trace_id", ""),
        }

    if thread.is_alive():
        # [v2.0] Set cancellation flag — _call() will check it and bail
        # on the next retry attempt instead of sleeping through backoff.
        request_cancellation()
        return {
            "status": "failed",
            "error": f"Autocode graph timed out after {timeout}s",
            "trace_id": initial_state.get("trace_id", ""),
        }
    return result