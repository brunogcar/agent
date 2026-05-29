"""
core/context_pruner.py — VRAM Context Pruning Middleware.
Intercepts massive tool outputs before they hit the LangGraph state or MCP client.
Saves full output to disk, truncates intelligently, and injects recovery metadata.
"""
from __future__ import annotations

import re
import uuid
import time
from pathlib import Path
from core.config import cfg

ARTIFACT_DIR = cfg.workspace_root / ".artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# ~8000 chars is roughly 2000-2500 tokens. Safe for 16GB VRAM envelope.
MAX_CHARS = 8000 

def prune_text(tool_name: str, text: str, trace_id: str = "") -> str:
    """Prune a raw string output from a tool."""
    if not text or not isinstance(text, str):
        return text
        
    if len(text) <= MAX_CHARS:
        return text
        
    # 1. Save full artifact to disk
    artifact_name = f"{trace_id or 'notrace'}_{tool_name}_{uuid.uuid4().hex[:6]}.txt"
    artifact_path = ARTIFACT_DIR / artifact_name
    try:
        artifact_path.write_text(text, encoding="utf-8")
    except Exception:
        pass # Fail open - truncation is more important than saving artifact
        
    # 2. Tool-aware truncation
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
        
    # 3. Inject metadata warning
    warning = (
        f"\n\n[⚠️ CONTEXT PRUNED]\n"
        f"Original output: {len(text):,} chars. Truncated to: {len(truncated):,} chars.\n"
        f"Full output saved to: {artifact_path}\n"
        f"Use the 'file' tool to read the complete text if critical details are missing."
    )
    
    return truncated + warning

def prune_tool_dict(tool_name: str, data: dict, trace_id: str = "") -> dict:
    """Prune string fields inside a tool's return dictionary."""
    if not isinstance(data, dict):
        return data
        
    # Handle web scrape/read
    if "text" in data and isinstance(data["text"], str):
        data["text"] = prune_text(tool_name, data["text"], trace_id)
        
    # Handle web search_and_read
    if "results" in data and isinstance(data["results"], list):
        for item in data["results"]:
            if isinstance(item, dict) and "text" in item and isinstance(item["text"], str):
                item["text"] = prune_text(tool_name, item["text"], trace_id)
                
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