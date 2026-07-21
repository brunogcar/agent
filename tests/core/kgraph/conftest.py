"""Shared fixtures for kgraph-module tests.

[v1.4.2] Provides a `mocker` fixture as a lightweight shim for pytest-mock.

The moved test files (test_embeddings.py, test_tree_sitter_parser.py) were
written against pytest-mock's `mocker` fixture. pytest-mock isn't installed
in this environment, so those tests errored at fixture-resolution time.

Rather than rewrite every test to use `unittest.mock.patch` with `with`
blocks (which changes the test style significantly), this conftest provides
a minimal `mocker` fixture that wraps `unittest.mock` and auto-stops all
patches at the end of the test. Mirrors the shim in
`tests/workflows/understand/conftest.py`.

The shim supports:
  - mocker.patch(target, **kwargs)         → unittest.mock.patch
  - mocker.patch.object(obj, attr, **kw)   → unittest.mock.patch.object
  - mocker.MagicMock(**kwargs)             → unittest.mock.MagicMock
  - mocker.Mock(**kwargs)                  → unittest.mock.Mock
  - mocker.stopall()                       → stop all patches started via mocker

It does NOT support mocker.spy (rarely used; not needed by these tests).
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest import mock


class _MockerShim:
    """Minimal pytest-mock-compatible mocker shim backed by unittest.mock.

    Tracks every patch started via .patch() / .patch.object() so they can
    be stopped automatically when the fixture is torn down.
    """

    def __init__(self):
        self._patches: list = []
        self._mocks: list = []

        # Build a `patch` callable that ALSO exposes `patch.object`.
        # Can't just assign self.patch = mock.patch because methods don't
        # have a settable .object attribute. Use a closure + setattr.
        outer = self

        def _patch(target, *args, **kwargs):
            p = mock.patch(target, *args, **kwargs)
            started = p.start()
            outer._patches.append(p)
            outer._mocks.append(started)
            return started

        def _patch_object(target, attribute, *args, **kwargs):
            p = mock.patch.object(target, attribute, *args, **kwargs)
            started = p.start()
            outer._patches.append(p)
            outer._mocks.append(started)
            return started

        _patch.object = _patch_object
        self.patch = _patch

    def MagicMock(self, *args, **kwargs):
        m = mock.MagicMock(*args, **kwargs)
        self._mocks.append(m)
        return m

    def Mock(self, *args, **kwargs):
        m = mock.Mock(*args, **kwargs)
        self._mocks.append(m)
        return m

    def stopall(self):
        while self._patches:
            p = self._patches.pop()
            try:
                p.stop()
            except RuntimeError:
                pass  # already stopped
        self._mocks.clear()

    def teardown(self):
        self.stopall()


@pytest.fixture
def mocker():
    """[v1.4.2] pytest-mock-compatible mocker shim (mirrors understand conftest)."""
    shim = _MockerShim()
    yield shim
    shim.teardown()
