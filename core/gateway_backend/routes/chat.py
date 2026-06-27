"""
core/gateway_backend/routes/chat.py — Synchronous chat endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.tracer import tracer
from core.gateway_backend.models import ChatRequest, ChatResponse
from core.gateway_backend.dependencies import check_auth, get_dispatcher
from types import ModuleType

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Synchronous chat",
    description="Submits a message and blocks until the agent returns a result. Use /task for long-running workflows.",
)
def chat(
    req: ChatRequest,
    _: None = Depends(check_auth),
    dispatcher: ModuleType = Depends(get_dispatcher)
):
    """
    Synchronous chat -- submit a message and wait for result.
    Use /task + /result for long-running workflows.
    """
    trace_id = tracer.new_trace("chat", goal=req.message[:60])

    payload = {
        "goal": req.message,
        "workflow": "auto",
        "params": {},
        "platform": req.platform,
        "user": req.user,
    }

    from core.gateway_backend.exceptions import ToolExecutionError

    try:
        result = dispatcher.dispatch(trace_id, payload)
    except Exception as e:
        raise ToolExecutionError(trace_id=trace_id, tool="chat", error=str(e))

    # Propagate inner status: if dispatch returned an error dict, reflect it
    # in the outer response status instead of hardcoding "success".
    inner_status = (
        result.get("status", "success")
        if isinstance(result, dict) else "success"
    )

    return {
        "trace_id": trace_id,
        "status": inner_status,
        "result": result,
        "platform": req.platform,
    }
