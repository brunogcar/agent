"""
Utility functions for autocode workflow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.llm import llm
from core.config import cfg

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
        if _have_patch and hint and len(content) > cfg.autocode_max_file_chars:
            snippet  = extract_relevant_sections(content, hint, max_chars=cfg.autocode_max_file_chars)
            was_compressed = len(snippet) < len(content)
            if was_compressed:
                parts.append(
                    f"### {path} (relevant sections, {len(content)} total chars)\n"
                    f"```\n{snippet}\n```"
                )
                continue

        snippet = content[:cfg.autocode_max_file_chars]
        if len(content) > cfg.autocode_max_file_chars:
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