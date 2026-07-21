"""
Skill creation node.

[P1 #3] Now resolves skill path via project_root/workspace_root, not always agent_root.
[P2 #15] Skill name sanitized — no path separators allowed (prevents path traversal).
[P2 #16] Skill code validated with ast.parse() before writing.
[P2 #17] skill_created flag is now set on success.

[v1.2 #36] Added:
  - Empty-file early rejection (was: silently wrote empty file when LLM
    returned no skill_file content).
  - Skill code fallback keys (skill_code, code) — LLMs sometimes use
    alternate keys.
  - Smoke-test: importlib.import_module the new skill file to catch
    missing-dep / import-time errors before reporting success.
  - Git commit the new skill file so the workflow's git history captures
    the skill creation.
[v1.2] Removed unused `from typing import Any` import.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from core.atomic_write import atomic_write
from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_impl.constants import CREATE_SKILL_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from core.config import cfg
from core.tracer import tracer


def _sanitize_skill_name(name: str) -> str:
    """[P2 #15] Sanitize skill name — only alphanumeric + underscore allowed."""
    # Replace any non-alphanumeric chars with underscore
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip("_")
    # Fallback if empty
    return sanitized or "unnamed_skill"


def _validate_python_syntax(code: str) -> tuple[bool, str]:
    """[P2 #16] Validate that skill code is valid Python."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"


def node_create_skill(state: AutocodeState) -> dict:
    """Create a new skill file based on the task description."""
    # [v3.4 #38] HiTL check — if enabled and not approved, pause before creating skill
    if getattr(cfg, "autocode_hitl_enabled", False) and not state.get("hitl_approved", False):
        tid = state.get("trace_id", "")
        tracer.step(tid, "hitl_gate", "create_skill paused — awaiting human approval")
        try:
            from core.observability.checkpoint import save_checkpoint
            save_checkpoint(tid, "hitl", state)
        except Exception:
            pass
        return {"status": "awaiting_approval"}

    tid = state.get("trace_id", "")
    task = state.get("task", "")
    tracer.step(tid, "node_create_skill", f"Creating skill: {task[:100]}...")

    # Generate skill using CREATE_SKILL_SYSTEM
    raw = _call(
        role="executor",
        system=CREATE_SKILL_SYSTEM,
        user=f"Task:\n{task}",
        timeout=EXECUTOR_TIMEOUT,
        trace_id=tid,  # [v1.2 P1] attribute retry-exhaustion errors to this trace
    )
    data = _parse_json(raw)

    # [P2 #15] Sanitize skill name — prevent path traversal via / or \
    skill_name = _sanitize_skill_name(data.get("skill_name", "unknown"))
    skill_file_content = data.get("skill_file", "")
    explanation = data.get("explanation", "")

    # [v1.2 fix] Reject empty skill_file content early — prevents silent empty-file write.
    # Also try common alternative key names the LLM might use.
    if not skill_file_content:
        skill_file_content = data.get("skill_code", "") or data.get("code", "")
    if not skill_file_content:
        updates = {}
        updates["error"] = "LLM returned empty skill_file content"
        updates["status"] = "failed"
        tracer.error(tid, "node_create_skill", updates["error"])
        return updates

    updates = {}

    # [P2 #16] Validate syntax before writing
    if skill_file_content:
        ok, syntax_error = _validate_python_syntax(skill_file_content)
        if not ok:
            updates["error"] = f"Skill code has invalid Python syntax: {syntax_error}"
            updates["status"] = "failed"
            tracer.error(tid, "node_create_skill", updates["error"])
            return updates

    # Write skill file
    if not state.get("dry_run", False):
        try:
            # [P1 #3] Resolve skill directory based on project_root, not always agent_root.
            # If working on a workspace project, write to that project's skills/ dir.
            project_root = state.get("project_root", "")
            if project_root:
                base = Path(project_root) / "skills"
            else:
                base = cfg.agent_root / "skills"

            skill_path = base / f"{skill_name}.py"
            # [Pre-2.0 Fix / v1.10 Phase A] Atomic write — was: direct write_text
            # (crash mid-write corrupts the skill file). Now: tempfile + os.replace
            # via the shared core.atomic_write helper (replaces the inline block).
            atomic_write(skill_path, skill_file_content)

            updates["skill_path"] = str(skill_path)
            updates["skill_created"] = True  # [P2 #17] Set flag so autocode.py can detect it
            updates["status"] = "done"
            updates["result"] = f"Skill created: {skill_path}\n{explanation}"

            tracer.step(tid, "node_create_skill", f"Created skill: {skill_path}")

            # [v1.2 #36] Smoke-test: import the module to catch missing deps.
            try:
                import importlib
                import importlib.util
                # [v1.4 P1] Removed sys.path.insert — spec_from_file_location loads
                # directly from the file path, doesn't need sys.path. The insert
                # was unnecessary AND leaked parent_dir into sys.path permanently.
                # [v1.2 fix] Use spec_from_file_location to load the module
                # directly from the file path. This bypasses namespace-package
                # conflicts when an existing `skills/` package (e.g. the agent's
                # own skills dir) is already in sys.modules — the naive
                # `importlib.import_module("skills.<name>")` lookup would fail
                # because Python caches the first-loaded `skills` package's
                # __path__.
                spec = importlib.util.spec_from_file_location(
                    f"_smoke_test_{skill_name}", skill_path
                )
                _smoke_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_smoke_module)
            except Exception as e:
                # Import failed — delete the broken file
                try:
                    skill_path.unlink()
                except Exception:
                    pass
                updates["error"] = f"Skill file failed import smoke-test: {e}"
                updates["status"] = "failed"
                updates.pop("skill_created", None)
                tracer.error(tid, "node_create_skill", updates["error"])
                return updates

            # [v1.2 #36] Git commit the new skill file
            try:
                # [v1.10 / Phase B] _git_commit signature changed: now
                # `commit(project_root, message, target_file="", tid="")`
                # (project_root FIRST). The backward-compat alias in
                # workflows.autocode_impl.git_ops points at the new function
                # object — so we use the new arg order here.
                from workflows.autocode_impl.git_ops import _git_commit
                _git_commit(
                    state.get("project_root", ""),
                    f"skill(autocode): {skill_name}",
                    "",
                    tid,
                )
                tracer.step(tid, "node_create_skill", f"Committed skill: {skill_name}")
            except Exception as e:
                tracer.warning(tid, "node_create_skill", f"Git commit failed (non-fatal): {e}")
        except Exception as e:
            updates["error"] = f"Failed to create skill: {e}"
            updates["status"] = "failed"
            tracer.error(tid, "node_create_skill", updates["error"])
    else:
        updates["skill_path"] = f"[DRY RUN] Would create: skills/{skill_name}.py"
        updates["skill_created"] = True  # [P2 #17]
        updates["status"] = "done"
        updates["result"] = f"Dry run: {explanation}"

    return updates
