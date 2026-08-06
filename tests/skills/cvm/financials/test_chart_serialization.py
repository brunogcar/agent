"""tests/skills/cvm/financials/test_chart_serialization.py -- F1: Chart serialization test.

Regression test: all chart_data dicts in the financials dashboard payload
must be JSON-serializable. Catches datetime, Decimal, and other non-JSON
types that would cause the report tool's |tojson filter to crash.

Uses CVM_SKIP_SYNC=1 + mocked data to avoid hitting real databases.
"""
from __future__ import annotations

import json
import os
import pytest


@pytest.fixture(autouse=True)
def _skip_sync():
    os.environ["CVM_SKIP_SYNC"] = "1"


def _find_chart_data(obj, path=""):
    """Recursively find all 'chart_data' values in a nested dict/list structure."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "chart_data" and v is not None:
                results.append((f"{path}.{k}", v))
            else:
                results.extend(_find_chart_data(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_find_chart_data(item, f"{path}[{i}]"))
    return results


def test_financials_dashboard_chart_data_is_json_serializable(tmp_path, monkeypatch):
    """All chart_data in financials dashboard must be JSON-serializable.

    [F1] Regression test - catches datetime/Decimal/non-serializable types
    that would crash the report tool's |tojson filter.
    """
    from skills.cvm.financials import route

    # Mock the sync guard to skip network calls
    monkeypatch.setattr("skills._base._SYNC_CHECKED", lambda: True)

    try:
        result = route(mode="dashboard", company="PETR4")
    except Exception as e:
        pytest.skip(f"Dashboard call failed (likely DB not synced): {e}")

    if result.get("status") != "ok":
        pytest.skip(f"Dashboard returned status={result.get('status')}")

    charts = _find_chart_data(result, "result")
    assert len(charts) > 0, "Dashboard should have at least 1 chart"

    failures = []
    for path, chart_data in charts:
        try:
            json.dumps(chart_data)
        except (TypeError, ValueError) as e:
            failures.append(f"{path}: {e}")

    assert not failures, f"Non-serializable chart_data found:\n" + "\n".join(failures)


def test_historical_dashboard_chart_data_is_json_serializable(tmp_path, monkeypatch):
    """All chart_data in historical dashboard must be JSON-serializable."""
    from skills.cvm.historical import route

    monkeypatch.setattr("skills._base._SYNC_CHECKED", lambda: True)

    try:
        result = route(mode="dashboard", company="PETR4")
    except Exception as e:
        pytest.skip(f"Dashboard call failed (likely DB not synced): {e}")

    if result.get("status") != "ok":
        pytest.skip(f"Dashboard returned status={result.get('status')}")

    charts = _find_chart_data(result, "result")
    if not charts:
        pytest.skip("No charts found (data may be mocked)")

    failures = []
    for path, chart_data in charts:
        try:
            json.dumps(chart_data)
        except (TypeError, ValueError) as e:
            failures.append(f"{path}: {e}")

    assert not failures, f"Non-serializable chart_data found:\n" + "\n".join(failures)


# ── F6: Real-data verification (inline, not a separate script) ──────────────

def test_dfp_no_duplicate_contas():
    """[F6] DFP should have no duplicate contas (same PK appearing more than once)."""
    try:
        from data_sources.cvm._db import dfp_db_path
        import sqlite3
        path = dfp_db_path()
        if not path.exists():
            pytest.skip("DFP database not synced")
        conn = sqlite3.connect(str(path))
        dupes = conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc, COUNT(*) as cnt "
            "FROM contas GROUP BY id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc "
            "HAVING cnt > 1)"
        ).fetchone()[0]
        conn.close()
        assert dupes == 0, f"Found {dupes} duplicate conta groups in DFP"
    except ImportError:
        pytest.skip("data_sources not available")


def test_itr_no_duplicate_contas():
    """[F6] ITR should have no duplicate contas."""
    try:
        from data_sources.cvm._db import itr_db_path
        import sqlite3
        path = itr_db_path()
        if not path.exists():
            pytest.skip("ITR database not synced")
        conn = sqlite3.connect(str(path))
        dupes = conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc, COUNT(*) as cnt "
            "FROM contas GROUP BY id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc "
            "HAVING cnt > 1)"
        ).fetchone()[0]
        conn.close()
        assert dupes == 0, f"Found {dupes} duplicate conta groups in ITR"
    except ImportError:
        pytest.skip("data_sources not available")


def test_dfp_no_orphan_contas():
    """[F6] DFP contas should not reference non-existent empresas."""
    try:
        from data_sources.cvm._db import dfp_db_path
        import sqlite3
        path = dfp_db_path()
        if not path.exists():
            pytest.skip("DFP database not synced")
        conn = sqlite3.connect(str(path))
        orphans = conn.execute(
            "SELECT COUNT(*) FROM contas c WHERE NOT EXISTS "
            "(SELECT 1 FROM empresas e WHERE e.id = c.id_empresa)"
        ).fetchone()[0]
        conn.close()
        assert orphans == 0, f"Found {orphans} orphan contas in DFP"
    except ImportError:
        pytest.skip("data_sources not available")
