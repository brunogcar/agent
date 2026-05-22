"""
skills/cvm/cvm_shareholders/cvm_shareholders.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_shareholders\cvm_shareholders.py

Shareholder/equity structure from rapina.db using CORRECT schema (confirmed 2026-05-21):

=== RAPINA.DB SCHEMA (actual) ===
empresas: id, cnpj, nome, ano
contas:   id_empresa, codigo, descr, grupo, consolidado,
          data_ini_exerc, data_fim_exerc, meses, valor, escala, moeda

Join:  contas.id_empresa = empresas.id
Value: valor * escala  (escala=1000 -> stored in thousands of BRL)
Annual filter: meses=12 (not date suffix -- fiscal year may end any month)

=== BPP 2.03.* CONFIRMED for Petrobras ===
2.03       Patrimonio Liquido Consolidado
2.03.01    Capital Social Realizado
2.03.02    Reservas de Capital
2.03.03    (Reservas de Avaliacao -- if present)
2.03.04    (Reservas de Lucros -- if present)
2.03.05    (Lucros/Prejuizos Acumulados -- if present)
2.03.09    (Participacao Nao Controladores -- if present)

NOTE: BPP rows have meses=12 regardless of quarter-end date.
This is because BPP is a balance sheet (stock, not flow) --
rapina stores it as if it were an annual figure even for quarterly reports.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from skills.cvm._db import connect_rapina as _connect_rapina
from skills.cvm._bridge import resolve_company as _resolve_company


def _connect() -> sqlite3.Connection:
    return _connect_rapina()


def _val(valor, escala) -> float:
    """Return actual BRL. valor * escala (escala usually 1000)."""
    try:
        return float(valor or 0) * float(escala or 1)
    except (TypeError, ValueError):
        return 0.0


# ── Mode: equity_structure (BPP 2.03.*) ──────────────────────────────────────

def _mode_equity_structure(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Full PL breakdown per period from BPP 2.03.*.

    DECISION: No meses filter here -- BPP rows have meses=12 even for
    quarterly reports (balance sheet is always a full-period snapshot).
    We fetch all data_fim_exerc periods and show the last N.

    Codes fetched: 2.03 (total) + children 2.03.01 through 2.03.09.
    Children that are missing (zero or not filed) simply show 0.
    """
    if not ids:
        return "Empresa nao encontrada."

    ph   = ",".join("?" * len(ids))
    # Fetch parent + all likely children
    codes = (
        "2.03", "2.03.01", "2.03.02", "2.03.03",
        "2.03.04", "2.03.05", "2.03.06", "2.03.07",
        "2.03.08", "2.03.09", "2.03.10",
    )
    ph_c = ",".join("?" * len(codes))

    sql = f"""
        SELECT c.data_fim_exerc, c.codigo, c.descr,
               MAX(c.valor) AS valor, MAX(c.escala) AS escala
        FROM contas c
        WHERE c.id_empresa IN ({ph})
          AND c.codigo IN ({ph_c})
          AND c.consolidado = 1
        GROUP BY c.data_fim_exerc, c.codigo
        ORDER BY c.data_fim_exerc DESC, c.codigo
        LIMIT ?
    """
    rows = conn.execute(sql, list(ids) + list(codes) + [periods * len(codes)]).fetchall()

    if not rows:
        return f"{company_name}: sem dados BPP Patrimonio Liquido (2.03.*) no banco."

    by_period: dict[str, dict] = defaultdict(dict)
    descriptions: dict[str, str] = {}
    for r in rows:
        by_period[r["data_fim_exerc"]][r["codigo"]] = (r["valor"], r["escala"])
        descriptions[r["codigo"]] = r["descr"] or ""

    lines = [
        f"=== {company_name} -- Patrimonio Liquido (BPP 2.03) ===",
        "Fonte: BPP -- saldo ao final de cada periodo (consolidado=1).",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]

        def v(code): return _val(*d[code]) if code in d else 0.0

        total    = v("2.03")
        capital  = v("2.03.01")
        res_cap  = v("2.03.02")
        res_aval = v("2.03.03")
        res_luc  = v("2.03.04")
        luc_prej = v("2.03.05")
        ajustes  = v("2.03.06")
        minority = v("2.03.09")

        min_pct = f"  ({abs(minority)/abs(total)*100:.1f}% do PL)" if total and minority else ""

        lines.append(f"Periodo: {period}")
        lines.append(f"  Total PL                    : R$ {total/1e9:>10.3f} bi")
        lines.append(f"  Capital Social Realizado    : R$ {capital/1e9:>10.3f} bi")
        if res_cap:
            lines.append(f"  Reservas de Capital         : R$ {res_cap/1e9:>10.3f} bi")
        if res_aval:
            lines.append(f"  Reservas de Avaliacao       : R$ {res_aval/1e9:>10.3f} bi")
        if res_luc:
            lines.append(f"  Reservas de Lucros          : R$ {res_luc/1e9:>10.3f} bi")
        if luc_prej:
            lines.append(f"  Lucros/Prejuizos Acumulados : R$ {luc_prej/1e9:>10.3f} bi")
        if ajustes:
            lines.append(f"  Ajustes Aval. Patrimonial   : R$ {ajustes/1e9:>10.3f} bi")
        lines.append(f"  Nao Controladores (2.03.09) : R$ {minority/1e9:>10.3f} bi{min_pct}")
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
    Minority interest (2.03.09) vs total equity (2.03) trend.
    Both fetched together for % calculation.
    """
    if not ids:
        return "Empresa nao encontrada."

    ph = ",".join("?" * len(ids))
    sql = f"""
        SELECT c.data_fim_exerc, c.codigo,
               MAX(c.valor) AS valor, MAX(c.escala) AS escala
        FROM contas c
        WHERE c.id_empresa IN ({ph})
          AND c.codigo IN ('2.03', '2.03.09')
          AND c.consolidado = 1
        GROUP BY c.data_fim_exerc, c.codigo
        ORDER BY c.data_fim_exerc DESC
        LIMIT ?
    """
    rows = conn.execute(sql, list(ids) + [periods * 2]).fetchall()

    if not rows:
        return f"{company_name}: sem dados de participacao de nao controladores (2.03.09)."

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["data_fim_exerc"]][r["codigo"]] = (r["valor"], r["escala"])

    lines = [
        f"=== {company_name} -- Nao Controladores (BPP 2.03.09) ===",
        "Fonte: BPP -- saldo do patrimonio de minoritarios.",
        "Nota: valor zero = sem subsidiarias com minoritarios consolidadas.",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        minority = _val(*d["2.03.09"]) if "2.03.09" in d else 0.0
        total    = _val(*d["2.03"])    if "2.03"    in d else 0.0

        pct_str = ""
        if total and minority:
            pct_str = f"  ({abs(minority)/abs(total)*100:.1f}% do PL total R${total/1e9:.2f}bi)"

        lines.append(f"Periodo: {period}")
        lines.append(f"  Nao Controladores : R$ {minority/1e9:>10.3f} bi{pct_str}")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: status ──────────────────────────────────────────────────────────────

def _mode_status(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
) -> str:
    """Latest PL snapshot: total + key components, most recent period."""
    if not ids:
        return "Empresa nao encontrada."

    ph    = ",".join("?" * len(ids))
    codes = ("2.03", "2.03.01", "2.03.04", "2.03.05", "2.03.09")
    ph_c  = ",".join("?" * len(codes))

    sql = f"""
        SELECT c.data_fim_exerc, c.codigo,
               MAX(c.valor) AS valor, MAX(c.escala) AS escala
        FROM contas c
        WHERE c.id_empresa IN ({ph})
          AND c.codigo IN ({ph_c})
          AND c.consolidado = 1
        GROUP BY c.data_fim_exerc, c.codigo
        ORDER BY c.data_fim_exerc DESC
        LIMIT ?
    """
    rows = conn.execute(sql, list(ids) + list(codes) + [len(codes) * 8]).fetchall()

    if not rows:
        return f"{company_name}: sem dados de Patrimonio Liquido no banco."

    # Find most recent period with total PL (2.03)
    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["data_fim_exerc"]][r["codigo"]] = (r["valor"], r["escala"])

    periods_with_total = sorted(
        [p for p in by_period if "2.03" in by_period[p]], reverse=True
    )
    if not periods_with_total:
        return f"{company_name}: codigo 2.03 (total PL) nao encontrado."

    latest = periods_with_total[0]
    annual_periods = [p for p in periods_with_total if
                      any(r["codigo"] == "2.03" and r["data_fim_exerc"] == p and
                          # annual if it appears with meses=12 or is a Dec-31
                          True
                          for r in rows)]
    # Simpler: just pick second most recent as comparison if different
    prev = periods_with_total[1] if len(periods_with_total) > 1 else None

    def v(period, code):
        d = by_period.get(period, {})
        return _val(*d[code]) if code in d else 0.0

    lines = [
        f"=== {company_name} -- Status do Patrimonio Liquido ===",
        "",
        f"Periodo mais recente: {latest}",
        f"  Total PL                    : R$ {v(latest,'2.03')/1e9:.3f} bi",
        f"  Capital Social              : R$ {v(latest,'2.03.01')/1e9:.3f} bi",
        f"  Reservas de Lucros          : R$ {v(latest,'2.03.04')/1e9:.3f} bi",
        f"  Lucros/Prejuizos Acumulados : R$ {v(latest,'2.03.05')/1e9:.3f} bi",
        f"  Nao Controladores           : R$ {v(latest,'2.03.09')/1e9:.3f} bi",
        "",
    ]

    if prev and prev != latest:
        lines += [
            f"Periodo anterior: {prev}",
            f"  Total PL                    : R$ {v(prev,'2.03')/1e9:.3f} bi",
            f"  Capital Social              : R$ {v(prev,'2.03.01')/1e9:.3f} bi",
            f"  Reservas de Lucros          : R$ {v(prev,'2.03.04')/1e9:.3f} bi",
            f"  Lucros/Prejuizos Acumulados : R$ {v(prev,'2.03.05')/1e9:.3f} bi",
            f"  Nao Controladores           : R$ {v(prev,'2.03.09')/1e9:.3f} bi",
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
        ticker:  B3 ticker (VALE3), name fragment (VALE), or CNPJ.
                 Tickers resolved via bridge.db if available.
        mode:    "status"           -- latest PL snapshot (default)
                 "equity_structure" -- full breakdown per period
                 "minority"         -- minority interest trend
        periods: periods to return (default 5)
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
            return {"status": "not_found", "error": msg, "report": msg, "data": []}

        mode_clean = mode.lower().strip()

        if mode_clean == "equity_structure":
            report = _mode_equity_structure(conn, ids, company_name, periods)
        elif mode_clean == "minority":
            report = _mode_minority(conn, ids, company_name, periods)
        elif mode_clean == "status":
            report = _mode_status(conn, ids, company_name)
        else:
            msg = f"Modo '{mode}' invalido. Use: status | equity_structure | minority"
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
