"""tools/agent.py — Agent meta-tool (thin @tool facade).

Replaces: tools/agent_tool.py (monolithic)
Split into: agent_core/prompts.py, agent_core/roles.py, agent_core/context.py

The LLM sees ONE tool: agent(role, task, ...)
All prompts, role config, and context trimming live in agent_core/.

Architecture:
 1. Validate inputs (role exists, task non-empty)
 2. Vision role → delegate to tools.vision.vision() (multimodal, not text LLM)
 3. Lookup role config from agent_core.roles.ROLE_CONFIG
 4. Inject sleep-learn rules for high-latency roles
 5. Check response cache for deterministic roles
 6. Trim context + content via agent_core.context._trim_context()
 7. Call llm.complete() with role-specific model, timeout, json_mode
 8. Auto-retry with fallback role on transient failure (one attempt)
 9. Escalate to heavy model on parse failure (autonomous model escalation)
10. Parse JSON for structured-output roles (extract, route, plan, code, review)
11. Log per-role metrics
12. Compress and return result dict

JSON Parsing:
 - API json_mode: extract role (model enforces JSON schema)
 - Prompt-only JSON: route, plan, code, review (parsed post-hoc with brace-counting fallback)
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
from tools.agent_core.context import _trim_context, _max_context_chars, _max_context_tokens, _estimate_tokens

# Optional sleep-learn integration — non-fatal if unavailable
try:
    from core.sleep_learn.injector import inject_rules_into_prompt as _inject_rules
except ImportError:
    _inject_rules = None

# Module-level flags
PARALLEL_SAFE = False

# ── Response cache for deterministic roles ────────────────────────────────────
_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_MAX = 100
_CACHE_TTL_SECONDS = 300


def _cache_key(role: str, task: str, context: str, content: str) -> str:
    raw = f"{role}:{task}:{context}:{content}"
    return _hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_cached(key: str) -> dict | None:
    if key not in _CACHE:
        return None
    response, timestamp = _CACHE[key]
    if _time.time() - timestamp > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return response


def _set_cached(key: str, response: dict) -> None:
    _CACHE[key] = (response, _time.time())
    while len(_CACHE) > _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][1])
        del _CACHE[oldest]


def _clear_cache() -> None:
    """Clear all cached responses. Primarily for testing."""
    _CACHE.clear()


# ── Per-role metrics ──────────────────────────────────────────────────────────
_ROLE_METRICS: dict[str, dict] = {}


def _record_metric(role: str, status: str, elapsed: float, tokens: int, parse_failed: bool = False) -> None:
    """Record a lightweight metric for the given role.

    Metrics are stored in memory and can be queried via agent(role="metrics").
    This is prerequisite infrastructure for self-improving prompts.
    """
    if role not in _ROLE_METRICS:
        _ROLE_METRICS[role] = {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "total_elapsed": 0.0,
            "total_tokens": 0,
            "parse_failures": 0,
            "last_call": None,
        }
    m = _ROLE_METRICS[role]
    m["calls"] += 1
    m["last_call"] = _time.time()
    if status == "success":
        m["successes"] += 1
    else:
        m["failures"] += 1
    m["total_elapsed"] += elapsed
    m["total_tokens"] += tokens
    if parse_failed:
        m["parse_failures"] += 1


def _get_metrics(role: str | None = None) -> dict:
    """Return metrics for a specific role or all roles."""
    if role:
        return _ROLE_METRICS.get(role, {})
    return dict(_ROLE_METRICS)


def _clear_metrics() -> None:
    """Clear all metrics. Primarily for testing."""
    _ROLE_METRICS.clear()


# ── Parse warning logging ───────────────────────────────────────────────────────
_PARSE_WARNING_LOG: list[dict] = []
_PARSE_WARNING_LOG_MAX = 50


def _log_parse_warning(role: str, warning: str, text_preview: str) -> None:
    """Log a parse warning for later analysis of prompt degradation.

    This enables data-driven prompt tuning: if a role's parse_warning rate
    spikes, its system prompt likely needs tightening.
    """
    _PARSE_WARNING_LOG.append({
        "timestamp": _time.time(),
        "role": role,
        "warning": warning,
        "text_preview": text_preview[:200],
    })
    # Trim to max size
    while len(_PARSE_WARNING_LOG) > _PARSE_WARNING_LOG_MAX:
        _PARSE_WARNING_LOG.pop(0)


def _get_parse_warnings(role: str | None = None) -> list[dict]:
    """Return recent parse warnings, optionally filtered by role."""
    if role:
        return [w for w in _PARSE_WARNING_LOG if w["role"] == role]
    return list(_PARSE_WARNING_LOG)


def _clear_parse_warnings() -> None:
    """Clear parse warning log. Primarily for testing."""
    _PARSE_WARNING_LOG.clear()


# ── Prompt versioning ───────────────────────────────────────────────────────────
_PROMPT_VERSION = _hashlib.sha256(
    _json.dumps(_SYSTEM_PROMPTS, sort_keys=True).encode()
).hexdigest()[:8]


def _extract_first_json(text: str) -> str | None:
    """Extract first complete JSON object or array using brace/bracket counting.

    Handles nested structures, escaped quotes, and strings containing braces
    or brackets. Validates each candidate with json.loads before returning.

    Prefers the largest valid JSON structure to handle arrays at root and
    prose with accidental {} before real JSON correctly.
    """
    try:
        _json.loads(text)
        return text
    except _json.JSONDecodeError:
        pass

    _MATCHING = {"{": "}", "[": "]"}
    candidates = []

    for opener in ("{", "["):
        closer = _MATCHING[opener]
        positions = [i for i, c in enumerate(text) if c == opener]

        for start in positions:
            stack = []
            in_string = False
            escape = False

            for i in range(start, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == opener:
                    stack.append(c)
                elif c == closer:
                    if stack and stack[-1] == opener:
                        stack.pop()
                    if not stack:
                        candidate = text[start:i + 1]
                        try:
                            _json.loads(candidate)
                            candidates.append(candidate)
                        except _json.JSONDecodeError:
                            pass
                        break

    if not candidates:
        return None

    def _score(c):
        parsed = _json.loads(c)
        is_dict = isinstance(parsed, dict)
        return (len(c), is_dict)

    candidates.sort(key=_score, reverse=True)
    return candidates[0]


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
    if role == "metrics":
        target = task.strip() if task else None
        return {
            "status": "success",
            "role": "metrics",
            "metrics": _get_metrics(target),
            "parse_warnings": _get_parse_warnings(target),
            "prompt_version": _PROMPT_VERSION,
        }

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

        vision_kwargs: dict = {"task": task, "file_path": file_path, "base64": b64, "url": url, "trace_id": trace_id, "context": ""}
        if mime_type:
            vision_kwargs["mime_type"] = mime_type
        if vision_json_mode:
            vision_kwargs["json_mode"] = vision_json_mode

        return _vision(**vision_kwargs)

    role_cfg = ROLE_CONFIG[role]
    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role = role_cfg["llm_role"]
    json_mode = role in _API_JSON_ROLES

    # ── Sleep-learn injection ──────────────────────────────────────────────
    if role in _SLEEP_LEARN_ROLES and _inject_rules is not None:
        try:
            system_prompt = _inject_rules(
                goal=task,
                system_prompt=system_prompt,
                trace_id=trace_id,
            )
        except Exception:
            pass

    # ── Response cache ───────────────────────────────────────────────────────
    if role_cfg.get("cacheable"):
        cache_key = _cache_key(role, task, context, content)
        cached = _get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    # Build call kwargs
    call_kwargs: dict = {}
    if temperature >= 0:
        call_kwargs["temperature"] = temperature
    if max_tokens > 0:
        call_kwargs["max_tokens"] = max_tokens

    # ── Context trimming with token-aware budget ─────────────────────────────
    budget_chars = role_cfg.get("budget_chars") or _max_context_chars()
    # Prefer token budget if config supports it
    budget_tokens = role_cfg.get("budget_tokens")
    if budget_tokens:
        trimmed_context = _trim_context(context, max_tokens=budget_tokens)
        remaining_tokens = max(0, budget_tokens - _estimate_tokens(trimmed_context))
        content_budget_tokens = min(1000, remaining_tokens)  # ~4000 chars
        trimmed_content = _trim_context(content, max_tokens=content_budget_tokens)
    else:
        trimmed_context = _trim_context(context, max_chars=budget_chars)
        remaining = max(0, budget_chars - len(trimmed_context))
        content_budget = min(4000, remaining)
        trimmed_content = _trim_context(content, max_chars=content_budget)

    # ── LLM call with retry fallback ─────────────────────────────────────────
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

    if not result.ok:
        error_code = "MODEL_ERROR"
        error_lower = (result.error or "").lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            error_code = "TIMEOUT"
        elif "circuit" in error_lower or "breaker" in error_lower:
            error_code = "CIRCUIT_OPEN"
        elif "rate" in error_lower or "quota" in error_lower:
            error_code = "RATE_LIMIT"

        _record_metric(role, "error", elapsed, result.usage.get("total_tokens", 0) if hasattr(result, "usage") else 0)

        return {
            "status": "error",
            "error_code": error_code,
            "role": role,
            "error": result.error,
            "elapsed": elapsed,
            "model": result.model,
        }

    response: dict = {
        "status": "success",
        "role": role,
        "text": result.text,
        "model": result.model,
        "elapsed": elapsed,
        "usage": result.usage,
        "prompt_version": _PROMPT_VERSION,
    }

    # ── JSON parsing with autonomous model escalation ──────────────────────────
    parse_failed = False
    if role in _JSON_ROLES:
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
        if parse_failed and role_cfg.get("llm_role") != "planner":
            # Retry with planner (heavy model) for better JSON compliance
            # Only escalate once to avoid infinite loops
            escalation_result = llm.complete(
                role="planner",
                system=system_prompt,
                user=f"[ESCALATION: The {role_cfg['llm_role']} model failed to produce valid JSON. Please produce valid JSON only.]\n\n{task}",
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
                    del response["parse_warning"]
                    parse_failed = False
                    response["escalated"] = True
                except _json.JSONDecodeError:
                    extracted = _extract_first_json(clean)
                    if extracted:
                        try:
                            response["parsed"] = _json.loads(extracted)
                            del response["parse_warning"]
                            parse_failed = False
                            response["escalated"] = True
                        except _json.JSONDecodeError:
                            pass  # Keep original parse_warning

    if parse_failed:
        _log_parse_warning(role, response.get("parse_warning", ""), result.text)

    # ── Metrics and cache ────────────────────────────────────────────────────
    total_tokens = result.usage.get("total_tokens", 0) if hasattr(result, "usage") and result.usage else 0
    _record_metric(role, "success", elapsed, total_tokens, parse_failed)

    if role_cfg.get("cacheable"):
        cache_key = _cache_key(role, task, context, content)
        _set_cached(cache_key, response.copy())

    return compress_result(response)
