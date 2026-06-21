# core/gateway_backend/routes/health.py — Health, version, and system info endpoints.
"""Health, version, and system info endpoints."""
from __future__ import annotations

import subprocess as _sp
import httpx as _httpx
from fastapi import APIRouter, Depends, Query, Response

from core.config import cfg
from core.tracer import tracer
from core.gateway_backend.dependencies import check_auth

router = APIRouter()

@router.get("/version")
def version():
    try:
        commit = _sp.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cfg.agent_root), stderr=_sp.DEVNULL, text=True,
        ).strip()
        branch = _sp.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cfg.agent_root), stderr=_sp.DEVNULL, text=True,
        ).strip()
    except Exception as e:
        tracer.error("", "git_info", f"Failed to get git info: {e}")
        commit = "unknown"
        branch = "unknown"
    return {"commit": commit, "branch": branch, "env": cfg.env}

@router.get("/health")
async def health():
    """Health check endpoint"""
    from core.runtime.health import health_check_endpoint
    return Response(content=health_check_endpoint(), media_type="application/json")

# [PHASE 2 FIX] Autocode health endpoint with optional deep check
@router.get("/health/autocode")
async def health_autocode(deep: bool = Query(False), _: None = Depends(check_auth)):
    """[PHASE 2 FIX] Autocode workflow health check."""
    from core.memory import memory as mem

    checks = {
        "lm_studio": "unknown",
        "chromadb": "unknown",
        "agent_root": str(cfg.agent_root),
    }
    try:
        if deep:
            resp = _httpx.get(f"{cfg.lm_studio_base_url}/models", timeout=5)
            checks["lm_studio"] = "ok" if resp.status_code == 200 else "error"
        else:
            checks["lm_studio"] = "ok"  # Assume ok for fast path
    except Exception:
        checks["lm_studio"] = "unreachable"

    try:
        mem.recall("__ping__", top_k=0)
        checks["chromadb"] = "ok"
    except Exception:
        checks["chromadb"] = "degraded"

    all_ok = all(v == "ok" for v in [checks["lm_studio"], checks["chromadb"]])
    return {"status": "ok" if all_ok else "degraded", "checks": checks}

# [PHASE 2 FIX] Circuit breaker monitoring endpoint
@router.get("/health/circuit-breakers")
async def health_circuit_breakers(_: None = Depends(check_auth)):
    """[PHASE 2 FIX] Return state of all LLM circuit breakers for monitoring."""
    from core.llm import llm
    try:
        return {
            "status": "ok",
            "breakers": llm.circuit_breaker_states
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get("/health/models")
def health_models(_: None = Depends(check_auth)):
    required = {
        "planner": cfg.planner_model,
        "executor": cfg.executor_model,
        "router": cfg.router_model,
    }
    try:
        resp = _httpx.get(f"{cfg.lm_studio_base_url}/models", timeout=5)
        loaded = [m["id"] for m in resp.json().get("data", [])]
        status = {}
        all_ok = True
        for role, model in required.items():
            found = any(model.lower() in m.lower() for m in loaded)
            status[role] = {"model": model, "loaded": found}
            if not found:
                all_ok = False
        return {
            "status": "ok" if all_ok else "degraded",
            "all_loaded": all_ok,
            "models": status,
            "loaded_models": loaded,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "all_loaded": False}

@router.get("/tools")
def list_tools(_: None = Depends(check_auth)):
    """
    [P1 FIX] Return the list of registered tools from the registry.
    Falls back to a static list if the registry hasn't been scanned yet
    (e.g., gateway started before MCP server booted).
    """
    try:
        from registry import get_tool_names
        names = get_tool_names()
        if names:
            return {"tools": names}
    except Exception:
        pass  # Fall back to static list

    # Static fallback — kept as safety net for edge cases
    return {
        "tools": [
            "web", "python", "file", "git", "vision",
            "memory", "agent", "notify", "report", "workflow",
        ]
    }

@router.get("/memory/stats")
def memory_stats(_: None = Depends(check_auth)):
    from core.memory import memory
    return memory.stats()
