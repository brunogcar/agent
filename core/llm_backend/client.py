"""
core/llm_backend/client.py — The core LLMClient execution engine.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

import httpx

from core.config import cfg
from core.tracer import tracer
from core.llm_backend.response import LLMResponse
from core.llm_backend.circuit_breaker import CircuitBreaker
from core.llm_backend.provider import ProviderRegistry
from core.llm_backend.config import RoleConfig, _build_role_configs

_ROLE_BUDGETS = {
    "planner":   32000,
    "executor":  12000,
    "router":     4000,
    "classify":   4000,
    "route":      4000,
    "summarize": 16000,
    "research":  16000,
    "code":      16000,
    "analyze":   12000,
    "critique":  12000,
    "review":    12000,
    "extract":    8000,
    "consultor":  8000,
}

class LLMClient:
    """
    The single LLM client used by everything in the agent.
    Thread-safe via per-thread httpx.Client instances in LMStudioProvider.
    """
    MAX_RETRIES = 2
    RETRY_DELAY = 2.0

    def __init__(self) -> None:
        self._registry = ProviderRegistry()
        self._roles    = _build_role_configs()
        
        # HIG-02: Per-role circuit breakers for resilience
        self._breakers: dict[str, CircuitBreaker] = {}
        self._build_breakers()

    # [FIX] Changed from @cached_property to @property to reflect dynamic breaker states
    @property
    def circuit_breaker_states(self) -> dict[str, dict] | None:
        """Public API for gateway to query breaker states."""
        # 1. Always log states to JSONL for observability
        for role, breaker in self._breakers.items():
            try:
                tracer.log("circuit_breaker", role=role, **breaker.get_state_info())
            except Exception as e:
                tracer.error("", "circuit_breaker_metrics", error=str(e), role=role)

        # 2. Optionally expose via property if --metrics flag is enabled
        if getattr(cfg, "enable_metrics_endpoint", False):
            return {role: breaker.get_state_info() for role, breaker in self._breakers.items()}
        return None

    def call(
        self,
        role:        str,
        messages:    list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens:  Optional[int]   = None,
        timeout:     Optional[int]   = None,
        json_mode:   bool            = False,
        trace_id:    str             = "",
        **kwargs:    Any,
    ) -> LLMResponse:
        """Make an LLM call by role. Always returns LLMResponse, never raises."""
        from core.runtime.activity_tracker import tracker
        
        with tracker.inference_slot(timeout=60.0):
            role_cfg = self._get_role(role)
            provider = self._registry.get(role_cfg.provider)

            _temperature = temperature if temperature is not None else role_cfg.temperature
            _max_tokens  = max_tokens  if max_tokens  is not None else role_cfg.max_tokens
            _timeout     = timeout     if timeout     is not None else role_cfg.timeout

            # 🔴 PHASE 5: COGNITIVE BUDGETING
            # Intercept messages to ensure they fit the context window.
            # This prevents OOM crashes and attention dilution.
            from core.memory_backend.budget import budget_messages
            _budget = _ROLE_BUDGETS.get(role, cfg.max_context_tokens)
            estimated = sum(len(m.get("content", "")) for m in messages) // 4
            logger.info("LLM call: role=%s messages=%d est_tokens=%d budget=%d", role, len(messages), estimated, _budget)
            messages = budget_messages(messages, _budget)

            if trace_id:
                tracer.step(
                    trace_id, "llm_call",
                    role=role, model=role_cfg.model,
                    messages=len(messages), timeout=_timeout,
                )

            start = time.time()

            # HIG-02: Check circuit breaker before attempt
            breaker = self._get_breaker(role)
            if not breaker.can_execute():
                elapsed = 0.1
                err     = f"Circuit breaker OPEN for {role}: service degraded (fail-fast)."
                if trace_id:
                    tracer.warning(trace_id, "llm_call", err)
                return LLMResponse.from_error(role, role_cfg.model, err, elapsed=0.1)

            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    raw  = provider.chat_completion(
                        model       = role_cfg.model,
                        messages    = messages,
                        temperature = _temperature,
                        max_tokens  = _max_tokens,
                        timeout     = _timeout,
                        json_mode   = json_mode,
                        **kwargs,
                    )
                    elapsed = round(time.time() - start, 2)
                    # HIG-02: Record success
                    breaker.record_success()
                    return self._parse_response(raw, role, role_cfg.model, elapsed, json_mode)

                except httpx.TimeoutException:
                    elapsed = round(time.time() - start, 2)
                    err     = f"Timeout after {elapsed}s (limit: {_timeout}s)"
                    if breaker:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role, attempt=attempt)
                    if attempt == self.MAX_RETRIES:
                        return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                except httpx.ConnectError:
                    elapsed = round(time.time() - start, 2)
                    err     = f"Cannot connect to {cfg.lm_studio_base_url} - is LM Studio running?"
                    if breaker:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role)
                    return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                except httpx.HTTPStatusError as e:
                    elapsed = round(time.time() - start, 2)
                    if e.response.status_code == 429 and attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY * (attempt + 1))
                        continue
                    err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                    if breaker:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role)
                    return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                except Exception as e:
                    elapsed = round(time.time() - start, 2)  
                    err     = f"Unexpected error: {type(e).__name__}: {e}"
                    if breaker:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role)
                    return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)

            elapsed = round(time.time() - start, 2)
            return LLMResponse.from_error(role, role_cfg.model, "Max retries exceeded", elapsed)

    def complete(
        self,
        role:        str,
        system:      str,
        user:        str,
        context:     str  = "",
        content:     str  = "",
        *,
        temperature: Optional[float] = None,
        max_tokens:  Optional[int]   = None,
        timeout:     Optional[int]   = None,
        json_mode:   bool            = False,
        trace_id:    str             = "",
    ) -> LLMResponse:
        messages: list[dict] = [{"role": "system", "content": system}]

        if context:
            messages.append({"role": "user",         "content": f"Background:\n{context}"})
            messages.append({"role": "assistant",    "content": "Understood."})

        user_text = user
        if content:
            user_text = f"{user}\n\nContent:\n{content}"

        messages.append({"role": "user", "content": user_text})

        return self.call(
            role        = role,
            messages    = messages,
            temperature = temperature,
            max_tokens  = max_tokens,
            timeout     = timeout,
            json_mode   = json_mode,
            trace_id    = trace_id,
        )

    def is_available(self, role: str = "planner") -> bool:
        role_cfg = self._get_role(role)
        provider = self._registry.get(role_cfg.provider)
        return provider.is_available()

    def register_provider(self, name: str, provider: Any) -> None:
        self._registry.register(name, provider)

    def list_roles(self) -> list[dict]:
        return [
            {
                "role":        name,
                "model":       rc.model,
                "provider":    rc.provider,
                "timeout":     rc.timeout,
                "temperature": rc.temperature,
                "max_tokens":  rc.max_tokens,
            }
            for name, rc in sorted(self._roles.items())
        ]

    def _build_breakers(self) -> None:
        """
        HIG-02 + DeepSeek fix: Build circuit breakers for each role.
        Uses role timeout config as circuit open duration.
        """
        for role_name, role_cfg in self._roles.items():
            breaker = CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=role_cfg.timeout,
                half_open_max_calls=1,
            )
            self._breakers[role_name] = breaker

    def _get_breaker(self, role: str) -> CircuitBreaker:
        """Get circuit breaker for role, create if not exists."""
        if role not in self._breakers:
            fallback_timeout = cfg.model_registry.get("executor", {}).get("timeout", 120)
            fallback_breaker = CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=fallback_timeout,
                half_open_max_calls=1,
            )
            self._breakers[role] = fallback_breaker
        return self._breakers[role]

    def _get_role(self, role: str) -> RoleConfig:
        if role not in self._roles:
            tracer.error(
                "", 
                "llm_role_fallback", 
                f"Unknown role {role!r} -- falling back to executor. Known: {sorted(self._roles.keys())}"
            )
            return self._roles["executor"]
        return self._roles[role]

    @staticmethod
    def _parse_response(
        raw: dict, role: str, model: str, elapsed: float, json_mode: bool,
    ) -> LLMResponse:
        try:
            choice  = raw["choices"][0]["message"]["content"].strip()
            usage_r = raw.get("usage", {})
            usage   = {
                "prompt":     usage_r.get("prompt_tokens", 0),
                "completion": usage_r.get("completion_tokens", 0),
                "total":      usage_r.get("total_tokens", 0),
            }
        except (KeyError, IndexError) as e:
            return LLMResponse.from_error(role, model, f"Response parse error: {e}", elapsed)

        parsed: Optional[Any] = None
        if json_mode:
            # [P1] Robust JSON extraction
            # Strategy:
            # 1. Try parsing the raw string directly (handles clean JSON, arrays, and backticks in strings)
            # 2. Try extracting from markdown code blocks
            # 3. Fall back to finding outermost JSON object/array
            
            json_str = None
            choice_stripped = choice.strip()
            
            # 1. Direct parse attempt (fixes arrays and backticks inside strings)
            try:
                parsed = json.loads(choice_stripped)
            except json.JSONDecodeError:
                pass
            
            # 2. If direct parse failed, try extraction
            if parsed is None:
                # Try markdown code block extraction
                # Use a regex that expects the fence to be on its own line or at the start/end
                code_block_match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', choice, re.DOTALL)
                if code_block_match:
                    json_str = code_block_match.group(1).strip()
                else:
                    # Fall back to finding outermost JSON structure
                    obj_match = re.search(r'\{.*\}', choice, re.DOTALL)
                    arr_match = re.search(r'\[.*\]', choice, re.DOTALL)
                    
                    # Pick the one that starts earliest in the string
                    if obj_match and arr_match:
                        json_str = obj_match.group(0) if obj_match.start() < arr_match.start() else arr_match.group(0)
                    elif obj_match:
                        json_str = obj_match.group(0)
                    elif arr_match:
                        json_str = arr_match.group(0)
                    else:
                        json_str = choice_stripped
                
            if json_str:
                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError:
                    pass

            # 🔴 Schema Validation: Catch LLM tool call drift
            # Only validate if it looks like a tool call (has 'tool' and 'action')
            if parsed and isinstance(parsed, dict) and "tool" in parsed and "action" in parsed:
                try:
                    from core.contracts import validate_tool_call
                    validate_tool_call(parsed)
                except Exception as e:
                    tracer.error(
                        "",
                        "schema_validation_failed",
                        f"Tool call schema validation failed for {role}/{model}: {e}"
                    )
        
        return LLMResponse(
            text=choice,
            role=role,
            model=model,
            usage=usage,
            elapsed=elapsed,
            parsed=parsed,
            ok=True,
        )