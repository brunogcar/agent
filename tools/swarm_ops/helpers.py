"""Shared helpers for swarm actions.

The swarm calls cloud providers DIRECTLY (not through llm.complete()),
because llm.complete() dispatches by role, not by provider. The swarm
needs to call the SAME question on DIFFERENT providers in parallel.

Each provider's chat_completion() returns a dict in OpenAI shape:
  {"choices": [{"message": {"content": "..."}}], "usage": {...}}

So we can extract text the same way for all providers, including the
native AnthropicProvider and GeminiProvider (they normalize to OpenAI shape).
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

# Patterns that may leak secrets into error messages. Applied to str(e) before
# the error is stored in a swarm result dict (which flows into logs + LLM context).
# Gemini puts the API key in the URL query string (?key=...); httpx surfaces the
# full URL in HTTPStatusError. Anthropic/OpenAI use headers and are not affected,
# but we sanitize defensively for all providers.
_SECRET_PATTERNS = [
    # URL query params: ?key=... / &key=... / ?token=... / &api_key=...
    re.compile(r"([?&](?:key|token|api_key|access_token|secret)=)[^&\s]+", re.IGNORECASE),
    # Authorization headers
    re.compile(r"(Authorization\s*:\s*Bearer\s+)[^\s,;\"']+", re.IGNORECASE),
    re.compile(r"(x-api-key\s*:\s*)[^\s,;\"']+", re.IGNORECASE),
    # Bare key=... inside a repr (e.g. {'key': 'AIza...'})
    re.compile(r"(['\"](?:key|token|api_key|access_token|secret)['\"]\s*:\s*['\"])[^'\"]+", re.IGNORECASE),
]


def _sanitize_error(exc: BaseException) -> str:
    """Return a log-safe string representation of an exception.

    Strips API keys / tokens that may appear in URL query strings (Gemini)
    or header reprs. Gemini is the primary motivator: its API key is sent as
    a URL query param (?key=AIzaSy...), and httpx includes the full request
    URL in HTTPStatusError messages. A 429 (common under swarm fan-out) would
    otherwise leak the key into logs + LLM context.
    """
    try:
        msg = str(exc)
    except Exception:
        msg = repr(exc)
    for pat in _SECRET_PATTERNS:
        msg = pat.sub(r"\1<redacted>", msg)
    # Fallback: redact long opaque tokens after a known key name
    msg = re.sub(
        r"((?:key|token|api_key|access_token|secret)['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9_\-]{32,}",
        r"\1<redacted>",
        msg,
        flags=re.IGNORECASE,
    )
    return msg


def _get_available_providers(providers_filter: str = "") -> list[tuple[str, str, Any]]:
    """Get all registered cloud providers with their model names.

    Returns list of (provider_name, model_name, provider_instance).
    Skips 'lmstudio' (local — swarm is for cloud providers only).
    Skips providers without a BASE_MODEL env var.
    """
    from core.llm import llm

    all_providers = []
    for name, provider in llm._registry._providers.items():
        if name == "lmstudio":
            continue
        model = os.getenv(f"{name.upper()}_BASE_MODEL", "")
        if not model:
            continue
        if providers_filter:
            allowed = [p.strip().lower() for p in providers_filter.split(",")]
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
) -> dict:
    """Call a single provider directly. Returns result dict.

    Does NOT go through llm.complete() — calls provider.chat_completion()
    directly. This bypasses role routing, circuit breakers, and rate
    limiting. The swarm handles error/resilience at its own level.

    v1.0.1: Error messages are sanitized via _sanitize_error() before being
    stored. Gemini puts the API key in the URL query string; httpx surfaces
    the full URL in HTTPStatusError. Without sanitization, a 429/5xx from
    Gemini would leak the key into logs + LLM context.
    """
    start = time.time()
    try:
        raw = provider.chat_completion(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            timeout=timeout,
            json_mode=False,
            json_schema=None,
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


def _call_all_providers(
    providers: list[tuple[str, str, Any]],
    system: str,
    user: str,
    context: str,
    timeout: int,
    max_tokens: int,
) -> list[dict]:
    """Call all providers in parallel via ThreadPoolExecutor.

    Returns list of result dicts (one per provider). Failed providers
    have empty text and an error message.
    """
    messages = _build_messages(system, user, context)
    results = []

    with ThreadPoolExecutor(max_workers=min(len(providers), 5)) as executor:
        futures = {}
        for name, model, prov in providers:
            future = executor.submit(
                _call_provider, name, model, prov, messages, timeout, max_tokens
            )
            futures[future] = name

        for future in as_completed(futures, timeout=timeout + 10):
            results.append(_collect_future(future, futures))

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
) -> list[dict]:
    """Call all providers in parallel, return as soon as first valid response.

    v1.0.1: Rewritten to actually return early. The v1.0 implementation used
    `as_completed` + `future.cancel()` + `break`, but ThreadPoolExecutor's
    context-manager `__exit__` calls `shutdown(wait=True)`, which blocked
    until ALL in-flight provider calls finished — making race have the same
    wall-clock latency as consensus. The new implementation uses
    `wait(return_when=FIRST_COMPLETED)` in a loop and
    `shutdown(wait=False, cancel_futures=True)` so the function returns as
    soon as the first valid response lands, without waiting for slower
    providers.

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
                _call_provider, name, model, prov, messages, timeout, max_tokens
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
                    results.append({
                        "provider": name,
                        "model": "",
                        "text": "",
                        "latency": 0,
                        "tokens": 0,
                        "error": "timeout",
                    })
                break

            done, _pending = wait(futures, timeout=remaining, return_when=FIRST_COMPLETED)

            if not done:
                # No future completed in the remaining window — timed out
                for f in list(futures):
                    name = futures.pop(f, "")
                    f.cancel()
                    results.append({
                        "provider": name,
                        "model": "",
                        "text": "",
                        "latency": 0,
                        "tokens": 0,
                        "error": "timeout",
                    })
                break

            for future in done:
                result = _collect_future(future, futures)
                results.append(result)
                if result["text"] and not result["error"] and winner is None:
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
