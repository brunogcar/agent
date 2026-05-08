"""
autocode.py -- Superpowers-enhanced autonomous coding workflow.

Integrates superpowers methodologies into a LangGraph state machine:
  1. Task Classification    -- Router model classifies task type
  2. Memory Summarization   -- Past fixes recalled before spec writing
  3. Brainstorming          -- Spec refinement tailored to task type
  4. Writing Plans          -- Structured, acceptance-criteria-driven plans
  5. TDD on Disk            -- Tests run via pytest subprocess, real exit codes
  6. Systematic Debugging   -- Root-cause hypothesis, defense notes, one fix at a time
  7. Verification Gate      -- Automated checks override LLM opinion (hallucination guard)
  8. Procedural Memory      -- Successful debug fixes stored as reusable knowledge

Model routing:
  Planner  (Qwen 3.5 9B)    -- brainstorm, plan, spec
  Router   (Nemotron 4B)    -- task classification
  Executor (Hermes 3 8B)    -- code generation, test writing, fixes, review

API compatibility:
  Imports: core.tracer.tracer singleton, core.llm.llm singleton
  Config:  cfg.planner_model, cfg.executor_model, cfg.router_model (no cfg.get())
  Git:     git(operation) -- init|snapshot|commit|rollback|log|status|diff only
  Tracer:  tracer.step(trace_id, node, message, **kwargs) API

Usage:
    from autocode import run_autocode_agent
    result = run_autocode_agent(
        task="Add input validation to memory store",
        files={"memory/store.py": open("memory/store.py").read()},
    )
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from filelock import FileLock, Timeout

from core.config  import cfg
from core.tracer  import tracer
from core.llm     import llm

# ── Tunables ------------------------------------------------------------------
MAX_RETRIES:    int  = cfg.autocode_max_retries
MAX_FILE_CHARS: int  = cfg.autocode_max_file_chars
DEBUG:          bool = getattr(cfg, "autocode_debug", False)

PLANNER_TIMEOUT:  int = 90
EXECUTOR_TIMEOUT: int = 120
ROUTER_TIMEOUT:   int = 15

# autocode writes to the AGENT root (not workspace) when editing agent code.
# Skills and workspace projects use cfg.workspace_root.
AGENT_ROOT: Path = cfg.agent_root

# ── State TypedDict -----------------------------------------------------------

class AutocodeState(TypedDict, total=False):
    # Inputs
    task:           str
    files:          dict[str, str]
    mode:           str          # "feature" | "fix_error" | "improve" | "add_feature"
    target_file:    str

    # Classification
    task_type:      str          # "feature" | "bugfix" | "refactor" | "unclear"
    memory_context: str

    # Planning
    spec:           str
    plan:           list[dict]
    branch:         str
    current_step:   int
    step_attempt:   int

    # Execution
    generated_code: str
    test_code:      str
    test_result:    str
    error_log:      str

    # Debugging
    hypothesis:     str
    defense_note:   str
    debug_attempts: int
    came_from_debug: bool

    # Verification
    verification_passed: bool
    verification_notes:  str
    evidence_outputs:    dict    # {"tests": "...", "lint": "...", "regression": "..."}

    # Result
    status:     str              # "running" | "done" | "failed" | "needs_clarification"
    result:     str
    commit_sha: str
    trace_id:   str


def _default_state(task: str, files: dict[str, str], mode: str = "feature",
                   target_file: str = "") -> AutocodeState:
    return AutocodeState(
        task=task,
        files={k: v[:MAX_FILE_CHARS] for k, v in files.items()},
        mode=mode,
        target_file=target_file,
        task_type="feature",
        memory_context="",
        spec="",
        plan=[],
        branch="",
        current_step=0,
        step_attempt=0,
        generated_code="",
        test_code="",
        test_result="",
        error_log="",
        hypothesis="",
        defense_note="",
        debug_attempts=0,
        came_from_debug=False,
        verification_passed=False,
        verification_notes="",
        evidence_outputs={},
        status="running",
        result="",
        commit_sha="",
        trace_id="",
    )


# ── Helpers -------------------------------------------------------------------

def _files_context(files: dict[str, str], hint: str = "") -> str:
    """
    Build file context for LLM prompts.
    When hint is provided, extracts only sections relevant to the task
    instead of the full file -- saves significant input tokens on large files.
    """
    if not files:
        return "(no files provided)"

    try:
        from core.patch import extract_relevant_sections
        _have_patch = True
    except ImportError:
        _have_patch = False

    parts = []
    for path, content in files.items():
        if _have_patch and hint and len(content) > MAX_FILE_CHARS:
            snippet  = extract_relevant_sections(content, hint, max_chars=MAX_FILE_CHARS)
            was_compressed = len(snippet) < len(content)
            if was_compressed:
                parts.append(
                    f"### {path} (relevant sections, {len(content)} total chars)\n"
                    f"```\n{snippet}\n```"
                )
                continue

        snippet = content[:MAX_FILE_CHARS]
        if len(content) > MAX_FILE_CHARS:
            snippet += f"\n... (truncated, {len(content)} total chars)"
        parts.append(f"### {path}\n```\n{snippet}\n```")
    return "\n\n".join(parts)


def _extract_code(text: str, lang: str = "python") -> str:
    pattern = rf"```(?:{lang})?\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def _parse_json(raw: str) -> dict:
    """Try to extract a JSON object from raw LLM output."""
    raw = raw.strip()
    # Strip think tags (Qwen sometimes emits them)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences
    for fence in ("```json", "```"):
        if raw.startswith(fence):
            raw = raw[len(fence):]
    raw = raw.strip().rstrip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Extract first {...} block
    m = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _parse_json_array(raw: str) -> list:
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


def _should_copy_file(path: Path, relative_to: Path) -> bool:
    """Return True if a file should be copied to the temp test directory."""
    try:
        rel = path.relative_to(relative_to)
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return False
    skip = {".git", "venv", ".venv", "__pycache__", "build", "dist",
            ".pytest_cache", ".mypy_cache", "node_modules"}
    if parts[0] in skip or parts[0].startswith("."):
        return False
    return True


def _call(role: str, system: str, user: str, timeout: int) -> str:
    """
    Call the LLM via the project's llm singleton.
    Maps role name to the correct model and uses llm.complete().
    """
    r = llm.complete(role=role, system=system, user=user)
    return r.text if r.ok else ""


# ── Disk-based test runner ----------------------------------------------------

def run_tests_on_disk(
    files:     dict[str, str],
    test_code: str,
    workspace: Path | None = None,
) -> tuple[bool, str]:
    """
    Run tests using a real pytest subprocess in a temporary directory.
    Returns (passed: bool, output: str).
    Using real pytest exit codes -- LLM cannot hallucinate a pass here.
    """
    if not files or not test_code:
        return False, "No files or tests provided"

    try:
        test_dir = Path(tempfile.mkdtemp(prefix="autocode_test_"))
        try:
            # Copy workspace context (so imports from the real project work)
            if workspace and workspace.exists():
                for src in workspace.rglob("*"):
                    if src.is_file() and _should_copy_file(src, workspace):
                        dst = test_dir / src.relative_to(workspace)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass

            # Write the generated implementation files
            for rel_path, content in files.items():
                target = test_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            # Write tests
            test_file = test_dir / "test_autocode_feature.py"
            test_file.write_text(test_code, encoding="utf-8")

            cmd  = [sys.executable, "-m", "pytest", str(test_dir),
                    "--tb=short", "--color=no", "-q"]
            if DEBUG:
                cmd.insert(cmd.index("--tb=short"), "-v")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = (result.stdout + result.stderr).strip()
            passed = result.returncode == 0
            return passed, output or "(no output)"

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired running tests"
    except Exception as e:
        return False, f"Exception during test execution: {e}"


# ── Git helpers ---------------------------------------------------------------

def _git_snapshot(message: str, tid: str = "") -> bool:
    from tools.git_ops import git
    try:
        r = git(operation="snapshot", message=f"autocode: before {message[:40]}", root="agent")
        ok = r.get("status") in ("committed", "nothing_to_commit")
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot: {r.get('status')}")
        return ok
    except Exception as e:
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot failed: {e}")
        return False


def _git_commit(message: str, tid: str = "") -> str | None:
    from tools.git_ops import git
    try:
        status = git(operation="status", root="agent")
        if status.get("count", 0) > 0:
            r = git(operation="commit", message=message, root="agent")
            sha = r.get("commit_hash", "")
            if tid:
                tracer.step(tid, "git_commit", f"committed {sha}")
            return sha
        else:
            _git_snapshot(f"baseline: {message[:40]}", tid)
            return None
    except Exception as e:
        if tid:
            tracer.step(tid, "git_commit", f"commit failed: {e}")
        return None


def _git_create_branch(branch: str, tid: str = "") -> bool:
    """Create branch using snapshot pattern -- checkout not in our git tool."""
    root = str(cfg.agent_root)
    try:
        r = subprocess.run(
            ["git", "-C", root, "checkout", "-b", branch],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            # Branch exists -- switch to it
            subprocess.run(["git", "-C", root, "checkout", branch],
                          capture_output=True)
        if tid:
            tracer.step(tid, "git_branch", f"branch: {branch}")
        return True
    except Exception as e:
        if tid:
            tracer.step(tid, "git_branch", f"branch failed: {e}")
        return False


# ── System prompts ------------------------------------------------------------

TASK_CLASSIFIER_SYSTEM = """\
You are the Router model. Classify a coding task into one category.

Categories:
- "feature":  New functionality (requires brainstorming and spec)
- "bugfix":   Fix an existing error (skip brainstorming, go straight to plan)
- "refactor": Improve structure without changing behaviour (skip brainstorming)
- "unclear":  Insufficient information (ask 1-2 clarifying questions)

Output ONLY this JSON:
{"task_type": "bugfix|feature|refactor|unclear", "questions": []}

No prose outside the JSON. questions is empty unless task_type is "unclear"."""


# Standard brainstorm for features/unclear
BRAINSTORM_SYSTEM = """\
You are the Planner model. Clarify and refine a coding task before any code is written.

Rules:
- Identify ambiguities in the task description.
- Ask NO MORE than 3 targeted clarifying questions if truly needed;
  if the task is clear, skip questions and go straight to spec.
- Review past fixes from memory if provided (see below) to avoid repeating mistakes.
- Output a REFINED SPEC in this exact JSON format:
  {
    "spec": "<one clear paragraph, max 200 words>",
    "acceptance_criteria": ["<criterion>", ...],
    "constraints": ["<constraint>", ...],
    "questions": []
  }
- If questions are non-empty, set spec to "" and return immediately.
- Output ONLY the JSON object. No prose outside it."""


# New bugfix-specific prompt: zero questions, deep analysis
BUGFIX_BRAINSTORM_SYSTEM = """\
You are the Planner model. Refine a bugfix task before any code is written.

Rules:
- Analyse the existing code and error description to understand the root cause.
- Do NOT ask clarifying questions – the information provided is sufficient.
- Write a concise spec (max 150 words) that describes the correct behaviour after the fix.
- Define 2‑4 acceptance criteria that must be true for the fix to be considered successful.
- Include any constraints (e.g., "must not break existing API", "must handle edge case X").
- Output ONLY a JSON object:
  {
    "spec": "<refined spec>",
    "acceptance_criteria": ["...", "..."],
    "constraints": ["...", "..."],
    "questions": []
  }
No prose outside the JSON."""


# New refactor-specific prompt: restructuring focus, limited questions
REFACTOR_BRAINSTORM_SYSTEM = """\
You are the Planner model. Refine a refactoring task before any code is written.

The existing code is provided. You must:
- Understand the current structure and its limitations.
- Define the desired new behaviour and architecture.
- Ensure backward compatibility unless explicitly told to break it.
- Review past fixes from memory (provided) to avoid repeating mistakes.
- Do NOT ask clarifying questions unless the task is genuinely ambiguous; if needed, limit to 1 question.

Output ONLY a JSON object with spec, acceptance_criteria, constraints, and questions (if any).
Use the same JSON format as the standard brainstorm."""


PLAN_SYSTEM = """\
You are the Planner model. Produce a granular implementation plan.

Rules:
- Each step must be concrete enough for a junior developer.
- Prefer YAGNI -- only what satisfies the acceptance criteria.
- First step MUST be writing tests (TDD). Label it "write_tests".
- Last step MUST be verification. Label it "verify".
- Maximum 8 steps. Merge related operations.
- Output ONLY a JSON array:
  [{"id": 1, "label": "write_tests", "description": "...", "acceptance": "...", "files": []}, ...]
No prose outside the JSON array."""


TEST_SYSTEM = """\
You are the Executor model acting as a senior test engineer.
Write FAILING tests -- do NOT write the implementation yet.

Rules:
- Use pytest style (assert statements, no unittest classes unless needed).
- Tests must fail because the implementation does not exist yet.
- Cover all acceptance criteria from the spec.
- Output ONLY a fenced Python code block.
- No implementation code. No explanations outside the code block."""


CODER_SYSTEM = """\
You are the Executor model acting as a focused Python developer.

CRITICAL: Prefer targeted patches over full file rewrites to save tokens.

For EXISTING files -- output patches (str_replace):
  {
    "patches": [
      {"path": "<file>", "old": "<exact existing text>", "new": "<replacement>"},
      ...
    ],
    "new_files": {},
    "explanation": "<one sentence>"
  }
  - old must be the EXACT text from the file (copy-paste, do not paraphrase).
  - old must be unique enough to appear only once -- include surrounding lines.
  - Multiple patches to the same file are applied sequentially.

For NEW files -- use new_files:
  {
    "patches": [],
    "new_files": {"<relative/path.py>": "<full file content>"},
    "explanation": "<one sentence>"
  }

If you must rewrite a whole existing file (major restructure only):
  put it in new_files with the same path -- it will overwrite.

Output ONLY the JSON. No prose before or after."""


DEBUG_SYSTEM = """\
You are the Executor model acting as a systematic debugger.

Steps:
1. Trace the error to the exact line and condition where failure originates.
2. Make ONE targeted fix -- no shotgun edits.
3. Output JSON ONLY:
   {
     "hypothesis": "<single sentence root cause>",
     "files": {"<path>": "<full corrected file content>"},
     "explanation": "<what was changed and why>",
     "defense_note": "<how to prevent this class of bug in future>"
   }
No prose outside the JSON."""


VERIFY_SYSTEM = """\
You are the Executor model performing a pre-commit verification audit.

CRITICAL RULE: Automated test exit codes are ground truth.
If pytest returned exit code != 0 (tests FAILED), you MUST set all_passed=false.
The LLM cannot override real test results.

Review:
1. syntax     -- Does the code parse without SyntaxError?
2. tests      -- Did pytest return exit code 0? Check attached test output.
3. spec       -- Does implementation address every acceptance criterion?
4. regressions-- Are existing files that were not meant to change intact?
5. cleanliness-- No debug prints, TODOs, or placeholder code.

Output JSON ONLY:
{
  "checks": {
    "syntax":      {"passed": true/false, "note": "..."},
    "tests":       {"passed": true/false, "note": "..."},
    "spec":        {"passed": true/false, "note": "..."},
    "regressions": {"passed": true/false, "note": "..."},
    "cleanliness": {"passed": true/false, "note": "..."}
  },
  "automated_checks_passed": true/false,
  "all_passed": true/false,
  "summary": "<one honest sentence>"
}"""


# ── Graph nodes ---------------------------------------------------------------

def node_classify_task(state: AutocodeState) -> AutocodeState:
    """Classify task type to route feature vs bugfix/refactor paths."""
    tid = state.get("trace_id", "")
    tracer.step(tid, "classify_task", f"classifying: {state['task'][:60]}")

    raw  = _call(
        role    = "router",
        system  = TASK_CLASSIFIER_SYSTEM,
        user    = f"Task:\n{state['task']}",
        timeout = ROUTER_TIMEOUT,
    )
    data      = _parse_json(raw)
    task_type = data.get("task_type", "feature")
    questions = data.get("questions", [])

    # Override classification from mode if set
    mode = state.get("mode", "")
    if mode == "fix_error":
        task_type = "bugfix"
    elif mode == "improve":
        task_type = "refactor"

    tracer.step(tid, "classify_task", f"classified as: {task_type}")

    if questions and task_type == "unclear":
        qs = "\n".join(f"- {q}" for q in questions)
        return {**state, "task_type": task_type,
                "status": "needs_clarification", "result": qs}

    return {**state, "task_type": task_type}


def node_brainstorm(state: AutocodeState) -> AutocodeState:
    """Refine the spec using the appropriate system prompt for the task type."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    task_type = state.get("task_type", "feature")
    tracer.step(tid, "brainstorm", f"starting for {task_type}")

    # ── Memory recall (all tasks) ──
    try:
        from memory.store import memory as _mem
        results = _mem.recall(
            query       = state["task"][:150],
            top_k       = 3,
            collections = ["procedural", "episodic"],
        )
        mem_ctx = "\n\n".join(f"[{r['type']}] {r['text']}" for r in results)
    except Exception:
        mem_ctx = ""

    files_ctx = _files_context(state["files"])

    # ── Select system prompt based on task type ──
    if task_type == "bugfix":
        system = BUGFIX_BRAINSTORM_SYSTEM
    elif task_type == "refactor":
        system = REFACTOR_BRAINSTORM_SYSTEM
    else:  # feature / unclear
        system = BRAINSTORM_SYSTEM

    user = (
        f"Task:\n{state['task']}\n\n"
        f"Relevant files:\n{files_ctx}"
        + (f"\n\nPast fixes:\n{mem_ctx}" if mem_ctx else "")
    )

    raw  = _call(role="planner", system=system, user=user, timeout=PLANNER_TIMEOUT)
    data = _parse_json(raw)

    if data.get("questions"):
        qs = "\n".join(f"- {q}" for q in data["questions"])
        return {**state, "memory_context": mem_ctx,
                "status": "needs_clarification", "result": qs}

    spec = data.get("spec", state["task"])
    ac   = data.get("acceptance_criteria", [])
    cons = data.get("constraints", [])
    if ac:
        spec += "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in ac)
    if cons:
        spec += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in cons)

    tracer.step(tid, "brainstorm", f"spec ready ({len(spec)} chars)")
    return {**state, "memory_context": mem_ctx, "spec": spec}


def node_write_plan(state: AutocodeState) -> AutocodeState:
    """Generate step-by-step implementation plan."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    # For bugfix/refactor without spec from brainstorm, build spec from task
    spec = state.get("spec") or state["task"]
    tracer.step(tid, "write_plan", "writing plan")

    raw  = _call(role="planner", system=PLAN_SYSTEM,
                 user=f"Spec:\n{spec}", timeout=PLANNER_TIMEOUT)
    plan = _parse_json_array(raw)

    if not plan:
        plan = [
            {"id": 1, "label": "write_tests",
             "description": "Write failing tests", "acceptance": "Tests exist", "files": []},
            {"id": 2, "label": "implement",
             "description": spec[:200], "acceptance": "All tests pass", "files": []},
            {"id": 3, "label": "verify",
             "description": "Run verification", "acceptance": "All checks pass", "files": []},
        ]

    slug   = re.sub(r"[^a-z0-9]+", "-", state["task"][:40].lower()).strip("-")
    branch = f"autocode/{slug}"

    tracer.step(tid, "write_plan", f"{len(plan)} steps, branch: {branch}")
    return {**state, "spec": spec, "plan": plan, "branch": branch, "current_step": 0}


def node_git_branch(state: AutocodeState) -> AutocodeState:
    """Snapshot and create git branch before any code changes."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    _git_snapshot(f"pre-autocode: {state['task'][:30]}", tid)
    if state.get("branch"):
        _git_create_branch(state["branch"], tid)

    return state


def node_write_tests(state: AutocodeState) -> AutocodeState:
    """TDD red phase -- write failing tests before implementation."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    plan = state.get("plan", [])
    idx  = state.get("current_step", 0)
    if idx >= len(plan) or plan[idx]["label"] != "write_tests":
        return state

    step = plan[idx]
    tracer.step(tid, "write_tests", f"step {step['id']}")

    raw       = _call(
        role    = "executor",
        system  = TEST_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Existing files:\n{_files_context(state['files'])}\n\n"
            f"Step: {step['description']}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    test_code = _extract_code(raw)
    tracer.step(tid, "write_tests", f"tests written ({len(test_code)} chars)")

    # Advance past write_tests step
    return {**state, "test_code": test_code, "current_step": idx + 1}


def node_execute_step(state: AutocodeState) -> AutocodeState:
    """Generate code for the current plan step."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    plan = state.get("plan", [])
    idx  = state.get("current_step", 0)
    if idx >= len(plan):
        return state

    step = plan[idx]
    if step["label"] in ("write_tests", "verify"):
        return state

    attempt = state.get("step_attempt", 0) + 1
    tracer.step(tid, "execute_step", f"step {step['id']} ({step['label']}) attempt {attempt}")

    test_ctx = (
        f"Tests to satisfy:\n```python\n{state['test_code']}\n```\n\n"
        if state.get("test_code") else ""
    )

    raw  = _call(
        role    = "executor",
        system  = CODER_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"{test_ctx}"
            f"Current step ({step['id']}): {step['description']}\n"
            f"Acceptance: {step['acceptance']}\n\n"
            f"Existing files:\n{_files_context(state['files'], hint=state.get('task',''))}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)
    # Support both old format (files dict) and new patch format
    if "patches" in data or "new_files" in data:
        generated = json.dumps(data, indent=2)
    else:
        generated = json.dumps({"new_files": data.get("files", {})}, indent=2)

    tracer.step(tid, "execute_step", f"code generated ({len(generated)} chars)")
    return {**state, "generated_code": generated, "step_attempt": attempt}


def node_run_tests(state: AutocodeState) -> AutocodeState:
    """Run tests on disk with real pytest. Exit code is ground truth."""
    tid = state.get("trace_id", "")
    if not state.get("generated_code"):
        return {**state, "test_result": "", "error_log": ""}

    tracer.step(tid, "run_tests", "running pytest on disk")

    try:
        files = json.loads(state["generated_code"])
    except Exception as e:
        return {**state, "error_log": f"Cannot parse generated code: {e}"}

    if not state.get("test_code"):
        return {**state, "test_result": "(no tests)", "error_log": ""}

    passed, output = run_tests_on_disk(
        files=files,
        test_code=state["test_code"],
        workspace=cfg.workspace_root,
    )

    if passed:
        tracer.step(tid, "run_tests", "PASSED")
        # Advance step counter on pass -- prevents infinite test loops
        new_step = state.get("current_step", 0) + 1
        return {**state,
                "test_result": output,
                "error_log":   "",
                "current_step": new_step}
    else:
        tracer.step(tid, "run_tests", f"FAILED: {output[:80]}")
        return {**state, "test_result": output, "error_log": output}


def node_systematic_debug(state: AutocodeState) -> AutocodeState:
    """Hypothesis-driven debugging. One targeted fix per attempt."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state
    if not state.get("error_log"):
        return state

    attempts = state.get("debug_attempts", 0)
    if attempts >= MAX_RETRIES:
        tracer.step(tid, "debug", f"exhausted after {attempts} attempts")
        return {**state, "status": "failed",
                "result": f"Max retries ({MAX_RETRIES}) reached.\n{state['error_log']}"}

    tracer.step(tid, "debug", f"attempt {attempts + 1}")

    try:
        gen_files = json.loads(state["generated_code"])
        impl_ctx  = "\n\n".join(f"# {p}\n{c}" for p, c in gen_files.items())
    except Exception:
        impl_ctx = state.get("generated_code", "")

    raw  = _call(
        role    = "executor",
        system  = DEBUG_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Tests:\n```python\n{state['test_code']}\n```\n\n"
            f"Implementation:\n```python\n{impl_ctx}\n```\n\n"
            f"Error:\n```\n{state['error_log']}\n```\n\n"
            f"Existing files:\n{_files_context(state['files'])}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)

    hypothesis   = data.get("hypothesis", "unknown")
    fixed_files  = data.get("files", {})
    defense_note = data.get("defense_note", "")
    generated    = json.dumps(fixed_files, indent=2)

    tracer.step(tid, "debug", f"hypothesis: {hypothesis[:80]}")
    return {**state,
            "hypothesis":     hypothesis,
            "defense_note":   defense_note,
            "generated_code": generated,
            "debug_attempts": attempts + 1,
            "came_from_debug": True,
            "error_log":      ""}


def node_write_files(state: AutocodeState) -> AutocodeState:
    """
    Write generated code to agent root.
    Handles both patch format (str_replace) and full file writes.
    Patches are preferred -- faster, cheaper, less error-prone.
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return state
    if not state.get("generated_code"):
        return state

    try:
        data = json.loads(state["generated_code"])
    except Exception as e:
        tracer.step(tid, "write_files", f"JSON parse failed: {e}")
        return state

    from core.patch import apply_patch

    # -- Apply str_replace patches for existing files -------------------------
    patches      = data.get("patches", [])
    patch_errors = []
    for p in patches:
        rel_path = p.get("path", "")
        old_text = p.get("old", "")
        new_text = p.get("new", "")

        if cfg.is_protected(rel_path):
            tracer.step(tid, "write_files", f"BLOCKED protected: {rel_path}")
            continue

        target = cfg.agent_root / rel_path
        if not target.exists():
            tracer.step(tid, "write_files",
                        f"patch target missing, skipping: {rel_path}")
            patch_errors.append(f"{rel_path}: file not found for patch")
            continue

        result = apply_patch(target, old_text, new_text)
        if result.ok:
            tracer.step(tid, "write_files",
                        f"patched {rel_path} ({result.lines_changed} lines changed)")
        else:
            tracer.step(tid, "write_files",
                        f"patch FAILED {rel_path}: {result.error}")
            patch_errors.append(f"{rel_path}: {result.error}")

    # -- Write new / overwrite files ------------------------------------------
    new_files = data.get("new_files", {})
    # Backwards compat: if no patches/new_files keys, treat whole data as files dict
    if not patches and not new_files and isinstance(data, dict):
        new_files = data

    for rel_path, content in new_files.items():
        if cfg.is_protected(rel_path):
            tracer.step(tid, "write_files", f"BLOCKED protected: {rel_path}")
            continue

        target = cfg.agent_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = str(target) + ".lock"
        bak_path  = target.with_suffix(target.suffix + ".bak")

        try:
            with FileLock(lock_path, timeout=10):
                if target.exists():
                    shutil.copy2(target, bak_path)
                target.write_text(str(content), encoding="utf-8")
            tracer.step(tid, "write_files",
                        f"wrote {rel_path} ({len(content)} chars)")
        except Timeout:
            tracer.step(tid, "write_files", f"lock timeout: {rel_path}")
        except Exception as e:
            tracer.step(tid, "write_files", f"write error {rel_path}: {e}")

    if patch_errors:
        tracer.step(tid, "write_files",
                    f"{len(patch_errors)} patch error(s): {patch_errors[0]}")

    # Persist test file to agent root so verify can find it
    if state.get("test_code"):
        test_file = cfg.agent_root / "autocode" / "test_autocode_feature.py"
        lock_path = str(test_file) + ".lock"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(lock_path, timeout=10):
                test_file.write_text(state["test_code"], encoding="utf-8")
            tracer.step(tid, "write_files", "test file persisted")
        except Timeout:
            tracer.step(tid, "write_files", "lock timeout on test file")
        except Exception as e:
            tracer.step(tid, "write_files", f"test file write error: {e}")

    return state


def node_verify(state: AutocodeState) -> AutocodeState:
    """
    Verification gate. Runs fresh pytest + ruff. Real exit codes override LLM.
    Hallucination guard: if pytest failed but LLM claims pass, we trust pytest.
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return state

    tracer.step(tid, "verify", "running automated checks")

    # -- Fresh pytest on agent root --
    tests_passed  = False
    fresh_output  = ""
    test_file     = cfg.agent_root / "autocode" / "test_autocode_feature.py"
    tests_dir     = cfg.agent_root / "tests"

    try:
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "--color=no", "-q"]
        if tests_dir.exists():
            cmd.append(str(tests_dir))
        if test_file.exists():
            cmd.append(str(test_file))

        result       = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        fresh_output = (result.stdout + result.stderr).strip()
        tests_passed = result.returncode == 0
    except Exception as e:
        fresh_output = f"pytest failed to run: {e}"

    # -- Ruff lint (non-fatal -- warnings don't block commit) --
    lint_output = ""
    lint_passed = True
    try:
        result      = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(cfg.agent_root),
             "--select", "E,F", "--no-cache"],
            capture_output=True, text=True, timeout=30,
        )
        lint_output = (result.stdout + result.stderr).strip()
        lint_passed = result.returncode == 0
    except Exception as e:
        lint_output = f"ruff not available: {e}"
        lint_passed = True  # non-fatal

    automated_ok = tests_passed  # lint is advisory only

    tracer.step(tid, "verify",
                f"automated: {'PASS' if automated_ok else 'FAIL'} "
                f"(pytest={'OK' if tests_passed else 'FAIL'}, "
                f"lint={'OK' if lint_passed else 'WARN'})")

    # -- LLM review (for spec coverage and cleanliness) --
    try:
        gen_files = json.loads(state["generated_code"])
        impl_ctx  = "\n\n".join(f"# {p}\n{c}" for p, c in gen_files.items())
    except Exception:
        impl_ctx = state.get("generated_code", "")

    raw  = _call(
        role    = "executor",
        system  = VERIFY_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Implementation:\n```python\n{impl_ctx[:3000]}\n```\n\n"
            f"Tests:\n```python\n{state['test_code'][:1000]}\n```\n\n"
            f"FRESH PYTEST OUTPUT (exit code {'0' if tests_passed else '1'}):\n"
            f"{fresh_output[:2000]}\n\n"
            f"RUFF OUTPUT:\n{lint_output[:500]}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)

    # Hallucination guard: real exit code overrides LLM claim
    llm_claims_tests_ok = data.get("automated_checks_passed", True)
    if not tests_passed and llm_claims_tests_ok:
        tracer.step(tid, "verify",
                    "HALLUCINATION DETECTED: LLM claimed tests passed but pytest failed")

    llm_checks_ok = all(
        data.get("checks", {}).get(k, {}).get("passed", False)
        for k in ("syntax", "tests", "spec", "regressions", "cleanliness")
    )

    # Final decision: automated_ok (real) AND llm_checks_ok (spec/cleanliness)
    all_passed = automated_ok and llm_checks_ok
    summary    = data.get("summary", "verification incomplete")
    notes      = json.dumps(data.get("checks", {}), indent=2)

    tracer.step(tid, "verify", f"result: {'PASS' if all_passed else 'FAIL'} -- {summary[:80]}")
    return {**state,
            "verification_passed": all_passed,
            "verification_notes":  (
                f"Automated: {'PASS' if automated_ok else 'FAIL'} | "
                f"LLM: {'PASS' if llm_checks_ok else 'FAIL'}\n"
                f"{summary}\n\n{notes}"
            ),
            "evidence_outputs": {
                "tests":      fresh_output[:2000],
                "lint":       lint_output[:500],
                "regression": fresh_output[:2000],
            }}


def node_commit(state: AutocodeState) -> AutocodeState:
    """Commit the verified change."""
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return state
    if not state.get("verification_passed"):
        return state

    plan   = state.get("plan", [])
    labels = ", ".join(
        s["label"] for s in plan
        if s["label"] not in ("write_tests", "verify")
    )
    msg = (
        f"feat(autocode): {state['task'][:60]}\n\n"
        f"- Steps: {labels}\n"
        f"- Tests: pass\n"
        f"- Verified: yes"
    )

    sha = _git_commit(msg, tid)
    tracer.step(tid, "commit", f"sha: {sha}")

    result_lines = [
        f"autocode complete -- {sha or '(no new commits)'}",
        f"Branch: {state.get('branch', 'main')}",
        "",
        state.get("verification_notes", ""),
    ]
    if state.get("defense_note"):
        result_lines.append(f"\nDefense note: {state['defense_note']}")

    return {**state,
            "status":     "done",
            "commit_sha": sha or "",
            "result":     "\n".join(result_lines)}


def node_distill_memory(state: AutocodeState) -> AutocodeState:
    """
    Store successful debug fixes as procedural knowledge.
    Only runs after a successful commit.
    """
    tid = state.get("trace_id", "")
    if state.get("status") != "done":
        return state

    error_pattern = state.get("error_log", "")[:200]
    hypothesis    = state.get("hypothesis", "")
    defense_note  = state.get("defense_note", "")

    if hypothesis:  # Only store if debugging was involved
        try:
            from memory.store import memory as _mem
            _mem.store_procedural(
                text=(
                    f"Autocode debug fix:\n"
                    f"Task: {state['task'][:80]}\n"
                    f"Error pattern: {error_pattern}\n"
                    f"Hypothesis: {hypothesis[:200]}\n"
                    f"Defense: {defense_note[:150]}"
                ),
                importance = 7,
                tags       = "autocode,debug,fix_pattern",
            )
            tracer.step(tid, "distill_memory", "procedural memory stored")
        except Exception as e:
            tracer.step(tid, "distill_memory", f"store failed: {e}")

    return state


# ── Routing ------------------------------------------------------------------

def route_after_classify(state: AutocodeState) -> str:
    """All tasks go through brainstorming – no more skipping."""
    if state.get("status") == "needs_clarification":
        return "end"
    return "brainstorm"


def route_after_brainstorm(state: AutocodeState) -> str:
    if state.get("status") == "needs_clarification":
        return "end"
    return "write_plan"


def route_after_run_tests(state: AutocodeState) -> str:
    if state.get("error_log"):
        return "systematic_debug"
    return "write_files"


def route_after_debug(state: AutocodeState) -> str:
    if state.get("status") == "failed":
        return "end"
    return "run_tests"


def route_after_write_files(state: AutocodeState) -> str:
    plan    = state.get("plan", [])
    cur_idx = state.get("current_step", 0)

    # If we just wrote a debug fix, re-run tests to validate it
    if state.get("came_from_debug"):
        return "run_tests"

    # Advance to next step or verify
    if cur_idx < len(plan):
        label = plan[cur_idx]["label"]
        if label == "verify":
            return "verify"
        if label not in ("write_tests",):
            return "execute_step"

    return "verify"


def route_after_verify(state: AutocodeState) -> str:
    if state.get("verification_passed"):
        return "commit"
    if state.get("debug_attempts", 0) < MAX_RETRIES:
        return "systematic_debug"
    return "end"


def node_write_files_with_flag_reset(state: AutocodeState) -> AutocodeState:
    """Write files then clear came_from_debug flag (cannot mutate in router)."""
    result = node_write_files(state)
    return {**result, "came_from_debug": False}


# ── Graph assembly -----------------------------------------------------------

def build_graph() -> Any:
    g = StateGraph(AutocodeState)

    g.add_node("classify_task",     node_classify_task)
    g.add_node("brainstorm",        node_brainstorm)
    g.add_node("write_plan",        node_write_plan)
    g.add_node("git_branch",        node_git_branch)
    g.add_node("write_tests",       node_write_tests)
    g.add_node("execute_step",      node_execute_step)
    g.add_node("run_tests",         node_run_tests)
    g.add_node("systematic_debug",  node_systematic_debug)
    g.add_node("write_files",       node_write_files_with_flag_reset)
    g.add_node("verify",            node_verify)
    g.add_node("commit",            node_commit)
    g.add_node("distill_memory",    node_distill_memory)

    g.set_entry_point("classify_task")

    g.add_conditional_edges("classify_task", route_after_classify,
                             {"end": END, "brainstorm": "brainstorm"})

    g.add_conditional_edges("brainstorm", route_after_brainstorm,
                             {"end": END, "write_plan": "write_plan"})

    g.add_edge("write_plan",  "git_branch")
    g.add_edge("git_branch",  "write_tests")

    g.add_conditional_edges(
        "write_tests",
        lambda s: "execute_step" if s.get("test_code") else "verify",
        {"execute_step": "execute_step", "verify": "verify"},
    )

    g.add_edge("execute_step", "run_tests")

    g.add_conditional_edges("run_tests", route_after_run_tests,
                             {"systematic_debug": "systematic_debug",
                              "write_files": "write_files"})

    g.add_conditional_edges("systematic_debug", route_after_debug,
                             {"end": END, "run_tests": "run_tests"})

    g.add_conditional_edges("write_files", route_after_write_files,
                             {"execute_step":    "execute_step",
                              "run_tests":       "run_tests",
                              "verify":          "verify"})

    g.add_conditional_edges("verify", route_after_verify,
                             {"commit": "commit",
                              "systematic_debug": "systematic_debug",
                              "end": END})

    g.add_edge("commit",         "distill_memory")
    g.add_edge("distill_memory", END)

    return g.compile()


_GRAPH = None


def get_graph() -> Any:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ── Public entry point -------------------------------------------------------

def run_autocode_agent(
    task:        str,
    files:       dict[str, str] | None = None,
    mode:        str = "feature",
    target_file: str = "",
    error_msg:   str = "",
) -> dict:
    """
    Run the superpowers-enhanced autocode workflow.

    Args:
        task:        Natural language description of what to build / fix.
        files:       {relative_path: content} of relevant source files.
        mode:        "feature" | "fix_error" | "improve" | "add_feature"
        target_file: File to edit (used to set task for fix_error / add_feature).
        error_msg:   Error traceback (for mode="fix_error").

    Returns:
        dict with: status, result, commit_sha, spec, plan, branch
    """
    import time
    from tools.notify import notify

    # Adjust task based on mode
    if mode == "fix_error" and target_file:
        task = f"Fix error in {target_file}: {error_msg or task}"
    elif mode == "add_feature" and target_file:
        task = f"Add feature to {target_file}: {task}"

    tid   = tracer.new_trace("autocode", goal=task[:60])
    state = _default_state(task, files or {}, mode=mode, target_file=target_file)
    state["trace_id"] = tid

    # Pre-run snapshot
    _git_snapshot(f"pre-autocode: {task[:30]}", tid)

    # Store episodic start
    try:
        from memory.store import memory as _mem
        _mem.store_episodic(
            text=f"Autocode started: '{task[:60]}' mode={mode}",
            importance=5, goal=task, outcome="unknown", tools_used="autocode",
        )
    except Exception:
        pass

    t0 = time.time()
    try:
        final = get_graph().invoke(state)
    except Exception as e:
        tracer.error(tid, "autocode", f"crash: {e}")
        tracer.finish(tid, success=False, result=str(e))
        final = {**state, "status": "failed", "result": str(e)}

    elapsed = round(time.time() - t0, 1)
    success = final.get("status") == "done"
    tracer.finish(tid, success=success, result=final.get("result", "")[:200])

    # Store episodic completion
    try:
        from memory.store import memory as _mem
        _mem.store_episodic(
            text=(
                f"Autocode {'succeeded' if success else 'failed'}: '{task[:60]}' "
                f"sha={final.get('commit_sha','')}"
            ),
            importance=7 if success else 5,
            goal=task, outcome="success" if success else "failure",
            tools_used="autocode,file,git",
        )
    except Exception:
        pass

    # Notify
    summary = final.get("result", "")[:60]
    if success:
        notify(action="send", title="Autocode complete", message=f"{task[:40]}: {summary}")
    else:
        notify(action="send", title="Autocode FAILED",
               message=f"{task[:40]}: {final.get('error_log','')[:60]}")

    return {
        "status":     final.get("status", "unknown"),
        "result":     final.get("result", ""),
        "commit_sha": final.get("commit_sha", ""),
        "spec":       final.get("spec", ""),
        "plan":       final.get("plan", []),
        "branch":     final.get("branch", ""),
        "elapsed_s":  elapsed,
        "trace_id":   tid,
    }


# Alias for compatibility with the workflow_tool.py autocode graph builder
build_autocode_graph = build_graph