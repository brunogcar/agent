"""
skills/cvm/cvm_shareholders/cvm_shareholders.py -- Shareholder structure from rapina.db.

=== UPGRADE LOG ===
v2 (this version): _resolve_company() is now bridge-aware.
  Identical upgrade pattern as cvm_dividends v2:
  - B3 ticker input -> bridge.db -> (rapina_ids, denom_social)
  - Falls back to CNPJ or name search in rapina.db if bridge unavailable
  Both paths produce the same (ids, name) tuple consumed by _mode_*().

=== DATA MODEL (from inspect_dividends_shareholders.py, confirmed) ===

rapina.db table: empresas
  One row per (company, fiscal_period). Same CNPJ -> multiple ids.
  Columns: id, nome, cnpj (digits only), ano, dt_refer

Two sources for shareholder/equity structure:

  BPP 2.03.* "Patrimonio Liquido" -- quarterly available
    2.03.01  Capital Social Realizado
    2.03.02  Reservas de Capital
    2.03.03  Reservas de Avaliacao (ajustes valor justo, conversao)
    2.03.04  Reservas de Lucros
      2.03.04.01..09  Sub-items -- ALL ZERO for Petrobras (roll up into parent)
                      DECISION: Only query parent 2.03.04, not sub-items.
    2.03.05  Lucros/Prejuizos Acumulados
    2.03.06  Ajustes de Avaliacao Patrimonial
    2.03.09  Participacao dos Acionistas Nao Controladores (minority interest)
    2.03.10  Outros componentes do Patrimonio Liquido
    Total PL = 2.03 (parent code, confirmed present)

  DFC 6.* "Fluxo de Caixa" -- for equity movement context (optional)
    Not queried here -- use cvm_dividends for DFC data.

=== WHAT WE DO NOT USE ===
  BPP 2.03.04.01..09 sub-items: ALL ZERO for Petrobras.
    DECISION: confirmed by inspection. These codes exist in the schema
    but rapina stores 0 for all of them. Use parent 2.03.04 only.
  BPP 2.01.05.02.01 and similar: those are dividend payables,
    handled by cvm_dividends. Shareholders skill focuses on EQUITY structure.

=== MODES ===
  equity_structure -- full PL breakdown: capital, reserves, retained, minority
  minority         -- minority interest (2.03.09) trend over time
  status           -- quick PL snapshot: total equity + key components

=== UNIT ===
Values in rapina.db are in REAIS (not thousands/millions).
Display as billions (/1e9) for large-cap companies.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ── DB connection + resolution (shared helpers) ───────────────────────────────
# DECISION: Import from skills/cvm/_db.py and skills/cvm/_bridge.py.
# No inline copies -- one place to fix if resolution logic changes.

from skills.cvm._db import connect_rapina as _connect_rapina
from skills.cvm._bridge import resolve_company as _resolve_company, looks_like_ticker as _looks_like_ticker


def _connect() -> sqlite3.Connection:
    """Open rapina.db read-only. Wraps _db.connect_rapina() for local use."""
    return _connect_rapina()


# ── Mode: equity_structure (BPP 2.03.*) ──────────────────────────────────────

def _mode_equity_structure(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Full equity (Patrimonio Liquido) breakdown from BPP form 2, code 2.03.*.

    Codes queried (confirmed present in rapina.db for Petrobras):
      2.03      -- Total PL (parent, always present)
      2.03.01   -- Capital Social Realizado
      2.03.02   -- Reservas de Capital
      2.03.03   -- Reservas de Avaliacao
      2.03.04   -- Reservas de Lucros (parent; sub-items 2.03.04.01-09 are ALL ZERO)
      2.03.05   -- Lucros / Prejuizos Acumulados
      2.03.06   -- Ajustes de Avaliacao Patrimonial
      2.03.09   -- Participacao dos Acionistas Nao Controladores (minority)
      2.03.10   -- Outros (catch-all)

    DECISION: We query PARENT codes only (not 2.03.04.01 etc).
    Inspection confirmed sub-items are all zero for Petrobras.
    This may not hold for all companies but the parent 2.03.04 is always
    the correct total regardless of how sub-items are broken out.

    DEDUP: MAX(vl_conta) per (dt_refer, cd_conta) -- same rationale as
    cvm_dividends: rapina may have duplicate imports for restated periods.

    PERIOD ANNOTATION: Dec-31 rows are labeled [anual] for clarity.
    Quarterly rows show the cumulative balance at that quarter-end.
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    # All equity codes we want to fetch
    codes = (
        "2.03", "2.03.01", "2.03.02", "2.03.03",
        "2.03.04", "2.03.05", "2.03.06", "2.03.09", "2.03.10",
    )
    placeholders_ids  = ",".join("?" * len(ids))
    placeholders_codes = ",".join("?" * len(codes))

    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders_ids})
          AND cd_conta IN ({placeholders_codes})
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(
        sql, list(ids) + list(codes) + [periods * len(codes)]
    ).fetchall()

    if not rows:
        return f"{company_name}: sem dados BPP Patrimonio Liquido (2.03.*) no banco."

    # Group by period
    by_period: dict[str, dict[str, float]] = defaultdict(dict)
    # Also store descriptions for display
    descriptions: dict[str, str] = {}
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"] or 0
        descriptions[r["cd_conta"]] = r["ds_conta"] or ""

    lines = [
        f"=== {company_name} -- Estrutura do Patrimonio Liquido (BPP 2.03) ===",
        "Fonte: Balanco Patrimonial Passivo (saldo ao final de cada periodo)",
        "",
    ]

    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]

        label = period
        if period.endswith("-12-31"):
            label = f"{period}  [anual]"

        total      = d.get("2.03",    0)
        capital    = d.get("2.03.01", 0)
        res_cap    = d.get("2.03.02", 0)
        res_aval   = d.get("2.03.03", 0)
        res_lucros = d.get("2.03.04", 0)
        luc_prej   = d.get("2.03.05", 0)
        ajustes    = d.get("2.03.06", 0)
        minority   = d.get("2.03.09", 0)
        outros     = d.get("2.03.10", 0)

        # Minority % of total equity (when total != 0)
        minority_pct = ""
        if total and minority:
            pct = abs(minority) / abs(total) * 100
            minority_pct = f"  ({pct:.1f}% do PL total)"

        lines.append(f"Periodo: {label}")
        lines.append(f"  Total PL                    : R$ {total/1e9:>10.3f} bi")
        lines.append(f"  Capital Social Realizado    : R$ {capital/1e9:>10.3f} bi")
        lines.append(f"  Reservas de Capital         : R$ {res_cap/1e9:>10.3f} bi")
        lines.append(f"  Reservas de Avaliacao       : R$ {res_aval/1e9:>10.3f} bi")
        lines.append(f"  Reservas de Lucros          : R$ {res_lucros/1e9:>10.3f} bi")
        lines.append(f"  Lucros/Prejuizos Acumulados : R$ {luc_prej/1e9:>10.3f} bi")
        if ajustes:
            lines.append(f"  Ajustes Aval. Patrimonial  : R$ {ajustes/1e9:>10.3f} bi")
        lines.append(
            f"  Part. Nao Controladores     : R$ {minority/1e9:>10.3f} bi"
            f"{minority_pct}"
        )
        if outros:
            lines.append(f"  Outros                      : R$ {outros/1e9:>10.3f} bi")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: minority (BPP 2.03.09) ─────────────────────────────────────────────

def _mode_minority(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Minority interest (Participacao dos Acionistas Nao Controladores) trend.

    Code 2.03.09 is the balance sheet value of minority shareholders' claim
    on consolidated equity. It is NON-ZERO only for companies with subsidiaries
    that are not 100% owned (consolidated in the BPP).

    For Petrobras: large minority interest exists because Petrobras Distribuidora
    (BR Distribuidora) and other subsidiaries had minority shareholders.

    DECISION: Show both absolute value AND as % of total PL (2.03) to give
    context. A growing minority % may indicate dilution of controlling interest
    or acquisition of non-100% subsidiaries.

    TREND NOTE: This is a BALANCE SHEET figure (stock, not flow).
    To see changes in minority interest, compare consecutive periods.
    Large swings indicate M&A activity or subsidiary restructuring.
    """
    if not ids:
        return "Empresa nao encontrada."

    placeholders = ",".join("?" * len(ids))

    # Fetch minority (2.03.09) AND total PL (2.03) together for % calculation
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('2.03', '2.03.09')
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC
        LIMIT ?
    """
    rows = conn.execute(sql, list(ids) + [periods * 2]).fetchall()

    if not rows:
        return f"{company_name}: sem dados de participacao de nao controladores (2.03.09)."

    # Group by period
    by_period: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"] or 0

    lines = [
        f"=== {company_name} -- Participacao de Nao Controladores (BPP 2.03.09) ===",
        "Fonte: Balanco Patrimonial Passivo -- saldo do patrimonio de minoritarios",
        "Nota: valor zero indica que nao ha subsidiarias com minoritarios consolidadas.",
        "",
    ]

    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        minority = d.get("2.03.09", 0)
        total_pl = d.get("2.03",    0)

        pct_str = ""
        if total_pl and minority is not None:
            pct = abs(minority) / abs(total_pl) * 100 if total_pl else 0
            pct_str = f"  ({pct:.1f}% do PL total R${total_pl/1e9:.2f}bi)"

        label = period
        if period.endswith("-12-31"):
            label = f"{period}  [anual]"

        lines.append(f"Periodo: {label}")
        lines.append(
            f"  Nao Controladores : R$ {minority/1e9:>10.3f} bi{pct_str}"
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
    Quick shareholder/equity snapshot: latest total PL + key components.

    Shows the most recent available period (quarterly or annual).
    Useful as a quick health check before diving into detailed modes.

    DECISION: mode="status" is the default. It answers "what is this
    company's current equity structure?" without requiring the user to
    know BPP codes or period conventions.
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    placeholders = ",".join("?" * len(ids))

    codes = ("2.03", "2.03.01", "2.03.04", "2.03.05", "2.03.09")
    placeholders_codes = ",".join("?" * len(codes))

    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ({placeholders_codes})
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC
        LIMIT ?
    """
    rows = conn.execute(
        sql, list(ids) + list(codes) + [len(codes) * 4]  # fetch up to 4 recent periods
    ).fetchall()

    if not rows:
        return f"{company_name}: sem dados de Patrimonio Liquido no banco."

    # Find the most recent period that has the total (2.03)
    periods_with_total = sorted(
        set(r["dt_refer"] for r in rows if r["cd_conta"] == "2.03"),
        reverse=True,
    )
    if not periods_with_total:
        return f"{company_name}: codigo 2.03 (total PL) nao encontrado."

    latest = periods_with_total[0]

    # Also get the most recent annual period for comparison
    annual_periods = [p for p in periods_with_total if p.endswith("-12-31")]
    latest_annual = annual_periods[0] if annual_periods else None

    def _val(period: str, code: str) -> float:
        for r in rows:
            if r["dt_refer"] == period and r["cd_conta"] == code:
                return float(r["vl_conta"] or 0)
        return 0.0

    label = latest
    if latest.endswith("-12-31"):
        label = f"{latest}  [anual]"

    lines = [
        f"=== {company_name} -- Status do Patrimonio Liquido ===",
        "",
        f"Periodo mais recente: {label}",
        f"  Total PL                    : R$ {_val(latest, '2.03')/1e9:.3f} bi",
        f"  Capital Social              : R$ {_val(latest, '2.03.01')/1e9:.3f} bi",
        f"  Reservas de Lucros          : R$ {_val(latest, '2.03.04')/1e9:.3f} bi",
        f"  Lucros/Prejuizos Acumulados : R$ {_val(latest, '2.03.05')/1e9:.3f} bi",
        f"  Nao Controladores           : R$ {_val(latest, '2.03.09')/1e9:.3f} bi",
        "",
    ]

    # Show last annual for YoY comparison if different from latest
    if latest_annual and latest_annual != latest:
        lines += [
            f"Ultimo exercicio anual: {latest_annual[:4]}",
            f"  Total PL                    : R$ {_val(latest_annual, '2.03')/1e9:.3f} bi",
            f"  Capital Social              : R$ {_val(latest_annual, '2.03.01')/1e9:.3f} bi",
            f"  Reservas de Lucros          : R$ {_val(latest_annual, '2.03.04')/1e9:.3f} bi",
            f"  Lucros/Prejuizos Acumulados : R$ {_val(latest_annual, '2.03.05')/1e9:.3f} bi",
            f"  Nao Controladores           : R$ {_val(latest_annual, '2.03.09')/1e9:.3f} bi",
            "",
        ]

    return "\n".join(lines)


# ── Public dispatcher ─────────────────────────────────────────────────────────

def cvm_shareholders(
    ticker:  str = "",
    mode:    str = "status",
    periods: int = 5,
) -> dict:
    """
    Query shareholder/equity structure from rapina.db.

    Args:
        ticker:  B3 ticker (e.g. "VALE3"), company name fragment (e.g. "VALE"),
                 or 14-digit CNPJ. Tickers resolved via bridge.db if available.
        mode:    "status"           -- latest PL snapshot (default)
                 "equity_structure" -- full PL breakdown per period
                 "minority"         -- minority interest trend (2.03.09)
        periods: Number of periods to return for equity_structure/minority (default 5).

    Returns:
        dict: status, mode, company, ids, report, data.

    DECISION: Same return shape as cvm_dividends for consistency.
    All skills in the cvm domain return {status, mode, company, ids, report, data}.
    This lets the agent handle errors uniformly across skills.

    Examples:
        cvm_shareholders(ticker="PETR4")
        cvm_shareholders(ticker="VALE", mode="equity_structure", periods=4)
        cvm_shareholders(ticker="ITUB4", mode="minority")
        cvm_shareholders(ticker="60746948000112", mode="status")
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e), "report": str(e), "data": []}

    try:
        ids, company_name = _resolve_company(conn, ticker)

        if not ids:
            from skills.cvm._bridge import not_found_message
            msg = not_found_message(ticker)
            return {
                "status": "not_found",
                "error":  msg,
                "report": msg,
                "data":   [],
            }

        mode_clean = mode.lower().strip()

        if mode_clean == "equity_structure":
            report = _mode_equity_structure(conn, ids, company_name, periods)
        elif mode_clean == "minority":
            report = _mode_minority(conn, ids, company_name, periods)
        elif mode_clean == "status":
            report = _mode_status(conn, ids, company_name)
        else:
            msg = (
                f"Modo '{mode}' invalido. "
                "Use: status | equity_structure | minority"
            )
            return {"status": "error", "error": msg, "report": msg, "data": []}

        return {
            "status":  "success",
            "mode":    mode_clean,
            "company": company_name,
            "ids":     ids,
            "report":  report,
            "data":    [],
        }

    except Exception as e:
        import traceback
        err = f"cvm_shareholders error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        return {"status": "error", "error": err, "report": err, "data": []}

    finally:
        conn.close()
