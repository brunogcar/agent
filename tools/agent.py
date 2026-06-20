"""tools/agent.py — Agent meta-tool (thin @tool facade).

Replaces: tools/agent_tool.py (monolithic)
Split into: agent_core/ submodules for prompts, roles, context, cache, metrics,
            parse_warnings, and json_extract.

The LLM sees ONE tool: agent(role, task, ...)
All business logic lives in agent_core/ submodules. This file is the
orchestrator: validate inputs, delegate to specialists, compose the result.

Architecture (Phase 7 split):
 1. Validate inputs (role exists, task non-empty)
 2. Vision role → delegate to tools.vision.vision() (multimodal, not text LLM)
 3. Lookup role config from agent_core.roles.ROLE_CONFIG
 4. Inject sleep-learn rules for high-latency roles
 5. Check response cache for deterministic roles → agent_core.cache
 6. Trim context + content via agent_core.context._trim_context()
 7. Call llm.complete() with role-specific model, timeout, json_mode
 8. Auto-retry with fallback role on transient failure (one attempt)
 9. Escalate to heavy model on parse failure (autonomous model escalation)
10. Parse JSON for structured-output roles → agent_core.json_extract
11. Log per-role metrics → agent_core.metrics
12. Compress and return result dict

JSON Parsing delegation:
 - API json_mode: extract role (model enforces JSON schema)
 - Prompt-only JSON: route, plan, code, review (parsed post-hoc via json_extract)
 - Non-JSON: classify, research, summarize, critique, analyze, consultor
"""
from __future__ import annotations

import json as _json
import hashlib as _hashlib
import time as _time

from registry import tool
from core.llm import llm
from core.utils import compress_result
from core.config import cfg

from tools.agent_core.prompts import _SYSTEM_PROMPTS
from tools.agent_core.roles import (
    ROLE_CONFIG,
    _ROLE_TO_LLM,
    _API_JSON_ROLES,
    _JSON_ROLES,
    _SLEEP_LEARN_ROLES,
    _ROLE_FALLBACKS,
)
from tools.agent_core.context import (
    _trim_context,
    _max_context_chars,
    _max_context_tokens,
    _estimate_tokens,
)
from tools.agent_core.cache import (
    _cache_key,
    _get_cached,
    _set_cached,
    _clear_cache,
)
from tools.agent_core.metrics import (
    _record_metric,
    _get_metrics,
    _clear_metrics,
)
from tools.agent_core.parse_warnings import (
    _log_parse_warning,
    _get_parse_warnings,
    _clear_parse_warnings,
)
from tools.agent_core.json_extract import _extract_first_json

# Optional sleep-learn integration — non-fatal if unavailable.
# Imported lazily at module load; if missing, _inject_rules stays None.
try:
    from core.sleep_learn.injector import inject_rules_into_prompt as _inject_rules
except ImportError:
    _inject_rules = None

# Module-level flags
PARALLEL_SAFE = False

# ── Prompt versioning ───────────────────────────────────────────────────────────
# SHA256 hash of all system prompts. Included in every success response so
# debugging "why did behavior change?" is trivial — just compare versions.
_PROMPT_VERSION = _hashlib.sha256(
    _json.dumps(_SYSTEM_PROMPTS, sort_keys=True).encode()
).hexdigest()[:8]


@tool
def agent(
    role: str,
    task: str,
    context: str = "",
    content: str = "",
    trace_id: str = "",
    temperature: float = -1.0,
    max_tokens: int = -1,
    mime_type: str = "",
    vision_json_mode: bool = False,
) -> dict:
    """
    Agent tool — call a specialist sub-agent for a specific cognitive task.

    role: "classify" | "route" | "research" | "summarize" | "extract" |
          "critique" | "analyze" | "code" | "review" | "plan" | "consultor" | "vision"

    task : the instruction or question for this agent
    context : background information (injected before the task)
              for vision: file_path or public URL to the image
    content : raw material to process (code, text, data, or base64 image)
              for vision: base64-encoded image string
    trace_id: attach to current workflow trace for observability
    temperature: override temperature (-1 = use model default)
    max_tokens: override max_tokens (-1 = use model default)
    # Vision passthrough (optional):
    mime_type: (vision only) override MIME type for image
    vision_json_mode: (vision only) request structured JSON output from vision
    """
    role = role.strip().lower()

    # ── Meta-role: metrics query ─────────────────────────────────────────────
    # Bypasses all LLM logic. Returns in-memory metrics + parse warnings.
    if role == "metrics":
        target = task.strip() if task else None
        return {
            "status": "success",
            "role": "metrics",
            "metrics": _get_metrics(target),
            "parse_warnings": _get_parse_warnings(target),
            "prompt_version": _PROMPT_VERSION,
        }

    # ── Input validation ───────────────────────────────────────────────────────
    all_roles = set(_ROLE_TO_LLM.keys()) | {"vision"}
    if role not in all_roles:
        return {
            "status": "error",
            "error_code": "INVALID_ROLE",
            "error": (
                f"Unknown role '{role}'. "
                "Use: classify | route | research | summarize | extract | "
                "critique | analyze | code | review | plan | consultor | vision"
            ),
        }

    if not task:
        return {
            "status": "error",
            "error_code": "INVALID_INPUT",
            "error": "task is required",
        }

    # ── Vision: delegate to tools/vision.py ──────────────────────────────────
    # Vision is a special case: it uses a multimodal model, not the text LLM.
    # All vision parameters are forwarded directly to tools.vision.vision().
    if role == "vision":
        try:
            from tools.vision import vision as _vision
        except ImportError:
            return {
                "status": "error",
                "error_code": "MISSING_DEPENDENCY",
                "error": "tools/vision.py not found — ensure it exists and has @tool decorator.",
            }

        file_path = ""
        url = ""
        b64 = ""

        if context:
            if context.startswith(("http://", "https://")):
                url = context
            elif context.startswith("data:"):
                b64 = context
            else:
                file_path = context

        if content and not b64 and not file_path and not url:
            b64 = content

        vision_kwargs: dict = {
            "task": task,
            "file_path": file_path,
            "base64": b64,
            "url": url,
            "trace_id": trace_id,
            "context": "",
        }
        if mime_type:
            vision_kwargs["mime_type"] = mime_type
        if vision_json_mode:
            vision_kwargs["json_mode"] = vision_json_mode

        return _vision(**vision_kwargs)

    # ── Role configuration lookup ──────────────────────────────────────────────
    # ROLE_CONFIG is the single source of truth for all role metadata.
    role_cfg = ROLE_CONFIG[role]
    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role = role_cfg["llm_role"]
    json_mode = role in _API_JSON_ROLES

    # ── Sleep-learn injection ──────────────────────────────────────────────
    # Only for high-latency roles. Router roles skip to avoid ChromaDB overhead.
    if role in _SLEEP_LEARN_ROLES and _inject_rules is not None:
        try:
            system_prompt = _inject_rules(
                goal=task,
                system_prompt=system_prompt,
                trace_id=trace_id,
            )
        except Exception:
            # Non-fatal: if sleep-learn fails, use original prompt.
            pass

    # ── Response cache ───────────────────────────────────────────────────────
    # Deterministic roles (classify, route) are cached to avoid redundant LLM calls.
    if role_cfg.get("cacheable"):
        cache_key = _cache_key(role, task, context, content)
        cached = _get_cached(cache_key)
        if cached is not None:
            # Return a copy with the cache-hit marker to avoid mutating stored state.
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
    # Two code paths: token-aware (if role has budget_tokens) or char-based fallback.
    budget_chars = role_cfg.get("budget_chars") or _max_context_chars()
    budget_tokens = role_cfg.get("budget_tokens")
    if budget_tokens:
        # Token-accurate path: trim context to token budget, then give content
        # whatever tokens remain (capped at ~1000 tokens / ~4000 chars).
        trimmed_context = _trim_context(context, max_tokens=budget_tokens)
        remaining_tokens = max(0, budget_tokens - _estimate_tokens(trimmed_context))
        content_budget_tokens = min(1000, remaining_tokens)
        trimmed_content = _trim_context(content, max_tokens=content_budget_tokens)
    else:
        # Char-based fallback: trim context to char budget, then give content
        # whatever chars remain (capped at 4000).
        trimmed_context = _trim_context(context, max_chars=budget_chars)
        remaining = max(0, budget_chars - len(trimmed_context))
        content_budget = min(4000, remaining)
        trimmed_content = _trim_context(content, max_chars=content_budget)

    # ── Primary LLM call ───────────────────────────────────────────────────────
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

    # ── Retry with fallback role on transient failure ──────────────────────
    # One attempt only. If fallback also fails, return the error.
    fallback_role = _ROLE_FALLBACKS.get(role)
    if not result.ok and fallback_role and fallback_role in ROLE_CONFIG:
        fb_cfg = ROLE_CONFIG[fallback_role]
        fb_prompt = _SYSTEM_PROMPTS[fallback_role]
        result = llm.complete(
            role=fb_cfg["llm_role"],
            system=fb_prompt,
            user=task,
            context=trimmed_context,
            content=trimmed_content,
            json_mode=fallback_role in _API_JSON_ROLES,
            trace_id=trace_id,
            **call_kwargs,
        )

    elapsed = _time.time() - start_time

    # ── Error path ─────────────────────────────────────────────────────────────
    if not result.ok:
        error_code = "MODEL_ERROR"
        error_lower = (result.error or "").lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            error_code = "TIMEOUT"
        elif "circuit" in error_lower or "breaker" in error_lower:
            error_code = "CIRCUIT_OPEN"
        elif "rate" in error_lower or "quota" in error_lower:
            error_code = "RATE_LIMIT"

        _record_metric(
            role, "error", elapsed,
            result.usage.get("total", 0) if hasattr(result, "usage") else 0,
        )

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
        "prompt_version": _PROMPT_VERSION,
    }

    # ── JSON parsing for structured-output roles ─────────────────────────────
    parse_failed = False
    if role in _JSON_ROLES:
        if result.parsed is not None:
            # API json_mode succeeded — model already returned parsed JSON.
            response["parsed"] = result.parsed
        else:
            # Prompt-only JSON: strip markdown fences, then parse.
            clean = result.text.strip()
            for fence in ("```json", "```"):
                if clean.startswith(fence):
                    clean = clean[len(fence):]
                    clean = clean.strip().rstrip("`").strip()

            try:
                response["parsed"] = _json.loads(clean)
            except _json.JSONDecodeError:
                # Fast path failed — try brace-counting extraction.
                extracted = _extract_first_json(clean)
                if extracted:
                    try:
                        response["parsed"] = _json.loads(extracted)
                    except _json.JSONDecodeError:
                        parse_failed = True
                        response["parsed"] = {}
                        response["parse_warning"] = (
                            f"Extracted JSON was invalid for role '{role}'. "
                            "Empty dict returned for parsed. "
                            "Check response.text for raw output."
                        )
                else:
                    parse_failed = True
                    response["parsed"] = {}
                    response["parse_warning"] = (
                        f"Response was not valid JSON for role '{role}'. "
                        "Empty dict returned for parsed. "
                        "Check response.text for raw output."
                    )

        # ── Autonomous model escalation on parse failure ─────────────────────────
        # NOTE: fallback + escalation can produce up to 3 sequential LLM calls
        # (primary → fallback → planner escalation). This is intentional
        # defense-in-depth, but be aware of compounding timeout risk.
        if parse_failed and role_cfg.get("llm_role") != "planner":
            # Retry with planner (heavy model) for better JSON compliance.
            # Only escalate once — the guard prevents planner→planner loops.
            escalation_result = llm.complete(
                role="planner",
                system=system_prompt,
                user=(
                    f"[ESCALATION: The {role_cfg['llm_role']} model failed to "
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
                except _json.JSONDecodeError:
                    extracted = _extract_first_json(clean)
                    if extracted:
                        try:
                            response["parsed"] = _json.loads(extracted)
                            response.pop("parse_warning", None)
                            parse_failed = False
                            response["escalated"] = True
                        except _json.JSONDecodeError:
                            pass  # Keep original parse_warning.

    if parse_failed:
        _log_parse_warning(role, response.get("parse_warning", ""), result.text)

    # ── Metrics and cache ────────────────────────────────────────────────────
    total_tokens = (
        result.usage.get("total", 0)
        if hasattr(result, "usage") and result.usage
        else 0
    )
    _record_metric(role, "success", elapsed, total_tokens, parse_failed)

    if role_cfg.get("cacheable"):
        cache_key = _cache_key(role, task, context, content)
        _set_cached(cache_key, response.copy())

    return compress_result(response)
