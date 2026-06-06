"""Helpers for autocode workflow."""
from __future__ import annotations
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from core.config import cfg
from core.tracer import tracer

def _extract_code(text: str) -> list[str]:
    """Extract code blocks from text."""
    pattern = r"```(?:[^\n]*\n)?(.*?)```"
    matches = re.finditer(pattern, text, re.DOTALL)
    return [m.group(1).strip() for m in matches]

def _parse_json(text: str | None) -> dict:
    """Parse JSON from text, extracting from code blocks if needed."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        code_blocks = _extract_code(text)
        for block in code_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return {}

def _parse_json_array(text: str | None) -> list:
    """Parse JSON array from text."""
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        code_blocks = _extract_code(text)
        for block in code_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return []

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

def _call(role: str, system: str, user: str, timeout: int | None = None, temperature: float | None = None) -> str:
    """Call the LLM with the given role, system prompt, and user message."""
    from workflows.autocode_helpers.state import NODE_TIMEOUTS
    if timeout is None:
        timeout = NODE_TIMEOUTS.get(role, NODE_TIMEOUTS["default"])
    try:
        response = llm.complete(
            role=role,
            system=system,
            user=user,
            timeout=timeout,
            temperature=temperature,
        )
        if response.ok:
            return response.text
        else:
            raise RuntimeError(f"LLM error: {response.error}")
    except Exception as e:
        tracer.error("llm_call", f"Failed to call {role} model: {e}")
        raise

def _write_files(state: dict) -> dict:
    """
    Write files with EXPLICIT base directory resolution:
    - If project_root is set, uses ProjectManager to resolve source_root
      (either cfg.agent_root OR cfg.workspace_root/projects/X/code).
    - Fallback: legacy heuristic based on 'workspace/' string.
    """
    files_map = state.get("files_map") or state.get("files", {})
    if not files_map:
        return {"error": "No files to write"}

    backups = {}
    written = []
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "")

    # 1. Determine the absolute base directory for writing
    if project_root:
        try:
            from core.kgraph.project import ProjectManager, is_same_path
            # Check if the project_root IS the agent_root
            is_agent = is_same_path(Path(project_root), cfg.agent_root)
            pm = ProjectManager(project_root, is_agent_root=is_agent)
            base = pm.source_root
            tracer.step(tid, "write_files", f"Resolved base via ProjectManager: {base}")
        except Exception as e:
            tracer.warning(tid, "write_files", f"ProjectManager failed ({e}), falling back to cfg.agent_root")
            base = cfg.agent_root
    else:
        # Fallback legacy behavior if project_root is not provided
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
            if full_path.exists():
                backup_path = full_path.with_suffix(full_path.suffix + ".bak")
                backup_path.write_text(full_path.read_text(encoding="utf-8"), encoding="utf-8")
                backups[file_path] = str(backup_path)

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
            # Best-effort rollback if write fails mid-loop
            for orig_str, backup_path in backups.items():
                try:
                    Path(orig_str).write_text(Path(backup_path).read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass
            tracer.error(tid, f"Atomic write failed for {file_path}: {e}")
            return {"error": f"Write failed: {e}", "partial_written": written, "backups": backups}

    return {"files_written": written, "backups": backups}

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
