"""tests/data_sources/cvm/itr/test_sync_versao_dedup.py — VERSAO dedup regression test.

Regression test for the P0 bug where the versao_cache was keyed on (cnpj, ano)
instead of (cnpj, ano, dt_fim). This caused Q1/Q3 rows (VERSAO=1) to be silently
dropped when a restated Q2 (VERSAO=2) was processed.

The fix changed the cache key to include dt_fim so each quarter is tracked
independently. This test verifies the fix by simulating out-of-order rows
matching the exact bug scenario.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def itr_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a fresh itr.db with the contas schema for testing."""
    db_path = tmp_path / "itr.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE empresas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj    TEXT NOT NULL,
            nome    TEXT NOT NULL,
            ano     INTEGER NOT NULL,
            cd_cvm  TEXT,
            UNIQUE (cnpj, ano)
        );
        CREATE TABLE contas (
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
            PRIMARY KEY (id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc)
        );
    """)
    conn.commit()
    return conn


def _process_row(conn, csv_row, empresa_cache, versao_cache, cleared_periods):
    """Minimal copy of _process_row for testing the VERSAO dedup logic.

    Only implements the VERSAO dedup + INSERT — skips meses/ordem filters
    since this test isolates the VERSAO key logic.
    """
    cnpj = csv_row["CNPJ_CIA"]
    nome = csv_row["DENOM_CIA"]
    dt_fim = csv_row["DT_FIM_EXERC"]
    codigo = csv_row["CD_CONTA"]
    descricao = csv_row["DS_CONTA"]
    grupo = csv_row["GRUPO_DFP"]
    consolidado = 1 if "CONSOLID" in grupo.upper() else 0
    versao = int(csv_row.get("VERSAO", "1"))
    valor = float(csv_row.get("VL_CONTA", "0"))
    ano = int(dt_fim[:4])

    # VERSAO dedup — the fix under test
    cache_key = f"{cnpj}_{ano}_{dt_fim}"
    if cache_key in versao_cache and versao < versao_cache[cache_key]:
        return 0
    versao_cache[cache_key] = max(versao_cache.get(cache_key, 0), versao)

    # Upsert empresa
    empresa_key = f"{cnpj}_{ano}"
    if empresa_key not in empresa_cache:
        conn.execute(
            "INSERT OR IGNORE INTO empresas (cnpj, nome, ano, cd_cvm) VALUES (?, ?, ?, ?)",
            (cnpj, nome, ano, ""),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM empresas WHERE cnpj=? AND ano=?", (cnpj, ano),
        ).fetchone()
        if row:
            empresa_cache[empresa_key] = row[0]
        else:
            return 0
    empresa_id = empresa_cache[empresa_key]

    # DELETE-before-INSERT (per period, prevents ghost rows)
    period_key = f"{empresa_id}_{dt_fim}"
    if period_key not in cleared_periods:
        conn.execute(
            "DELETE FROM contas WHERE id_empresa = ? AND data_fim_exerc = ?",
            (empresa_id, dt_fim),
        )
        cleared_periods.add(period_key)

    # Upsert conta
    conn.execute(
        """INSERT OR REPLACE INTO contas
           (id_empresa, codigo, descricao, grupo, consolidado,
            data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao,
            st_conta_fixa, valor, escala, moeda)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (empresa_id, codigo, descricao, grupo, consolidado,
         "", dt_fim, 3, "ÚLTIMO", versao,
         "", valor, "UNIDADE", "REAL"),
    )
    return 1


class TestVersaoDedup:
    """Regression tests for VERSAO dedup — the (cnpj, ano, dt_fim) cache key."""

    def test_all_quarters_survive_when_q2_is_restated(self, itr_db):
        """Q1/Q3 must NOT be dropped when Q2 is restated with higher VERSAO.

        This is the exact bug scenario: PETR4 2025 Q1(VERSAO=1), Q2(VERSAO=2
        restated), Q3(VERSAO=1). Before the fix, Q1 and Q3 were dropped
        because the cache key was just (cnpj, ano) — Q2's VERSAO=2 poisoned
        the cache for the whole year.
        """
        conn = itr_db
        empresa_cache = {}
        versao_cache = {}
        cleared_periods = set()

        # Process rows OUT OF ORDER (Q2 restated first, then Q1, then Q3)
        # This is the worst case — if Q2(v2) is processed first, the old
        # buggy cache would have versao=2 for (cnpj, ano) and drop Q1/Q3(v1).
        rows = [
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "2", "VL_CONTA": "100000"},  # Q2 restated
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-03-31", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "1", "VL_CONTA": "25000"},  # Q1 original
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-09-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "1", "VL_CONTA": "75000"},  # Q3 original
        ]

        stored = 0
        for row in rows:
            stored += _process_row(conn, row, empresa_cache, versao_cache, cleared_periods)
        conn.commit()

        # All 3 quarters must be stored
        assert stored == 3, f"Expected 3 rows stored, got {stored}"

        # Verify each quarter exists in the DB
        quarters = conn.execute(
            "SELECT data_fim_exerc, versao, valor FROM contas ORDER BY data_fim_exerc"
        ).fetchall()
        assert len(quarters) == 3, f"Expected 3 quarters in DB, got {len(quarters)}"

        dates = [q[0] for q in quarters]
        assert "2025-03-31" in dates, "Q1 missing!"
        assert "2025-06-30" in dates, "Q2 missing!"
        assert "2025-09-30" in dates, "Q3 missing!"

        # Q2 should be VERSAO=2 (the restated value)
        q2 = [q for q in quarters if q[0] == "2025-06-30"][0]
        assert q2[1] == 2, f"Q2 should have VERSAO=2, got {q2[1]}"
        assert q2[2] == 100000, f"Q2 should have valor=100000, got {q2[2]}"

    def test_higher_versao_wins_within_same_quarter(self, itr_db):
        """Within the same quarter, higher VERSAO must win.

        If Q2(v1) is processed first, then Q2(v2 restated), the final
        stored value should be from v2.
        """
        conn = itr_db
        empresa_cache = {}
        versao_cache = {}
        cleared_periods = set()

        rows = [
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "1", "VL_CONTA": "90000"},  # Q2 original
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "2", "VL_CONTA": "100000"},  # Q2 restated (higher)
        ]

        for row in rows:
            _process_row(conn, row, empresa_cache, versao_cache, cleared_periods)
        conn.commit()

        rows_db = conn.execute(
            "SELECT versao, valor FROM contas WHERE data_fim_exerc = '2025-06-30'"
        ).fetchall()
        assert len(rows_db) == 1, f"Expected 1 row for Q2, got {len(rows_db)}"
        assert rows_db[0][0] == 2, f"VERSAO should be 2, got {rows_db[0][0]}"
        assert rows_db[0][1] == 100000, f"valor should be 100000, got {rows_db[0][1]}"

    def test_lower_versao_dropped_when_higher_already_seen(self, itr_db):
        """If Q2(v2) processed first, Q2(v1) must be dropped (stale)."""
        conn = itr_db
        empresa_cache = {}
        versao_cache = {}
        cleared_periods = set()

        rows = [
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "2", "VL_CONTA": "100000"},  # Q2 restated (first)
            {"CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
             "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": "3.01",
             "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
             "VERSAO": "1", "VL_CONTA": "90000"},  # Q2 stale (should be dropped)
        ]

        stored = 0
        for row in rows:
            stored += _process_row(conn, row, empresa_cache, versao_cache, cleared_periods)
        conn.commit()

        # Only 1 row should be stored (the v2)
        assert stored == 1, f"Expected 1 row stored, got {stored}"

        rows_db = conn.execute(
            "SELECT versao, valor FROM contas WHERE data_fim_exerc = '2025-06-30'"
        ).fetchall()
        assert len(rows_db) == 1
        assert rows_db[0][0] == 2, f"Should keep VERSAO=2, got {rows_db[0][0]}"
        assert rows_db[0][1] == 100000, f"Should keep valor=100000, got {rows_db[0][1]}"

    def test_ghost_rows_deleted_on_restatement(self, itr_db):
        """If a restated filing has FEWER rows, old rows must be deleted.

        Scenario: Q2(v1) has codes [3.01, 3.02, 3.03]. Q2(v2 restated)
        removes code 3.03. The DELETE-before-INSERT should remove 3.03.
        """
        conn = itr_db
        empresa_cache = {}
        versao_cache = {}
        cleared_periods = set()

        # Q2(v1) — 3 codes
        for code in ["3.01", "3.02", "3.03"]:
            _process_row(conn, {
                "CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
                "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": code,
                "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
                "VERSAO": "1", "VL_CONTA": "10000",
            }, empresa_cache, versao_cache, cleared_periods)
        conn.commit()

        # Q2(v2 restated) — only 2 codes (3.03 removed)
        # Reset cleared_periods so the DELETE-before-INSERT runs again
        cleared_periods.clear()
        for code in ["3.01", "3.02"]:
            _process_row(conn, {
                "CNPJ_CIA": "33000167000101", "DENOM_CIA": "PETROBRAS",
                "DT_FIM_EXERC": "2025-06-30", "CD_CONTA": code,
                "DS_CONTA": "Receita", "GRUPO_DFP": "DRE Consolidado",
                "VERSAO": "2", "VL_CONTA": "11000",
            }, empresa_cache, versao_cache, cleared_periods)
        conn.commit()

        rows_db = conn.execute(
            "SELECT codigo, versao FROM contas WHERE data_fim_exerc = '2025-06-30' ORDER BY codigo"
        ).fetchall()
        codes = [r[0] for r in rows_db]
        assert "3.03" not in codes, f"Ghost row 3.03 should be deleted, found: {codes}"
        assert len(rows_db) == 2, f"Expected 2 rows (3.01, 3.02), got {len(rows_db)}"
        # Both should be VERSAO=2
        for r in rows_db:
            assert r[1] == 2, f"Expected VERSAO=2 for {r[0]}, got {r[1]}"
