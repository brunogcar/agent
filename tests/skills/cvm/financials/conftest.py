"""Shared fixtures for the financials skill tests.

[Phase 3] Extracted from the original single-file `test_financials.py` so
each mode (metrics / annual / quarterly / complete / summary / route) can
live in its own per-mode test module. The fixture builds synthetic DFP +
ITR SQLite databases with realistic CVM account data for PETROBRAS
(CNPJ 33000167000101, cd_cvm 9512) and monkeypatches `connect_dfp` /
`connect_itr` plus the bridge helpers so the skill reads only from the
synthetic DBs.

Env vars (PLANNER_MODEL etc.) are set by the parent conftest at
``tests/skills/cvm/conftest.py``.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm._db import _ensure_schema


# ── Synthetic DB builders ────────────────────────────────────────────────────

def _make_dfp_db(tmp_path: Path) -> Path:
    """Create synthetic DFP db with annual data (meses=12) for 2023 + 2022."""
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    # Company: PETROBRAS, cnpj=33000167000101, cd_cvm=9512
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (2, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2022, '9512')")
    # 2023 annual values (valor in thousands, escala="MIL")
    vals_2023 = {
        "1": 100000000, "1.01.01": 20000000, "2": 100000000, "2.03": 40000000,
        "2.01.04": 15000000, "2.02.01": 25000000,
        "3.01": 50000000, "3.03": 30000000, "3.05": 20000000, "3.06": -5000000,
        "3.11": 12000000,
        "6.01": 18000000, "6.02": -8000000, "6.03": -5000000, "6.01.01.02": 3000000,
        "7.08.04": 6000000,
    }
    for code, val in vals_2023.items():
        grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, ?, ?, ?, 1, '2023-01-01', '2023-12-31', 12, 'ÚLTIMO', 1, ?, 'MIL')",
            (code, f"Account {code}", grupo, val))
    # 2022 annual values (smaller, for trend)
    vals_2022 = {"1": 90000000, "2.03": 35000000, "3.01": 45000000, "3.11": 10000000}
    for code, val in vals_2022.items():
        grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE"
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (2, ?, ?, ?, 1, '2022-01-01', '2022-12-31', 12, 'ÚLTIMO', 1, ?, 'MIL')",
            (code, f"Account {code}", grupo, val))
    conn.commit()
    conn.close()
    return db_path


def _make_itr_db(tmp_path: Path) -> Path:
    """Create synthetic ITR db with cumulative quarterly data for 2023."""
    db_path = tmp_path / "itr.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    # Same company, 2023 quarterly
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    # Q1 cumulative (meses=3): 25% of annual for flows, snapshot at Mar 31
    # Q2 cumulative (meses=6): 50% of annual for flows, snapshot at Jun 30
    # Q3 cumulative (meses=9): 75% of annual for flows, snapshot at Sep 30
    annual_vals = {
        "1": 100000000, "1.01.01": 20000000, "2": 100000000, "2.03": 40000000,
        "2.01.04": 15000000, "2.02.01": 25000000,
        "3.01": 50000000, "3.03": 30000000, "3.05": 20000000, "3.06": -5000000,
        "3.11": 12000000,
        "6.01": 18000000, "6.02": -8000000, "6.03": -5000000, "6.01.01.02": 3000000,
        "7.08.04": 6000000,
    }
    for meses, pct, date_end in [(3, 0.25, "2023-03-31"), (6, 0.50, "2023-06-30"), (9, 0.75, "2023-09-30")]:
        for code, annual_val in annual_vals.items():
            grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
            # Snapshots use the period-end value (same as annual for simplicity)
            # Flows use cumulative (pct * annual)
            is_snapshot = grupo in ("BPA", "BPP")
            val = annual_val if is_snapshot else int(annual_val * pct)
            data_ini = "" if is_snapshot else "2023-01-01"
            conn.execute(
                "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
                "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
                "VALUES (1, ?, ?, ?, 1, ?, ?, 12, 'ÚLTIMO', 1, ?, 'MIL')",
                (code, f"Account {code}", grupo, data_ini, date_end, val))
    # Fix: meses should match the quarter, not always 12
    # Actually the _ensure_schema sets meses via the INSERT. Let me fix.
    conn.close()
    # Re-do with correct meses
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM contas")
    for meses, pct, date_end in [(3, 0.25, "2023-03-31"), (6, 0.50, "2023-06-30"), (9, 0.75, "2023-09-30")]:
        for code, annual_val in annual_vals.items():
            grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
            is_snapshot = grupo in ("BPA", "BPP")
            val = annual_val if is_snapshot else int(annual_val * pct)
            data_ini = "" if is_snapshot else "2023-01-01"
            conn.execute(
                "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
                "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
                "VALUES (1, ?, ?, ?, 1, ?, ?, ?, 'ÚLTIMO', 1, ?, 'MIL')",
                (code, f"Account {code}", grupo, data_ini, date_end, meses, val))
    conn.commit()
    conn.close()
    return db_path


# ── Pytest fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def financials_env(tmp_path: Path, monkeypatch):
    """Set up synthetic DFP + ITR DBs and patch all CVM access paths.

    Patches:
      - ``data_sources.cvm._db.connect_dfp`` / ``connect_itr`` → synthetic DBs
      - ``data_sources.cvm._db.dfp_db_path`` / ``itr_db_path`` → synthetic paths
      - ``data_sources.cvm._bridge.bridge_db_path`` / ``cad_db_path`` → nonexistent
        (so resolve_company only uses the empresas table by CNPJ)
      - ``data_sources.cvm._bridge._resolve_via_cad`` → returns (None, None)

    Returns:
        ``(dfp_path, itr_path)`` tuple of Paths to the synthetic DB files.
    """
    dfp_path = _make_dfp_db(tmp_path)
    itr_path = _make_itr_db(tmp_path)

    def mock_connect_dfp(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(dfp_path))
        c.row_factory = sqlite3.Row
        return c

    def mock_connect_itr(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{itr_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(itr_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
    monkeypatch.setattr("data_sources.cvm._db.connect_itr", mock_connect_itr)
    monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: dfp_path)
    monkeypatch.setattr("data_sources.cvm._db.itr_db_path", lambda: itr_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                        lambda name: (None, None))
    return dfp_path, itr_path
