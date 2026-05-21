"""
lms.py — LM Studio management actions for cli meta-tool.

Provides raw HTTP access to LM Studio API for model management.
All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

import requests

from tools.cli_ops.actions._registry import register_action

_LMS = "http://localhost:1234"

@register_action("lms", "ls")
def _lms_ls() -> str:
    """List downloaded models."""
    try:
        r = requests.get(f"{_LMS}/api/v0/models", timeout=5)
        r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json()]
        return "\n".join(f" • {m}" for m in ms) if ms else "No downloaded models."
    except Exception as e:
        return f"LM Studio error: {e}"

@register_action("lms", "ps")
def _lms_ps() -> str:
    """List loaded models."""
    try:
        r = requests.get(f"{_LMS}/v1/models", timeout=5)
        r.raise_for_status()
        ms = [m.get("id") or str(m) for m in r.json().get("data", [])]
        return "\n".join(f" • {m}" for m in ms) if ms else "No models loaded."
    except Exception as e:
        return f"LM Studio error: {e}"

@register_action("lms", "load")
def _lms_load(model: str) -> str:
    """Load a model."""
    try:
        r = requests.post(
            f"{_LMS}/v1/models/load",
            json={"model": model},
            timeout=10
        )
        r.raise_for_status()
        return f"Loaded: {model}"
    except Exception as e:
        return f"LM Studio error: {e}"

@register_action("lms", "unload")
def _lms_unload(model: str = "") -> str:
    """Unload a model or all models."""
    try:
        r = requests.post(
            f"{_LMS}/v1/models/unload",
            json={"model": model} if model else {},
            timeout=10
        )
        r.raise_for_status()
        return f"Unloaded: {model or 'all models'}"
    except Exception as e:
        return f"LM Studio error: {e}"

@register_action("lms", "log")
def _lms_log() -> str:
    """Get LM Studio logs."""
    try:
        r = requests.get(f"{_LMS}/api/v0/log", timeout=5)
        r.raise_for_status()
        return r.text[-2000:] if len(r.text) > 2000 else r.text
    except Exception as e:
        return f"LM Studio error: {e}"