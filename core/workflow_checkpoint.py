"""
core/workflow_checkpoint.py — Append-only JSONL journal for workflow resumability.
Saves workflow state at critical boundaries to survive agent crashes.
"""
from __future__ import annotations

import json
import time
import shutil
import logging
from pathlib import Path
from typing import Any, Optional

from core.config import cfg

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = cfg.workspace_root / "checkpoints"
QUARANTINE_DIR = CHECKPOINT_DIR / "quarantine"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

MAX_RESUMES = 3

def sanitize_state(state: dict) -> dict:
    """Extract only JSON-safe primitives from WorkflowState."""
    safe = {}
    for k, v in state.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            safe[k] = v
        elif isinstance(v, (list, tuple)):
            try:
                json.dumps(v)
                safe[k] = v
            except (TypeError, ValueError):
                safe[k] = [str(item) for item in v]
        elif isinstance(v, dict):
            try:
                json.dumps(v)
                safe[k] = v
            except (TypeError, ValueError):
                safe[k] = {str(ik): str(iv) for ik, iv in v.items()}
        elif isinstance(v, Path):
            safe[k] = str(v)
        else:
            # Drop non-serializable objects (httpx clients, locks, CircuitBreakers)
            pass
    return safe

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
        "resume_count": 0 
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
        if entry.get("resume_count", 0) >= MAX_RESUMES:
            logger.warning(f"[Checkpoint] Quarantining zombie workflow {trace_id}")
            quarantine(trace_id)
            return None
            
        return entry.get("state")
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