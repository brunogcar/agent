"""
core/gateway_backend/routes/metrics.py — Telemetry and graph endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from core.gateway_backend.dependencies import check_auth

router = APIRouter()

@router.get("/metrics")
def metrics_endpoint(_: None = Depends(check_auth)):
    """
    GET /metrics -- Prometheus telemetry endpoint.

    Returns standard Prometheus text/plain metrics for autocode nodes,
    task outcomes, TDD iterations, and LLM token usage. 
    Auth: Bearer token (GATEWAY_SECRET).
    """
    from core.metrics import generate_metrics, get_content_type
    return Response(content=generate_metrics(), media_type=get_content_type())

@router.get("/autocode/graph")
def autocode_graph(_: None = Depends(check_auth)):
    """
    GET /autocode/graph -- Mermaid flowchart of the autocode state machine.

    Dynamically extracts nodes & routing from the LangGraph definition.
    Useful for debugging routing loops or documenting workflow structure.
    Auth: Bearer token (GATEWAY_SECRET).
    """
    from workflows.autocode_helpers.graph import build_graph
    from workflows.autocode_helpers.mermaid import export_mermaid
    graph = build_graph()
    mermaid = export_mermaid(graph)
    return Response(content=mermaid, media_type="text/plain")