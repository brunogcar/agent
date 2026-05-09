"""
core/llm.py - Unified LLM client with provider abstraction.

Design goals:
  1. Single call site for ALL model interactions - nothing else calls requests directly
  2. Provider abstraction from day one - adding DeepSeek/Claude/Groq later
     requires only a new Provider class, zero changes to callers
  3. Role-based dispatch - callers say "executor" not "hermes-3-llama-3.1-8b"
  4. Per-role timeouts enforced here, not scattered across tool files
  5. Structured output support - request JSON, get a parsed dict back
  6. Full trace integration - every call logged with trace_id

FIX: P0-4 Thread-safety
  The original code kept a single shared httpx.Client instance on the provider.
  httpx.Client is NOT thread-safe -- concurrent calls from the gateway's thread
  pool corrupt each other's requests. Fix: create a new httpx.Client per call
  using threading.local() so each thread gets its own instance with connection
  pooling scoped to that thread. This avoids the overhead of a brand-new client
  on every call while fixing the race condition.

Usage:
    from core.llm import llm

    result = llm.complete(
        role   = "executor",
        system = "You are a senior Python developer...",
        user   = "Fix this bug: ...",
    )
    text = result.text   # str
    ok   = result.ok     # bool
"""

from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from core.config import cfg
from core.tracer import tracer


# -- Response dataclass --------------------------------------------------------

@dataclass
class LLMResponse:
    """Unified response object returned by all LLM calls."""

    text:     str
    role:     str
    model:    str
    usage:    dict[str, int]
    elapsed:  float
    parsed:   Optional[dict]  = None
    error:    str             = ""
    ok:       bool            = True

    @classmethod
    def from_error(cls, role: str, model: str, error: str, elapsed: float = 0.0) -> "LLMResponse":
        return cls(
            text="", role=role, model=model,
            usage={"prompt": 0, "completion": 0, "total": 0},
            elapsed=elapsed, error=error, ok=False,
        )


# -- Provider abstraction ------------------------------------------------------

class BaseProvider(ABC):
    """
    Abstract LLM provider. Implement this to add a new backend.
    Subclass, implement chat_completion(), register in ProviderRegistry.
    """

    name: str = "base"

    @abstractmethod
    def chat_completion(
        self,
        model:       str,
        messages:    list[dict],
        temperature: float,
        max_tokens:  int,
        timeout:     int,
        json_mode:   bool,
        **kwargs:    Any,
    ) -> dict: ...

    def is_available(self) -> bool:
        return True


class LMStudioProvider(BaseProvider):
    """
    OpenAI-compatible provider for LM Studio (local).
    Also works with Ollama, vLLM, or any OpenAI-compatible endpoint.

    THREAD-SAFETY FIX (P0-4):
    The original code held a single shared httpx.Client. httpx.Client is not
    thread-safe -- the gateway serves multiple concurrent requests from a thread
    pool, causing silent request corruption.

    Fix: threading.local() gives each thread its own httpx.Client instance.
    Connection pooling still works (per-thread pool), and we avoid creating a
    brand-new client on every single call.
    """

    name = "lmstudio"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._local   = threading.local()  # thread-local storage for client

    def _get_client(self) -> httpx.Client:
        """
        Return (or create) a thread-local httpx.Client.
        Each thread gets its own client -- no shared mutable state.
        """
        if not hasattr(self._local, "client") or self._local.client.is_closed:
            self._local.client = httpx.Client(
                base_url = self.base_url,
                headers  = {"Content-Type": "application/json"},
                timeout  = None,  # timeout enforced per-request
            )
        return self._local.client

    def chat_completion(
        self,
        model:       str,
        messages:    list[dict],
        temperature: float,
        max_tokens:  int,
        timeout:     int,
        json_mode:   bool,
        **kwargs:    Any,
    ) -> dict:
        payload: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(kwargs)

        response = self._get_client().post(
            "/chat/completions",
            json    = payload,
            timeout = timeout,
        )
        response.raise_for_status()
        return response.json()

    def is_available(self) -> bool:
        try:
            resp = self._get_client().get("/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# -- Provider registry ---------------------------------------------------------

class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> BaseProvider:
        if name not in self._providers:
            raise KeyError(
                f"Provider '{name}' not registered. "
                f"Available: {list(self._providers.keys())}"
            )
        return self._providers[name]

    def available(self) -> list[str]:
        return list(self._providers.keys())


# -- Role configuration --------------------------------------------------------

@dataclass
class RoleConfig:
    model:       str
    provider:    str   = "lmstudio"
    timeout:     int   = 60
    temperature: float = 0.2
    max_tokens:  int   = 1024


def _build_role_configs() -> dict[str, RoleConfig]:
    roles: dict[str, RoleConfig] = {}

    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "vision":    {"temperature": 0.1, "max_tokens": 1024, "timeout": 60},
        # vision shares cfg.vision_model (same Qwen 9B as planner).
        # LMStudioProvider forwards multimodal image_url blocks as-is to
        # /chat/completions — no separate provider class needed.
        "summarize": {"temperature": 0.1, "max_tokens": 512,  "timeout": 60},
        "extract":   {"temperature": 0.0, "max_tokens": 512,  "timeout": 60},
        "classify":  {"temperature": 0.0, "max_tokens": 64,   "timeout": 15},
        "research":  {"temperature": 0.2, "max_tokens": 1024, "timeout": 120},
        "critique":  {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
        "analyze":   {"temperature": 0.1, "max_tokens": 1024, "timeout": 90},
        "code":      {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "review":    {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
    }

    executor_model = cfg.model_registry.get("executor", {}).get("model", cfg.executor_model)

    for role, d in defaults.items():
        reg_entry = cfg.model_registry.get(role, {})
        # Vision falls back to cfg.vision_model, not executor_model
        if role == "vision":
            model = reg_entry.get("model", cfg.vision_model or executor_model)
        else:
            model = reg_entry.get("model", executor_model)
        timeout   = reg_entry.get("timeout", d["timeout"])
        roles[role] = RoleConfig(
            model       = model,
            timeout     = timeout,
            temperature = d["temperature"],
            max_tokens  = d["max_tokens"],
        )

    return roles


# -- LLM client ----------------------------------------------------------------

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

        self._registry.register(
            "lmstudio",
            LMStudioProvider(cfg.lm_studio_base_url),
        )

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
        """
        Make an LLM call by role. Always returns LLMResponse, never raises.
        Check response.ok and response.error for failures.
        """
        role_cfg = self._get_role(role)
        provider = self._registry.get(role_cfg.provider)

        _temperature = temperature if temperature is not None else role_cfg.temperature
        _max_tokens  = max_tokens  if max_tokens  is not None else role_cfg.max_tokens
        _timeout     = timeout     if timeout     is not None else role_cfg.timeout

        if trace_id:
            tracer.step(
                trace_id, "llm_call",
                role=role, model=role_cfg.model,
                messages=len(messages), timeout=_timeout,
            )

        start = time.time()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                raw = provider.chat_completion(
                    model       = role_cfg.model,
                    messages    = messages,
                    temperature = _temperature,
                    max_tokens  = _max_tokens,
                    timeout     = _timeout,
                    json_mode   = json_mode,
                    **kwargs,
                )
                elapsed = round(time.time() - start, 2)
                return self._parse_response(raw, role, role_cfg.model, elapsed, json_mode)

            except httpx.TimeoutException:
                elapsed = round(time.time() - start, 2)
                err     = f"Timeout after {elapsed}s (limit: {_timeout}s)"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=role, attempt=attempt)
                if attempt == self.MAX_RETRIES:
                    return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

            except httpx.ConnectError:
                elapsed = round(time.time() - start, 2)
                err     = f"Cannot connect to {cfg.lm_studio_base_url} - is LM Studio running?"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=role)
                return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

            except httpx.HTTPStatusError as e:
                elapsed = round(time.time() - start, 2)
                if e.response.status_code == 429 and attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if trace_id:
                    tracer.error(trace_id, "llm_call", err, role=role)
                return LLMResponse.from_error(role, role_cfg.model, err, elapsed)

            except Exception as e:
                elapsed = round(time.time() - start, 2)
                err     = f"Unexpected error: {type(e).__name__}: {e}"
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
            messages.append({"role": "user",      "content": f"Background:\n{context}"})
            messages.append({"role": "assistant",  "content": "Understood."})

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

    def register_provider(self, name: str, provider: BaseProvider) -> None:
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

    def _get_role(self, role: str) -> RoleConfig:
        if role not in self._roles:
            import sys as _sys
            print(
                f"[llm] WARNING: unknown role {role!r} -- falling back to executor. "
                f"Known: {sorted(self._roles.keys())}",
                file=_sys.stderr,
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

        parsed: Optional[dict] = None
        if json_mode:
            clean = choice
            for fence in ["```json", "```"]:
                if clean.startswith(fence):
                    clean = clean[len(fence):]
            clean = clean.strip().rstrip("`").strip()
            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                pass

        return LLMResponse(
            text=choice, role=role, model=model,
            usage=usage, elapsed=elapsed, parsed=parsed, ok=True,
        )


# -- Singleton -----------------------------------------------------------------
llm = LLMClient()
