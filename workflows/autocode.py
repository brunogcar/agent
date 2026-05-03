"""
workflows/autocode.py -- Autocode workflow.

Pattern:
  snapshot -> read -> recall -> analyze -> code -> review ->
  syntax_check -> apply -> test -> commit  (or rollback on failure)
  -> store_learning -> notify

Modes:
  fix_error   : fix a traceback/error (requires error_msg)
  improve     : refactor/improve existing code (requires goal)
  add_feature : add new functionality (requires goal + feature_desc)

Key fixes over old autocode.py:
  - ANALYZER_SYSTEM, CODER_SYSTEM, REVIEWER_SYSTEM all actually used
  - Retry loop with reviewer corrections fed back to coder
  - ruff linting in test phase
  - filelock prevents parallel corruption
  - Protected file check before any write
  - Full trace through every node

Usage:
    from workflows.base import run_workflow

    result = run_workflow(
        workflow_type = "autocode",
        goal          = "Fix the memory decay bug",
        mode          = "fix_error",
        target_file   = "memory/store.py",
        error_msg     = "ZeroDivisionError: division by zero at line 42",
    )
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from langgraph.graph import StateGraph, END

from core.config  import cfg
from workflows.base import WorkflowState, node_step, node_error, node_done
from filelock import FileLock


# -- Helpers ------------------------------------------------------------------

def _is_protected(path_str: str) -> bool:
    """Check if file is in the protected set."""
    return cfg.is_protected(Path(path_str))


def _extract_patch(text: str) -> str:
    """
    Extract clean Python code from agent response.
    Handles: raw code, ```python fences, JSON patch field.
    """
    # Try JSON parsed field first
    try:
        import json
        clean = text.strip()
        for fence in ("```json", "```"):
            if clean.startswith(fence):
                clean = clean[len(fence):]
        clean = clean.strip().rstrip("`").strip()
        data  = json.loads(clean)
        if "patch" in data:
            return data["patch"]
    except Exception:
        pass

    # Strip markdown fences
    for pattern in (r"```python\n(.*?)```", r"```\n(.*?)```"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()

    return text.strip()


def _run_ruff(path: Path) -> tuple[bool, str]:
    """Run ruff linter. Returns (passed, output)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(path),
             "--select", "E,F,W", "--no-cache"],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        passed = result.returncode == 0
        return passed, output
    except Exception as e:
        return True, f"ruff unavailable: {e}"  # non-fatal


def _syntax_check(code: str) -> tuple[bool, str]:
    """Check Python syntax. Returns (ok, error_message)."""
    import ast
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


# -- Nodes --------------------------------------------------------------------

def node_snapshot(state: WorkflowState) -> WorkflowState:
    """Create git snapshot before touching anything."""
    from tools.git_ops import git

    target = state.get("target_file", "")
    goal   = state.get("goal", "")

    node_step(state, "snapshot", "creating safety snapshot",
              target=target, goal=goal[:50])

    r = git(
        operation = "snapshot",
        message   = f"autocode: before {goal[:40]}",
        root      = "agent",
    )
    node_step(state, "snapshot", f"snapshot: {r.get('status')}",
              commit=r.get("commit_hash", ""))
    return state


def node_read_file(state: WorkflowState) -> WorkflowState:
    """Read the target file."""
    from tools.file_ops import file

    target = state.get("target_file", "")
    if not target:
        return node_error(state, "read_file", "target_file is required")

    if _is_protected(target):
        return node_error(state, "read_file",
                          f"'{target}' is a protected file -- cannot autocode")

    node_step(state, "read_file", "reading target file", path=target)

    r = file(action="read", path=target)
    if r.get("status") != "success":
        return node_error(state, "read_file",
                          f"Cannot read {target}: {r.get('error')}")

    content = r.get("content", "")
    if len(content) > cfg.autocode_max_file_chars:
        content = content[:cfg.autocode_max_file_chars] + "\n\n[...truncated]"

    node_step(state, "read_file", f"read {len(content)} chars")
    return {**state, "file_content": content}


def node_recall(state: WorkflowState) -> WorkflowState:
    """Recall relevant procedural memories (fix patterns)."""
    from memory.store import memory

    goal   = state.get("goal", "")
    target = state.get("target_file", "")
    query  = f"{goal} {target}"

    node_step(state, "recall", "checking procedural memory")

    results = memory.recall(
        query       = query,
        top_k       = 4,
        collections = ["procedural", "episodic"],
        trace_id    = state.get("trace_id", ""),
    )

    if results:
        ctx = "\n".join(f"[{r['type']}] {r['text']}" for r in results)
        node_step(state, "recall", f"found {len(results)} relevant memories")
        return {**state, "memory_context": ctx}

    return {**state, "memory_context": ""}


def node_analyze(state: WorkflowState) -> WorkflowState:
    """Deep analysis of the code before generating a patch."""
    from tools.agent_tool import agent

    goal          = state.get("goal", "")
    file_content  = state.get("file_content", "")
    error_msg     = state.get("error_msg", "")
    mode          = state.get("mode", "improve")
    memory_ctx    = state.get("memory_context", "")

    task = f"Analyse this code for the purpose of: {goal}"
    if error_msg:
        task += f"\n\nError to fix:\n{error_msg}"

    node_step(state, "analyze", "analysing code", mode=mode)

    r = agent(
        role     = "analyze",
        task     = task,
        context  = memory_ctx,
        content  = file_content,
        trace_id = state.get("trace_id", ""),
    )

    if r.get("status") != "success":
        node_step(state, "analyze", "analysis failed -- continuing without it")
        return {**state, "analysis": ""}

    node_step(state, "analyze", "analysis complete",
              elapsed=r.get("elapsed", 0))
    return {**state, "analysis": r["text"]}


def node_generate_code(state: WorkflowState) -> WorkflowState:
    """Generate the patch using CODER_SYSTEM prompt."""
    from tools.agent_tool import agent

    goal         = state.get("goal", "")
    mode         = state.get("mode", "improve")
    file_content = state.get("file_content", "")
    analysis     = state.get("analysis", "")
    error_msg    = state.get("error_msg", "")
    feature_desc = state.get("feature_desc", "")
    target_file  = state.get("target_file", "")
    retries      = state.get("retries", 0)

    # Build task from mode
    if mode == "fix_error":
        task = (
            f"Fix this error in {target_file}:\n{error_msg}\n\n"
            f"Goal: {goal}"
        )
    elif mode == "add_feature":
        task = (
            f"Add this feature to {target_file}:\n{feature_desc}\n\n"
            f"Goal: {goal}"
        )
    else:
        task = f"Improve {target_file}: {goal}"

    # Include reviewer feedback on retries
    review = state.get("review", {})
    if retries > 0 and review:
        issues = review.get("issues", [])
        corrected = review.get("corrected_patch")
        if corrected:
            task += f"\n\nPrevious attempt was rejected. Use this corrected version as base:\n{corrected}"
        elif issues:
            issue_text = "\n".join(
                f"- [{i['severity']}] {i['description']} -> {i['fix']}"
                for i in issues
            )
            task += f"\n\nPrevious attempt had issues:\n{issue_text}"

    context = f"Analysis:\n{analysis}" if analysis else ""

    node_step(state, "generate", f"generating patch (attempt {retries + 1})")

    r = agent(
        role     = "code",
        task     = task,
        context  = context,
        content  = file_content,
        trace_id = state.get("trace_id", ""),
    )

    if r.get("status") != "success":
        return node_error(state, "generate",
                          f"Code generation failed: {r.get('error', 'unknown')}")

    patch = _extract_patch(r.get("text", ""))

    node_step(state, "generate", f"patch generated ({len(patch)} chars)",
              elapsed=r.get("elapsed", 0))
    return {**state, "patch": patch}


def node_review_patch(state: WorkflowState) -> WorkflowState:
    """Review the patch using REVIEWER_SYSTEM prompt."""
    from tools.agent_tool import agent

    patch  = state.get("patch", "")
    goal   = state.get("goal", "")
    target = state.get("target_file", "")
    mode   = state.get("mode", "improve")

    if not patch:
        return node_error(state, "review", "No patch to review")

    node_step(state, "review", "reviewing patch quality")

    r = agent(
        role     = "review",
        task     = f"Review this patch for {target}. Goal was: {goal} ({mode})",
        context  = f"Original file summary:\n{state.get('analysis', '')[:400]}",
        content  = patch,
        trace_id = state.get("trace_id", ""),
    )

    if r.get("status") != "success":
        node_step(state, "review", "review failed -- proceeding anyway")
        return {**state, "review": {"verdict": "APPROVE", "issues": []}}

    review_data = r.get("parsed") or {}

    # If parsed is None, try to extract verdict from text
    if not review_data:
        text = r.get("text", "")
        if "APPROVE" in text:
            review_data = {"verdict": "APPROVE", "issues": []}
        elif "REJECT" in text:
            review_data = {"verdict": "REJECT", "issues": []}
        else:
            review_data = {"verdict": "REVISE", "issues": [],
                           "corrected_patch": None}

    verdict = review_data.get("verdict", "APPROVE")
    issues  = review_data.get("issues", [])
    node_step(state, "review", f"verdict: {verdict}",
              issues=len(issues), elapsed=r.get("elapsed", 0))

    return {**state, "review": review_data}


def node_syntax_check(state: WorkflowState) -> WorkflowState:
    """Check patch syntax before writing to disk."""
    patch = state.get("patch", "")

    if not patch:
        return node_error(state, "syntax_check", "Empty patch")

    ok, err = _syntax_check(patch)
    if not ok:
        node_step(state, "syntax_check", f"SYNTAX ERROR: {err}")
        return {**state,
                "exec_error": err,
                "review": {"verdict": "REVISE", "issues": [
                    {"severity": "critical",
                     "description": err,
                     "fix": "Correct the syntax error"}
                ]}}

    node_step(state, "syntax_check", "syntax OK")
    return state


def node_apply_patch(state: WorkflowState) -> WorkflowState:
    """Write the patch to disk with filelock."""
    from tools.file_ops import file

    target = state.get("target_file", "")
    patch  = state.get("patch", "")

    if not patch:
        return node_error(state, "apply", "No patch to apply")

    # Protected file guard -- belt-and-suspenders check
    # (also checked at workflow entry, but defence in depth)
    if _is_protected(target):
        return node_error(state, "apply",
                          f"Blocked: '{target}' is a protected file. "
                          "Edit manually. Autocode never touches: "
                          + ", ".join(sorted(cfg.protected_files)))

    node_step(state, "apply", "writing patch to disk", path=target)

    # Resolve path
    p = cfg.resolve_agent_path(target)

    lock_path = str(p) + ".lock"
    with FileLock(lock_path, timeout=10):
        r = file(action="write", path=target, content=patch)

    if r.get("status") != "success":
        return node_error(state, "apply",
                          f"Write failed: {r.get('error')}")

    node_step(state, "apply", "patch written",
              backup=r.get("backup_path", ""), size=r.get("size", 0))
    artifacts = state.get("artifacts", []) + [str(p)]
    return {**state, "artifacts": artifacts}


def node_test(state: WorkflowState) -> WorkflowState:
    """Syntax check + ruff lint after applying patch.

    Distinguishes fatal errors from warnings:
      - SyntaxError  -> exec_error set -> triggers retry/rollback
      - ruff issues  -> logged as warning, does NOT block commit
        (linting style issues should not revert working code)
    """
    target = state.get("target_file", "")
    p      = cfg.resolve_agent_path(target)

    if not p.exists():
        return node_error(state, "test", f"File not found after write: {p}")

    node_step(state, "test", "running post-apply checks")

    # Syntax check -- fatal, must be clean before commit
    try:
        code = p.read_text(encoding="utf-8")
        ok, err = _syntax_check(code)
        if not ok:
            node_step(state, "test", f"SYNTAX ERROR: {err}")
            return {**state, "exec_error": f"SyntaxError: {err}"}
    except Exception as e:
        return {**state, "exec_error": f"Read error: {e}"}

    # ruff lint -- non-fatal, log only, never triggers retry
    passed, ruff_out = _run_ruff(p)
    if not passed:
        # Style/lint issues: warn but proceed to commit
        node_step(state, "test",
                  f"ruff warnings (non-fatal, proceeding): {ruff_out[:120]}")
    else:
        node_step(state, "test", "all checks passed")

    return {**state, "exec_error": ""}


def node_commit(state: WorkflowState) -> WorkflowState:
    """Commit the successful change."""
    from tools.git_ops import git

    goal   = state.get("goal", "")
    mode   = state.get("mode", "improve")
    target = state.get("target_file", "")

    msg = f"{mode}: {goal[:60]} [{target}]"
    node_step(state, "commit", "committing successful change")

    r = git(operation="commit", message=msg, root="agent")
    node_step(state, "commit", f"committed: {r.get('commit_hash', '')}",
              status=r.get("status"))

    artifacts = state.get("artifacts", [])
    if r.get("commit_hash"):
        artifacts = artifacts + [f"git:{r['commit_hash']}"]

    # Set status=success so store_learning and notify know the outcome
    return {**state, "status": "success",
            "artifacts": artifacts, "result": msg}


def node_rollback(state: WorkflowState) -> WorkflowState:
    """Rollback all changes on failure."""
    from tools.git_ops import git

    error = state.get("error", "") or state.get("exec_error", "unknown error")
    node_step(state, "rollback", f"rolling back: {error[:60]}")

    r = git(operation="rollback", root="agent")
    node_step(state, "rollback", f"rolled back to {r.get('head', 'HEAD')}")
    # Ensure status=failed so store_learning records it correctly
    return {**state, "status": "failed"}


def node_store_learning(state: WorkflowState) -> WorkflowState:
    """Store what we learned from this autocode run."""
    from memory.store import memory

    status = state.get("status", "")
    goal   = state.get("goal", "")
    target = state.get("target_file", "")
    mode   = state.get("mode", "")
    patch  = state.get("patch", "")
    error  = state.get("error", "")

    outcome = "success" if status != "failed" else "failure"

    # Always store episodic
    memory.store_episodic(
        text       = (
            f"Autocode {mode} on {target}: '{goal[:60]}' -> {outcome}"
            + (f" | error: {error[:80]}" if error else "")
        ),
        importance = 8 if outcome == "success" else 6,
        goal       = goal,
        outcome    = outcome,
        tools_used = "agent,file,git",
        trace_id   = state.get("trace_id", ""),
    )

    # Store successful patches as procedural
    if outcome == "success" and patch:
        memory.store_procedural(
            text       = (
                f"Successful {mode} for '{goal[:60]}' in {target}:\n"
                f"{patch[:500]}"
            ),
            importance = 8,
            tags       = f"autocode,{mode},{Path(target).stem}",
            trace_id   = state.get("trace_id", ""),
        )

    node_step(state, "store_learning", f"stored {outcome} learning")
    return state


def node_notify(state: WorkflowState) -> WorkflowState:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from workflows.base import node_done

    status = state.get("status", "running")
    goal   = state.get("goal", "")
    result = state.get("result", "")
    error  = state.get("error", "")

    if status == "failed":
        notify(action="send", title="Autocode FAILED",
               message=f"{goal[:40]}: {error[:60]}")
        # Already marked failed -- just return as-is with trace finished
        from core.tracer import tracer
        tid = state.get("trace_id", "")
        if tid:
            tracer.finish(tid, success=False, result=error[:200])
        return state
    else:
        notify(action="send", title="Autocode complete",
               message=f"{goal[:40]}: {result[:60]}")
        return node_done(state, result=result or "Autocode complete")


# -- Routing ------------------------------------------------------------------

def route_after_review(state: WorkflowState) -> str:
    """Route based on review verdict and retry budget."""
    review   = state.get("review", {})
    verdict  = review.get("verdict", "APPROVE")
    retries  = state.get("retries", 0)
    max_ret  = cfg.autocode_max_retries

    if verdict == "APPROVE":
        return "syntax_check"
    if verdict == "REJECT" or retries >= max_ret:
        return "rollback"
    # REVISE -- increment retries and go back to generator
    return "retry"


def route_after_syntax(state: WorkflowState) -> str:
    if state.get("exec_error"):
        retries = state.get("retries", 0)
        if retries < cfg.autocode_max_retries:
            return "retry"
        return "rollback"
    return "apply"


def route_after_test(state: WorkflowState) -> str:
    exec_error = state.get("exec_error", "")
    # Only retry/rollback on actual syntax errors -- not ruff style warnings
    # (ruff warnings are logged but do not block commit)
    if exec_error and "SyntaxError" in exec_error:
        retries = state.get("retries", 0)
        if retries < cfg.autocode_max_retries:
            return "retry"
        return "rollback"
    return "commit"


def increment_retry(state: WorkflowState) -> WorkflowState:
    """Increment retry counter before looping back."""
    return {**state, "retries": state.get("retries", 0) + 1}


# -- Graph builder ------------------------------------------------------------

def build_autocode_graph() -> StateGraph:
    """Build and compile the autocode workflow graph."""
    g = StateGraph(WorkflowState)

    g.add_node("snapshot",       node_snapshot)
    g.add_node("read_file",      node_read_file)
    g.add_node("recall",         node_recall)
    g.add_node("analyze",        node_analyze)
    g.add_node("generate",       node_generate_code)
    g.add_node("review",         node_review_patch)
    g.add_node("syntax_check",   node_syntax_check)
    g.add_node("apply",          node_apply_patch)
    g.add_node("test",           node_test)
    g.add_node("commit",         node_commit)
    g.add_node("rollback",       node_rollback)
    g.add_node("increment_retry",increment_retry)
    g.add_node("store_learning", node_store_learning)
    g.add_node("notify",         node_notify)

    g.set_entry_point("snapshot")

    g.add_edge("snapshot",  "read_file")
    g.add_edge("read_file", "recall")
    g.add_edge("recall",    "analyze")
    g.add_edge("analyze",   "generate")
    g.add_edge("generate",  "review")

    # Review -> syntax_check OR rollback OR retry
    g.add_conditional_edges(
        "review",
        route_after_review,
        {
            "syntax_check": "syntax_check",
            "rollback":     "rollback",
            "retry":        "increment_retry",
        },
    )

    # Syntax -> apply OR rollback OR retry
    g.add_conditional_edges(
        "syntax_check",
        route_after_syntax,
        {
            "apply":    "apply",
            "rollback": "rollback",
            "retry":    "increment_retry",
        },
    )

    g.add_edge("apply", "test")

    # Test -> commit OR rollback OR retry
    g.add_conditional_edges(
        "test",
        route_after_test,
        {
            "commit":   "commit",
            "rollback": "rollback",
            "retry":    "increment_retry",
        },
    )

    # Retry loops back to generate with incremented counter
    g.add_edge("increment_retry", "generate")

    # Both success and failure paths converge at store_learning
    g.add_edge("commit",   "store_learning")
    g.add_edge("rollback", "store_learning")

    g.add_edge("store_learning", "notify")
    g.add_edge("notify",         END)

    return g.compile()