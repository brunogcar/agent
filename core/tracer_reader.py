"""
core/trace_reader.py — Trace log reader and parser.
Reads structured traces from the in-memory store and falls back to 
scanning JSONL log files on disk for historical traces.
"""
from __future__ import annotations

import json
from typing import Optional

from core.config import cfg
from core.tracer import tracer


def read_trace(trace_id: str) -> Optional[dict]:
    """
    Retrieve a full trace timeline by trace_id.
    1. Fast path: Check in-memory _TraceStore (holds last 200 traces).
    2. Slow path: Scan JSONL log files on disk.
    """
    if not trace_id:
        return None

    # 1. Fast path: In-memory store
    mem_trace = tracer.get(trace_id)
    if mem_trace:
        return _format_trace(mem_trace)

    # 2. Slow path: Disk scan
    return _scan_disk(trace_id)


def _format_trace(trace: dict) -> dict:
    """Format a trace dict into a clean timeline payload."""
    return {
        "trace_id": trace.get("trace_id"),
        "workflow": trace.get("workflow"),
        "goal": trace.get("goal"),
        "status": trace.get("status"),
        "started_at": trace.get("started_fmt"),
        "elapsed_s": trace.get("elapsed"),
        "result": trace.get("result"),
        "steps": trace.get("steps", []),
    }


def _scan_disk(trace_id: str) -> Optional[dict]:
    """Scan JSONL log files in reverse chronological order."""
    log_dir = cfg.log_path
    if not log_dir.exists():
        return None

    # Get all log files, sorted newest first
    log_files = sorted(log_dir.glob("agent_*.jsonl"), reverse=True)
    
    # Limit scan to last 14 days to prevent massive I/O on huge log dirs
    log_files = log_files[:14]

    steps = []
    trace_meta = {}

    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # Quick string check before expensive JSON parse
                    if trace_id not in line:
                        continue
                    
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if record.get("trace_id") != trace_id:
                        continue

                    event = record.get("event")
                    
                    if event == "trace_start":
                        trace_meta = {
                            "workflow": record.get("workflow"),
                            "goal": record.get("goal"),
                            "started_at": record.get("started_fmt"),
                        }
                    elif event == "trace_finish":
                        trace_meta["status"] = "success" if record.get("success") else "failed"
                        trace_meta["elapsed_s"] = record.get("elapsed_s")
                        trace_meta["result"] = record.get("result")
                    else:
                        # step, error, warning
                        steps.append({
                            "ts": record.get("ts"),
                            "event": event,
                            "node": record.get("node"),
                            "message": record.get("message"),
                            **{k: v for k, v in record.items() if k not in ("event", "trace_id", "node", "message", "ts")}
                        })
        except Exception:
            continue

    if not trace_meta and not steps:
        return None

    # Sort steps by timestamp
    steps.sort(key=lambda x: x.get("ts", 0))

    return {
        "trace_id": trace_id,
        **trace_meta,
        "steps": steps,
    }

def list_recent_traces(limit: int = 10) -> list[dict]:
    """List recent traces from memory."""
    mem_traces = tracer.recent(limit)
    return [_format_trace(t) for t in mem_traces]