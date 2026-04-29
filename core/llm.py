"""
core/llm.py — Unified LLM client with provider abstraction.

Design goals:
  1. Single call site for ALL model interactions — nothing else calls requests directly
  2. Provider abstraction from day one — adding DeepSeek/Claude/Groq later
     requires only a new Provider class, zero changes to callers
  3. Role-based dispatch — callers say "executor" not "hermes-3-llama-3.1-8b"
  4. Per-role timeouts enforced here, not scattered across tool files
  5. Structured output support — request JSON, get a parsed dict back
  6. Full trace integration — every call logged with trace_id

Usage:
    from core.llm import llm

    # Simple call by role
    result = llm.call("executor", messages=[...])
    text   = result.text          # str
    tokens = result.usage         # {"prompt": N, "completion": N}

    # Structured JSON output
    result = llm.call("router", messages=[...], json_mode=True)
    data   = result.parsed        # dict (None if parse failed)

    # With system prompt shortcut
    result = llm.complete(
        role    = "executor",
        system  = "You are a senior Python developer...",
        user    = "Fix this bug: ...",
        context = "Background: ...",          # optional
        content = "File content: ...",        # optional
    )

    # Trace-attached call
    result = llm.call("planner", messages=[...], trace_id=tid)
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from core.config import cfg
from core.tracer import tracer


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Unified response object returned by all LLM calls."""

    text:     str                        # raw text content
    role:     str                        # which role was used
    model:    str                        # actual model string used
    usage:    dict[str, int]             # {"prompt": N, "completion": N, "total": N}
    elapsed:  float                      # seconds
    parsed:   Optional[dict]  = None     # populated if json_mode=True and parse succeeded
    error:    str             = ""       # non-empty if the call failed
    ok:       bool            = True     # False if error is non-empty

    @classmethod
    def from_error(cls, role: str, model: str, error: str, elapsed: float = 0.0) -> "LLMResponse":
        return cls(
            text="", role=role, model=model,
            usage={"prompt": 0, "completion": 0, "total": 0},
            elapsed=elapsed, error=error, ok=False,
        )


# ── Provider abstraction ──────────────────────────────────────────────────────

class BaseProvider(ABC):
    """
    Abstract LLM provider. Implement this to add a new backend.

    To add DeepSeek, Claude, Groq, etc.:
      1. Subclass BaseProvider
      2. Implement chat_completion()
      3. Register in ProviderRegistry below

    The rest of the system never changes.
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
    ) -> dict:
        """
        Make a chat completion request.
        Must return the raw API response dict, or raise on failure.
        """
        ...

    def is_available(self) -> bool:
        """Optional health check. Override for providers that need it."""
        return True


class LMStudioProvider(BaseProvider):
    """
    OpenAI-compatible provider for LM Studio (local).
    Also works with any OpenAI-compatible endpoint (Ollama, vLLM, etc.).
    """

    name = "lmstudio"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        # Shared httpx client — connection pooling across calls
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            timeout=None,  # timeout is set per-request
        )

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

        payload.update(kwargs)  # allow extra params (top_p, stop, etc.)

        response = self._client.post(
            "/chat/completions",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def is_available(self) -> bool:
        try:
            resp = self._client.get("/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# ── Provider registry ─────────────────────────────────────────────────────────

class ProviderRegistry:
    """
    Maps provider names to provider instances.
    New providers are registered here — callers never change.
    """

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


# ── Role configuration ────────────────────────────────────────────────────────

@dataclass
class RoleConfig:
    """Per-role defaults. Callers can override at call time."""
    model:       str
    provider:    str   = "lmstudio"
    timeout:     int   = 60
    temperature: float = 0.2
    max_tokens:  int   = 1024


def _build_role_configs() -> dict[str, RoleConfig]:
    """Build role configs from cfg.model_registry."""
    roles: dict[str, RoleConfig] = {}

    # Role-specific defaults — these mirror the registry in config.py
    defaults = {
        "planner":  {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor": {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":   {"temperature": 0.0, "max_tokens": 256,  "timeout": 15},
        "vision":   {"temperature": 0.2, "max_tokens": 1024, "timeout": 60},
        # Agent personas — used by the agent meta-tool
        "summarize": {"temperature": 0.1, "max_tokens": 512,  "timeout": 60},
        "extract":   {"temperature": 0.0, "max_tokens": 512,  "timeout": 60},
        "classify":  {"temperature": 0.0, "max_tokens": 64,   "timeout": 15},
        "research":  {"temperature": 0.2, "max_tokens": 1024, "timeout": 120},
        "critique":  {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
        "analyze":   {"temperature": 0.1, "max_tokens": 1024, "timeout": 90},
        "code":      {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "review":    {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
    }

    # Persona roles use executor model by default
    executor_model = cfg.model_registry.get("executor", {}).get("model", cfg.executor_model)

    for role, d in defaults.items():
        # Get model from cfg registry, fall back to executor for persona roles
        reg_entry = cfg.model_registry.get(role, {})
        model     = reg_entry.get("model", executor_model)
        timeout   = reg_entry.get("timeout", d["timeout"])

        roles[role] = RoleConfig(
            model       = model,
            timeout     = timeout,
            temperature = d["temperature"],
            max_tokens  = d["max_tokens"],
        )

    return roles


# ── LLM client ────────────────────────────────────────────────────────────────

class LLMClient:
    """
    The single LLM client used by everything in the agent.

    Features:
    - Role-based dispatch (no model names in callers)
    - Per-role timeout enforcement
    - JSON mode with auto-parsing
    - Trace integration
    - Provider abstraction (swap backend without touching callers)
    - Retry on transient errors (connection reset, 429)
    """

    MAX_RETRIES = 2
    RETRY_DELAY = 2.0  # seconds between retries

    def __init__(self) -> None:
        self._registry = ProviderRegistry()
        self._roles    = _build_role_configs()

        # Register default local provider
        self._registry.register(
            "lmstudio",
            LMStudioProvider(cfg.lm_studio_base_url),
        )

    # ── Public API ────────────────────────────────────────────────────────────

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
        Make an LLM call by role.

        role     : "planner" | "executor" | "router" | "vision"
                   | "summarize" | "extract" | "classify"
                   | "research" | "critique" | "analyze" | "code" | "review"
        messages : OpenAI-format list of {"role": ..., "content": ...} dicts
        json_mode: if True, request JSON output and auto-parse it
        trace_id : attach this call to an existing trace

        Returns LLMResponse — always, never raises.
        Check response.ok and response.error for failures.
        """
        role_cfg  = self._get_role(role)
        provider  = self._registry.get(role_cfg.provider)

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
                err     = f"Cannot connect to {cfg.lm_studio_base_url} — is LM Studio running?"
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

            # Retry delay for transient errors
            if attempt < self.MAX_RETRIES:
                time.sleep(self.RETRY_DELAY)

        # Should never reach here
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
        """
        Convenience wrapper that builds the messages list from parts.

        system  : system prompt
        user    : the main instruction / question
        context : background info (injected before user turn as assistant ack)
        content : raw content to process (appended to user turn)
        """
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
        """Quick health check — returns True if the provider is reachable."""
        role_cfg = self._get_role(role)
        provider = self._registry.get(role_cfg.provider)
        return provider.is_available()

    def register_provider(self, name: str, provider: BaseProvider) -> None:
        """
        Register an additional provider (DeepSeek, Claude API, Groq, etc.).

        Example:
            from core.llm import llm, LMStudioProvider
            llm.register_provider("deepseek", LMStudioProvider("https://api.deepseek.com/v1"))
        """
        self._registry.register(name, provider)

    def list_roles(self) -> list[dict]:
        """List all configured roles with their settings."""
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

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_role(self, role: str) -> RoleConfig:
        if role not in self._roles:
            # Unknown role — fall back to executor with a warning
            print(f"[llm] WARNING: unknown role '{role}', falling back to executor")
            return self._roles["executor"]
        return self._roles[role]

    @staticmethod
    def _parse_response(
        raw:       dict,
        role:      str,
        model:     str,
        elapsed:   float,
        json_mode: bool,
    ) -> LLMResponse:
        """Parse raw API response into LLMResponse."""
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
            # Strip markdown fences if model wrapped the JSON
            clean = choice
            for fence in ["```json", "```"]:
                if clean.startswith(fence):
                    clean = clean[len(fence):]
            clean = clean.strip().rstrip("`").strip()
            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                pass  # parsed stays None — caller checks

        return LLMResponse(
            text    = choice,
            role    = role,
            model   = model,
            usage   = usage,
            elapsed = elapsed,
            parsed  = parsed,
            ok      = True,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
llm = LLMClient()
