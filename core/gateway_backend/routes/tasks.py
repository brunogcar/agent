"""
core/gateway_backend/routes/tasks.py — Async task submission and polling endpoints.
"""
from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException

from core.tracer import tracer
from core.gateway_backend.models import TaskRequest
from core.gateway_backend.dependencies import check_auth
from core.gateway_backend.store import _store_task, _update_task, _get_task
from core.gateway_backend.dispatcher import dispatch as _dispatch
from core.runtime.task_runner import run_background_task

router = APIRouter()

@router.post("/task")
def submit_task(
    req: TaskRequest,
    _:   None = Depends(check_auth),
):
    """
    Submit a task asynchronously.
    Returns trace_id immediately. Poll /result/{trace_id} for completion.
    """
    trace_id = tracer.new_trace(
        req.workflow or "direct",
        goal = req.goal or req.action or "",
    )

    payload = {
        "goal":     req.goal,
        "workflow": req.workflow,
        "tool":     req.tool,
        "action":   req.action,
        "params":   req.params or {},
        "platform": req.platform,
        "user":     req.user,
    }

    _store_task(trace_id, payload)
    
    def _execute_and_update() -> None:
        try:
            _update_task(trace_id, "running")
            result = _dispatch(trace_id, payload)
            _update_task(trace_id, "success", result=result)
        except Exception as e:
            _update_task(trace_id, "failed", error=str(e))

    def _on_timeout(tid: str) -> None:
        _update_task(tid, "failed", error="Task exceeds 300s timeout")

    run_background_task(trace_id, _execute_and_update, 300, _on_timeout)

    return {
        "trace_id": trace_id,
        "status":      "submitted",
        "poll_url": f"/result/{trace_id}",
    }

@router.get("/result/{trace_id}")
def get_result(trace_id: str, _: None = Depends(check_auth)):
    task = _get_task(trace_id)
    if not task:
        trace = tracer.get(trace_id)
        if trace:
            return {
                "trace_id": trace_id,
                "status":   trace.get("status", "unknown"),
                "result":   trace.get("result", ""),
                "elapsed":  trace.get("elapsed", 0),
            }
        raise HTTPException(status_code=404,
                            detail=f"trace_id '{trace_id}' not found")

    elapsed = (
        round(time.time() - task["submitted"], 1)
        if task["status"] in ("pending", "running")
        else round((task.get("completed") or time.time()) - task["submitted"], 1)
    )
    return {
        "trace_id": trace_id,
        "status":   task["status"],
        "result":   task.get("result"),
        "error":    task.get("error"),
        "elapsed":  elapsed,
    }