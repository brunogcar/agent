"""
core/gateway_backend/routes/tasks.py — Async task submission and polling endpoints.
"""
from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException

from core.tracer import tracer
from core.gateway_backend.models import TaskRequest, TaskSubmitResponse, TaskResultResponse
from core.gateway_backend.dependencies import check_auth, get_task_store, get_dispatcher, get_task_runner
from types import ModuleType

router = APIRouter()

@router.post(
    "/task", 
    response_model=TaskSubmitResponse,
    summary="Submit an asynchronous task",
    description="Submits a goal or tool execution to the agent. Returns a trace_id immediately. Poll /result/{trace_id} for completion.",
)
def submit_task(
    req: TaskRequest,
    _:          None = Depends(check_auth),
    store:      ModuleType = Depends(get_task_store),
    dispatcher: ModuleType = Depends(get_dispatcher),
    runner:     ModuleType = Depends(get_task_runner),
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

    store._store_task(trace_id, payload)

    def _execute_and_update() -> None:
        try:
            store._update_task(trace_id, "running")
            result = dispatcher.dispatch(trace_id, payload)
            store._update_task(trace_id, "success", result=result)
        except Exception as e:
            store._update_task(trace_id, "failed", error=str(e))

    def _on_timeout(tid: str) -> None:
        store._update_task(tid, "failed", error="Task exceeds 300s timeout")

    runner.run_background_task(trace_id, _execute_and_update, 300, _on_timeout)

    return {
        "trace_id": trace_id,
        "status":      "submitted",
        "poll_url": f"/result/{trace_id}",
    }

@router.get(
    "/result/{trace_id}", 
    response_model=TaskResultResponse,
    summary="Poll for task result",
    description="Returns the current status, result, or error of a previously submitted task.",
)
def get_result(
    trace_id: str,
    _:    None = Depends(check_auth),
    store: ModuleType = Depends(get_task_store)
):
    task = store._get_task(trace_id)
    if not task:
        trace = tracer.get(trace_id)
        if trace:
            return {
                "trace_id": trace_id,
                "status":   trace.get("status", "unknown"),
                "result":   trace.get("result", ""),
                "elapsed":  trace.get("elapsed", 0),
            }
        from core.gateway_backend.exceptions import TaskNotFoundError
        raise TaskNotFoundError(trace_id)

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