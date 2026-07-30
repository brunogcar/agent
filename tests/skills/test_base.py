"""Direct tests for skills/_base.py — shared infrastructure.

Tests the make_registry(), auto_discover_modes(), make_route(), and
build_manifest_modes() functions in isolation, without relying on the
11 skills' indirect coverage.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from skills._base import (
    ModeSpec, make_registry, build_manifest_modes, list_modes, get_mode,
    auto_discover_modes, make_route,
)


class TestMakeRegistry:
    """Tests for make_registry() factory."""

    def test_returns_empty_modes_and_callable_register(self):
        """make_registry() returns (dict, callable) — dict starts empty."""
        MODES, register_mode = make_registry()
        assert isinstance(MODES, dict)
        assert len(MODES) == 0
        assert callable(register_mode)

    def test_register_mode_populates_modes(self):
        """@register_mode adds the mode to the MODES dict."""
        MODES, register_mode = make_registry()

        @register_mode("test_mode", description="A test mode")
        def test_mode(company=""):
            return {"status": "ok"}

        assert "test_mode" in MODES
        assert MODES["test_mode"].name == "test_mode"
        assert MODES["test_mode"].description == "A test mode"
        assert callable(MODES["test_mode"].fn)

    def test_duplicate_registration_raises(self):
        """Registering the same mode name twice raises ValueError."""
        MODES, register_mode = make_registry()

        @register_mode("dup_mode")
        def first(company=""):
            return {}

        with pytest.raises(ValueError, match="Duplicate mode registration"):
            @register_mode("dup_mode")
            def second(company=""):
                return {}

    def test_each_registry_is_isolated(self):
        """Two make_registry() calls create independent MODES dicts."""
        MODES1, reg1 = make_registry()
        MODES2, reg2 = make_registry()

        @reg1("mode_a")
        def mode_a():
            return {}

        assert "mode_a" in MODES1
        assert "mode_a" not in MODES2  # isolated

    def test_params_set_cached_at_registration(self):
        """[v1.1] register_mode caches the function's accepted params."""
        MODES, register_mode = make_registry()

        @register_mode("cached")
        def cached(company="", limit=10, consolidado=1):
            return {}

        spec = MODES["cached"]
        assert spec.params_set == {"company", "limit", "consolidado"}


class TestBuildManifestModes:
    """Tests for build_manifest_modes()."""

    def test_empty_registry_returns_empty_dict(self):
        MODES, _ = make_registry()
        assert build_manifest_modes(MODES) == {}

    def test_returns_dict_with_mode_metadata(self):
        MODES, register_mode = make_registry()

        @register_mode("test", description="Test", include_in_all=True,
                       params={"company": "str"}, examples=["skill(...)"])
        def test(company=""):
            return {}

        manifest = build_manifest_modes(MODES)
        assert "test" in manifest
        assert manifest["test"]["description"] == "Test"
        assert manifest["test"]["include_in_all"] is True
        assert manifest["test"]["params"] == {"company": "str"}
        assert manifest["test"]["examples"] == ["skill(...)"]


class TestListModesAndGetMode:
    """Tests for list_modes() and get_mode()."""

    def test_list_modes_returns_sorted_names(self):
        MODES, register_mode = make_registry()

        @register_mode("zebra")
        def z1():
            return {}

        @register_mode("alpha")
        def a1():
            return {}

        assert list_modes(MODES) == ["alpha", "zebra"]

    def test_get_mode_returns_spec_or_none(self):
        MODES, register_mode = make_registry()

        @register_mode("exists")
        def exists():
            return {}

        assert get_mode(MODES, "exists") is not None
        assert get_mode(MODES, "missing") is None


class TestMakeRoute:
    """Tests for make_route() factory."""

    def test_route_dispatches_to_registered_mode(self):
        MODES, register_mode = make_registry()

        @register_mode("echo")
        def echo(company=""):
            return {"status": "ok", "company": company}

        route = make_route("sub_domain", "test_skill", MODES)
        result = route(mode="echo", company="PETR4")
        assert result == {"status": "ok", "company": "PETR4"}

    def test_route_no_mode_returns_error(self):
        MODES, _ = make_registry()
        route = make_route("sub_domain", "test_skill", MODES)
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode_returns_error(self):
        MODES, _ = make_registry()
        route = make_route("sub_domain", "test_skill", MODES)
        result = route(mode="nope")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_filters_unknown_kwargs(self):
        """Unknown kwargs are silently dropped (inspect.signature filtering)."""
        MODES, register_mode = make_registry()

        @register_mode("strict")
        def strict(company=""):
            return {"status": "ok", "company": company}

        route = make_route("sub_domain", "test_skill", MODES)
        # Pass an unknown kwarg — should be filtered, not cause an error
        result = route(mode="strict", company="PETR4", unknown_param="ignored")
        assert result["status"] == "ok"
        assert result["company"] == "PETR4"

    def test_route_catches_exceptions_and_returns_error(self):
        MODES, register_mode = make_registry()

        @register_mode("boom")
        def boom():
            raise RuntimeError("Kaboom!")

        route = make_route("sub_domain", "test_skill", MODES)
        result = route(mode="boom")
        assert result["status"] == "error"
        assert "Kaboom!" in result["error"]
        assert result["sub_domain"] == "test_skill"

    def test_route_accept_sub_domain_true_for_flat_domain(self):
        """investsite-style route accepts sub_domain param (ignored)."""
        MODES, register_mode = make_registry()

        @register_mode("test")
        def test(ticker=""):
            return {"status": "ok", "ticker": ticker}

        route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
        # sub_domain is accepted but ignored
        result = route(sub_domain="ignored", mode="test", ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

    def test_route_error_includes_correct_manifest_key(self):
        """CVM skills use 'sub_domain' in exception errors; investsite uses 'domain'."""
        MODES, register_mode = make_registry()

        @register_mode("boom")
        def boom():
            raise RuntimeError("Kaboom!")

        route_cvm = make_route("sub_domain", "gov", MODES)
        route_flat = make_route("domain", "investsite", MODES, accept_sub_domain=True)

        r1 = route_cvm(mode="boom")
        assert r1["sub_domain"] == "gov"

        r2 = route_flat(mode="boom")
        assert r2["domain"] == "investsite"


class TestAutoDiscoverModes:
    """Tests for auto_discover_modes() — including missing/empty modes/."""

    def test_warns_when_modes_dir_missing(self, monkeypatch, capsys, tmp_path):
        """[v1.1] auto_discover_modes prints a warning when modes/ is missing."""
        # Create a fake package with no modes/ directory
        pkg_name = "_test_skill_no_modes"
        pkg = types.ModuleType(pkg_name)
        pkg.__file__ = str(tmp_path / "fake_init.py")
        monkeypatch.setitem(sys.modules, pkg_name, pkg)

        auto_discover_modes(pkg_name)

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "no modes/ directory" in captured.err

    def test_warns_when_modes_dir_empty(self, monkeypatch, capsys, tmp_path):
        """[v1.1] auto_discover_modes prints a warning when modes/ is empty."""
        pkg_name = "_test_skill_empty_modes"
        pkg = types.ModuleType(pkg_name)
        pkg.__file__ = str(tmp_path / "fake_init.py")
        monkeypatch.setitem(sys.modules, pkg_name, pkg)

        # Create an empty modes/ directory
        modes_dir = tmp_path / "modes"
        modes_dir.mkdir()
        (modes_dir / "__init__.py").write_text("")

        auto_discover_modes(pkg_name)

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "empty" in captured.err
