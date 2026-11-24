"""skills/cvm/_shared_report/company_header.py — Company header builder.

[v1.16.1] Extracted from skills/cvm/financials/report.py so all CVM skills
(financials, valuation, historical, governance, etc.) can reuse the same
company info card without copying code.

[v2.2-header] Reorganized into 3 parts:
  Part 1 — Identity card (ticker, name, trade_name, last_close, market_cap,
           total_shares) as a standalone header.
  Part 2 — Registration details as 4 grouped tables (Identificação,
           Instrumento B3, Classificação, Governança) in a 2×2 grid.
  Part 3 — Atividade (full-width description table).

New fields added:
  - activity_description (FCA Descricao_Atividade — was fetched but not extracted)
  - auditor (CAD AUDITOR — was fetched but not extracted)
  - market_name (B3 instruments.db MktNm — e.g. "MERCADO A VISTA")
  - security_category (B3 instruments.db SctyCtgyNm — e.g. "ACAO PREFERENCIAL")
  - b3_segment (B3 instruments.db SgmtNm — e.g. "BOVESPA")
  - market_cap (computed: last_close × shares_at)
  - total_shares (from shares_at engine — FRE)
  - Formatted string variants for the template (last_close_str, market_cap_str,
    total_shares_str).

fiscal_year_end format changed from "MM-DD" (12-31) to "DD/MM" (31/12) — BR.

Pulls company registration data from:
  - FCA (fca.db): company name, CNPJ, CD_CVM, sector, listing segment,
    fiscal year-end, control type, website, activity description
  - CAD (cad.db): trade name, sector (fallback), UF, auditor
  - COTAHIST (cotahist.db): ISIN, latest close price
  - B3 instruments (instruments.db): market name, security category, B3 segment
  - FRE (fre.db via shares_at): total shares outstanding

All fields are best-effort — missing DBs or lookups return None/"".
"""
from __future__ import annotations

from typing import Any


def _format_compact_brl(value: float) -> str:
    """Format as compact BR currency: R$ 654,3 bi / R$ 654,3 mi / R$ 654,3 mil."""
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"R$ {value/1e12:.1f} tri".replace(".", ",")
    if abs_v >= 1e9:
        return f"R$ {value/1e9:.1f} bi".replace(".", ",")
    if abs_v >= 1e6:
        return f"R$ {value/1e6:.1f} mi".replace(".", ",")
    if abs_v >= 1e3:
        return f"R$ {value/1e3:.1f} mil".replace(".", ",")
    return f"R$ {value:.2f}".replace(".", ",")


def _format_compact_shares(value: int) -> str:
    """Format as compact shares: 13,0 bi ações / 650,0 mi ações."""
    abs_v = abs(value)
    if abs_v >= 1e9:
        return f"{value/1e9:.1f} bi ações".replace(".", ",")
    if abs_v >= 1e6:
        return f"{value/1e6:.1f} mi ações".replace(".", ",")
    return f"{value:,} ações"


def build_company_header(company: str) -> dict:
    """Build a company header with FCA/CAD/B3 registration info + latest price.

    Returns a dict with identity + registration fields + formatted strings.
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
        # [v2.2-header] New fields
        "activity_description": "",
        "auditor": "",
        "market_name": "",       # B3 MktNm
        "security_category": "", # B3 SctyCtgyNm
        "b3_segment": "",        # B3 SgmtNm
        "market_cap": None,
        "total_shares": None,
        "last_close_str": "",
        "market_cap_str": "",
        "total_shares_str": "",
    }

    ticker = (company or "").strip().upper()
    if not ticker:
        return header

    # ── FCA lookup: CNPJ, CD_CVM, name, sector, segment, control, website,
    #    activity description ──
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
                # [v2.2-header] Extract activity description (was fetched but not used)
                header["activity_description"] = row["Descricao_Atividade"] or ""
                mes = row["Mes_Encerramento_Exercicio_Social"]
                dia = row["Dia_Encerramento_Exercicio_Social"]
                if mes and dia:
                    # [v2.2-header] BR format: "DD/MM" (was "MM-DD")
                    header["fiscal_year_end"] = f"{int(dia):02d}/{int(mes):02d}"
            conn.close()
    except Exception:
        pass

    # ── CAD lookup: trade name, sector (fallback), UF, auditor ──
    # [v1.22.4] THE FALLBACK CHAIN — one missed FCA row used to blank
    # the whole identity card (sector "—" on the Carteira, empty
    # Identificação/Classificação/Governança). Order:
    #   1. CAD by CNPJ (FCA's, or the bridge ticker_map's), SIT=ATIVO
    #   2. CAD by the same CNPJ, ANY situation (a merged/delisted
    #      paper — MBRF3 after the BRF merger — still has a sector)
    #   3. CAD by CD_CVM (from FCA or the bridge — CNPJ formats drift)
    #   4. bridge.db ticker_map itself (sector cached at sync time)
    #   5. B3 dividends company_info (trading name + segment + cd_cvm)
    def _cad_by_cnpj(cnpj_raw: str, ativo_only: bool):
        try:
            from data_sources.cvm._db import cad_db_path
            import sqlite3
            cad = cad_db_path()
            if not cad.exists() or not cnpj_raw:
                return None
            digits = cnpj_raw.replace(".", "").replace("/", "").replace("-", "")
            conn = sqlite3.connect(f"file:{cad}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            sql = ("SELECT DENOM_SOCIAL, DENOM_COMERC, SETOR_ATIV, UF, "
                   "AUDITOR, SIT FROM cia_aberta "
                   "WHERE REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') = ?")
            if ativo_only:
                sql += " AND SIT = 'ATIVO'"
            sql += " ORDER BY SIT = 'ATIVO' DESC, rowid DESC LIMIT 1"
            row = conn.execute(sql, (digits,)).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def _cad_by_cd_cvm(cd_cvm_raw: str):
        try:
            from data_sources.cvm._db import cad_db_path
            import sqlite3
            cad = cad_db_path()
            if not cad.exists() or not cd_cvm_raw:
                return None
            conn = sqlite3.connect(f"file:{cad}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT DENOM_SOCIAL, DENOM_COMERC, SETOR_ATIV, UF, "
                "AUDITOR, SIT FROM cia_aberta WHERE CD_CVM = ? "
                "ORDER BY SIT = 'ATIVO' DESC, rowid DESC LIMIT 1",
                (str(cd_cvm_raw).strip(),),
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    # bridge.db ticker_map — the ticker's cached identity (CNPJ, CD_CVM,
    # names, sector) from the bridge sync's own FCA→CAD resolution.
    bridge_row = None
    try:
        from data_sources.cvm._db import bridge_db_path
        import sqlite3 as _sq
        bp = bridge_db_path()
        if bp.exists():
            bconn = _sq.connect(f"file:{bp}?mode=ro", uri=True)
            bconn.row_factory = _sq.Row
            brow = bconn.execute(
                "SELECT ticker, cd_cvm, cnpj, trading_name, denom_social, "
                "denom_comerc, sit, setor_ativ FROM ticker_map "
                "WHERE UPPER(ticker) = ? LIMIT 1", (ticker,)).fetchone()
            bconn.close()
            if brow:
                bridge_row = dict(brow)
    except Exception:
        bridge_row = None

    # CNPJ: FCA's, else the bridge's.
    if not header["cnpj"] and bridge_row:
        header["cnpj"] = bridge_row.get("cnpj") or ""
    if not header["cd_cvm"] and bridge_row:
        header["cd_cvm"] = str(bridge_row.get("cd_cvm") or "")

    cad_row = _cad_by_cnpj(header["cnpj"], ativo_only=True)
    if cad_row is None:
        cad_row = _cad_by_cnpj(header["cnpj"], ativo_only=False)
    if cad_row is None and header["cd_cvm"]:
        cad_row = _cad_by_cd_cvm(header["cd_cvm"])
    if cad_row is None and bridge_row and bridge_row.get("cd_cvm"):
        cad_row = _cad_by_cd_cvm(bridge_row["cd_cvm"])
    if cad_row:
        if not header["name"]:
            header["name"] = cad_row.get("DENOM_SOCIAL") or ""
        header["trade_name"] = cad_row.get("DENOM_COMERC") or ""
        if not header["sector"]:
            header["sector"] = cad_row.get("SETOR_ATIV") or ""
        header["uf"] = cad_row.get("UF") or ""
        header["auditor"] = cad_row.get("AUDITOR") or ""
    elif bridge_row:
        # CAD unreachable but the bridge cached the resolution.
        if not header["name"]:
            header["name"] = (bridge_row.get("denom_social")
                              or bridge_row.get("denom_comerc") or "")
        if not header["trade_name"]:
            header["trade_name"] = (bridge_row.get("denom_comerc")
                                    or bridge_row.get("trading_name") or "")
        if not header["sector"]:
            header["sector"] = bridge_row.get("setor_ativ") or ""

    # Last resort — B3 dividends company_info: trading name + the B3
    # listing segment (Nível 2 / NM…) + cd_cvm. No economic sector
    # there, but it fills Identificação when everything else missed.
    try:
        from data_sources.b3.dividends.catalog import connect as _b3div
        import sqlite3 as _sq2
        dconn = _b3div(read_only=True)
        dconn.row_factory = _sq2.Row
        drow = dconn.execute(
            "SELECT trading_name, code_cvm, segment FROM company_info "
            "WHERE ticker = ? LIMIT 1", (ticker,)).fetchone()
        dconn.close()
        if drow:
            if not header["cd_cvm"]:
                header["cd_cvm"] = str(drow["code_cvm"] or "")
            if not header["trade_name"]:
                header["trade_name"] = drow["trading_name"] or ""
            if not header["name"]:
                header["name"] = drow["trading_name"] or ""
            if not header["listing_segment"]:
                header["listing_segment"] = drow["segment"] or ""
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
                # [WebUI v1.5] Aligned with valuation fetchers._get_price_cotahist:
                # market_type=10 (equity spot PVista) + close>0, so an odd
                # market-type record can't become the identity-card price.
                "SELECT close FROM cotahist "
                "WHERE symbol=? AND market_type=10 AND close IS NOT NULL AND close>0 "
                "ORDER BY refdate DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if close_row and close_row["close"] is not None:
                header["last_close"] = float(close_row["close"])
            conn.close()
    except Exception:
        pass

    # ── B3 instruments.db lookup: market name, security category, B3 segment ──
    # [v2.2-header] New — fetches SgmtNm, MktNm, SctyCtgyNm from the B3
    # instruments reference table. Graceful degradation: if instruments.db
    # is not synced, these fields stay empty ("—").
    try:
        from data_sources.b3.api.catalog import connect as b3_connect
        conn = b3_connect("instruments", read_only=True)
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute(
            "SELECT SgmtNm, MktNm, SctyCtgyNm FROM instruments WHERE TckrSymb = ? LIMIT 1",
            (ticker,),
        ).fetchone()
        if row:
            header["b3_segment"] = row["SgmtNm"] or ""
            header["market_name"] = row["MktNm"] or ""
            header["security_category"] = row["SctyCtgyNm"] or ""
        conn.close()
    except Exception:
        pass

    # ── Shares + Market Cap (current values for the identity card) ──
    # [v2.2-header] Fetches current shares from FRE via the calculations
    # shares engine, then computes market_cap = last_close × shares.
    # This makes the header self-contained (works for all dashboards
    # including historical, which doesn't compute ratios).
    try:
        from skills.cvm.calculations.engines.shares import shares_at
        from datetime import date
        today = date.today().isoformat()
        shares = shares_at(company, today)
        if shares and shares > 0:
            header["total_shares"] = shares
            if header["last_close"]:
                header["market_cap"] = shares * header["last_close"]
    except Exception:
        pass

    # ── Formatted strings for the template ──
    if header["last_close"]:
        header["last_close_str"] = f"{header['last_close']:.2f}".replace(".", ",")
    if header["market_cap"]:
        header["market_cap_str"] = _format_compact_brl(header["market_cap"])
    if header["total_shares"]:
        header["total_shares_str"] = _format_compact_shares(header["total_shares"])

    # ── Last synced trimester (e.g. "2T2026") from ITR ──────────────────
    try:
        from skills._freshness import get_last_synced_period
        periods = get_last_synced_period()
        itr_period = periods.get("itr", "")
        if itr_period:
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
