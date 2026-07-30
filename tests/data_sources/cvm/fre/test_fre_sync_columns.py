"""Regression test for FRE sync column name mappings.

Verifies that the sync engine correctly reads the CVM FRE CSV column names
(Percentual_Total_Acoes_Circulacao, etc.) and stores non-NULL values in the
database. This prevents the v1.0 bug where abbreviated names (Pct_Total_Circulacao)
caused all values to be stored as NULL for 6+ years.

Uses synthetic CSV data with the correct CVM column names — no real database
or network needed.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import zipfile

import pytest

from data_sources.cvm.fre.sync_engine import (
    _read_csv_from_zip, _store_posicao_acionaria, _store_distribuicao_capital,
    _store_capital_social, _store_remuneracao_orgao,
)
from data_sources.cvm.fre.catalog import SCHEMA_SQL


# ── CVM FRE CSV column names (verified against official CVM metadata) ─────────
# These are the ACTUAL column names CVM uses in their FRE CSV files.
# Source: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/META/

DISTRIBUICAO_CAPITAL_COLS = [
    "CNPJ_Companhia", "Data_Referencia", "Data_Ultima_Assembleia",
    "ID_Documento", "Nome_Companhia", "Versao",
    "Percentual_Acoes_Ordinarias_Circulacao",
    "Percentual_Acoes_Preferenciais_Circulacao",
    "Percentual_Total_Acoes_Circulacao",
    "Quantidade_Acoes_Ordinarias_Circulacao",
    "Quantidade_Acoes_Preferenciais_Circulacao",
    "Quantidade_Total_Acoes_Circulacao",
    "Quantidade_Acionistas_PF",
    "Quantidade_Acionistas_PJ",
    "Quantidade_Acionistas_Investidores_Institucionais",
]

POSICAO_ACIONARIA_COLS = [
    "Acionista", "Acionista_Controlador", "CNPJ_Companhia",
    "CPF_CNPJ_Acionista", "Data_Referencia", "ID_Documento",
    "Nome_Companhia", "Versao", "Nacionalidade",
    "Participante_Acordo_Acionistas",
    "Percentual_Acao_Ordinaria_Circulacao",
    "Percentual_Acao_Preferencial_Circulacao",
    "Percentual_Total_Acoes_Circulacao",
    "Quantidade_Acao_Ordinaria_Circulacao",
    "Quantidade_Acao_Preferencial_Circulacao",
    "Quantidade_Total_Acoes_Circulacao",
    "Tipo_Pessoa_Acionista",
]

CAPITAL_SOCIAL_COLS = [
    "CNPJ_Companhia", "Data_Referencia", "ID_Documento",
    "Nome_Companhia", "Versao", "Data_Autorizacao_Aprovacao",
    "Tipo_Capital", "Valor_Capital",
    "Quantidade_Acoes_Ordinarias",
    "Quantidade_Acoes_Preferenciais",
    "Quantidade_Total_Acoes",
]

REMUNERACAO_ORGAO_COLS = [
    "CNPJ_Companhia", "Data_Referencia", "ID_Documento",
    "Nome_Companhia", "Versao",
    "Orgao_Administracao",
    "Data_Inicio_Exercicio_Social",
    "Data_Fim_Exercicio_Social",
    "Numero_Membros", "Numero_Membros_Remunerados",
    "Salario", "Beneficios_Diretos_Indiretos",
    "Bonus", "Participacao_Resultados",
    "Baseada_Acoes", "Total_Remuneracao", "Total_Remuneracao_Orgao",
]


@pytest.fixture
def fre_db(tmp_path):
    """Create an in-memory fre.db with the CVM FRE schema."""
    db_path = tmp_path / "fre.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


def _make_csv_row(columns, **overrides):
    """Build a CSV row dict with the given columns + sensible defaults."""
    row = {col: "" for col in columns}
    row.update(overrides)
    return row


def _rows_to_csv(rows: list[dict]) -> str:
    """Convert a list of row dicts to CSV string."""
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys(), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDistribuicaoCapitalColumns:
    """Verify distribuicao_capital sync reads CVM column names correctly."""

    def test_non_null_values_stored(self, fre_db):
        """[v1.1 regression] Values are stored as non-NULL when CVM column names are used."""
        row = _make_csv_row(
            DISTRIBUICAO_CAPITAL_COLS,
            CNPJ_Companhia="33000167000101",
            Data_Referencia="2026-12-31",
            ID_Documento="159462",
            Nome_Companhia="PETROLEO BRASILEIRO S.A. PETROBRAS",
            Versao="1",
            Percentual_Acoes_Ordinarias_Circulacao="45.23",
            Percentual_Acoes_Preferenciais_Circulacao="52.10",
            Percentual_Total_Acoes_Circulacao="48.50",
            Quantidade_Acionistas_PF="500000",
            Quantidade_Acionistas_PJ="200",
            Quantidade_Acionistas_Investidores_Institucionais="50",
        )
        _store_distribuicao_capital(fre_db, [row])
        fre_db.commit()

        result = fre_db.execute(
            "SELECT pct_total_circulacao, qtd_acionistas_pf, qtd_acionistas_pj, "
            "qtd_acionistas_inst FROM distribuicao_capital WHERE cnpj = ?",
            ("33000167000101",),
        ).fetchone()

        assert result is not None
        assert result[0] == 48.50  # pct_total_circulacao
        assert result[1] == 500000  # qtd_acionistas_pf
        assert result[2] == 200  # qtd_acionistas_pj
        assert result[3] == 50  # qtd_acionistas_inst

    def test_no_null_values_when_cvm_names_used(self, fre_db):
        """All pct/qtd columns should be non-NULL (the v1.0 bug stored NULLs)."""
        row = _make_csv_row(
            DISTRIBUICAO_CAPITAL_COLS,
            CNPJ_Companhia="33000167000101",
            Data_Referencia="2026-12-31",
            ID_Documento="159462",
            Nome_Companhia="PETR4",
            Versao="1",
            Percentual_Total_Acoes_Circulacao="48.50",
            Quantidade_Acionistas_PF="500000",
        )
        _store_distribuicao_capital(fre_db, [row])
        fre_db.commit()

        result = fre_db.execute(
            "SELECT SUM(CASE WHEN pct_total_circulacao IS NOT NULL THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN qtd_acionistas_pf IS NOT NULL THEN 1 ELSE 0 END) "
            "FROM distribuicao_capital"
        ).fetchone()

        assert result[0] == 1  # non-NULL pct
        assert result[1] == 1  # non-NULL pf


class TestPosicaoAcionariaColumns:
    """Verify posicao_acionaria sync reads CVM column names correctly."""

    def test_non_null_values_stored(self, fre_db):
        """[v1.1 regression] Values are stored as non-NULL when CVM column names are used."""
        row = _make_csv_row(
            POSICAO_ACIONARIA_COLS,
            CNPJ_Companhia="33000167000101",
            Data_Referencia="2026-12-31",
            ID_Documento="159462",
            Nome_Companhia="PETR4",
            Versao="1",
            Acionista="União Federal",
            Tipo_Pessoa_Acionista="PJ",
            Percentual_Acao_Ordinaria_Circulacao="29.021",
            Percentual_Acao_Preferencial_Circulacao="0.0",
            Percentual_Total_Acoes_Circulacao="29.021",
            Quantidade_Acao_Ordinaria_Circulacao="5000000000",
        )
        _store_posicao_acionaria(fre_db, [row])
        fre_db.commit()

        result = fre_db.execute(
            "SELECT pct_on, pct_pn, pct_total, qtd_on, tipo_pessoa "
            "FROM posicao_acionaria WHERE cnpj = ?",
            ("33000167000101",),
        ).fetchone()

        assert result is not None
        assert result[0] == 29.021  # pct_on
        assert result[1] == 0.0  # pct_pn
        assert result[2] == 29.021  # pct_total
        assert result[3] == 5000000000  # qtd_on
        assert result[4] == "PJ"  # tipo_pessoa


class TestCapitalSocialColumns:
    """Verify capital_social sync reads CVM column names correctly."""

    def test_non_null_values_stored(self, fre_db):
        """[v1.1 regression] Values are stored as non-NULL when CVM column names are used."""
        row = _make_csv_row(
            CAPITAL_SOCIAL_COLS,
            CNPJ_Companhia="33000167000101",
            Data_Referencia="2026-12-31",
            ID_Documento="159462",
            Nome_Companhia="PETR4",
            Versao="1",
            Tipo_Capital="Subscrito",
            Valor_Capital="205431960490.52",
            Quantidade_Acoes_Ordinarias="10000000000",
            Quantidade_Acoes_Preferenciais="5000000000",
            Quantidade_Total_Acoes="15000000000",
            Data_Autorizacao_Aprovacao="2026-04-16",
        )
        _store_capital_social(fre_db, [row])
        fre_db.commit()

        result = fre_db.execute(
            "SELECT valor_capital, qtd_acoes_on, qtd_acoes_pn, qtd_acoes_total, "
            "data_aprovacao FROM capital_social WHERE cnpj = ?",
            ("33000167000101",),
        ).fetchone()

        assert result is not None
        assert result[0] == 205431960490.52  # valor_capital
        assert result[1] == 10000000000  # qtd_acoes_on
        assert result[2] == 5000000000  # qtd_acoes_pn
        assert result[3] == 15000000000  # qtd_acoes_total
        assert result[4] == "2026-04-16"  # data_aprovacao


class TestReadCsvFromZip:
    """[v1.2] Test the fixed _read_csv_from_zip — exact match + sibling exclusion."""

    def _make_zip(self, files: dict[str, str]) -> zipfile.ZipFile:
        """Create an in-memory ZIP with the given filename:content mapping."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buf.seek(0)
        return zipfile.ZipFile(buf)

    def test_exact_match_with_year(self):
        """_read_csv_from_zip finds fre_cia_aberta_posicao_acionaria_2026.csv."""
        zf = self._make_zip({
            "fre_cia_aberta_posicao_acionaria_2026.csv": "CNPJ;Data\n123;2026\n",
            "fre_cia_aberta_posicao_acionaria_classe_acao_2026.csv": "CNPJ;Data\n456;2026\n",
        })
        rows = _read_csv_from_zip(zf, "posicao_acionaria", year=2026)
        assert len(rows) == 1
        assert rows[0]["CNPJ"] == "123"  # the base file, not classe_acao

    def test_excludes_classe_acao_sibling(self):
        """_read_csv_from_zip does NOT return the _classe_acao sibling file."""
        zf = self._make_zip({
            "fre_cia_aberta_distribuicao_capital_classe_acao_2026.csv": "CNPJ;Data\n456;2026\n",
            "fre_cia_aberta_distribuicao_capital_2026.csv": "CNPJ;Data\n123;2026\n",
        })
        rows = _read_csv_from_zip(zf, "distribuicao_capital", year=2026)
        assert len(rows) == 1
        assert rows[0]["CNPJ"] == "123"  # base file, not classe_acao

    def test_excludes_aumento_sibling(self):
        """_read_csv_from_zip does NOT return the _aumento sibling file."""
        zf = self._make_zip({
            "fre_cia_aberta_capital_social_aumento_2026.csv": "CNPJ;Data\n456;2026\n",
            "fre_cia_aberta_capital_social_2026.csv": "CNPJ;Data\n123;2026\n",
        })
        rows = _read_csv_from_zip(zf, "capital_social", year=2026)
        assert len(rows) == 1
        assert rows[0]["CNPJ"] == "123"

    def test_returns_empty_when_only_siblings_exist(self):
        """If only _classe_acao exists (no base file), returns empty."""
        zf = self._make_zip({
            "fre_cia_aberta_posicao_acionaria_classe_acao_2026.csv": "CNPJ;Data\n456;2026\n",
        })
        rows = _read_csv_from_zip(zf, "posicao_acionaria", year=2026)
        assert rows == []

    def test_documentos_exact_match(self):
        """Documentos file is fre_cia_aberta_{year}.csv (no fragment)."""
        zf = self._make_zip({
            "fre_cia_aberta_2026.csv": "ID_DOC;CNPJ\n1;123\n",
            "fre_cia_aberta_posicao_acionaria_2026.csv": "ID_DOC;CNPJ\n2;456\n",
        })
        rows = _read_csv_from_zip(zf, "", year=2026)
        assert len(rows) == 1
        assert rows[0]["ID_DOC"] == "1"
