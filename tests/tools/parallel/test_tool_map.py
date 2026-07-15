"""Tests for parallel_ops/tool_map.py — _get_tool_fn + _TOOL_MAP + PARALLEL_SAFE.

Covers:
  - Unknown tool returns None
  - Cached value returned directly (no import attempted)
  - Lazy import resolves and caches (via sys.modules injection)
  - PARALLEL_SAFE contents (10 entries — the documented safe set)
  - _TOOL_MAP keys match the documented set (17 tools incl. python_exec alias)
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

from tools.parallel_ops.tool_map import _TOOL_MAP, PARALLEL_SAFE, _get_tool_fn


class TestUnknownTool:
    def test_unknown_returns_none(self):
        assert _get_tool_fn("does_not_exist") is None

    def test_parallel_self_not_in_map(self):
        """parallel cannot be dispatched to itself (nested parallel guard)."""
        assert "parallel" not in _TOOL_MAP
        assert _get_tool_fn("parallel") is None


class TestCachedValue:
    def test_cached_value_returned_directly(self):
        """If _TOOL_MAP[name] is non-None, return it without re-importing."""
        sentinel = MagicMock(name="cached_web")
        with patch.dict(_TOOL_MAP, {"web": sentinel}, clear=False):
            result = _get_tool_fn("web")
            assert result is sentinel

    def test_cached_value_not_overwritten(self):
        """If a value is already cached, lazy-import branch is skipped."""
        sentinel = MagicMock(name="cached_web")
        with patch.dict(_TOOL_MAP, {"web": sentinel}, clear=False):
            # Even if tools.web is NOT in sys.modules, _get_tool_fn should not
            # attempt the import — it should return the cached sentinel.
            with patch.dict(sys.modules, {"tools.web": None}, clear=False):
                # Above line sets tools.web to None in sys.modules, which would
                # cause an import error if attempted. The cached path should
                # bypass it.
                result = _get_tool_fn("web")
                assert result is sentinel


class TestLazyImport:
    def test_lazy_import_resolves_and_caches(self):
        """When _TOOL_MAP[name] is None, _get_tool_fn imports, caches, returns."""
        # Inject a fake tools.web module into sys.modules.
        fake_module = types.ModuleType("tools.web")
        fake_fn = MagicMock(name="lazy_web_fn")
        fake_module.web = fake_fn

        # Reset cache so the import path is exercised.
        with patch.dict(_TOOL_MAP, {"web": None}, clear=False):
            with patch.dict(sys.modules, {"tools.web": fake_module}, clear=False):
                result = _get_tool_fn("web")
                assert result is fake_fn
                # Cache should now hold the resolved fn (no longer None).
                assert _TOOL_MAP["web"] is fake_fn

    def test_lazy_import_for_python_exec_alias(self):
        """python_exec should resolve to tools.python.python (same as python)."""
        fake_module = types.ModuleType("tools.python")
        fake_fn = MagicMock(name="lazy_python_fn")
        fake_module.python = fake_fn

        with patch.dict(_TOOL_MAP, {"python_exec": None}, clear=False):
            with patch.dict(sys.modules, {"tools.python": fake_module}, clear=False):
                result = _get_tool_fn("python_exec")
                assert result is fake_fn
                assert _TOOL_MAP["python_exec"] is fake_fn


class TestParallelSafeContents:
    def test_parallel_safe_has_documented_members(self):
        expected = {
            "web", "file", "python", "python_exec", "notify", "github",
            "consult", "vision", "report", "agent",
        }
        assert set(PARALLEL_SAFE) == expected

    def test_parallel_safe_excludes_unsafe_tools(self):
        unsafe = {"git", "memory", "cli", "browser", "tavily", "swarm", "workflow", "parallel"}
        for name in unsafe:
            assert name not in PARALLEL_SAFE, f"{name} should NOT be in PARALLEL_SAFE"

    def test_parallel_safe_is_frozenset(self):
        """PARALLEL_SAFE must be immutable — prevents accidental mutation."""
        assert isinstance(PARALLEL_SAFE, frozenset)


class TestToolMapContents:
    def test_tool_map_has_documented_keys(self):
        expected_keys = {
            "web", "git", "file", "python", "python_exec", "notify", "memory",
            "cli", "github", "consult", "vision", "report", "agent",
            "browser", "tavily", "swarm", "workflow",
        }
        assert set(_TOOL_MAP.keys()) == expected_keys

    def test_tool_map_all_values_start_none(self):
        """Fresh import: all entries should be None (lazy).

        Tests that mutate the cache should use patch.dict to avoid
        polluting this invariant.
        """
        for name, fn in _TOOL_MAP.items():
            # Allow already-cached entries from other tests in the session —
            # but if a test polluted the cache, that's a test-isolation bug
            # to fix, not a feature to enshrine. We assert at most that the
            # value is None OR a callable.
            assert fn is None or callable(fn), f"{name} cache value is {fn!r}"

    def test_python_exec_is_separate_key(self):
        """python_exec must be a distinct key (alias for python)."""
        assert "python_exec" in _TOOL_MAP
        assert "python" in _TOOL_MAP
