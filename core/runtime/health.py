"""
Health check endpoint for monitoring agent status.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict

from core.config import cfg
from core.tracer import tracer

def get_health() -> Dict[str, Any]:
    """
    Returns a comprehensive health check dictionary.
    """
    health = {
        "status": "healthy",
        "timestamp": int(time.time()),
        "env": cfg.env,
        "agent_root": str(cfg.agent_root),
        "workspace_root": str(cfg.workspace_root),
        "checks": {},
        "version": "1.0.0"
    }

    # Check critical directories exist
    critical_dirs = [
        ("agent_root", cfg.agent_root),
        ("workspace_root", cfg.workspace_root),
        ("memory_root", cfg.memory_root),
        ("memory_chroma_path", cfg.memory_chroma_path),
        ("workspace_autocode", cfg.workspace_autocode),
        ("workspace_index", cfg.workspace_index),
        ("log_path", cfg.log_path),
    ]

    for name, path in critical_dirs:
        exists = path.exists()
        health["checks"][f"dir_{name}"] = {"status": "ok" if exists else "error", "path": str(path)}

    # Check LM Studio connection
    try:
        import httpx
        response = httpx.get(cfg.lm_studio_base_url, timeout=5)
        health["checks"]["lm_studio"] = {
            "status": "ok" if response.status_code < 500 else "error",
            "url": cfg.lm_studio_base_url,
            "response_code": response.status_code
        }
    except Exception as e:
        health["checks"]["lm_studio"] = {
            "status": "error",
            "url": cfg.lm_studio_base_url,
            "error": str(e)
        }

    # Check models are configured
    health["checks"]["models"] = {
        "planner": {"status": "ok" if cfg.planner_model else "error", "model": cfg.planner_model},
        "executor": {"status": "ok" if cfg.executor_model else "error", "model": cfg.executor_model},
        "router": {"status": "ok" if cfg.router_model else "error", "model": cfg.router_model},
        "vision": {"status": "ok" if cfg.vision_model else "error", "model": cfg.vision_model},
    }

    # Check ChromaDB
    try:
        from core.memory_engine import memory
        health["checks"]["chromadb"] = {
            "status": "ok",
            "client": "initialized"
        }
    except Exception as e:
        health["checks"]["chromadb"] = {
            "status": "error",
            "error": str(e)
        }

    # Determine overall status
    all_checks = list(health["checks"].values())
    error_count = sum(1 for c in all_checks if c.get("status") == "error")
    health["status"] = "degraded" if error_count > 0 else "healthy"

    return health

def health_check_endpoint() -> str:
    """
    Returns JSON health check response.
    """
    import json
    health = get_health()
    tracer.step("health", "Health check", extra={"status": health["status"]})
    return json.dumps(health, indent=2)