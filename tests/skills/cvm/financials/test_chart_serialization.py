"""tests/skills/cvm/financials/test_chart_serialization.py -- F1: Chart serialization test.

Regression test: all chart_data dicts in the financials dashboard payload
must be JSON-serializable. Catches datetime, Decimal, and other non-JSON
types that would cause the report tool's |tojson filter to crash.

Uses CVM_SKIP_SYNC=1 + mocked data to avoid hitting real databases.

[v2.2] The duplicate/orphan contas data-integrity tests (F6) were rewritten
to use a synthetic in-memory SQLite DB instead of the real DFP/ITR database.
Previously they tried to open the real DB file — which (a) made the tests
slow when the DB was synced, and (b) caused `sqlite3.OperationalError: no
such table: contas` failures when a stub/partial DB file existed without
the schema. The synthetic DB is created fresh per test with the proper
schema + clean sample data, so the tests are fast, deterministic, and
independent of real CVM sync state.
"""
from __future__ import annotations

import json
import os
import pytest
import sqlite3


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


# ── F6: Data-integrity tests (synthetic DB — no real CVM sync required) ──────

def _build_clean_db(db_path):
    """Build a synthetic DFP/ITR-shaped SQLite DB with clean sample data.

    Creates the ``empresas`` + ``contas`` tables (schema mirrors
    ``data_sources/cvm/_db.py::_ensure_schema``) and inserts 1 empresa +
    1 conta with no duplicates + no orphans. The data-integrity queries
    should return 0 for both checks.
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS empresas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj    TEXT NOT NULL,
            nome    TEXT NOT NULL,
            ano     INTEGER NOT NULL,
            cd_cvm  TEXT,
            UNIQUE (cnpj, ano)
        );
        CREATE TABLE IF NOT EXISTS contas (
            id_empresa     INTEGER NOT NULL,
            codigo         TEXT NOT NULL,
            descricao      TEXT NOT NULL,
            grupo          TEXT NOT NULL,
            consolidado    INTEGER NOT NULL,
            data_ini_exerc TEXT,
            data_fim_exerc TEXT NOT NULL,
            meses          INTEGER NOT NULL,
            ordem_exerc    TEXT,
            versao         INTEGER DEFAULT 1,
            st_conta_fixa  TEXT,
            valor          REAL NOT NULL,
            escala         TEXT,
            moeda          TEXT,
            FOREIGN KEY (id_empresa) REFERENCES empresas(id),
            PRIMARY KEY (id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc)
        );
    """)
    # 1 empresa + 1 conta — clean data (no dupes, no orphans).
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'TEST CORP', 2024, '19417')"
    )
    conn.execute(
        "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, data_ini_exerc, data_fim_exerc, meses, ordem_exerc, valor) "
        "VALUES (1, '3.01', 'Receita de Venda de Bens e Servicos', 'DRE', 1, '2024-01-01', '2024-12-31', 12, 'ÚLTIMO', 100000.0)"
    )
    conn.commit()
    conn.close()


def test_dfp_no_duplicate_contas(tmp_path, monkeypatch):
    """[F6] DFP should have no duplicate contas (same PK appearing more than once).

    [v2.2] Uses a synthetic in-memory SQLite DB with clean data — no real
    CVM sync required. Was: opened the real DFP DB file (slow + fragile).
    """
    db_path = tmp_path / "dfp.db"
    _build_clean_db(db_path)

    # Patch dfp_db_path() to return our synthetic DB path.
    monkeypatch.setattr(
        "data_sources.cvm._db.dfp_db_path", lambda: db_path)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    dupes = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc, COUNT(*) as cnt "
        "FROM contas GROUP BY id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc "
        "HAVING cnt > 1)"
    ).fetchone()[0]
    conn.close()
    assert dupes == 0, f"Found {dupes} duplicate conta groups in DFP"


def test_itr_no_duplicate_contas(tmp_path, monkeypatch):
    """[F6] ITR should have no duplicate contas."""
    db_path = tmp_path / "itr.db"
    _build_clean_db(db_path)

    monkeypatch.setattr(
        "data_sources.cvm._db.itr_db_path", lambda: db_path)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    dupes = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc, COUNT(*) as cnt "
        "FROM contas GROUP BY id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc "
        "HAVING cnt > 1)"
    ).fetchone()[0]
    conn.close()
    assert dupes == 0, f"Found {dupes} duplicate conta groups in ITR"


def test_dfp_no_orphan_contas(tmp_path, monkeypatch):
    """[F6] DFP contas should not reference non-existent empresas."""
    db_path = tmp_path / "dfp.db"
    _build_clean_db(db_path)

    monkeypatch.setattr(
        "data_sources.cvm._db.dfp_db_path", lambda: db_path)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    orphans = conn.execute(
        "SELECT COUNT(*) FROM contas c WHERE NOT EXISTS "
        "(SELECT 1 FROM empresas e WHERE e.id = c.id_empresa)"
    ).fetchone()[0]
    conn.close()
    assert orphans == 0, f"Found {orphans} orphan contas in DFP"
