"""
core/context_pruner.py — VRAM Context Pruning Middleware.
Intercepts massive tool outputs before they hit the LangGraph state or MCP client.
Saves full output to disk atomically, truncates intelligently, and injects 
structured recovery metadata.
"""
from __future__ import annotations

import uuid
import time
import os
from pathlib import Path
from core.config import cfg

ARTIFACT_DIR = cfg.workspace_root / ".artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# ~8000 chars is roughly 2000-2500 tokens. Safe for 16GB VRAM envelope.
MAX_CHARS = 8000 
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024  # 10MB limit per artifact

def _save_artifact(tool_name: str, text: str, trace_id: str) -> str | None:
    """Save full text to disk atomically. Returns path or None."""
    # Skip saving massive artifacts to prevent disk bloat
    if len(text.encode('utf-8', errors='ignore')) > MAX_ARTIFACT_BYTES:
        return None 
        
    artifact_name = f"{trace_id or 'notrace'}_{tool_name}_{uuid.uuid4().hex[:6]}.txt"
    artifact_path = ARTIFACT_DIR / artifact_name
    tmp_path = artifact_path.with_suffix('.tmp')
    
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, artifact_path) # Atomic rename (prevents partial reads)
        return str(artifact_path)
    except Exception:
        if tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass
        return None

def _truncate_text(tool_name: str, text: str) -> str:
    """Apply tool-aware truncation."""
    if tool_name in ("python_exec", "cli"):
        # Errors and tracebacks are almost always at the end
        truncated = text[-MAX_CHARS:]
        # Try to not cut exactly in the middle of a line if possible
        newline_idx = truncated.find('\n')
        if newline_idx != -1 and newline_idx < 500:
            truncated = truncated[newline_idx+1:]
    else:
        # Web / Default: Keep head + tail
        head = MAX_CHARS // 2
        tail = MAX_CHARS - head
        truncated = text[:head] + f"\n\n... [TRUNCATED {len(text) - MAX_CHARS} CHARS] ...\n\n" + text[-tail:]
    return truncated

def prune_text(tool_name: str, text: str, trace_id: str = "") -> str:
    """
    Prune a raw string output from a tool.
    Used by tools that return raw strings (like cli).
    """
    if not text or not isinstance(text, str):
        return text
        
    if len(text) <= MAX_CHARS:
        return text
        
    artifact_path = _save_artifact(tool_name, text, trace_id)
    truncated = _truncate_text(tool_name, text)
        
    # For string returns, we MUST append the warning to the text
    warning = (
        f"\n\n[⚠️ CONTEXT PRUNED]\n"
        f"Original output: {len(text):,} chars. Truncated to: {len(truncated):,} chars.\n"
    )
    if artifact_path:
        warning += f"Full output saved to: {artifact_path}\nUse the 'file' tool to read the complete text if critical details are missing."
    else:
        warning += "Full output was too large to save or disk write failed."
        
    return truncated + warning

def prune_tool_dict(tool_name: str, data: dict, trace_id: str = "") -> dict:
    """
    Prune string fields inside a tool's return dictionary.
    Used by tools that return dicts (web, python_exec).
    Injects structured metadata keys instead of polluting the string.
    """
    if not isinstance(data, dict):
        return data
        
    def _prune_field(key: str, text: str) -> tuple[str, dict]:
        if len(text) <= MAX_CHARS:
            return text, {}
            
        artifact_path = _save_artifact(tool_name, text, trace_id)
        truncated = _truncate_text(tool_name, text)
        
        metadata = {
            "_pruned": True,
            "_original_chars": len(text),
            "_truncated_chars": len(truncated),
        }
        if artifact_path:
            metadata["_artifact_path"] = artifact_path
            metadata["_recovery_hint"] = f"Use file(path='{artifact_path}') to read full output."
            
        return truncated, metadata

    # Handle web scrape/read and python_exec
    if "text" in data and isinstance(data["text"], str):
        data["text"], meta = _prune_field("text", data["text"])
        data.update(meta)
        
    if "output" in data and isinstance(data["output"], str):
        data["output"], meta = _prune_field("output", data["output"])
        data.update(meta)
        
    # Handle web search_and_read
    if "results" in data and isinstance(data["results"], list):
        for item in data["results"]:
            if isinstance(item, dict) and "text" in item and isinstance(item["text"], str):
                item["text"], meta = _prune_field("text", item["text"])
                item.update(meta)
                
    return data

def cleanup_old_artifacts(max_age_days: int = 7):
    """Delete artifacts older than max_age_days. Call on server startup."""
    cutoff = time.time() - (max_age_days * 86400)
    try:
        for f in ARTIFACT_DIR.glob("*.txt"):
            if f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass