"""Helpers for autocode workflow."""
from __future__ import annotations
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from core.config import cfg
from core.llm import llm
from core.tracer import tracer

def _extract_code(text: str) -> list[str]:
    """Extract code blocks from text."""
    pattern = r"```(?:[^\n]*\n)?(.*?)```"
    matches = re.finditer(pattern, text, re.DOTALL)
    return [m.group(1).strip() for m in matches]

def _parse_json(text: str | None) -> dict:
    """Parse JSON from text, extracting from code blocks if needed.

    [v2.0] Now delegates to core.json_extract.extract_json — single source of
    truth for all LLM JSON parsing in the codebase.
    """
    from core.json_extract import extract_json
    return extract_json(text)

def _parse_json_array(text: str | None) -> list:
    """Parse JSON array from text.

    [v2.0] Now delegates to core.json_extract.extract_json_array.
    """
    from core.json_extract import extract_json_array
    return extract_json_array(text)

def _files_context(files: dict[str, str], max_len: int = 2000) -> str:
    """Format files dictionary for LLM context."""
    if not files:
        return "No files provided."
    context = []
    for path, content in files.items():
        context.append(f"# {path}\n{content[:max_len]}")
    return "\n\n".join(context)

def _should_copy_file(path: str | Path, protected_files: frozenset[str]) -> bool:
    """Check if a file should be copied (not protected)."""
    path_str = str(path).replace("\\", "/")
    name = Path(path).name
    return name not in protected_files and path_str not in protected_files


# [v2.0] Cancellation flag for graph-level timeout.
# When invoke_with_timeout() detects a timeout, it sets this flag.
# _call() checks it between retries — prevents waiting through a retry
# backoff when the graph has already timed out.
# TODO(2.0-later): Consider threading.Event for cleaner cross-thread signaling.
_cancellation_requested = False


def request_cancellation() -> None:
    """[v2.0] Set the cancellation flag — called by invoke_with_timeout on timeout.

    After this is called, _call() will raise RuntimeError on the next retry
    check instead of sleeping through the backoff.
    """
    global _cancellation_requested
    _cancellation_requested = True


def clear_cancellation() -> None:
    """[v2.0] Clear the cancellation flag — called at the start of a new graph invocation."""
    global _cancellation_requested
    _cancellation_requested = False


def is_cancellation_requested() -> bool:
    """[v2.0] Check if cancellation was requested."""
    return _cancellation_requested


def _call(role: str, system: str, user: str, timeout: int | None = None, temperature: float | None = None, json_schema: dict | None = None, retries: int = 2) -> str:
    """Call the LLM with the given role, system prompt, and user message.

    v1.3: Added json_schema param for structured generation. When provided,
    LM Studio enforces the schema at generation time via outlines.
    [Pre-2.0 Fix] Added retry with exponential backoff for transient failures.
    Was: single attempt — a rate limit or network blip crashed the entire workflow.
    [v2.0] Added cancellation flag check between retries — prevents waiting
    through a retry backoff when the graph has already timed out.
    """
    import time as _time
    if timeout is None:
        timeout = cfg.model_registry.get(role, {}).get("timeout", cfg.execution_timeout)
    last_error = None
    for attempt in range(retries + 1):
        # [v2.0] Check cancellation flag before each attempt — if the graph
        # timed out during a previous retry's backoff sleep, bail immediately.
        if _cancellation_requested:
            raise RuntimeError("LLM call cancelled — graph timeout exceeded")
        try:
            response = llm.complete(
                role=role,
                system=system,
                user=user,
                timeout=timeout,
                temperature=temperature,
                json_schema=json_schema,
            )
            if response.ok:
                return response.text
            else:
                raise RuntimeError(f"LLM error: {response.error}")
        except Exception as e:
            last_error = e
            if attempt < retries:
                _time.sleep(2 ** attempt)  # 1s, 2s, 4s...
                continue
            tracer.error("", "llm_call", f"Failed to call {role} model after {retries+1} attempts: {e}")
            raise
    # Should never reach here, but defensive
    raise last_error  # type: ignore[misc]

def _write_files(state: dict) -> dict:
    """[v2.0] DEPRECATED — use node_apply_patches + node_write_new_files instead.

    This function is kept for backward compatibility but is never called by
    any node (Phase 5 cleanup confirmed: execute.py imported it but never
    called it — dead import removed). The actual file writing logic now lives
    in nodes/apply_patches.py + nodes/write_new_files.py.

    Original docstring:
    Write files with EXPLICIT base directory resolution.
    """
    files_map = state.get("files_map") or state.get("files", {})
    if not files_map:
        return {"error": "No files to write"}

    # [Bug #1] No .bak backups — atomic writes only. Git provides versioning.
    written = []
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "")

    if project_root:
        try:
            from core.kgraph.project import ProjectManager, is_same_path
            is_agent = is_same_path(Path(project_root), cfg.agent_root)
            pm = ProjectManager(project_root, is_agent_root=is_agent)
            base = pm.source_root
            tracer.step(tid, "write_files", f"Resolved base via ProjectManager: {base}")
        except Exception as e:
            tracer.warning(tid, "write_files", f"ProjectManager failed ({e}), falling back to cfg.agent_root")
            base = cfg.agent_root
    else:
        if any("workspace" in str(p) for p in files_map.keys()):
            base = cfg.workspace_root
        else:
            base = cfg.agent_root
        tracer.step(tid, "write_files", f"Using fallback base: {base}")

    for file_path, content in files_map.items():
        if not file_path or not content:
            continue

        full_path = Path(base) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Atomic write: tempfile + os.replace (no .bak backup)
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=full_path.parent,
                delete=False, suffix='.tmp'
            ) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)

            os.replace(tmp_path, full_path)
            written.append(file_path)

        except Exception as e:
            if 'tmp_path' in locals() and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            tracer.error(tid, "atomic_write", f"Atomic write failed for {file_path}: {e}")  # [Pre-2.0 Fix] was 2 args
            return {"error": f"Write failed: {e}", "partial_written": written}

    return {"files_written": written}

def _get_autocode_run_path(trace_id: str) -> Path:
    """Return per-run autocode directory: workspace/autocode/YYYYMMDD/{trace_id}/"""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    run_dir = cfg.workspace_root / "autocode" / date_str / trace_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def _cleanup_old_autocode_runs(max_age_days: int = 7) -> None:
    """Delete autocode run folders older than max_age_days. Called on-demand."""
    import shutil
    from datetime import datetime, timedelta
    autocode_base = cfg.workspace_root / "autocode"
    if not autocode_base.exists():
        return
    cutoff = datetime.now() - timedelta(days=max_age_days)
    for date_dir in autocode_base.iterdir():
        if not date_dir.is_dir() or not date_dir.name.isdigit() or len(date_dir.name) != 8:
            continue
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y%m%d")
            if dir_date < cutoff:
                shutil.rmtree(date_dir, ignore_errors=True)
                tracer.step("autocode", "cleanup", f"Removed old autocode dir: {date_dir}")
        except (ValueError, OSError):
            continue
