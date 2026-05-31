"""
core/gateway_backend/routes/chat.py — Synchronous chat endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.tracer import tracer
from core.gateway_backend.models import ChatRequest
from core.gateway_backend.dependencies import check_auth
from core.gateway_backend.dispatcher import dispatch as _dispatch

router = APIRouter()

@router.post("/chat")
def chat(req: ChatRequest, _: None = Depends(check_auth)):
    """
    Synchronous chat -- submit a message and wait for result.
    Use /task + /result for long-running workflows.
    """
    trace_id = tracer.new_trace("chat", goal=req.message[:60])

    payload = {
        "goal":     req.message,
        "workflow": "auto",
        "params":   {},
        "platform": req.platform,
        "user":     req.user,
    }

    try:
        result = _dispatch(trace_id, payload)
        return {
            "trace_id": trace_id,
            "status":      "success",
            "result":   result,
            "platform": req.platform,
        }
    except Exception as e:
        return {
            "trace_id": trace_id,
            "status":      "failed",
            "error":    str(e),
            "platform": req.platform,
        }