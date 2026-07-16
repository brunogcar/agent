# core/llm_backend/client.py — The core LLMClient execution engine.
"""The core LLMClient execution engine."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

import httpx

from core.config import cfg
from core.tracer import tracer
from core.llm_backend.response import LLMResponse, ToolCall
from core.llm_backend.circuit_breaker import CircuitBreaker
from core.llm_backend.provider import ProviderRegistry
from core.llm_backend.config import RoleConfig, _build_role_configs

_ROLE_BUDGETS = {
    "planner": 32000,
    "executor": 12000,
    "router": 4000,
    "classify": 4000,
    "route": 4000,
    "summarize": 16000,
    "research": 16000,
    "code": 16000,
    "analyze": 12000,
    "critique": 12000,
    "review": 12000,
    "extract": 8000,
    "consultor": 8000,
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
        self._roles = _build_role_configs()

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
                # [BUGFIX-1] tracer.log() does not exist; use tracer.step() instead.
                tracer.step("", "circuit_breaker", f"State check for {role}", role=role, **breaker.get_state_info())
            except Exception as e:
                tracer.error("", "circuit_breaker_metrics", f"Metrics failed for {role}", error=str(e), role=role)

        # 2. Optionally expose via property if --metrics flag is enabled
        if getattr(cfg, "enable_metrics_endpoint", False):
            return {role: breaker.get_state_info() for role, breaker in self._breakers.items()}
        return None

    def call(
        self,
        role: str,
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        trace_id: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        """Make an LLM call by role. Always returns LLMResponse, never raises."""
        from core.runtime.activity_tracker import tracker

        with tracker.inference_slot(timeout=60.0):
            role_cfg = self._get_role(role)
            provider = self._registry.get(role_cfg.provider)

            _temperature = temperature if temperature is not None else role_cfg.temperature
            _max_tokens = max_tokens if max_tokens is not None else role_cfg.max_tokens
            _timeout = timeout if timeout is not None else role_cfg.timeout

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
                err = f"Circuit breaker OPEN for {role}: service degraded (fail-fast)."
                if trace_id:
                    tracer.warning(trace_id, "llm_call", err)
                return LLMResponse.from_error(role, role_cfg.model, err, elapsed=0.1)

            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    raw = provider.chat_completion(
                        model = role_cfg.model,
                        messages = messages,
                        temperature = _temperature,
                        max_tokens = _max_tokens,
                        timeout = _timeout,
                        json_mode = json_mode,
                        json_schema = json_schema,
                        **kwargs,
                    )
                    elapsed = round(time.time() - start, 2)
                    # HIG-02: Record success
                    breaker.record_success()
                    # v1.2: json_schema implies json_mode for parsing purposes.
                    # When a schema is provided, the response is JSON and should be parsed.
                    effective_json_mode = json_mode or (json_schema is not None)
                    result = self._parse_response(raw, role, role_cfg.model, elapsed, effective_json_mode)
                    # v1.3 (#43): Post-parse enum validation. If a schema was
                    # passed and the response parsed to a Python object, walk
                    # the schema recursively and verify every `enum` constraint
                    # is satisfied. Failures log a warning but DO NOT fail the
                    # call (graceful degradation — return parsed value as-is).
                    if json_schema and result.parsed is not None:
                        if not self._validate_enum_constraints(result.parsed, json_schema):
                            if trace_id:
                                tracer.warning(
                                    trace_id, "llm",
                                    "Post-parse enum validation failed — returning parsed value as-is (graceful degradation)",
                                )
                            else:
                                logger.warning(
                                    "Post-parse enum validation failed for role=%s model=%s",
                                    role, role_cfg.model,
                                )
                    return result

                except httpx.TimeoutException:
                    elapsed = round(time.time() - start, 2)
                    err = f"Timeout after {elapsed}s (limit: {_timeout}s)"
                    if breaker:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role, attempt=attempt)
                    if attempt == self.MAX_RETRIES:
                        return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                except httpx.ConnectError:
                    elapsed = round(time.time() - start, 2)
                    err = f"Cannot connect to {cfg.lm_studio_base_url} - is LM Studio running?"
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
                    # Hardening fix: if json_schema caused a 400 (provider doesn't support it),
                    # retry WITHOUT the schema — fall back to json_mode only.
                    # This handles older LM Studio versions and cloud providers that don't
                    # support response_format=json_schema (e.g., Mistral).
                    if (e.response.status_code == 400 and json_schema is not None
                            and attempt < self.MAX_RETRIES
                            and "response_format" in e.response.text.lower()):
                        if trace_id:
                            tracer.warning(trace_id, "llm_call",
                                f"Provider rejected json_schema (400), retrying with json_mode only")
                        json_schema = None  # strip schema for retry
                        json_mode = True    # ensure JSON parsing still works
                        continue
                    err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                    # Hardening fix: don't record circuit breaker failures for 4xx client
                    # errors (400 = bad request, 401 = auth, 403 = forbidden). These are not
                    # server availability issues — retrying won't help. Only 5xx and 429
                    # should trigger breaker. (Pre-existing behavior, documented here.)
                    if breaker and e.response.status_code >= 500:
                        breaker.record_failure()
                    if trace_id:
                        tracer.error(trace_id, "llm_call", err, role=role)
                    return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

                except Exception as e:
                    elapsed = round(time.time() - start, 2)
                    err = f"Unexpected error: {type(e).__name__}: {e}"
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
        role: str,
        system: str,
        user: str,
        context: str = "",
        content: str = "",
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        trace_id: str = "",
    ) -> LLMResponse:
        messages: list[dict] = [{"role": "system", "content": system}]

        if context:
            messages.append({"role": "user", "content": f"Background:\n{context}"})
            messages.append({"role": "assistant", "content": "Understood."})

        user_text = user
        if content:
            user_text = f"{user}\n\nContent:\n{content}"

        messages.append({"role": "user", "content": user_text})

        return self.call(
            role = role,
            messages = messages,
            temperature = temperature,
            max_tokens = max_tokens,
            timeout = timeout,
            json_mode = json_mode,
            json_schema = json_schema,
            trace_id = trace_id,
        )

    def complete_provider(
        self,
        provider_name: str,
        system: str,
        user: str,
        context: str = "",
        content: str = "",
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 60,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        trace_id: str = "",
    ) -> LLMResponse:
        """Call a specific provider directly (bypasses role routing).

        v1.3 (#22): New method for swarm and other callers that need
        provider-direct calls without role-based dispatch. Still uses
        registry plumbing (circuit breakers, telemetry, metrics) but
        skips role lookup — caller specifies provider + model directly.

        Unlike ``complete()`` which takes a role, this takes a provider_name
        (e.g. "openai", "claude", "gemini") and an optional model string.
        If ``model`` is empty, the caller is expected to supply it via the
        ``<NAME>_BASE_MODEL`` env var lookup; if both are empty, the call
        will still proceed but the provider may reject the empty model name
        with a 400 (handled by the standard error path).

        Thread-safety: same as ``call()`` — the provider's ``chat_completion``
        is thread-safe (per-provider singleton httpx.Client with double-checked
        locking). The per-role circuit breaker dict is guarded by Python's GIL
        for dict mutations; individual breaker state transitions are guarded
        by per-breaker ``threading.Lock``. Safe to call from a
        ``ThreadPoolExecutor`` (swarm's pattern).
        """
        from core.runtime.activity_tracker import tracker

        with tracker.inference_slot(timeout=60.0):
            # Resolve provider — raises KeyError with available names if unknown.
            provider = self._registry.get(provider_name)

            # Model: caller-supplied > env var > empty (provider will reject).
            # This matches the swarm's existing pattern (os.getenv NAME_BASE_MODEL).
            _model = model or os.getenv(f"{provider_name.upper()}_BASE_MODEL", "")

            if trace_id:
                tracer.step(
                    trace_id, "llm_call",
                    role=f"provider:{provider_name}", model=_model,
                    messages=1, timeout=timeout,
                )

            start = time.time()

            # Circuit breaker — keyed on the provider_name (no role). Reuses
            # the same _breakers dict + _get_breaker helper; the breaker is
            # created lazily on first use with the executor timeout fallback.
            breaker = self._get_breaker(provider_name)
            if not breaker.can_execute():
                elapsed = 0.1
                err = f"Circuit breaker OPEN for provider {provider_name}: service degraded (fail-fast)."
                if trace_id:
                    tracer.warning(trace_id, "llm_call", err)
                return LLMResponse.from_error(provider_name, _model, err, elapsed=0.1)

            # Build messages — same shape as complete(): system + optional
            # context (as user/assistant turn) + user (with optional content).
            messages: list[dict] = [{"role": "system", "content": system}]
            if context:
                messages.append({"role": "user", "content": f"Background:\n{context}"})
                messages.append({"role": "assistant", "content": "Understood."})
            user_text = user
            if content:
                user_text = f"{user}\n\nContent:\n{content}"
            messages.append({"role": "user", "content": user_text})

            # Context budget — same defensive budgeting as call(). Uses the
            # executor role's budget as a sensible default (no role to look up).
            from core.memory_backend.budget import budget_messages
            _budget = _ROLE_BUDGETS.get("executor", cfg.max_context_tokens)
            messages = budget_messages(messages, _budget)

            try:
                raw = provider.chat_completion(
                    model = _model,
                    messages = messages,
                    temperature = temperature,
                    max_tokens = max_tokens,
                    timeout = timeout,
                    json_mode = json_mode,
                    json_schema = json_schema,
                )
                elapsed = round(time.time() - start, 2)
                breaker.record_success()
                effective_json_mode = json_mode or (json_schema is not None)
                result = self._parse_response(
                    raw, provider_name, _model, elapsed, effective_json_mode,
                )
                # v1.3 (#43): post-parse enum validation (same as call()).
                if json_schema and result.parsed is not None:
                    if not self._validate_enum_constraints(result.parsed, json_schema):
                        if trace_id:
                            tracer.warning(
                                trace_id, "llm",
                                "Post-parse enum validation failed — returning parsed value as-is (graceful degradation)",
                            )
                        else:
                            logger.warning(
                                "Post-parse enum validation failed for provider=%s model=%s",
                                provider_name, _model,
                            )
                return result

            except httpx.TimeoutException:
                elapsed = round(time.time() - start, 2)
                breaker.record_failure()
                err = f"Timeout after {elapsed}s (limit: {timeout}s)"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=provider_name)
                return LLMResponse.from_error(provider_name, _model, err, elapsed)

            except httpx.ConnectError:
                elapsed = round(time.time() - start, 2)
                breaker.record_failure()
                err = f"Cannot connect to provider {provider_name}"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=provider_name)
                return LLMResponse.from_error(provider_name, _model, err, elapsed)

            except httpx.HTTPStatusError as e:
                elapsed = round(time.time() - start, 2)
                # Same 4xx-vs-5xx policy as call(): 5xx + 429 trip the breaker,
                # 4xx don't (caller's fault — bad model name, bad request).
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    breaker.record_failure()
                err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=provider_name)
                return LLMResponse.from_error(provider_name, _model, err, elapsed)

            except Exception as e:
                elapsed = round(time.time() - start, 2)
                breaker.record_failure()
                err = f"Unexpected error: {type(e).__name__}: {e}"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=provider_name)
                return LLMResponse.from_error(provider_name, _model, err, elapsed)

    def is_available(self, role: str = "planner") -> bool:
        role_cfg = self._get_role(role)
        provider = self._registry.get(role_cfg.provider)
        return provider.is_available()

    def register_provider(self, name: str, provider: Any) -> None:
        self._registry.register(name, provider)

    def list_roles(self) -> list[dict]:
        return [
            {
                "role": name,
                "model": rc.model,
                "provider": rc.provider,
                "timeout": rc.timeout,
                "temperature": rc.temperature,
                "max_tokens": rc.max_tokens,
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

    def complete_with_tools(
        self,
        role: str,
        system: str,
        user: str,
        tools: list,
        *,
        context: str = "",
        content: str = "",
        max_iterations: int = 10,
        execute: "Callable[[ToolCall], dict]",
        max_consecutive_errors: int = 3,
        tool_timeout: float = 30.0,
        trace_id: str = "",
        **kwargs,
    ) -> LLMResponse:
        """Native tool-calling loop (v1.4).

        Sends messages + tool definitions to the LLM. If the LLM returns
        ``tool_calls``, executes each via ``execute()``, appends the results
        to messages, and loops. Returns when the LLM produces a text response
        (no tool calls) or ``max_iterations`` is exceeded.

        Unlike ``complete()``, this method does NOT use ``json_mode`` or
        ``json_schema`` — it uses the provider's native tool-calling API
        (OpenAI ``tools``, Anthropic ``tool_use``, Gemini ``functionCall``).

        Args:
            role: LLM role (planner/executor/router/etc.) — resolves provider + model.
            system: System prompt.
            user: User message (the task).
            tools: list[ToolDefinition] — the tools the LLM can call.
            context: Optional background context (appended as user/assistant turn).
            content: Optional content block (appended to user message).
            max_iterations: Hard cap on LLM calls (default 10). Prevents runaway loops.
            execute: Callback that executes a ToolCall and returns a dict result.
                     The dict is JSON-stringified and appended as a ``tool`` role
                     message. If execute raises, the error is caught, formatted as
                     ``{"error": str(e)}``, and appended — the LLM sees the error
                     and can adapt. The loop does NOT break on tool errors.
            max_consecutive_errors: Bail after N consecutive tool errors (default 3).
            tool_timeout: Per-tool-call timeout in seconds (default 30). A hanging tool
                          is killed and the error is fed back to the LLM as a tool result.
                                    Prevents silent infinite loops on a misbehaving tool.
            trace_id: Trace identifier for observability.
            **kwargs: Forwarded to ``call()`` → provider's ``chat_completion()``.

        Returns:
            LLMResponse with the final text response. ``tool_calls`` is empty
            on the returned response (the loop consumed them all). ``usage``
            is aggregated across all iterations. If ``max_iterations`` is
            exceeded, ``ok=False`` + ``error`` describes the bail.

        Tool-call flow per iteration:
          1. call(role, messages, tools=tools) → LLMResponse
          2. If result.tool_calls is empty → return result (done)
          3. For each ToolCall: execute(tc) → dict result
          4. Append assistant message (with tool_calls) + tool result messages
          5. Check max_consecutive_errors + cancellation → continue or bail
        """
        import json as _json
        import time as _time
        from core.runtime.activity_tracker import tracker

        # Build messages (same shape as complete())
        messages: list[dict] = [{"role": "system", "content": system}]
        if context:
            messages.append({"role": "user", "content": f"Background:\n{context}"})
            messages.append({"role": "assistant", "content": "Understood."})
        user_text = user
        if content:
            user_text = f"{user}\n\nContent:\n{content}"
        messages.append({"role": "user", "content": user_text})

        # v1.4.2: Validate inputs before entering the loop.
        if max_iterations < 1:
            return LLMResponse.from_error(role, "", "max_iterations must be >= 1", 0.0)
        if not callable(execute):
            return LLMResponse.from_error(role, "", "execute must be a callable", 0.0)

        total_usage = {"prompt": 0, "completion": 0, "total": 0}
        consecutive_errors = 0
        last_result: LLMResponse | None = None
        start_time = _time.time()

        for iteration in range(max_iterations):
            # Cancellation check between iterations (minimax #6).
            try:
                if trace_id and tracker.is_cancelled(trace_id):
                    elapsed = round(_time.time() - start_time, 2)
                    return LLMResponse(
                        text="", role=role, model="",
                        usage={"prompt": 0, "completion": 0, "total": 0},
                        elapsed=elapsed, ok=False,
                        error=f"Tool-calling loop cancelled at iteration {iteration}",
                        reason="cancelled", iterations=iteration,
                    )
            except Exception:
                pass  # is_cancelled not available — proceed

            # LLM call (tools flows through kwargs to the provider)
            if trace_id:
                tracer.step(trace_id, "llm_tools", f"iteration {iteration}")

            result = self.call(
                role=role,
                messages=messages,
                json_mode=False,
                json_schema=None,
                trace_id=trace_id,
                tools=tools,
                **kwargs,
            )

            if not result.ok:
                # v1.4.1: Tag the bail reason + iteration count.
                # v1.4.2: Aggregate usage on error bail (was returning single-turn usage).
                result.reason = "llm_error"
                result.iterations = iteration + 1
                result.usage = total_usage
                return result  # LLM error — bail immediately

            # Aggregate usage across iterations (minimax #5)
            # v1.4.2: defensive — usage could theoretically be None
            for k in total_usage:
                total_usage[k] += (result.usage or {}).get(k, 0)

            last_result = result

            # No tool calls → done (text response)
            if not result.tool_calls:
                elapsed = round(_time.time() - start_time, 2)
                if trace_id:
                    tracer.step(trace_id, "llm_tools", f"completed in {iteration+1} iterations")
                return LLMResponse(
                    text=result.text,
                    role=role,
                    model=result.model,
                    usage=total_usage,
                    elapsed=elapsed,
                    ok=True,
                    iterations=iteration + 1,
                    reason="",
                )

            # Process tool calls
            # Append the assistant message (with tool_calls) to messages
            assistant_msg: dict = {"role": "assistant", "content": result.text or ""}
            # Include tool_calls in OpenAI shape for the provider to convert
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json.dumps(tc.arguments),
                    },
                }
                for tc in result.tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call + append result
            had_error = False
            for tc in result.tool_calls:
                if trace_id:
                    tracer.step(trace_id, "llm_tools",
                                f"executing tool '{tc.name}' action='{tc.arguments.get('action', '')}'")

                # v1.5: Tool execution with timeout — prevents a hanging tool from
                # blocking the loop indefinitely. Uses ThreadPoolExecutor (the tool
                # runs in a worker thread; the main thread waits with a timeout).
                # On timeout, the error is fed back to the LLM (same as any exception).
                try:
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(execute, tc)
                        tool_result = future.result(timeout=tool_timeout)
                    if not isinstance(tool_result, dict):
                        tool_result = {"result": str(tool_result)}
                    consecutive_errors = 0
                except FuturesTimeoutError:
                    had_error = True
                    consecutive_errors += 1
                    tool_result = {"error": f"Tool execution timed out after {tool_timeout}s"}
                    if trace_id:
                        tracer.warning(trace_id, "llm_tools",
                                       f"tool '{tc.name}' timed out after {tool_timeout}s")
                except Exception as e:
                    had_error = True
                    consecutive_errors += 1
                    tool_result = {"error": str(e)[:500]}  # truncate to avoid context overflow
                    if trace_id:
                        tracer.warning(trace_id, "llm_tools",
                                       f"tool '{tc.name}' error: {str(e)[:200]}")

                # Append tool result message (OpenAI shape).
                # v1.4.2: Wrap in try/except — a non-serializable tool result
                # (Path, bytes, custom class) would crash the loop with TypeError.
                try:
                    content_str = _json.dumps(tool_result)
                except (TypeError, ValueError):
                    content_str = _json.dumps({"error": "Tool returned non-JSON-serializable data"})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content_str,
                })

            # Bail on too many consecutive errors (minimax #4)
            if consecutive_errors >= max_consecutive_errors:
                elapsed = round(_time.time() - start_time, 2)
                err = f"{max_consecutive_errors} consecutive tool errors — bailing"
                if trace_id:
                    tracer.error(trace_id, "llm_tools", err)
                return LLMResponse(
                    text="", role=role, model=result.model,
                    usage=total_usage, elapsed=elapsed, ok=False,
                    error=err, reason="consecutive_errors",
                    iterations=iteration + 1,
                )

        # Max iterations exceeded
        elapsed = round(_time.time() - start_time, 2)
        err = f"max_iterations ({max_iterations}) exceeded"
        if trace_id:
            tracer.error(trace_id, "llm_tools", err)
        return LLMResponse(
            text="", role=role, model=last_result.model if last_result else "",
            usage=total_usage, elapsed=elapsed, ok=False,
            error=err, reason="max_iterations",
            iterations=max_iterations,
        )

    @staticmethod
    def _parse_response(
        raw: dict, role: str, model: str, elapsed: float, json_mode: bool,
    ) -> LLMResponse:
        try:
            # v1.4: content can be None when the LLM returns ONLY tool_calls
            # (no text). Handle gracefully — set to empty string.
            raw_content = raw["choices"][0]["message"].get("content")
            choice = (raw_content or "").strip()
            usage_r = raw.get("usage", {})
            usage = {
                "prompt": usage_r.get("prompt_tokens", 0),
                "completion": usage_r.get("completion_tokens", 0),
                "total": usage_r.get("total_tokens", 0),
            }
        except (KeyError, IndexError) as e:
            return LLMResponse.from_error(role, model, f"Response parse error: {e}", elapsed)

        # v1.4: Extract native tool_calls from the raw response (if present).
        # Converts OpenAI-shape tool_calls → ToolCall objects. The provider
        # adapters already normalized to OpenAI shape (choices[0].message.tool_calls).
        # Each entry: {"id":..., "type":"function", "function":{"name":..., "arguments": json_string}}
        tool_calls_list: list = []
        try:
            raw_tc = raw["choices"][0]["message"].get("tool_calls", [])
            for tc in raw_tc:
                fn = tc.get("function", {})
                args_str = fn.get("arguments", "{}")
                try:
                    args_dict = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
                except json.JSONDecodeError:
                    args_dict = {"_raw_arguments": args_str}
                tool_calls_list.append(ToolCall(
                    id=tc.get("id", f"tc_{len(tool_calls_list)}"),
                    name=fn.get("name", ""),
                    arguments=args_dict,
                ))
        except (KeyError, IndexError, TypeError):
            pass  # No tool_calls — normal text-only response.

        parsed: Optional[Any] = None
        if json_mode:
            # [Autocode v2.0] JSON extraction now delegates to core/json_extract.py
            # (single source of truth for all LLM JSON parsing in the codebase).
            # Was: 60-line inline implementation with 3-layer regex strategy.
            # Now: extract_first_json returns raw JSON string, we parse to handle
            # both dicts and arrays (extract_json returns dict only).
            from core.json_extract import extract_first_json
            raw_json = extract_first_json(choice)
            if raw_json:
                try:
                    parsed = json.loads(raw_json)
                except json.JSONDecodeError:
                    pass

            # Schema Validation: Catch LLM tool call drift
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
            tool_calls=tool_calls_list,
        )

    @staticmethod
    def _validate_enum_constraints(parsed: Any, schema: dict) -> bool:
        """Walk ``schema`` recursively and verify all ``enum`` constraints hold.

        v1.3 (#43): Post-parse enum validation. Runs after the provider returns
        and the response is parsed into a Python object. If any field with an
        ``enum`` constraint has a value not in that enum, this returns False.
        The caller (``call()`` / ``complete_provider()``) logs a warning and
        returns the parsed value as-is (graceful degradation — does NOT raise
        or fail the call).

        Why graceful: schema enforcement is best-effort. Even with native
        ``json_schema`` support (v1.3 Claude/Gemini), small/fast models can
        produce enum-violating output. Failing the call would push the failure
        up to the workflow layer, which has no good recovery path; logging +
        returning the value lets downstream code apply its own fallback
        (e.g. router's heuristic fallback, autocode's debug loop).

        Walks:
          - Object schemas: ``properties`` → each property sub-schema, matched
            against the corresponding key in the parsed dict.
          - Array schemas: ``items`` sub-schema, applied to each element of
            the parsed list.
          - ``allOf`` / ``anyOf`` / ``oneOf``: each sub-schema is checked
            independently (best-effort — combinatorial semantics ignored).
          - ``enum`` at any level: the parsed value at that position must be
            in the enum list.

        Returns True if no enum constraint is violated (or there are no enum
        constraints in the schema at all). Returns False on the first violation.
        """
        def _check(node: Any, sub: Any) -> bool:
            # `sub` is a JSON Schema fragment; `node` is the corresponding
            # Python value parsed from the LLM response.
            if not isinstance(sub, dict):
                return True  # not a schema fragment — nothing to check

            # Enum check at this level.
            enum = sub.get("enum")
            if isinstance(enum, list) and node not in enum:
                return False

            # Recurse into properties (object).
            props = sub.get("properties")
            if isinstance(props, dict) and isinstance(node, dict):
                for prop_name, prop_schema in props.items():
                    if prop_name in node:
                        if not _check(node[prop_name], prop_schema):
                            return False

            # Recurse into items (array).
            items = sub.get("items")
            if isinstance(items, dict) and isinstance(node, list):
                for el in node:
                    if not _check(el, items):
                        return False

            # allOf / anyOf / oneOf — best-effort, check each branch.
            for combiner in ("allOf", "anyOf", "oneOf"):
                branches = sub.get(combiner)
                if isinstance(branches, list):
                    for branch in branches:
                        if not _check(node, branch):
                            # For `anyOf`/`oneOf` a single branch failing
                            # doesn't necessarily mean the value is invalid,
                            # but for enum-checking purposes we treat any
                            # enum violation in any branch as a failure —
                            # conservative (over-reports) but safe.
                            return False

            return True

        try:
            return _check(parsed, schema)
        except Exception:
            # Never let validation crash the call — log only (caller's tracer.warning).
            # A pathological schema (circular $ref, etc.) shouldn't break parsing.
            return True
