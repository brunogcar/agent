"""Shared helpers for swarm actions.

The swarm calls cloud providers DIRECTLY (not through llm.complete()),
because llm.complete() dispatches by role, not by provider. The swarm
needs to call the SAME question on DIFFERENT providers in parallel.

Each provider's chat_completion() returns a dict in OpenAI shape:
  {"choices": [{"message": {"content": "..."}}], "usage": {...}}

So we can extract text the same way for all providers, including the
native AnthropicProvider and GeminiProvider (they normalize to OpenAI shape).

v1.0.1: Added _sanitize_error() (P1-1), rewrote _call_providers_race (P1-2).
v1.0.2: Hardened _call_all_providers timeout/shutdown (P1-1 cross-LLM),
        fixed race done-future loss (P1-2 cross-LLM), guarded _sanitize_error
        against self-raise (P1-4 cross-LLM), broadened sanitize patterns
        (P2-1 cross-LLM), snapshot provider dict (P2-2), cleaned provider
        filter (P2-3 cross-LLM).
"""
from __future__ import annotations

import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from typing import Any

from core.contracts import fail, ok

_SWARM_SYSTEM_PROMPT = (
    "You are an expert consultant. Provide a clear, concise, and actionable "
    "answer to the question. Focus on practical solutions and potential pitfalls. "
    "Keep responses structured and easy to read."
)

# v1.0.2 (P2-1 cross-LLM): Broadened secret-redaction patterns.
# v1.0.1 covered: URL query params (?key=...), Authorization: Bearer, x-api-key,
# dict reprs ('key': '...'). v1.0.2 adds: camelCase JSON keys (apiKey, accessToken),
# hyphenated (api-key), bare-in-prose provider prefixes (AIzaSy..., sk-ant-..., sk-...),
# and base64-friendly fallback chars (+, /, =).
_SECRET_PATTERNS = [
    # URL query params: ?key=... / &token=... / ?api_key=... / &api-key=... / &apikey=...
    # v1.0.2 (P2-1): includes bare 'key' (Gemini uses ?key=...), api_key, api-key,
    # apikey, token, access_token, access-token, secret.
    re.compile(r"([?&](?:key|api[-_]?key|apikey|token|access[-_]?token|secret)=)[^&\s]+", re.IGNORECASE),
    # Authorization headers (Bearer / token / basic)
    re.compile(r"(Authorization\s*:\s*(?:Bearer|Token|Basic)\s+)[^\s,;\"']+", re.IGNORECASE),
    re.compile(r"(x-api-key\s*:\s*)[^\s,;\"']+", re.IGNORECASE),
    # Dict/JSON reprs: 'key': '...', "apiKey": "...", "access_token": "..."
    # (covers snake_case, camelCase, and hyphenated key names inside quotes)
    re.compile(r"(['\"](?:key|api[-_]?key|apikey|token|access[-_]?token|secret)['\"]\s*:\s*['\"])[^'\"]+", re.IGNORECASE),
]

# v1.0.2 (P2-1 cross-LLM): Provider-specific key prefixes — catch bare keys in prose
# (e.g., "Authentication failed with API key AIzaSyD..."). These prefixes are
# highly specific to each provider and virtually never appear in non-secret contexts.
_PROVIDER_KEY_PREFIXES = [
    re.compile(r"(AIzaSy)[A-Za-z0-9_\-]{30,}"),          # Google/Gemini
    re.compile(r"(sk-ant-)[A-Za-z0-9_\-]{20,}"),          # Anthropic
    re.compile(r"(sk-)[A-Za-z0-9]{20,}"),                 # OpenAI (sk-... but not sk-ant-)
]

# v1.0.2 (P2-1 cross-LLM): Fallback for unknown key formats after a key-like label.
# Broadened from [A-Za-z0-9_\-]{32,} to include base64 chars (+, /, =) and lowered
# to {16,} to catch shorter keys (some providers issue 20-28 char keys).
_KEY_VALUE_FALLBACK = re.compile(
    r"((?:api[-_]?key|token|access[-_]?token|secret|apikey)['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9_\-+/=]{16,}",
    re.IGNORECASE,
)


def _sanitize_error(exc: BaseException) -> str:
    """Return a log-safe string representation of an exception.

    Strips API keys / tokens that may appear in URL query strings (Gemini),
    header reprs, JSON bodies, or bare in prose. Gemini is the primary
    motivator: its API key is sent as a URL query param (?key=AIzaSy...),
    and httpx includes the full request URL in HTTPStatusError messages.

    v1.0.2 (P1-4 cross-LLM): Wrapped in try/except so a pathological exception
    whose str() AND repr() both raise cannot crash this function. Previously,
    such an exception would propagate out of _collect_future and break
    per-provider error isolation.
    """
    try:
        try:
            msg = str(exc)
        except Exception:
            msg = repr(exc)
        for pat in _SECRET_PATTERNS:
            msg = pat.sub(r"\1<redacted>", msg)
        for pat in _PROVIDER_KEY_PREFIXES:
            msg = pat.sub(r"\1<redacted>", msg)
        msg = _KEY_VALUE_FALLBACK.sub(r"\1<redacted>", msg)
        return msg
    except Exception:
        # Last resort — never let sanitization itself crash the action.
        return f"<unstringifiable {type(exc).__name__}>"


def _get_available_providers(providers_filter: str = "") -> list[tuple[str, str, Any]]:
    """Get all registered cloud providers with their model names.

    Returns list of (provider_name, model_name, provider_instance).
    Skips 'lmstudio' (local — swarm is for cloud providers only).
    Skips providers without a BASE_MODEL env var.

    v1.0.2 (P2-2 cross-LLM): Snapshots the providers dict before iterating
    to avoid `RuntimeError: dictionary changed size during iteration` if a
    provider is registered concurrently.
    v1.0.2 (P2-3 cross-LLM): Cleans the providers filter — drops empty entries
    and duplicates. Unknown names are silently skipped (documented); callers
    can use list_providers to discover valid names.
    """
    from core.llm import llm

    all_providers = []
    # P2-2: snapshot to avoid mutation-during-iteration race
    for name, provider in list(llm._registry._providers.items()):
        if name == "lmstudio":
            continue
        model = os.getenv(f"{name.upper()}_BASE_MODEL", "")
        if not model:
            continue
        if providers_filter:
            # P2-3: filter empties + dedupe (preserve order)
            allowed = []
            seen = set()
            for p in providers_filter.split(","):
                clean = p.strip().lower()
                if clean and clean not in seen:
                    allowed.append(clean)
                    seen.add(clean)
            if name not in allowed:
                continue
        all_providers.append((name, model, provider))
    return all_providers


def _build_messages(system: str, user: str, context: str = "") -> list[dict]:
    """Build OpenAI-style messages from system/user/context."""
    messages = [{"role": "system", "content": system}]
    if context:
        messages.append({"role": "user", "content": f"Background:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": user})
    return messages


def _call_provider(
    provider_name: str,
    model: str,
    provider: Any,
    messages: list[dict],
    timeout: int,
    max_tokens: int,
    temperature: float = 0.7,
    json_mode: bool = False,
    json_schema: dict | None = None,
) -> dict:
    """Call a single provider directly. Returns result dict.

    v1.3 (#22): Now delegates to ``llm.complete_provider()`` instead of
    calling ``provider.chat_completion()`` directly. This gives swarm the
    same registry plumbing that role-routed calls get:
      - Circuit breaker (per-provider-name, fail-fast on 3 cumulative failures)
      - Telemetry (tracer.step / tracer.error)
      - Defensive JSON parsing (_parse_response)
      - v1.3 (#43): post-parse enum validation
      - Context budgeting (budget_messages)
    All for free — no duplicated invocation logic.

    The provider and messages args are kept in the signature for backward
    compatibility with the existing _call_all_providers / _call_providers_race
    call sites. They are still used as a fallback if complete_provider is
    unavailable (e.g. in unit tests that patch llm with a MagicMock that
    doesn't expose complete_provider — those keep using direct
    chat_completion). Production path is complete_provider.

    Return shape is unchanged: dict with ``provider``, ``model``, ``text``,
    ``latency``, ``tokens``, ``error`` keys. The error message is still
    sanitized via ``_sanitize_error()`` (the sanitization logic stays in
    swarm — complete_provider returns LLMResponse objects whose .error
    field is built by us from the exception, so we sanitize it ourselves
    before storing in the result dict).

    v1.0.1: Error messages sanitized via _sanitize_error() before storing.
    v1.0.2: _sanitize_error() is now self-guarded (P1-4) and broader (P2-1).
    v1.1 (#21): temperature, json_mode, json_schema params added (was hardcoded
    temperature=0.7, json_mode=False, json_schema=None). Callers can now
    request deterministic output (temperature=0) and structured output
    (json_schema). Native json_schema for Claude/Gemini is now implemented
    at the provider layer (v1.3 #39+#40) — no changes needed here.
    """
    from core.llm import llm

    start = time.time()
    # Reconstruct system/user/context from the messages list so we can use
    # llm.complete_provider()'s convenience signature. The messages list is
    # already in OpenAI shape ([{"role": "system", "content": "..."},
    # {"role": "user", "content": "..."}]) — we extract the first system
    # message and concatenate the rest as the user turn.
    system_text = ""
    user_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_text += content + "\n"
        elif role == "assistant":
            # Swarm's _build_messages inserts an "Understood." ack after
            # context. Preserve it as part of the user turn (the provider
            # doesn't need to see it as a separate assistant message —
            # complete_provider builds its own messages list).
            user_parts.append(f"(ack: {content})")
        else:
            user_parts.append(content)

    user_text = "\n".join(p for p in user_parts if p).strip()
    trace_id = f"swarm:{provider_name}"

    try:
        # Prefer the new complete_provider() path (v1.3 #22). It threads
        # through circuit breakers, telemetry, and post-parse enum validation.
        # Wrap in its own try/except so ANY failure (provider not registered,
        # mock returning non-LLMResponse, etc.) falls through to the direct
        # provider.chat_completion() path — which is what unit tests mock.
        use_complete_provider = False
        try:
            complete_provider = getattr(llm, "complete_provider", None)
            if callable(complete_provider):
                response = complete_provider(
                    provider_name=provider_name,
                    system=system_text.strip(),
                    user=user_text,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    json_mode=json_mode,
                    json_schema=json_schema,
                    trace_id=trace_id,
                )
                # Guard: verify this is a real LLMResponse, not a MagicMock.
                if isinstance(getattr(response, "text", None), str) and isinstance(getattr(response, "ok", None), bool):
                    use_complete_provider = True
                    latency = round(time.time() - start, 2)
                    if response.ok:
                        usage = response.usage or {}
                        return {
                            "provider": provider_name,
                            "model": response.model or model,
                            "text": response.text,
                            "latency": response.elapsed or latency,
                            "tokens": usage.get("total", 0),
                            "error": "",
                        }
                    else:
                        return {
                            "provider": provider_name,
                            "model": response.model or model,
                            "text": "",
                            "latency": response.elapsed or latency,
                            "tokens": 0,
                            "error": _sanitize_error(Exception(response.error)),
                        }
        except Exception:
            pass  # fall through to direct provider call

        if not use_complete_provider:
            # Fallback: direct provider.chat_completion() (pre-v1.3 path).
            # Used if complete_provider isn't available, returned a non-LLMResponse
            # (unit-test mocks), or raised an exception (provider not registered).
            raw = provider.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                json_mode=json_mode,
                json_schema=json_schema,
            )
            text = ""
            choices = raw.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")
            latency = round(time.time() - start, 2)
            usage = raw.get("usage", {})
            return {
                "provider": provider_name,
                "model": model,
                "text": text,
                "latency": latency,
                "tokens": usage.get("total_tokens", 0),
                "error": "",
            }
    except Exception as e:
        latency = round(time.time() - start, 2)
        return {
            "provider": provider_name,
            "model": model,
            "text": "",
            "latency": latency,
            "tokens": 0,
            "error": _sanitize_error(e),
        }


def _collect_future(future, futures_map: dict) -> dict:
    """Collect a completed future into a result dict, popping it from the map.

    Shared by _call_all_providers and _call_providers_race. Never raises —
    a future that raised is recorded as an error result for that provider.
    The future MUST already be done when called (callers guarantee this via
    as_completed or the `done` set from wait()).
    """
    name = futures_map.pop(future, "")
    try:
        return future.result()
    except Exception as e:
        return {
            "provider": name,
            "model": "",
            "text": "",
            "latency": 0,
            "tokens": 0,
            "error": _sanitize_error(e),
        }


def _timeout_result(name: str) -> dict:
    """Build a standardized timeout error result for a provider."""
    return {
        "provider": name,
        "model": "",
        "text": "",
        "latency": 0,
        "tokens": 0,
        "error": "timeout",
    }


def _call_all_providers(
    providers: list[tuple[str, str, Any]],
    system: str,
    user: str,
    context: str,
    timeout: int,
    max_tokens: int,
    temperature: float = 0.7,
    json_mode: bool = False,
    json_schema: dict | None = None,
) -> list[dict]:
    """Call all providers in parallel via ThreadPoolExecutor.

    Returns list of result dicts (one per provider). Failed providers
    have empty text and an error message.

    v1.0.2 (P1-1 cross-LLM): Rewrote to mirror _call_providers_race's
    shutdown pattern. The v1.0.1 implementation still used
    `with ThreadPoolExecutor(...)` + `as_completed(timeout=...)`. If
    as_completed raised TimeoutError, the `with` block's __exit__ called
    shutdown(wait=True), blocking forever on a hanging provider. This
    affected consensus, vote, and compare (3 of 5 actions). The new
    implementation uses an explicit executor + try/except TimeoutError +
    finally: shutdown(wait=False, cancel_futures=True), so a misbehaving
    provider can no longer deadlock the swarm.
    """
    messages = _build_messages(system, user, context)
    results: list[dict] = []

    executor = ThreadPoolExecutor(max_workers=min(len(providers), 5))
    try:
        futures = {}
        for name, model, prov in providers:
            future = executor.submit(
                _call_provider, name, model, prov, messages, timeout, max_tokens,
                temperature, json_mode, json_schema
            )
            futures[future] = name

        try:
            for future in as_completed(futures, timeout=timeout + 10):
                results.append(_collect_future(future, futures))
        except TimeoutError:
            # as_completed timed out — collect any done futures we missed,
            # then mark all remaining as timed out.
            for f in list(futures):
                if f.done() and not f.cancelled():
                    results.append(_collect_future(f, futures))
                else:
                    name = futures.pop(f, "")
                    f.cancel()
                    results.append(_timeout_result(name))
    finally:
        # Same pattern as _call_providers_race: don't block on in-flight calls.
        executor.shutdown(wait=False, cancel_futures=True)

    # Sort by provider name for deterministic output
    results.sort(key=lambda r: r["provider"])
    return results


def _call_providers_race(
    providers: list[tuple[str, str, Any]],
    system: str,
    user: str,
    context: str,
    timeout: int,
    max_tokens: int,
    temperature: float = 0.7,
    json_mode: bool = False,
    json_schema: dict | None = None,
) -> list[dict]:
    """Call all providers in parallel, return as soon as first valid response.

    v1.0.1: Rewrote to actually return early (was blocked on shutdown(wait=True)).
    v1.0.2 (P1-2 cross-LLM): Fixed done-future loss. The v1.0.1 inner loop
    `for future in done:` broke on the first winner, discarding any sibling
    futures in `done` (already completed but never collected). Now collects
    ALL done futures first, then checks for winner outside the inner loop.

    Returns a list with the winner first, followed by any providers that
    completed *before* the winner (e.g. failed fast). Late providers are
    cancelled (best effort — cancel_futures only cancels PENDING futures;
    running futures continue in the background but their results are
    discarded via wait=False).
    """
    messages = _build_messages(system, user, context)
    results: list[dict] = []

    executor = ThreadPoolExecutor(max_workers=min(len(providers), 5))
    try:
        futures = {}
        for name, model, prov in providers:
            future = executor.submit(
                _call_provider, name, model, prov, messages, timeout, max_tokens,
                temperature, json_mode, json_schema
            )
            futures[future] = name

        deadline = time.monotonic() + timeout + 10
        winner = None

        while futures and winner is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Timed out — record remaining futures as timeouts
                for f in list(futures):
                    name = futures.pop(f, "")
                    f.cancel()
                    results.append(_timeout_result(name))
                break

            done, _pending = wait(futures, timeout=remaining, return_when=FIRST_COMPLETED)

            if not done:
                # No future completed in the remaining window — timed out
                for f in list(futures):
                    name = futures.pop(f, "")
                    f.cancel()
                    results.append(_timeout_result(name))
                break

            # v1.0.2 (P1-2 cross-LLM): Collect ALL done futures BEFORE checking
            # for winner. The v1.0.1 code broke inside this loop on the first
            # winner, discarding sibling done futures (already completed but
            # never collected into results).
            for future in done:
                results.append(_collect_future(future, futures))

            # Now check if any of the collected results is a winner
            for result in results:
                if result["text"].strip() and not result["error"] and winner is None:
                    winner = result
                    # Cancel remaining (not-yet-started) futures and stop waiting.
                    for f in list(futures):
                        f.cancel()
                    futures.clear()
                    break
    finally:
        # cancel_futures=True (Python 3.9+) cancels PENDING futures; wait=False
        # returns immediately without blocking on in-flight HTTP calls. Running
        # futures complete in the background; their results are discarded.
        executor.shutdown(wait=False, cancel_futures=True)

    # Preserve insertion order (winner first). Do NOT sort — race semantics
    # require "who won" ordering (see INSTRUCTIONS.md #8).
    return results
