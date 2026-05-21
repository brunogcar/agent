"""
skills/cvm/cvm_dividends/cvm_dividends.py -- Dividend data from rapina.db.

=== UPGRADE LOG ===
v2 (this version): _resolve_company() now bridge-aware.
  - If the caller passes a B3 ticker (e.g. "PETR4"), we first try
    bridge.db to get the CNPJ + rapina_ids without any name matching.
  - Falls back to the original name/CNPJ search in rapina.db if:
      a) bridge.db does not exist yet (not synced)
      b) ticker not found in bridge
      c) the argument is clearly not a ticker (has spaces, is a CNPJ, etc.)
  This means cvm_dividends works BOTH with and without the bridge.
  The bridge just makes ticker resolution instant and reliable.

=== DATA MODEL (from inspect_dividends_shareholders.py, confirmed) ===

rapina.db table: empresas
  One row per (company, fiscal_period). Same CNPJ → multiple ids.
  Columns: id, nome, cnpj (digits only), ano, dt_refer

Three sources for dividend data:

  DVA 7.08.04.*  "Remuneracao de Capitais Proprios" -- annual only
    7.08.04.01  JCP (Juros sobre Capital Proprio) -- tax-deductible for company
    7.08.04.02  Dividendos declared in the fiscal year (accrual basis)
    7.08.04.03  Lucros Retidos / Prejuizo do Periodo
    7.08.04.04  Part. Nao Controladores nos Lucros Retidos
    KEY: dt_refer always Dec-31 for annual. Values in REAIS (not thousands).
    Petrobras 2022: declared R$155.9B. 2023: declared R$52.9B.

  DFC 6.03.05 / 6.03.06  "Dividendos pagos" -- quarterly available
    6.03.05  Cash paid to controlling shareholders (negative = outflow)
    6.03.06  Cash paid to non-controlling shareholders
    6.02.05  Dividends RECEIVED from investees -- NOT distributions, skip
    KEY: cumulative YTD. Dec-31 = full year. Use ABS(vl_conta).
    Petrobras 2022: paid R$194.2B (more than declared -- prior-year settling).

  BPP 2.01.05.02.01  "Dividendos e JCP a Pagar" -- quarterly, balance sheet
    Current liability: declared but not yet paid.
    Petrobras Q1-2023: R$0 (paid in prior quarter). Q2-2023: R$30.8B.
    ZERO IS CORRECT for Q1/Q3 -- it means the liability was cleared.
    2.01.05.02.02  "Dividendo Minimo Obrigatorio a Pagar" -- usually 0 for PETR.
    WARNING: This code is Petrobras-specific. Other companies may use
    different BPP sub-codes. Fallback search by ds_conta is included.

=== CNPJ IN rapina.db ===
Stored as digits-only string e.g. "33000167000101".
Strip all non-digits before matching.

=== UNIT ===
All values in rapina.db are in REAIS (not thousands, not millions).
Display as billions (/1e9) for readability of large companies.
For small companies, consider /1e6 (millions) -- future enhancement.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── Shared imports from parent modules (single source of truth)
# DECISION: No inline copies -- single source of truth in parent helpers.
from skills.cvm._db import connect_rapina as _connect_rapina, cnpj_digits as _cnpj
from skills.cvm._bridge import resolve_company as _resolve_company, looks_like_ticker as _looks_like_ticker


# ── DB connection ─────────────────────────────────────────────────────────────
# Shared helpers imported from skills/cvm/_db.py and skills/cvm/_bridge.py

def _connect() -> sqlite3.Connection:
    """Open rapina.db read-only. Wraps _db.connect_rapina() for local use."""
    return _connect_rapina()


# ── Company resolution (bridge-aware) ─────────────────────────────────────────

def _resolve_company(
    conn: sqlite3.Connection,
    ticker_or_name: str,
) -> tuple[list[int], str]:
    """Resolve a company identifier to (rapina_ids, canonical_name).

    Uses the imported resolve_company() from skills.cvm._bridge.
    
    Resolution order:
      1. If looks like a B3 ticker -> try bridge.db first (fast, reliable)
      2. If 14-digit CNPJ -> direct rapina.db query
      3. Name fragment -> LIKE search in rapina.db empresas.nome

    Returns ([], "") if not found.
    """
    # Delegate to shared implementation from skills.cvm._bridge
    return _resolve_company(conn, ticker_or_name)


# ── Mode: annual (DVA 7.08.04.*) ─────────────────────────────────────────────

def _mode_annual(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    years: int,
) -> str:
    """
    Annual dividend declared -- DVA form 7, code 7.08.04.*.

    Filters dt_refer LIKE '%-12-31' to get only annual rows (not YTD quarterly).
    Groups by year and shows total, JCP, dividends, retained earnings.

    DEDUP: MAX(vl_conta) per (dt_refer, cd_conta) because rapina may import
    the same period multiple times (e.g. restatements). MAX picks the latest.

    PAYOUT RATIO: (JCP + Dividends) / Total -- only shown when total != 0.
    For loss years, total is negative so payout is expressed as abs().
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    placeholders = ",".join("?") * len(ids)
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('7.08.04', '7.08.04.01', '7.08.04.02', '7.08.04.03')
          AND dt_refer LIKE '%-12-31'
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(sql, ids + [years * 4]).fetchall()

    if not rows:
        return f"{company_name}: sem dados DVA (7.08.04.*) no banco."

    by_year: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_year[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos Anuais (DVA 7.08.04) ===",
        "Fonte: Demonstracao do Valor Adicionado (regime de competencia -- valor DECLARADO)",
        "",
    ]
    count = 0
    for year in sorted(by_year.keys(), reverse=True):
        if count >= years:
            break
        d = by_year[year]
        total    = d.get("7.08.04",    0) or 0
        jcp      = d.get("7.08.04.01", 0) or 0
        div      = d.get("7.08.04.02", 0) or 0
        retained = d.get("7.08.04.03", 0) or 0
        lines.append(f"Ano: {year[:4]}")
        lines.append(f"  Total Remuneracao Capitais Proprios : R$ {total/1e9:>10.3f} bi")
        lines.append(f"  JCP (Juros s/ Capital Proprio)      : R$ {jcp/1e9:>10.3f} bi")
        lines.append(f"  Dividendos declarados               : R$ {div/1e9:>10.3f} bi")
        lines.append(f"  Lucros Retidos / Prejuizo           : R$ {retained/1e9:>10.3f} bi")
        if total != 0:
            payout = (jcp + div) / abs(total) * 100
            lines.append(f"  Payout ratio (JCP+Div / Total)      : {payout:.1f}%")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: cash_paid (DFC 6.03.05 / 6.03.06) ──────────────────────────────────

def _mode_cash_paid(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Cash dividends actually paid -- DFC form 6, code 6.03.05 and 6.03.06.

    6.03.05  = paid to controlling shareholders (NEGATIVE in DFC -- outflow)
    6.03.06  = paid to non-controlling (minority) shareholders
    6.02.05  = dividends RECEIVED from investees (NOT a distribution -- informational)

    We use ABS() because DFC convention stores outflows as negative values.
    Rows are cumulative YTD within each fiscal year:
      Dec-31 row = full year total (most useful)
      Sep-30 row = Jan-Sep cumulative

    DECISION: Show all periods including quarters. The analyst can read
    the Dec-31 row for annual comparisons. We do NOT subtract quarters
    to get discrete Q values -- the raw DFC as-filed is the standard.
    """
    if not ids:
        return "Empresa nao encontrada."

    placeholders = ",".join("?") * len(ids)
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(ABS(vl_conta)) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('6.03.05', '6.03.06', '6.02.05')
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(sql, ids + [periods * 3]).fetchall()

    if not rows:
        return f"{company_name}: sem dados DFC (6.03.05/6.03.06) no banco."

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos Pagos em Caixa (DFC 6.03) ===",
        "Fonte: Demonstracao dos Fluxos de Caixa (regime de caixa -- valor PAGO)",
        "Nota: valores cumulativos YTD. Linha Dec-31 = ano completo.",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        paid_ctrl = d.get("6.03.05", 0) or 0
        paid_min  = d.get("6.03.06", 0) or 0
        received  = d.get("6.02.05", 0) or 0
        total_out = paid_ctrl + paid_min

        # Annotate Dec-31 as annual
        label = period
        if period.endswith("-12-31"):
            label = f"{period}  [anual]"

        lines.append(f"Periodo: {label}")
        lines.append(f"  Pago a controladores     : R$ {paid_ctrl/1e9:>10.3f} bi")
        lines.append(f"  Pago a nao controladores : R$ {paid_min/1e9:>10.3f} bi")
        lines.append(f"  Total saida de caixa     : R$ {total_out/1e9:>10.3f} bi")
        if received:
            # Informational only -- this is money coming IN from subsidiaries
            lines.append(
                f"  Dividendos recebidos *   : R$ {received/1e9:>10.3f} bi"
                f"  (* recebidos de coligadas, nao distribuicoes)"
            )
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: declared (BPP 2.01.05.02.01) ───────────────────────────────────────

def _mode_declared(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Dividends payable on balance sheet -- BPP form 2, code 2.01.05.02.01.

    This is the OUTSTANDING LIABILITY at period-end: amounts declared
    by the board but not yet remitted to shareholders.

    IMPORTANT: Zero is a valid and EXPECTED value for many periods.
    Petrobras typically declares dividends mid-year (Q2/Q4) and pays
    them the same quarter. So Q1 and Q3 balance sheet often shows R$0.
    This is NOT missing data -- it means the liability was cleared.

    FALLBACK: If 2.01.05.02.01 returns no rows, try a description-based
    search for companies with non-standard BPP structure. This broadens
    coverage to companies that use different sub-codes.

    STRUCTURAL LIMITATION: Code 2.01.05.02.01 is tied to Petrobras's
    specific BPP layout. Other companies may classify dividends payable
    under 2.01.05.02, 2.01.04.08, or custom codes. The fallback helps
    but cannot guarantee coverage for all companies.
    """
    if not ids:
        return "Empresa nao encontrada."

    placeholders = ",".join("?") * len(ids)

    # Primary query: known exact codes
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('2.01.05.02.01', '2.01.05.02.02', '2.01.05.02')
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(sql, ids + [periods * 3]).fetchall()

    if not rows:
        # Fallback: description-based search for non-standard BPP structure
        sql2 = f"""
            SELECT dt_refer, cd_conta, ds_conta, MAX(vl_conta) AS vl_conta
            FROM empresas
            WHERE id IN ({placeholders})
              AND cd_conta LIKE '2.%'
              AND (lower(ds_conta) LIKE '%dividendo%pagar%'
                   OR lower(ds_conta) LIKE '%jcp%pagar%'
                   OR lower(ds_conta) LIKE '%juros%capital%pagar%')
            GROUP BY dt_refer, cd_conta
            ORDER BY dt_refer DESC
            LIMIT ?
        """
        rows = conn.execute(sql2, ids + [periods * 2]).fetchall()
        source_note = "Nota: usando busca por descricao (estrutura BPP nao padrao detectada)."
    else:
        source_note = ""

    if not rows:
        return (
            f"{company_name}: sem dados BPP de dividendos a pagar.\n"
            "Esta empresa pode usar estrutura BPP diferente da padrao (2.01.05.02.01).\n"
            "Experimente mode='annual' (DVA) ou mode='cash_paid' (DFC) para dados alternativos."
        )

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos a Pagar (BPP 2.01.05.02.01) ===",
        "Fonte: Balanco Patrimonial Passivo -- saldo do passivo circulante no final do periodo",
        "AVISO: Saldo R$0 e NORMAL para Q1/Q3 -- indica que o passivo foi liquidado no periodo.",
        "AVISO: Codigo 2.01.05.02.01 e especifico de certas empresas (ex: Petrobras).",
    ]
    if source_note:
        lines.append(source_note)
    lines.append("")

    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        payable   = d.get("2.01.05.02.01", 0) or 0
        mandatory = d.get("2.01.05.02.02", 0) or 0
        parent    = d.get("2.01.05.02",    0) or 0

        label = period
        if period.endswith("-12-31"):
            label = f"{period}  [anual]"

        lines.append(f"Periodo: {label}")
        lines.append(f"  Dividendos e JCP a Pagar : R$ {payable/1e9:>10.3f} bi")
        if mandatory:
            lines.append(
                f"  Div. Minimo Obrigatorio  : R$ {mandatory/1e9:>10.3f} bi"
            )
        if parent and parent != payable:
            lines.append(
                f"  Total Outros Passivos    : R$ {parent/1e9:>10.3f} bi"
            )
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: status ──────────────────────────────────────────────────────────────

def _mode_status(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
) -> str:
    """
    Quick dividend health summary combining DVA, DFC, and BPP.

    Answers: "Is this company paying dividends and how much?"
    Shows latest available data point from each source.

    DECISION: mode="status" is the default because it requires no domain
    knowledge from the user. They just call cvm_dividends(ticker="PETR4")
    and get a useful overview without needing to know DVA vs DFC vs BPP.
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    placeholders = ",".join("?") * len(ids)

    def _latest(code: str, annual_only: bool = False) -> tuple[str, float]:
        """Return (dt_refer, abs_value) for most recent row with given code."""
        date_filter = "AND dt_refer LIKE '%-12-31'" if annual_only else ""
        sql = f"""
            SELECT dt_refer, MAX(ABS(vl_conta)) AS vl
            FROM empresas
            WHERE id IN ({placeholders})
              AND cd_conta = ?
              {date_filter}
            GROUP BY dt_refer
            ORDER BY dt_refer DESC
            LIMIT 1
        """
        row = conn.execute(sql, ids + [code]).fetchone()
        if row and row["vl"] is not None:
            return row["dt_refer"], float(row["vl"])
        return "", 0.0

    # DVA annual -- declared
    dva_date,  dva_total = _latest("7.08.04",    annual_only=True)
    _,         dwa_jcp   = _latest("7.08.04.01", annual_only=True)
    _,         dva_div   = _latest("7.08.04.02", annual_only=True)

    # DFC -- cash paid (most recent period, could be quarterly)
    dfc_date,  dfc_ctrl  = _latest("6.03.05")
    _,         dfc_min   = _latest("6.03.06")

    # BPP -- payable balance
    bpp_date,  bpp_pay   = _latest("2.01.05.02.01")

    lines = [
        f"=== {company_name} -- Status de Dividendos ===",
        "",
    ]

    if dva_date:
        payout_str = ""
        if dva_total:
            payout = (dwa_jcp + dva_div) / abs(dva_total) * 100
            payout_str = f"  Payout ratio            : {payout:.1f}%%\n"
        lines.append(f"[DVA] Ultimo exercicio anual: {dva_date[:4]}")
        lines.append(f"  Total Capitais Proprios : R$ {dva_total/1e9:.3f} bi")
        lines.append(f"  JCP declarado           : R$ {dwa_jcp/1e9:.3f} bi")
        lines.append(f"  Dividendos declarados   : R$ {dva_div/1e9:.3f} bi")
        if payout_str:
            lines.append(payout_str.rstrip())
        lines.append("")
    else:
        lines.append("[DVA] Sem dados de dividendos declarados.\n")

    if dfc_date:
        total_paid = dfc_ctrl + dfc_min
        label = f"{dfc_date} [anual]" if dfc_date.endswith("-12-31") else dfc_date
        lines.append(f"[DFC] Ultimo periodo com dados: {label}")
        lines.append(f"  Pago a controladores    : R$ {dfc_ctrl/1e9:.3f} bi")
        lines.append(f"  Pago a nao controladores: R$ {dfc_min/1e9:.3f} bi")
        lines.append(f"  Total saida de caixa    : R$ {total_paid/1e9:.3f} bi")
        lines.append("")
    else:
        lines.append("[DFC] Sem dados de pagamento em caixa.\n")

    if bpp_date:
        label = f"{bpp_date} [anual]" if bpp_date.endswith("-12-31") else bpp_date
        lines.append(f"[BPP] Saldo passivo em {label}")
        lines.append(f"  Dividendos e JCP a Pagar: R$ {bpp_pay/1e9:.3f} bi")
        if bpp_pay == 0:
            lines.append(
                "  (Saldo zero: passivo liquidado no periodo -- normal para Q1/Q3)"
            )
        lines.append("")
    else:
        lines.append(
            "[BPP] Sem passivo de dividendos registrado "
            "(codigo 2.01.05.02.01 nao encontrado para esta empresa).\n"
        )

    return "\n".join(lines)


# ── Public dispatcher ─────────────────────────────────────────────────────────

def cvm_dividends(
    ticker:  str = "",
    mode:    str = "status",
    periods: int = 5,
) -> dict:
    """
    Query dividend data from rapina.db for a Brazilian listed company.

    Args:
        ticker:  B3 ticker (e.g. "PETR4"), company name fragment (e.g. "PETROBRAS"),
                 or 14-digit CNPJ. Tickers are resolved via bridge.db if available.
        mode:    "status"    -- quick summary: latest DVA + DFC + BPP (default)
                 "annual"    -- annual declared (DVA 7.08.04.*), last N years
                 "cash_paid" -- cash actually paid (DFC 6.03.05/06), last N periods
                 "declared"  -- dividends payable on BPP (2.01.05.02.01), last N periods
        periods: Number of years/periods to return for annual/cash_paid/declared (default 5).

    Returns:
        dict: status, mode, company, report (human-readable), data (list, future use).

    DECISION: Returns a human-readable "report" string as the primary output.
    This is ready for display, memory storage, or agent synthesis without
    any post-processing. The "data" list is reserved for future structured output.

    Examples:
        cvm_dividends(ticker="PETR4")               # quick status via bridge
        cvm_dividends(ticker="PETROBRAS", mode="annual", periods=5)
        cvm_dividends(ticker="VALE3", mode="cash_paid")
        cvm_dividends(ticker="33000167000101", mode="declared")
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e), "report": str(e), "data": []}

    try:
        ids, company_name = _resolve_company(conn, ticker)

        if not ids:
            # Give a helpful error distinguishing ticker-not-in-bridge from
            # company-genuinely-not-found
            from skills.cvm._bridge import not_found_message
            msg = not_found_message(ticker)
            return {
                "status": "not_found",
                "error":  msg,
                "report": msg,
                "data":   [],
            }

        mode_clean = mode.lower().strip()

        if mode_clean == "annual":
            report = _mode_annual(conn, ids, company_name, periods)
        elif mode_clean == "cash_paid":
            report = _mode_cash_paid(conn, ids, company_name, periods)
        elif mode_clean == "declared":
            report = _mode_declared(conn, ids, company_name, periods)
        elif mode_clean == "status":
            report = _mode_status(conn, ids, company_name)
        else:
            msg = (
                f"Modo '{mode}' invalido. "
                "Use: status | annual | cash_paid | declared"
            )
            return {"status": "error", "error": msg, "report": msg, "data": []}

        return {
            "status":  "success",
            "mode":    mode_clean,
            "company": company_name,
            "ids":     ids,        # expose for debugging / chaining with other skills
            "report":  report,
            "data":    [],         # reserved for structured output in a future version
        }

    except Exception as e:
        import traceback
        err = f"cvm_dividends error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        return {"status": "error", "error": err, "report": err, "data": []}

    finally:
        conn.close()
