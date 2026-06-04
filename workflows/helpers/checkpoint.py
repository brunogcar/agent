"""
core/workflow_checkpoint.py — Append-only JSONL journal for workflow resumability.
Saves workflow state at critical boundaries to survive agent crashes.
"""
from __future__ import annotations

import json
import time
import shutil
import logging
import os
import datetime
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from core.config import cfg

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = cfg.workspace_root / "checkpoints"
QUARANTINE_DIR = CHECKPOINT_DIR / "quarantine"

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

MAX_RESUMES = 5

def sanitize_state(state: Any, _seen: set = None) -> Any:
    """Recursively extract only JSON-safe primitives from state."""
    if _seen is None:
        _seen = set()
        
    # 🔴 CRITICAL FIX: Only track containers to prevent false positives on interned primitives
    if isinstance(state, (dict, list, tuple, set)):
        obj_id = id(state)
        if obj_id in _seen:
            return "<circular_reference>"
        _seen.add(obj_id)

    if isinstance(state, (str, int, float, bool, type(None))):
        return state
    elif isinstance(state, (datetime.datetime, datetime.date, datetime.time)):
        return state.isoformat()
    elif isinstance(state, datetime.timedelta):
        return state.total_seconds()
    elif isinstance(state, bytes):
        return state.decode("utf-8", errors="replace")
    elif isinstance(state, Decimal):
        return str(state)
    elif isinstance(state, uuid.UUID):
        return str(state)
    elif hasattr(state, "__fspath__"): # Path-like objects
        return str(state)
    elif isinstance(state, dict):
        return {str(k): sanitize_state(v, _seen) for k, v in state.items()}
    elif isinstance(state, (list, tuple)):
        return [sanitize_state(v, _seen) for v in state]
    elif isinstance(state, set):
        try:
            return [sanitize_state(v, _seen) for v in sorted(state)]
        except TypeError:
            return [sanitize_state(v, _seen) for v in state]
    else:
    # Drop non-serializable objects (httpx clients, locks, CircuitBreakers).
    # Returns None (falsy) to prevent truthy-string crashes on resume.
    # 
    # 🏗️ ARCHITECTURAL BEST PRACTICE FOR FUTURE NODES:
    # If a LangGraph node requires an unserializable object, it MUST reconstruct 
    # it on entry if missing.
    # Example:
    #   client = state.get("http_client")
    #   if client is None:
    #       client = httpx.Client()
    #       state["http_client"] = client
        return None

def save_checkpoint(trace_id: str, node_name: str, state: dict) -> None:
    """Append a checkpoint to the workflow's JSONL journal."""
    if not trace_id:
        return
        
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    entry = {
        "ts": time.time(),
        "node": node_name,
        "status": state.get("status", "running"),
        "state": sanitize_state(state),
        "resume_count": 0,
         "version": 1  # Checkpoint schema version for compatibility validation
    }
    
    try:
        # Count existing resumes to detect zombie loops
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                entry["resume_count"] = sum(1 for line in lines if '"node": "resume"' in line)
                
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno()) # Force OS to write to disk
    except Exception as e:
        logger.warning(f"[Checkpoint] Failed to write {trace_id}: {e}")

def get_latest(trace_id: str) -> Optional[dict]:
    """Get the latest checkpoint state for a trace."""
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if not path.exists():
        return None
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            return None
            
        last_line = lines[-1].strip()
        entry = json.loads(last_line)
        
        # Zombie check: if resumed too many times, quarantine
        is_zombie = False
        if entry.get("resume_count", 0) >= MAX_RESUMES:
            is_zombie = True
            
        # Check for consecutive same-node failures (pathological loop)
        if not is_zombie and len(lines) >= 2:
            try:
                prev = json.loads(lines[-2].strip())
                if (prev.get("status") == "failed" and entry.get("status") == "failed" and
                    prev.get("node") == entry.get("node") and prev.get("node") not in ("resume", "")):
                    is_zombie = True
            except Exception:
                pass
                
        if is_zombie:
            logger.warning(f"[Checkpoint] Quarantining zombie workflow {trace_id}")
            quarantine(trace_id)
            return None
            
        state = entry.get("state")
        if isinstance(state, dict):
            # Inject version from envelope into state so base.py can validate it
            state["_checkpoint_version"] = entry.get("version", 0)
        return state
    except Exception as e:
        logger.warning(f"[Checkpoint] Failed to read {trace_id}: {e}")
        return None

def quarantine(trace_id: str) -> None:
    """Move a workflow journal to quarantine."""
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if path.exists():
        try:
            shutil.move(str(path), str(QUARANTINE_DIR / f"{trace_id}.jsonl"))
        except Exception:
            pass

def mark_complete(trace_id: str) -> None:
    """Delete the checkpoint journal on successful completion."""
    path = CHECKPOINT_DIR / f"{trace_id}.jsonl"
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

def scan_incomplete() -> list[str]:
    """Find all incomplete workflows (modified in last 48h, status != success/failed)."""
    incomplete = []
    cutoff = time.time() - (48 * 3600)
    
    for path in CHECKPOINT_DIR.glob("*.jsonl"):
        if path.stat().st_mtime < cutoff:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                last = json.loads(lines[-1].strip())
                if last.get("status") not in ("success", "failed"):
                    incomplete.append(path.stem)
        except Exception:
            pass
            
    return incomplete