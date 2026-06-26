"""LM Studio management proxy for cli meta-tool.

Provides raw HTTP access to LM Studio API for model management.
All functions auto-register via @register_action decorator.

NOTE: The LM Studio base URL is hardcoded to http://localhost:1234.
There is currently no env var or config override. If LM Studio runs
on a different port or host, this module must be updated.
Future AIs: consider adding cfg.lms_base_url before changing the
hardcoded value.
"""
from __future__ import annotations

from tools.cli_ops._registry import register_action

# Hardcoded LM Studio API endpoint. See module docstring for rationale.
_LMS = "http://localhost:1234"


@register_action(
    "lms", "ls",
    help_text="List downloaded models (shortcut: 'lms ls').",
    examples=["lms ls"],
)
def _lms_ls(action: str = "", **params) -> str:
    """List downloaded models."""
    import requests
    try:
        r = requests.get(f"{_LMS}/api/v0/models", timeout=5)
        r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json()]
        return "\n".join(f" • {m}" for m in ms) if ms else "No downloaded models."
    except Exception as e:
        return f"LM Studio error: {e}"


@register_action(
    "lms", "ps",
    help_text="List loaded models (shortcut: 'lms ps').",
    examples=["lms ps"],
)
def _lms_ps(action: str = "", **params) -> str:
    """List loaded models."""
    import requests
    try:
        r = requests.get(f"{_LMS}/v1/models", timeout=5)
        r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json().get("data", [])]
        return "\n".join(f" • {m}" for m in ms) if ms else "No models loaded."
    except Exception as e:
        return f"LM Studio error: {e}"


@register_action(
    "lms", "load",
    help_text="Load a model (shortcut: 'lms load <model>').",
    examples=["lms load my-model"],
)
def _lms_load(action: str = "", model: str = "", **params) -> str:
    """Load a model."""
    import requests
    try:
        r = requests.post(
            f"{_LMS}/v1/models/load",
            json={"model": model},
            timeout=10,
        )
        r.raise_for_status()
        return f"Loaded: {model}"
    except Exception as e:
        return f"LM Studio error: {e}"


@register_action(
    "lms", "unload",
    help_text="Unload a model or all models (shortcut: 'lms unload [model]').",
    examples=["lms unload my-model", "lms unload"],
)
def _lms_unload(action: str = "", model: str = "", **params) -> str:
    """Unload a model or all models."""
    import requests
    try:
        r = requests.post(
            f"{_LMS}/v1/models/unload",
            json={"model": model} if model else {},
            timeout=10,
        )
        r.raise_for_status()
        return f"Unloaded: {model or 'all models'}"
    except Exception as e:
        return f"LM Studio error: {e}"


@register_action(
    "lms", "log",
    help_text="Get LM Studio logs (shortcut: 'lms log').",
    examples=["lms log"],
)
def _lms_log(action: str = "", **params) -> str:
    """Get LM Studio logs."""
    import requests
    try:
        r = requests.get(f"{_LMS}/api/v0/log", timeout=5)
        r.raise_for_status()
        return r.text[-2000:] if len(r.text) > 2000 else r.text
    except Exception as e:
        return f"LM Studio error: {e}"
