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

# [v2.0] Phase 7: _write_files() DELETED — was dead code (never called by any node).
# The actual file writing logic lives in nodes/apply_patches.py + nodes/write_new_files.py.

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
