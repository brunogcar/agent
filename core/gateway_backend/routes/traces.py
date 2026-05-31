"""
core/gateway_backend/routes/traces.py — Trace history and timeline endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.gateway_backend.dependencies import check_auth

router = APIRouter()

@router.get("/traces")
def recent_traces(limit: int = 10, _: None = Depends(check_auth)):
    from core.tracer_reader import list_recent_traces
    return {"traces": list_recent_traces(limit)}

@router.get("/traces/{trace_id}")
def get_trace_timeline(trace_id: str, _: None = Depends(check_auth)):
    """Retrieve the full execution timeline for a specific trace_id."""
    from core.tracer_reader import read_trace
    
    trace = read_trace(trace_id)
    if not trace:
        raise HTTPException(
            status_code=404,
            detail=f"trace_id '{trace_id}' not found in memory or last 14 days of logs"
        )
    return trace