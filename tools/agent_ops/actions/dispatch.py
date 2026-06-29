"""Agent dispatch action — core LLM orchestrator.

Handles the full lifecycle of an LLM call for a given role:
  1. Role config lookup from ROLES registry
  2. Sleep-learn rule injection (high-latency roles only)
  3. Response cache check (deterministic roles only)
  4. Context trimming (token-aware or char-based)
  5. Primary LLM call via llm.complete()
  6. Fallback retry on transient failure (one attempt)
  7. JSON parsing for structured-output roles
  8. Autonomous model escalation on parse failure
  9. Metrics recording
  10. Response cache store (deterministic roles only)
"""
from __future__ import annotations

import json as _json
import time as _time

from core.llm import llm
from core.utils import compress_result
from core.tracer import tracer

from tools.agent_ops._registry import register_action
from tools.agent_ops.context import (
    _trim_context,
    _max_context_chars,
    _estimate_tokens,
)
from tools.agent_ops.cache import (
    _cache_key,
    _get_cached,
    _set_cached,
)
from tools.agent_ops.metrics import (
    _record_metric,
)
from tools.agent_ops.parse_warnings import (
    _log_parse_warning,
)
from tools.agent_ops.json_extract import _extract_first_json

HELP_DISPATCH = """
dispatch
Route a task to an LLM role for execution.
Required: role (one of: classify, route, research, summarize, extract,
                 critique, analyze, code, review, plan, consultor,
                 refactor, test, document)
Required: task (the instruction or question)
Optional: context, content, trace_id, temperature, max_tokens
Returns: {status, role, text, model, elapsed, usage}
"""

@register_action(
    "agent",
    "dispatch",
    help_text=HELP_DISPATCH,
    examples=[
        'agent(action="dispatch", role="classify", task="Is this spam?")',
        'agent(action="dispatch", role="research", task="Summarize quantum computing")',
        'agent(action="dispatch", role="plan", task="Build a web scraper")',
    ],
)
def run_dispatch(
    role: str = "",
    task: str = "",
    context: str = "",
    content: str = "",
    trace_id: str = "",
    temperature: float = -1.0,
    max_tokens: int = -1,
    mime_type: str = "",
    vision_json_mode: bool = False,
) -> dict:
    """Dispatch a task to the specified LLM role."""
    role = role.strip().lower()

    # Lazy import to avoid circular import during module load
    from tools.agent_ops import ROLES

    # ── Role validation ──────────────────────────────────────────────────────
    if role not in ROLES:
        available = " | ".join(sorted(ROLES.keys()))
        return {
            "status": "error",
            "error_code": "INVALID_ROLE",
            "error": (
                f"Unknown role \'{role}\'. "
                f"Use: {available}"
            ),
        }

    if not task:
        return {
            "status": "error",
            "error_code": "INVALID_INPUT",
            "error": "task is required",
        }

    # Vision is a separate action, not a dispatch role
    if role == "vision":
        return {
            "status": "error",
            "error_code": "INVALID_ROLE",
            "error": (
                "Use action=\'vision_delegate\' for vision tasks, "
                "not action=\'dispatch\'."
            ),
        }

    # Consultor is disabled if no model is configured
    if role == "consultor":
        from core.config import cfg
        if "consultor" not in cfg.model_registry:
            return {
                "status": "error",
                "error_code": "INVALID_ROLE",
                "error": "Consultor role is not configured. Set CONSULTOR_MODEL in .env.",
            }

    # ── Load role config ─────────────────────────────────────────────────────
    role_data = ROLES[role]
    system_prompt = role_data["system_prompt"]
    role_cfg = role_data["role_config"]

    llm_role = role_cfg["llm_role"]
    json_mode = role_cfg.get("json_mode") == "api"
    budget_chars = role_cfg.get("budget_chars")
    if budget_chars is None:
        budget_chars = _max_context_chars()
    budget_tokens = role_cfg.get("budget_tokens")
    cacheable = role_cfg.get("cacheable", False)
    fallback_role = role_cfg.get("fallback_role")

    # ── Sleep-learn injection ────────────────────────────────────────────────
    # Only for high-latency roles. Router roles skip to avoid ChromaDB overhead.
    _sleep_learn_roles = {k for k, v in ROLES.items() if v["role_config"].get("sleep_learn")}
    if role in _sleep_learn_roles:
        try:
            from core.sleep_learn.injector import inject_rules_into_prompt
            system_prompt = inject_rules_into_prompt(
                goal=task,
                system_prompt=system_prompt,
                trace_id=trace_id,
            )
        except Exception:
            pass  # Non-fatal: use original prompt

    # ── Response cache ───────────────────────────────────────────────────────
    if cacheable:
        cache_key = _cache_key(role, task, context, content, temperature, max_tokens)
        cached = _get_cached(cache_key)
        if cached is not None:
            response = cached.copy()
            response["cached"] = True
            return response

    # ── Build LLM call kwargs ────────────────────────────────────────────────
    call_kwargs: dict = {}
    if temperature >= 0:
        call_kwargs["temperature"] = temperature
    if max_tokens > 0:
        call_kwargs["max_tokens"] = max_tokens

    # ── Context trimming with token-aware budget ─────────────────────────────
    if budget_tokens:
        trimmed_context = _trim_context(context, max_tokens=budget_tokens)
        remaining_tokens = max(0, budget_tokens - _estimate_tokens(trimmed_context))
        content_budget_tokens = min(1000, remaining_tokens)
        trimmed_content = _trim_context(content, max_tokens=content_budget_tokens)
    else:
        trimmed_context = _trim_context(context, max_chars=budget_chars)
        remaining = max(0, budget_chars - len(trimmed_context))
        content_budget = min(4000, remaining)
        trimmed_content = _trim_context(content, max_chars=content_budget)

    # ── Primary LLM call ─────────────────────────────────────────────────────
    start_time = _time.time()
    result = llm.complete(
        role=llm_role,
        system=system_prompt,
        user=task,
        context=trimmed_context,
        content=trimmed_content,
        json_mode=json_mode,
        trace_id=trace_id,
        **call_kwargs,
    )

    # ── Retry with fallback role on transient failure ────────────────────────
    if not result.ok and fallback_role and fallback_role in ROLES:
        fb_data = ROLES[fallback_role]
        fb_prompt = fb_data["system_prompt"]
        fb_cfg = fb_data["role_config"]
        result = llm.complete(
            role=fb_cfg["llm_role"],
            system=fb_prompt,
            user=task,
            context=trimmed_context,
            content=trimmed_content,
            json_mode=fb_cfg.get("json_mode") == "api",
            trace_id=trace_id,
            **call_kwargs,
        )

    elapsed = _time.time() - start_time

    # ── Error path ───────────────────────────────────────────────────────────
    if not result.ok:
        error_code = "MODEL_ERROR"
        error_lower = (result.error or "").lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            error_code = "TIMEOUT"
        elif "circuit" in error_lower or "breaker" in error_lower:
            error_code = "CIRCUIT_OPEN"
        elif "rate" in error_lower or "quota" in error_lower:
            error_code = "RATE_LIMIT"

        total_tokens = (
            result.usage.get("total", 0)
            if hasattr(result, "usage") and result.usage
            else 0
        )
        _record_metric(role, "error", elapsed, total_tokens)

        return {
            "status": "error",
            "error_code": error_code,
            "role": role,
            "error": result.error,
            "elapsed": elapsed,
            "model": result.model,
        }

    # ── Success response assembly ────────────────────────────────────────────
    response: dict = {
        "status": "success",
        "role": role,
        "text": result.text,
        "model": result.model,
        "elapsed": elapsed,
        "usage": result.usage,
    }

    # ── JSON parsing for structured-output roles ─────────────────────────────
    _prompt_json_roles = {k for k, v in ROLES.items() if v["role_config"].get("json_mode") == "prompt"}
    _api_json_roles = {k for k, v in ROLES.items() if v["role_config"].get("json_mode") == "api"}
    _json_roles = _prompt_json_roles | _api_json_roles

    parse_failed = False
    if role in _json_roles:
        if result.parsed is not None:
            response["parsed"] = result.parsed
        else:
            clean = result.text.strip()
            for fence in ("```json", "```"):
                if clean.startswith(fence):
                    clean = clean[len(fence):]
                    clean = clean.strip().rstrip("`").strip()

            try:
                response["parsed"] = _json.loads(clean)
            except _json.JSONDecodeError:
                extracted = _extract_first_json(clean)
                if extracted:
                    try:
                        response["parsed"] = _json.loads(extracted)
                    except _json.JSONDecodeError:
                        parse_failed = True
                        response["parsed"] = {}
                        response["parse_warning"] = (
                            f"Extracted JSON was invalid for role \'{role}\'. "
                            "Empty dict returned for parsed. "
                            "Check response.text for raw output."
                        )
                else:
                    parse_failed = True
                    response["parsed"] = {}
                    response["parse_warning"] = (
                        f"Response was not valid JSON for role \'{role}\'. "
                        "Empty dict returned for parsed. "
                        "Check response.text for raw output."
                    )

        # ── Autonomous model escalation on parse failure ─────────────────────
        if parse_failed and llm_role != "planner":
            escalation_result = llm.complete(
                role="planner",
                system=system_prompt,
                user=(
                    f"[ESCALATION: The {llm_role} model failed to "
                    f"produce valid JSON. Please produce valid JSON only.]\n\n{task}"
                ),
                context=trimmed_context,
                content=trimmed_content,
                json_mode=False,
                trace_id=trace_id,
                **call_kwargs,
            )
            if escalation_result.ok:
                clean = escalation_result.text.strip()
                for fence in ("```json", "```"):
                    if clean.startswith(fence):
                        clean = clean[len(fence):]
                        clean = clean.strip().rstrip("`").strip()
                try:
                    response["parsed"] = _json.loads(clean)
                    response.pop("parse_warning", None)
                    parse_failed = False
                    response["escalated"] = True
                    # Update response with escalation result data
                    response["text"] = escalation_result.text
                    response["model"] = escalation_result.model
                    response["usage"] = escalation_result.usage
                except _json.JSONDecodeError:
                    extracted = _extract_first_json(clean)
                    if extracted:
                        try:
                            response["parsed"] = _json.loads(extracted)
                            response.pop("parse_warning", None)
                            parse_failed = False
                            response["escalated"] = True
                            # Update response with escalation result data
                            response["text"] = escalation_result.text
                            response["model"] = escalation_result.model
                            response["usage"] = escalation_result.usage
                        except _json.JSONDecodeError:
                            pass

            if parse_failed:
                _log_parse_warning(role, response.get("parse_warning", ""), result.text)

    # ── Metrics and cache ────────────────────────────────────────────────────
    total_tokens = (
        result.usage.get("total", 0)
        if hasattr(result, "usage") and result.usage
        else 0
    )
    _record_metric(role, "success", elapsed, total_tokens, parse_failed)

    if cacheable:
        cache_key = _cache_key(role, task, context, content, temperature, max_tokens)
        _set_cached(cache_key, response.copy())

    return compress_result(response)
