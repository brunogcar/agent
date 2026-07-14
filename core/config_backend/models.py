"""core/config_backend/models.py — Initialize model roles, model_registry, derived timeouts.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.
This is the most complex builder: it resolves 16 model roles, builds the
``model_registry`` dict, and derives the three direct timeout attributes
from the registry (single source of truth).

Env vars read:
    PLANNER_MODEL   — REQUIRED; raises RuntimeError if missing/empty.

    Group mains (fallback to PLANNER_MODEL):
        EXECUTOR_MODEL, ROUTER_MODEL, VISION_MODEL
    CONSULTOR_MODEL — opt-in (no fallback; empty means consultor role disabled)

    Sub-role overrides (fallback chain noted inline):
        SUMMARIZE_MODEL, EXTRACT_MODEL, RESEARCH_MODEL, CRITIQUE_MODEL,
        ANALYZE_MODEL, CODE_MODEL, REVIEW_MODEL  -> fallback to EXECUTOR_MODEL
        CLASSIFY_MODEL, ROUTE_MODEL               -> fallback to ROUTER_MODEL
        REFACTOR_MODEL, TEST_MODEL                -> fallback to CODE_MODEL
        DOCUMENT_MODEL                            -> fallback to SUMMARIZE_MODEL

    Per-role timeouts (default noted inline; used by _make_entry):
        PLANNER_TIMEOUT=180, EXECUTOR_TIMEOUT=120, ROUTER_TIMEOUT=15,
        VISION_TIMEOUT=60, CLASSIFY_TIMEOUT=15, ROUTE_TIMEOUT=15,
        SUMMARIZE_TIMEOUT=60, EXTRACT_TIMEOUT=60, RESEARCH_TIMEOUT=120,
        CRITIQUE_TIMEOUT=90, ANALYZE_TIMEOUT=90, CODE_TIMEOUT=120,
        REVIEW_TIMEOUT=90, REFACTOR_TIMEOUT=120, TEST_TIMEOUT=120,
        DOCUMENT_TIMEOUT=120, CONSULTOR_TIMEOUT=60 (conditional)

Provider/model resolution is delegated to ``_resolve_role()`` in env_loader.py.
The ``_make_entry`` closure captures ``cfg`` (not ``self``) — it reads
``cfg.lm_studio_base_url`` for the local-provider base URL.
"""

from __future__ import annotations

import os

from core.config_backend.env_loader import _resolve_role


def _init_models(cfg) -> None:
    """Initialize model roles, build model_registry, derive direct timeouts."""

    # -- Model roles -------------------------------------------------------
    planner_raw = os.getenv("PLANNER_MODEL")
    if not planner_raw:
        raise RuntimeError("PLANNER_MODEL is required in .env")

    # Group mains
    executor_raw = os.getenv("EXECUTOR_MODEL") or planner_raw
    router_raw = os.getenv("ROUTER_MODEL") or planner_raw
    vision_raw = os.getenv("VISION_MODEL") or planner_raw
    consultor_raw = os.getenv("CONSULTOR_MODEL", "").strip()

    # Sub-role overrides (fallback to group main -> planner)
    summarize_raw = os.getenv("SUMMARIZE_MODEL") or executor_raw
    extract_raw = os.getenv("EXTRACT_MODEL") or executor_raw
    research_raw = os.getenv("RESEARCH_MODEL") or executor_raw
    critique_raw = os.getenv("CRITIQUE_MODEL") or executor_raw
    analyze_raw = os.getenv("ANALYZE_MODEL") or executor_raw
    code_raw = os.getenv("CODE_MODEL") or executor_raw
    review_raw = os.getenv("REVIEW_MODEL") or executor_raw
    classify_raw = os.getenv("CLASSIFY_MODEL") or router_raw
    route_raw = os.getenv("ROUTE_MODEL") or router_raw

    # NEW: Autonomous maintenance roles (fallback to executor/code/summarize)
    refactor_raw = os.getenv("REFACTOR_MODEL") or code_raw
    test_raw = os.getenv("TEST_MODEL") or code_raw
    document_raw = os.getenv("DOCUMENT_MODEL") or summarize_raw

    # Resolve provider and model automatically for each role
    planner_prov, planner_mod = _resolve_role(planner_raw)
    executor_prov, executor_mod = _resolve_role(executor_raw)
    router_prov, router_mod = _resolve_role(router_raw)
    vision_prov, vision_mod = _resolve_role(vision_raw)
    consultor_prov, consultor_mod = _resolve_role(consultor_raw)
    classify_prov, classify_mod = _resolve_role(classify_raw)
    route_prov, route_mod = _resolve_role(route_raw)
    summarize_prov, summarize_mod = _resolve_role(summarize_raw)
    extract_prov, extract_mod = _resolve_role(extract_raw)
    research_prov, research_mod = _resolve_role(research_raw)
    critique_prov, critique_mod = _resolve_role(critique_raw)
    analyze_prov, analyze_mod = _resolve_role(analyze_raw)
    code_prov, code_mod = _resolve_role(code_raw)
    review_prov, review_mod = _resolve_role(review_raw)

    # NEW: Resolve new roles
    refactor_prov, refactor_mod = _resolve_role(refactor_raw)
    test_prov, test_mod = _resolve_role(test_raw)
    document_prov, document_mod = _resolve_role(document_raw)

    cfg.planner_model = planner_mod
    cfg.executor_model = executor_mod
    cfg.router_model = router_mod
    cfg.vision_model = vision_mod
    cfg.consultor_model = consultor_mod

    # NOTE: _make_entry captures cfg (not self) — pre-v1.0 this was a method
    # closure on self.lm_studio_base_url. Behavior identical.
    def _make_entry(model, prov, timeout_env, default_timeout):
        return {
            "model": model,
            "provider": prov,
            "base_url": cfg.lm_studio_base_url if prov == "lmstudio" else os.getenv(f"{prov.upper()}_BASE_URL", ""),
            "timeout": int(os.getenv(timeout_env, str(default_timeout))),
        }

    cfg.model_registry: dict[str, dict] = {
        "planner": _make_entry(planner_mod, planner_prov, "PLANNER_TIMEOUT", 180),
        "executor": _make_entry(executor_mod, executor_prov, "EXECUTOR_TIMEOUT", 120),
        "router": _make_entry(router_mod, router_prov, "ROUTER_TIMEOUT", 15),
        "vision": _make_entry(vision_mod, vision_prov, "VISION_TIMEOUT", 60),
        "classify": _make_entry(classify_mod, classify_prov, "CLASSIFY_TIMEOUT", 15),
        "route": _make_entry(route_mod, route_prov, "ROUTE_TIMEOUT", 15),
        "summarize": _make_entry(summarize_mod, summarize_prov, "SUMMARIZE_TIMEOUT", 60),
        "extract": _make_entry(extract_mod, extract_prov, "EXTRACT_TIMEOUT", 60),
        "research": _make_entry(research_mod, research_prov, "RESEARCH_TIMEOUT", 120),
        "critique": _make_entry(critique_mod, critique_prov, "CRITIQUE_TIMEOUT", 90),
        "analyze": _make_entry(analyze_mod, analyze_prov, "ANALYZE_TIMEOUT", 90),
        "code": _make_entry(code_mod, code_prov, "CODE_TIMEOUT", 120),
        "review": _make_entry(review_mod, review_prov, "REVIEW_TIMEOUT", 90),
        # NEW: Autonomous maintenance roles
        "refactor": _make_entry(refactor_mod, refactor_prov, "REFACTOR_TIMEOUT", 120),
        "test": _make_entry(test_mod, test_prov, "TEST_TIMEOUT", 120),
        "document": _make_entry(document_mod, document_prov, "DOCUMENT_TIMEOUT", 120),
    }

    # Add consultor to registry ONLY if a model is explicitly resolved
    if consultor_mod:
        cfg.model_registry["consultor"] = _make_entry(consultor_mod, consultor_prov, "CONSULTOR_TIMEOUT", 60)

    # -- Derive direct timeout attributes from model_registry (single source of truth) --
    cfg.planner_timeout = cfg.model_registry["planner"]["timeout"]
    cfg.execution_timeout = cfg.model_registry["executor"]["timeout"]
    cfg.router_timeout = cfg.model_registry["router"]["timeout"]
