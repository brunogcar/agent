"""Smoke test: verify _cache.py imports correctly + cache round-trip works.

Catches the "import json missing" bug class that has hit us TWICE (v1.10 and
v1.25). The _StrictJSONEncoder class references json.JSONEncoder, but if
import json is missing from the module top, the class definition fails with
NameError. The @engine_cached decorator catches this silently (except: pass),
disabling the entire engine cache — no DB created, no cross-run caching.
"""
import os
import tempfile
import pytest


def test_cache_module_imports():
    """Verify _cache.py loads without missing imports."""
    from data_sources import _cache
    assert hasattr(_cache, 'is_enabled')
    assert hasattr(_cache, 'get_cached')
    assert hasattr(_cache, 'set_cached')
    assert hasattr(_cache, '_StrictJSONEncoder')


def test_strict_json_encoder_roundtrip():
    """Verify _StrictJSONEncoder works for periods data."""
    import json
    from data_sources._cache import _StrictJSONEncoder

    test_data = [
        {"date": "2024-12-31", "value": 100.5},
        {"date": "2025-03-31", "value": None},
    ]
    encoded = json.dumps(test_data, cls=_StrictJSONEncoder)
    decoded = json.loads(encoded)
    assert decoded == test_data


def test_cache_roundtrip(tmp_path, monkeypatch):
    """Verify cache write + read round-trip works (creates DB file)."""
    # Point cache at a temp directory
    monkeypatch.setenv("CVM_SKIP_DB_CACHE", "0")

    from data_sources import _cache

    # Mock the cache_data_dir to use tmp_path
    monkeypatch.setattr(_cache, "cache_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_cache, "db_path", lambda: tmp_path / "engine_cache.db")

    # Mock resolve_cnpj to return a fixed CNPJ
    monkeypatch.setattr(_cache, "resolve_cnpj", lambda c: "33000167000101")

    # Mock get_current_fingerprint to return a fixed value
    monkeypatch.setattr(_cache, "get_current_fingerprint", lambda e, c: "test_fp")

    # Write a value
    _cache.set_cached("test_engine", "PETR4", "2024-12-31", 42.5)

    # Read it back
    result = _cache.get_cached("test_engine", "PETR4", "2024-12-31")
    assert result is not None
    assert result["value"] == 42.5

    # Verify DB file was created
    db_file = tmp_path / "engine_cache.db"
    assert db_file.exists()
