"""core/router_backend/model_route.py -- Model-based routing via the Router role.

Extracted from core/router.py v1.0 split. Standalone functions:
    - model_route(goal, trace_id)        -- tries the LLM, returns RoutingDecision|None
    - _extract_first_json(text)          -- helper, delegates to core.json_extract
"""
from __future__ import annotations

import json
from typing import Optional

from core.llm import llm
from core.config import cfg
from core.router_backend.decision import RoutingDecision
from core.router_backend.constants import ROUTER_SYSTEM_PROMPT


def _extract_first_json(text: str) -> str | None:
    """Extract the first valid JSON object from text.

    [v2.0] Now delegates to core.json_extract.extract_first_json -- single
    source of truth for all LLM JSON parsing in the codebase.
    """
    from core.json_extract import extract_first_json
    return extract_first_json(text)


def model_route(goal: str, trace_id: str) -> Optional[RoutingDecision]:
    """Try to get a routing decision from the Router.

    Standalone function (v1.0 split -- was TaskRouter._model_route).

    Returns None if:
      - the LLM call fails (r.ok is False), or
      - the response can't be parsed as JSON, or
      - the parsed JSON doesn't contain a "workflow" key.

    v1.3: JSON schema enforcement -- LM Studio enforces the routing
    schema at generation time via outlines. The model cannot produce
    schema-invalid output. Defensive parsing below stays as fallback.
    Schema is imported from tools.agent_ops.roles.route (single source
    of truth -- hardening fix: was inline, now module-level import).
    """
    from tools.agent_ops.roles.route import JSON_SCHEMA as _ROUTER_JSON_SCHEMA
    r = llm.complete(
        role="router",
        system=ROUTER_SYSTEM_PROMPT,
        user=goal,
        json_schema=_ROUTER_JSON_SCHEMA,
        trace_id=trace_id,
        timeout=cfg.router_timeout,
    )

    if not r.ok:
        return None

    # Parse JSON from response
    text = r.text.strip()
    clean = text

    # Strip markdown fences and use deterministic JSON extractor
    for fence in ("```json", "```"):
        if clean.startswith(fence):
            clean = clean[len(fence):]
            clean = clean.strip().rstrip("`").strip()

    extracted = _extract_first_json(clean)
    if extracted:
        clean = extracted

    try:
        data = json.loads(clean)
        # Validate required fields
        if "workflow" in data:
            return RoutingDecision(data)
    except (json.JSONDecodeError, ValueError):
        pass

    return None
