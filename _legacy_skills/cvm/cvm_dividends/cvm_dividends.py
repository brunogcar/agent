"""
skills/cvm/cvm_dividends/cvm_dividends.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_dividends\cvm_dividends.py

Dividend data from dfp_itr.db using the CORRECT schema (confirmed 2026-05-21):

=== dfp_itr.db SCHEMA (actual) ===
empresas: id, cnpj, nome, ano
contas:   id_empresa, codigo, descr, grupo, consolidado,
          data_ini_exerc, data_fim_exerc, meses, valor, escala, moeda

Join:     contas.id_empresa = empresas.id
Value:    valor * escala  (escala=1000 means stored in thousands of BRL)
Annual:   meses=12  (NOT data_fim LIKE '%-12-31' -- fiscal year may end any month)
Codes:    codigo (not cd_conta), valor (not vl_conta), data_fim_exerc (not dt_refer)

=== DATA SOURCES ===
DVA 7.08.04.*  annual declared dividends (meses=12)
  7.08.04    total equity remuneration
  7.08.04.01 JCP (Juros sobre Capital Proprio)
  7.08.04.02 Dividendos declared
  7.08.04.03 Lucros Retidos

DFC 6.03.05 / 6.03.06  cash paid (all meses available, cumulative YTD)
  NOTE: 6.03.05/6.03.06 codes may vary -- dfp_itr DFC uses different numbering.
  We search by descr LIKE '%dividendo%' as fallback if exact codes missing.

BPP 2.01.05.02.01  dividends payable on balance sheet
  2.01.05.02.01  Dividendos e JCP a Pagar  (confirmed present for Petrobras)
  2.01.05.02.02  Dividendo Minimo Obrigatorio a Pagar

=== UNIT ===
valor * escala = BRL. Display /1e9 (billions).
Example: valor=110605000, escala=1000 -> 110,605,000,000 BRL = R$110.6 bi
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ── DB connection (shared helpers) ────────────────────────────────────────────

from skills.cvm._db import connect_dfp_itr as _connect_dfp_itr, cnpj_digits as _cnpj
from skills.cvm._bridge import resolve_company as _resolve_company, looks_like_ticker as _looks_like_ticker


def _connect() -> sqlite3.Connection:
    return _connect_dfp_itr()


# ── Value helper ──────────────────────────────────────────────────────────────

def _val(valor, escala) -> float:
    """Return actual BRL value. dfp_itr stores in units of escala (usually 1000)."""
    try:
        return float(valor or 0) * float(escala or 1)
    except (TypeError, ValueError):
        return 0.0


# ── Mode: annual (DVA 7.08.04.*, meses=12) ───────────────────────────────────

def _mode_annual(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Annual dividends from DVA, codes 7.08.04.*.
    Filter: meses=12 (full fiscal year), consolidado=1.
    Sort: data_fim_exerc DESC to get most recent years first.

    DEDUP: dfp_itr may have multiple rows per (id_empresa, codigo, data_fim_exerc)
    if the company restated. Use MAX(valor) -- latest restatement wins.
    Actually dfp_itr deduplicates on import, but MAX is safe defensive practice.
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados dfp_itr."

    ph = ",".join("?" * len(ids))
    codes = ("7.08.04", "7.08.04.01", "7.08.04.02", "7.08.04.03")
    ph_c  = ",".join("?" * len(codes))

    sql = f"""
        SELECT c.data_fim_exerc, c.codigo, c.descr,
               MAX(c.valor) AS valor, MAX(c.escala) AS escala
        FROM contas c
        WHERE c.id_empresa IN ({ph})
          AND c.codigo IN ({ph_c})
          AND c.meses = 12
          AND c.consolidado = 1
        GROUP BY c.data_fim_exerc, c.codigo
        ORDER BY c.data_fim_exerc DESC, c.codigo
        LIMIT ?
    """
    rows = conn.execute(sql, list(ids) + list(codes) + [periods * len(codes)]).fetchall()

    if not rows:
        return f"{company_name}: sem dados DVA (7.08.04.*) com meses=12."

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["data_fim_exerc"]][r["codigo"]] = (r["valor"], r["escala"])

    lines = [
        f"=== {company_name} -- Dividendos Anuais (DVA 7.08.04) ===",
        "Fonte: DVA (regime de competencia -- valor DECLARADO no exercicio, meses=12)",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]

        def v(code): return _val(*d[code]) if code in d else 0.0

        total    = v("7.08.04")
        jcp      = v("7.08.04.01")
        div      = v("7.08.04.02")
        retained = v("7.08.04.03")

        lines.append(f"Periodo: {period} (anual)")
        lines.append(f"  Total Remuneracao Capitais Proprios : R$ {total/1e9:>10.3f} bi")
        lines.append(f"  JCP (Juros s/ Capital Proprio)      : R$ {jcp/1e9:>10.3f} bi")
        lines.append(f"  Dividendos declarados               : R$ {div/1e9:>10.3f} bi")
        lines.append(f"  Lucros Retidos / Prejuizo           : R$ {retained/1e9:>10.3f} bi")
        if total:
            payout = (jcp + div) / abs(total) * 100
            lines.append(f"  Payout ratio (JCP+Div / Total)      : {payout:.1f}%")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: cash_paid (DFC, dividends paid in cash) ─────────────────────────────

def _mode_cash_paid(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Cash dividends paid from DFC.

    DECISION: Search by descr LIKE '%dividendo%' OR '%jcp%' in grupo='DFC'
    because Petrobras DFC numbering (6.03.05) may not match other companies.
    dfp_itr normalizes grupo to 'DFC' for all cash flow statement items.
    Also try exact codes 6.03.05 and 6.03.06 first.

    Values are negative in DFC (cash outflow) -- use ABS().
    meses=12 for annual; show all periods sorted desc.
    """
    if not ids:
        return "Empresa nao encontrada."

    ph = ",".join("?" * len(ids))

    # Try exact codes first
    sql_exact = f"""
        SELECT c.data_fim_exerc, c.codigo, c.descr, c.meses,
               MAX(ABS(c.valor)) AS valor, MAX(c.escala) AS escala
        FROM contas c
        WHERE c.id_empresa IN ({ph})
          AND c.codigo IN ('6.03.05','6.03.06','6.02.05')
          AND c.consolidado = 1
        GROUP BY c.data_fim_exerc, c.codigo
        ORDER BY c.data_fim_exerc DESC, c.codigo
        LIMIT ?
    """
    rows = conn.execute(sql_exact, list(ids) + [periods * 3]).fetchall()

    # Fallback: search by description in DFC group
    if not rows:
        sql_desc = f"""
            SELECT c.data_fim_exerc, c.codigo, c.descr, c.meses,
                   MAX(ABS(c.valor)) AS valor, MAX(c.escala) AS escala
            FROM contas c
            WHERE c.id_empresa IN ({ph})
              AND c.grupo = 'DFC'
              AND (lower(c.descr) LIKE '%dividendo%'
                   OR lower(c.descr) LIKE '%jcp%'
                   OR lower(c.descr) LIKE '%juros sobre%capital%')
              AND c.consolidado = 1
            GROUP BY c.data_fim_exerc, c.codigo
            ORDER BY c.data_fim_exerc DESC, c.codigo
            LIMIT ?
        """
        rows = conn.execute(sql_desc, list(ids) + [periods * 5]).fetchall()
        source_note = "Nota: usando busca por descricao (codigos DFC variam por empresa)."
    else:
        source_note = ""

    if not rows:
        return (
            f"{company_name}: sem dados DFC de dividendos pagos.\n"
            "Tente mode='annual' (DVA) para dividendos declarados."
        )

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        key = f"{r['data_fim_exerc']}|{r['meses']}"
        by_period[key][r["codigo"]] = {
            "descr": r["descr"], "valor": r["valor"], "escala": r["escala"]
        }

    lines = [
        f"=== {company_name} -- Dividendos Pagos em Caixa (DFC) ===",
        "Fonte: DFC (regime de caixa -- valor PAGO). Valores cumulativos YTD.",
        "Nota: meses=12 = ano completo. 6.02.05 = dividendos RECEBIDOS (nao distribuicoes).",
    ]
    if source_note:
        lines.append(source_note)
    lines.append("")

    count = 0
    for key in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        period, meses = key.split("|")
        d = by_period[key]

        label = f"{period}  [anual]" if meses == "12" else f"{period}  [{meses}m]"
        lines.append(f"Periodo: {label}")

        total_out = 0.0
        for codigo, info in sorted(d.items()):
            v = _val(info["valor"], info["escala"])
            descr = info["descr"][:40]
            if codigo == "6.02.05":
                lines.append(f"  {codigo} {descr:<40}: R$ {v/1e9:>10.3f} bi  (* RECEBIDO)")
            else:
                lines.append(f"  {codigo} {descr:<40}: R$ {v/1e9:>10.3f} bi")
                total_out += v

        if len(d) > 1:
            lines.append(f"  {'Total saida':<45}: R$ {total_out/1e9:>10.3f} bi")
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
    Dividends payable on balance sheet (BPP 2.01.05.02.01).
    Confirmed present for Petrobras. Other companies may use different codes.
    Zero balance is NORMAL -- means liability was cleared in that period.
    """
    if not ids:
        return "Empresa nao encontrada."

    ph = ",".join("?" * len(ids))
    codes = ("2.01.05.02.01", "2.01.05.02.02", "2.01.05.02")
    ph_c  = ",".join("?" * len(codes))

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

    # Fallback: description search
    if not rows:
        sql2 = f"""
            SELECT c.data_fim_exerc, c.codigo, c.descr,
                   MAX(c.valor) AS valor, MAX(c.escala) AS escala
            FROM contas c
            WHERE c.id_empresa IN ({ph})
              AND c.codigo LIKE '2.%'
              AND (lower(c.descr) LIKE '%dividendo%pagar%'
                   OR lower(c.descr) LIKE '%jcp%pagar%')
              AND c.consolidado = 1
            GROUP BY c.data_fim_exerc, c.codigo
            ORDER BY c.data_fim_exerc DESC
            LIMIT ?
        """
        rows = conn.execute(sql2, list(ids) + [periods * 2]).fetchall()
        source_note = "Nota: busca por descricao (estrutura BPP nao padrao)."
    else:
        source_note = ""

    if not rows:
        return (
            f"{company_name}: sem dados BPP de dividendos a pagar (2.01.05.02.01).\n"
            "Esta empresa pode usar estrutura BPP diferente."
        )

    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["data_fim_exerc"]][r["codigo"]] = (r["valor"], r["escala"], r["descr"])

    lines = [
        f"=== {company_name} -- Dividendos a Pagar (BPP 2.01.05.02.01) ===",
        "Fonte: BPP -- saldo do passivo circulante no final do periodo.",
        "AVISO: Saldo R$0 e NORMAL para periodos sem declaracao pendente.",
    ]
    if source_note:
        lines.append(source_note)
    lines.append("")

    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        lines.append(f"Periodo: {period}")
        for codigo in sorted(d.keys()):
            valor, escala, descr = d[codigo]
            v = _val(valor, escala)
            lines.append(f"  {codigo} {descr[:40]:<40}: R$ {v/1e9:>10.3f} bi")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: status ──────────────────────────────────────────────────────────────

def _mode_status(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
) -> str:
    """Quick dividend health summary: latest annual DVA + latest DFC + latest BPP."""
    if not ids:
        return "Empresa nao encontrada."

    ph = ",".join("?" * len(ids))

    def _latest_annual(code: str):
        """Most recent meses=12 row for given codigo."""
        row = conn.execute(f"""
            SELECT data_fim_exerc, MAX(valor) AS valor, MAX(escala) AS escala
            FROM contas
            WHERE id_empresa IN ({ph}) AND codigo=? AND meses=12 AND consolidado=1
            GROUP BY data_fim_exerc ORDER BY data_fim_exerc DESC LIMIT 1
        """, list(ids) + [code]).fetchone()
        if row and row["valor"] is not None:
            return row["data_fim_exerc"], _val(row["valor"], row["escala"])
        return "", 0.0

    def _latest_any(code: str):
        """Most recent row for given codigo (any meses)."""
        row = conn.execute(f"""
            SELECT data_fim_exerc, meses, MAX(ABS(valor)) AS valor, MAX(escala) AS escala
            FROM contas
            WHERE id_empresa IN ({ph}) AND codigo=? AND consolidado=1
            GROUP BY data_fim_exerc ORDER BY data_fim_exerc DESC LIMIT 1
        """, list(ids) + [code]).fetchone()
        if row and row["valor"] is not None:
            return row["data_fim_exerc"], row["meses"], _val(row["valor"], row["escala"])
        return "", 0, 0.0

    # DVA annual
    dva_date, dva_total = _latest_annual("7.08.04")
    dva_jcp = 0.0
    dva_div = 0.0

    if dva_date:
        def _val_at(code, date):
            row = conn.execute(f"""
                SELECT MAX(valor) AS valor, MAX(escala) AS escala FROM contas
                WHERE id_empresa IN ({ph}) AND codigo=? AND data_fim_exerc=?
                  AND meses=12 AND consolidado=1
            """, list(ids) + [code, dva_date]).fetchone()
            return _val(row["valor"], row["escala"]) if row and row["valor"] else 0.0
        dva_jcp = _val_at("7.08.04.01", dva_date)
        dva_div = _val_at("7.08.04.02", dva_date)

    # DFC - try exact code, fallback to description
    dfc_date, dfc_meses, dfc_paid = _latest_any("6.03.05")
    if not dfc_date:
        row = conn.execute(f"""
            SELECT data_fim_exerc, meses, MAX(ABS(valor)) AS valor, MAX(escala) AS escala
            FROM contas
            WHERE id_empresa IN ({ph}) AND grupo='DFC'
              AND (lower(descr) LIKE '%dividendo%pago%' OR lower(descr) LIKE '%dividendo%acionista%')
              AND consolidado=1
            GROUP BY data_fim_exerc ORDER BY data_fim_exerc DESC LIMIT 1
        """, list(ids)).fetchone()
        if row and row["valor"]:
            dfc_date, dfc_meses = row["data_fim_exerc"], row["meses"]
            dfc_paid = _val(row["valor"], row["escala"])

    # BPP payable
    bpp_date, _, bpp_pay = _latest_any("2.01.05.02.01")

    lines = [f"=== {company_name} -- Status de Dividendos ===", ""]

    if dva_date:
        payout_str = ""
        if dva_total:
            pct = (dva_jcp + dva_div) / abs(dva_total) * 100
            payout_str = f"  Payout ratio            : {pct:.1f}%"
        lines += [
            f"[DVA] Ultimo exercicio anual: {dva_date}",
            f"  Total Capitais Proprios : R$ {dva_total/1e9:.3f} bi",
            f"  JCP declarado           : R$ {dva_jcp/1e9:.3f} bi",
            f"  Dividendos declarados   : R$ {dva_div/1e9:.3f} bi",
        ]
        if payout_str:
            lines.append(payout_str)
        lines.append("")
    else:
        lines.append("[DVA] Sem dados de dividendos anuais.\n")

    if dfc_date:
        label = f"{dfc_date} [anual]" if dfc_meses == 12 else f"{dfc_date} [{dfc_meses}m]"
        lines += [
            f"[DFC] Ultimo periodo: {label}",
            f"  Dividendos/JCP pagos    : R$ {dfc_paid/1e9:.3f} bi",
            "",
        ]
    else:
        lines.append("[DFC] Sem dados de pagamento em caixa.\n")

    if bpp_date:
        lines += [
            f"[BPP] Saldo passivo em {bpp_date}",
            f"  Dividendos e JCP a Pagar: R$ {bpp_pay/1e9:.3f} bi",
            "(Saldo zero = passivo liquidado no periodo)" if bpp_pay == 0 else "",
            "",
        ]
    else:
        lines.append("[BPP] Sem passivo de dividendos (2.01.05.02.01 nao encontrado).\n")

    return "\n".join(l for l in lines)


# ── Public dispatcher ─────────────────────────────────────────────────────────

def cvm_dividends(
    ticker:  str = "",
    mode:    str = "status",
    periods: int = 5,
) -> dict:
    """
    Query dividend data from dfp_itr.db.

    Args:
        ticker:  B3 ticker (PETR4), name fragment (PETROBRAS), or CNPJ (14 digits).
                 Tickers resolved via bridge.db if available.
        mode:    "status"    -- quick summary (default)
                 "annual"    -- annual declared DVA 7.08.04.*
                 "cash_paid" -- cash paid DFC
                 "declared"  -- payable BPP 2.01.05.02.01
        periods: years/periods to return (default 5)
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

        if mode_clean == "annual":
            report = _mode_annual(conn, ids, company_name, periods)
        elif mode_clean == "cash_paid":
            report = _mode_cash_paid(conn, ids, company_name, periods)
        elif mode_clean == "declared":
            report = _mode_declared(conn, ids, company_name, periods)
        elif mode_clean == "status":
            report = _mode_status(conn, ids, company_name)
        else:
            msg = f"Modo '{mode}' invalido. Use: status | annual | cash_paid | declared"
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
        err = f"cvm_dividends error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        return {"status": "error", "error": err, "report": err, "data": []}

    finally:
        conn.close()
