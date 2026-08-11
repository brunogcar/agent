"""skills/cvm/_shared_report/company_header.py — Company header builder.

[v1.16.1] Extracted from skills/cvm/financials/report.py so all CVM skills
(financials, valuation, historical, governance, etc.) can reuse the same
company info card without copying code.

Pulls company registration data from:
  - FCA (fca.db): company name, CNPJ, CD_CVM, sector, listing segment,
    fiscal year-end, control type, website
  - CAD (cad.db): trade name, sector (fallback), UF
  - COTAHIST (cotahist.db): ISIN, latest close price

All fields are best-effort — missing DBs or lookups return None/"".
"""
from __future__ import annotations

from typing import Any


def build_company_header(company: str) -> dict:
    """Build a company header with FCA/CAD registration info + latest price.

    Returns a dict with:
      {"ticker", "name", "trade_name", "cnpj", "cd_cvm", "sector",
       "listing_segment", "control_type", "uf", "website", "isin",
       "last_close", "fiscal_year_end"}

    All fields are best-effort — missing DBs or lookups return None/"".
    """
    header: dict[str, Any] = {
        "ticker": company,
        "name": "",
        "trade_name": "",
        "cnpj": "",
        "cd_cvm": "",
        "sector": "",
        "listing_segment": "",
        "control_type": "",
        "uf": "",
        "website": "",
        "isin": "",
        "last_close": None,
        "fiscal_year_end": "",
        "last_synced_trimester": "",  # e.g. "2T2026" — latest ITR period
    }

    ticker = (company or "").strip().upper()
    if not ticker:
        return header

    # ── FCA lookup: CNPJ, CD_CVM, name, sector, segment, control, website ──
    try:
        from data_sources.cvm._db import fca_db_path
        import sqlite3
        fca = fca_db_path()
        if fca.exists():
            conn = sqlite3.connect(f"file:{fca}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT g.Nome_Empresarial, g.CNPJ_Companhia, g.Codigo_CVM,
                          g.Setor_Atividade, g.Descricao_Atividade,
                          g.Especie_Controle_Acionario, g.Pagina_Web,
                          g.Mes_Encerramento_Exercicio_Social,
                          g.Dia_Encerramento_Exercicio_Social,
                          v.Segmento, v.Codigo_Negociacao
                   FROM fca_valor_mobiliario v
                   JOIN fca_geral g
                     ON REPLACE(REPLACE(REPLACE(g.CNPJ_Companhia,'.',''),'/',''),'-','')
                      = REPLACE(REPLACE(REPLACE(v.CNPJ_Companhia,'.',''),'/',''),'-','')
                   WHERE UPPER(v.Codigo_Negociacao) = ?
                   ORDER BY v.Data_Referencia DESC, g.Data_Referencia DESC
                   LIMIT 1""",
                (ticker,),
            ).fetchone()
            if row:
                header["name"] = row["Nome_Empresarial"] or ""
                header["cnpj"] = row["CNPJ_Companhia"] or ""
                header["cd_cvm"] = str(row["Codigo_CVM"] or "")
                header["sector"] = row["Setor_Atividade"] or ""
                header["control_type"] = row["Especie_Controle_Acionario"] or ""
                header["website"] = row["Pagina_Web"] or ""
                header["listing_segment"] = row["Segmento"] or ""
                mes = row["Mes_Encerramento_Exercicio_Social"]
                dia = row["Dia_Encerramento_Exercicio_Social"]
                if mes and dia:
                    header["fiscal_year_end"] = f"{int(mes):02d}-{int(dia):02d}"
            conn.close()
    except Exception:
        pass

    # ── CAD lookup: trade name, sector (fallback), UF ──
    try:
        from data_sources.cvm._db import cad_db_path
        import sqlite3
        cad = cad_db_path()
        if cad.exists() and header["cnpj"]:
            cnpj_digits = header["cnpj"].replace(".", "").replace("/", "").replace("-", "")
            conn = sqlite3.connect(f"file:{cad}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT DENOM_SOCIAL, DENOM_COMERC, SETOR_ATIV, UF, AUDITOR
                   FROM cia_aberta
                   WHERE REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') = ?
                   AND SIT = 'ATIVO'
                   ORDER BY rowid DESC LIMIT 1""",
                (cnpj_digits,),
            ).fetchone()
            if row:
                header["trade_name"] = row["DENOM_COMERC"] or ""
                if not header["sector"]:
                    header["sector"] = row["SETOR_ATIV"] or ""
                header["uf"] = row["UF"] or ""
            conn.close()
    except Exception:
        pass

    # ── COTAHIST lookup: ISIN + latest close price ──
    try:
        from data_sources.b3.cotahist.catalog import db_path as cotahist_path
        import sqlite3
        cot = cotahist_path()
        if cot.exists():
            conn = sqlite3.connect(f"file:{cot}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            isin_row = conn.execute(
                "SELECT DISTINCT isin FROM cotahist WHERE symbol=? AND isin IS NOT NULL LIMIT 1",
                (ticker,),
            ).fetchone()
            if isin_row:
                header["isin"] = isin_row["isin"] or ""
            close_row = conn.execute(
                "SELECT close FROM cotahist WHERE symbol=? ORDER BY refdate DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if close_row and close_row["close"] is not None:
                header["last_close"] = float(close_row["close"])
            conn.close()
    except Exception:
        pass

    # ── Last synced trimester (e.g. "2T2026") from ITR ──────────────────
    # Shows the latest quarterly financial statement available. Uses the
    # shared freshness helper which queries ITR's MAX(data_fim_exerc).
    try:
        from skills.cvm._freshness import get_last_synced_period
        periods = get_last_synced_period()
        itr_period = periods.get("itr", "")
        if itr_period:
            # Convert "2026-06-30" → "2T2026"
            parts = itr_period.split("-")
            if len(parts) == 3:
                year = parts[0]
                month = int(parts[1])
                trimester = {3: "1T", 6: "2T", 9: "3T", 12: "4T"}.get(month, "")
                if trimester:
                    header["last_synced_trimester"] = f"{trimester}{year}"
    except Exception:
        pass

    return header
