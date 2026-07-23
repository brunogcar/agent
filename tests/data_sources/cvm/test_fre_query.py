"""tests/data_sources/cvm/test_fre_query.py -- Tests for FRE query engine.

Uses a synthetic SQLite DB (in tmp_path) to test query logic without
needing real CVM data. Never touches the real fre.db.
"""

from __future__ import annotations

import sqlite3
import pytest

from data_sources.cvm.fre.catalog import SCHEMA_SQL


@pytest.fixture
def fre_db(tmp_path, monkeypatch):
    """Create a synthetic FRE database with test data."""
    db_path = tmp_path / "fre.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    # Insert a test filing
    conn.execute(
        "INSERT INTO documentos (id_doc, cnpj, cd_cvm, nome, categ_doc, dt_receb, dt_refer, versao, link_doc, ano_origem) "
        "VALUES (100001, '33000167000101', '000123', 'JHSF PARTICIPACOES S.A.', 'FRE', '2024-03-15', '2023-12-31', 1, 'http://example.com/doc', 2024)"
    )

    # Insert shareholder data
    conn.execute(
        "INSERT INTO posicao_acionaria (cnpj, id_documento, data_referencia, versao, nome_companhia, "
        "acionista, cpf_cnpj_acionista, tipo_pessoa, acionista_controlador, pct_on, pct_pn, pct_total, qtd_on, qtd_pn, qtd_total) "
        "VALUES ('33000167000101', 100001, '2023-12-31', 1, 'JHSF PARTICIPACOES S.A.', "
        "'JOSE AJIME EMERICK', '12345678901', 'PF', 'S', 50.0, 0.0, 50.0, 50000000, 0, 50000000)"
    )
    conn.execute(
        "INSERT INTO posicao_acionaria (cnpj, id_documento, data_referencia, versao, nome_companhia, "
        "acionista, cpf_cnpj_acionista, tipo_pessoa, acionista_controlador, pct_on, pct_pn, pct_total, qtd_on, qtd_pn, qtd_total) "
        "VALUES ('33000167000101', 100001, '2023-12-31', 1, 'JHSF PARTICIPACOES S.A.', "
        "'BLACKROCK INC', '00000000000001', 'PJ', 'N', 0.0, 5.0, 3.0, 0, 3000000, 3000000)"
    )

    # Insert free float data
    conn.execute(
        "INSERT INTO distribuicao_capital (cnpj, id_documento, data_referencia, versao, nome_companhia, "
        "pct_on_circulacao, pct_pn_circulacao, pct_total_circulacao, qtd_on_circulacao, qtd_pn_circulacao, "
        "qtd_total_circulacao, qtd_acionistas_pf, qtd_acionistas_pj, qtd_acionistas_inst, data_ultima_assembleia) "
        "VALUES ('33000167000101', 100001, '2023-12-31', 1, 'JHSF PARTICIPACOES S.A.', "
        "50.0, 95.0, 47.0, 50000000, 57000000, 107000000, 12000, 50, 30, '2024-04-30')"
    )

    # Insert compensation data
    conn.execute(
        "INSERT INTO remuneracao_orgao (cnpj, id_documento, data_referencia, versao, nome_companhia, "
        "orgao, dt_ini_exercicio, dt_fim_exercicio, num_membros, num_membros_remunerados, "
        "salario, beneficios, bonus, participacao_resultados, baseada_acoes, total_remuneracao, total_remuneracao_orgao) "
        "VALUES ('33000167000101', 100001, '2023-12-31', 1, 'JHSF PARTICIPACOES S.A.', "
        "'Diretoria', '2023-01-01', '2023-12-31', 5, 5, 5000000, 1000000, 2000000, 0, 500000, 8500000, 8500000)"
    )

    # Insert capital social data
    conn.execute(
        "INSERT INTO capital_social (cnpj, id_documento, data_referencia, versao, nome_companhia, "
        "tipo_capital, valor_capital, qtd_acoes_on, qtd_acoes_pn, qtd_acoes_total, data_aprovacao) "
        "VALUES ('33000167000101', 100001, '2023-12-31', 1, 'JHSF PARTICIPACOES S.A.', "
        "'Subscrito', 1000000000, 100000000, 60000000, 160000000, '2023-12-31')"
    )

    conn.commit()
    conn.close()

    def mock_connect_fre(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_fre", mock_connect_fre)
    monkeypatch.setattr("data_sources.cvm.fre.query_engine.connect_fre", mock_connect_fre)
    monkeypatch.setattr("data_sources.cvm.fre.status_reporter.connect_fre", mock_connect_fre)
    monkeypatch.setattr("data_sources.cvm.fre.status_reporter.fre_db_path", lambda: db_path)
    return db_path


class TestFREShareholders:
    def test_query_by_name(self, fre_db):
        from data_sources.cvm.fre.query_engine import shareholders
        result = shareholders(company="JHSF")
        assert result["status"] == "ok"
        assert "JHSF" in result["company"]
        assert len(result["shareholders"]) == 2

    def test_query_by_cnpj(self, fre_db):
        from data_sources.cvm.fre.query_engine import shareholders
        result = shareholders(company="33000167000101")
        assert result["status"] == "ok"

    def test_shareholder_sorted_by_pct(self, fre_db):
        from data_sources.cvm.fre.query_engine import shareholders
        result = shareholders(company="JHSF")
        pcts = [s["pct_total"] for s in result["shareholders"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_not_found(self, fre_db):
        from data_sources.cvm.fre.query_engine import shareholders
        result = shareholders(company="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_no_company(self, fre_db):
        from data_sources.cvm.fre.query_engine import shareholders
        result = shareholders()
        assert result["status"] == "error"


class TestFreeFloat:
    def test_query(self, fre_db):
        from data_sources.cvm.fre.query_engine import free_float
        result = free_float(company="JHSF")
        assert result["status"] == "ok"
        assert len(result["periods"]) == 1
        assert result["periods"][0]["pct_total_circulacao"] == 47.0

    def test_not_found(self, fre_db):
        from data_sources.cvm.fre.query_engine import free_float
        result = free_float(company="NONEXISTENT")
        assert result["status"] == "not_found"


class TestCompensation:
    def test_query(self, fre_db):
        from data_sources.cvm.fre.query_engine import compensation
        result = compensation(company="JHSF")
        assert result["status"] == "ok"
        assert len(result["periods"]) == 1
        assert result["periods"][0]["salario"] == 5000000

    def test_not_found(self, fre_db):
        from data_sources.cvm.fre.query_engine import compensation
        result = compensation(company="NONEXISTENT")
        assert result["status"] == "not_found"


class TestCapital:
    def test_query(self, fre_db):
        from data_sources.cvm.fre.query_engine import capital
        result = capital(company="JHSF")
        assert result["status"] == "ok"
        assert len(result["periods"]) == 1
        assert result["periods"][0]["qtd_acoes_total"] == 160000000

    def test_not_found(self, fre_db):
        from data_sources.cvm.fre.query_engine import capital
        result = capital(company="NONEXISTENT")
        assert result["status"] == "not_found"


class TestFRESearch:
    def test_search(self, fre_db):
        from data_sources.cvm.fre.query_engine import search
        result = search(query="JHSF")
        assert result["status"] == "ok"
        assert len(result["companies"]) >= 1
        assert "JHSF" in result["companies"][0]["nome"]

    def test_search_not_found(self, fre_db):
        from data_sources.cvm.fre.query_engine import search
        result = search(query="NONEXISTENT")
        assert result["status"] == "not_found"


class TestFREStatus:
    def test_status(self, fre_db):
        from data_sources.cvm.fre.status_reporter import status
        result = status()
        assert result["status"] == "ok"
        assert result["form"] == "FRE"
        assert result["tables"]["documentos"] == 1
        assert result["tables"]["posicao_acionaria"] == 2
