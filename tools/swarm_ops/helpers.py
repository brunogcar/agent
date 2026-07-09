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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.contracts import fail, ok

_SWARM_SYSTEM_PROMPT = (
    "You are an expert consultant. Provide a clear, concise, and actionable "
    "answer to the question. Focus on practical solutions and potential pitfalls. "
    "Keep responses structured and easy to read."
)


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
            "error": str(e),
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
            try:
                result = future.result(timeout=timeout + 10)
                results.append(result)
            except Exception as e:
                results.append({
                    "provider": futures[future],
                    "model": "",
                    "text": "",
                    "latency": 0,
                    "tokens": 0,
                    "error": str(e),
                })

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

    Remaining futures are cancelled (best effort). Returns list with at
    least one result (the winner). May include failed results that
    completed before the winner.
    """
    messages = _build_messages(system, user, context)
    results = []
    winner = None

    with ThreadPoolExecutor(max_workers=min(len(providers), 5)) as executor:
        futures = {}
        for name, model, prov in providers:
            future = executor.submit(
                _call_provider, name, model, prov, messages, timeout, max_tokens
            )
            futures[future] = name

        for future in as_completed(futures, timeout=timeout + 10):
            try:
                result = future.result(timeout=timeout + 10)
                results.append(result)
                if result["text"] and not result["error"] and winner is None:
                    winner = result
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    break
            except Exception as e:
                results.append({
                    "provider": futures[future],
                    "model": "",
                    "text": "",
                    "latency": 0,
                    "tokens": 0,
                    "error": str(e),
                })

    return results
