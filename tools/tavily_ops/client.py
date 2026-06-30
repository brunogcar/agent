from __future__ import annotations
import atexit
import logging

from core.config import cfg
import tools.tavily_ops.state as state

logger = logging.getLogger(__name__)


def _get_singleton_client():
    """Lazy-load AsyncTavilyClient. Keyless if no API key configured."""
    current_key = cfg.tavily_api_key or None
    if state._TAVILY_CLIENT is None or state._TAVILY_CLIENT_KEY != current_key:
        with state._CLIENT_LOCK:
            if state._TAVILY_CLIENT is None or state._TAVILY_CLIENT_KEY != current_key:
                try:
                    from tavily import AsyncTavilyClient
                except ImportError as e:
                    raise ImportError(
                        "tavily-python not installed. Run: pip install tavily-python"
                    ) from e
                state._TAVILY_CLIENT = AsyncTavilyClient(api_key=current_key)
                state._TAVILY_CLIENT_KEY = current_key
    return state._TAVILY_CLIENT


def _close_client():
    """Close the singleton client if it exists. Registered with atexit."""
    if state._TAVILY_CLIENT is not None:
        try:
            if hasattr(state._TAVILY_CLIENT, "close"):
                import asyncio
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    pass
        except Exception:
            pass
        state._TAVILY_CLIENT = None
        state._TAVILY_CLIENT_KEY = None


atexit.register(_close_client)


def _is_keyless() -> bool:
    """Return True if running without an API key."""
    return not bool(cfg.tavily_api_key)


def _warn_keyless_once():
    """Log a single warning when keyless mode is first used."""
    if not state._KEYLESS_WARNED:
        state._KEYLESS_WARNED = True
        logger.warning(
            "Tavily running in keyless mode. Set TAVILY_API_KEY in .env for higher limits."
        )
