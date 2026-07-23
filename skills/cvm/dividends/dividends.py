"""skills/cvm/dividends/dividends.py -- Dividend skill combining B3 + DFP + IPE.

Combines three data sources:
  1. B3 dividends   -- individual events (rate, dates, label Dividendo/JCP)
  2. DFP DVA 7.08.* -- annual declared totals (Dividendos + JCP per fiscal year)
  3. CVM IPE        -- official regulatory filings (announcements)

MODES
-----
  history       -- individual dividend events from B3 (rate, dates, label)
  annual        -- annual declared totals from DFP DVA 7.08.04.* per fiscal year
  payable       -- dividends declared but not yet paid (DFP BPP 2.01.05.02.01)
  announcements -- official IPE filings (keyword "dividendo")
  summary       -- combined: recent events + annual trend + last payable

RESOLUTION
----------
  - history / announcements: accept `company` (ticker for B3, ticker/name/CNPJ for IPE)
  - annual / payable: accept `company` (ticker/name/CNPJ via bridge → DFP)
  - summary: accepts `company` (ticker preferred — covers all 3 sources)

NO SYNC
-------
Read-only. Assumes dividends.db + dfp.db + ipe.db are already synced.
"""

from __future__ import annotations

from typing import Any


# ── Mode: history (B3 dividends) ─────────────────────────────────────────────

def history(company: str = "", limit: int = 50) -> dict:
    """Individual dividend events from B3 (cash dividends).

    Returns: rate, approved_on, payment_date, last_date_prior, label, related_to.
    The label field distinguishes Dividendo vs JCP (Juros sobre Capital Próprio).

    Delegates to data_sources.b3.dividends.query_engine.dividends.
    """
    if not company:
        return {"status": "error", "error": "company (ticker) is required"}

    from data_sources.b3.dividends.query_engine import dividends as b3_dividends
    return b3_dividends(ticker=company, limit=limit)


# ── Mode: annual (DFP DVA 7.08.04.*) ─────────────────────────────────────────

def annual(company: str = "", periods: int = 5) -> dict:
    """Annual declared dividend totals from DFP DVA 7.08.04.* per fiscal year.

    DVA codes:
      7.08.04     Remuneração de Capitais Próprios (total)
      7.08.04.01  Juros sobre Capital Próprio (JCP)
      7.08.04.02  Dividendos
      7.08.04.03  Lucros Retidos / Prejuízos do Exercício

    Returns: per fiscal year, Dividendos + JCP + total in BRL.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, parse_escala
    from data_sources.cvm._bridge import resolve_company

    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        # DVA 7.08.04.* codes
        codes = ["7.08.04", "7.08.04.01", "7.08.04.02", "7.08.04.03"]
        placeholders_ids = ",".join("?" * len(empresa_ids))
        placeholders_codes = ",".join("?" * len(codes))

        # Get last N distinct fiscal years
        year_rows = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND codigo IN ({placeholders_codes})
                AND meses=12
                ORDER BY data_fim_exerc DESC LIMIT ?""",
            (*empresa_ids, *codes, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found",
                    "error": f"No DVA 7.08.04.* dividend data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        placeholders_dates = ",".join("?" * len(target_dates))

        rows = conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND codigo IN ({placeholders_codes})
                AND meses=12
                AND data_fim_exerc IN ({placeholders_dates})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, *target_dates),
        ).fetchall()

        code_labels = {
            "7.08.04": "Remuneração de Capitais Próprios (total)",
            "7.08.04.01": "Juros sobre Capital Próprio (JCP)",
            "7.08.04.02": "Dividendos",
            "7.08.04.03": "Lucros Retidos / Prejuízos do Exercício",
        }

        periods_data: dict[str, dict] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = {}
            # [v1.0.1] parse_escala handles "MIL", "MILHOES", "UNIDADE" strings
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key][r["codigo"]] = {
                "label": code_labels.get(r["codigo"], r["descricao"]),
                "valor_brl": valor_brl,
            }

        return {
            "status": "ok",
            "company": company_name,
            "periods": [
                {"data_fim_exerc": date, "accounts": periods_data[date]}
                for date in sorted(periods_data.keys(), reverse=True)
            ],
        }
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()


# ── Mode: payable (DFP BPP 2.01.05.02.01) ────────────────────────────────────

def payable(company: str = "", periods: int = 5) -> dict:
    """Dividends declared but not yet paid (DFP BPP 2.01.05.02.01).

    Balance sheet liability: "Dividendos e JCP a Pagar" — shows the amount
    declared but still owed to shareholders as of the balance sheet date.

    Returns: per fiscal year, the payable amount in BRL.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, parse_escala
    from data_sources.cvm._bridge import resolve_company

    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        placeholders_ids = ",".join("?" * len(empresa_ids))

        # BPP 2.01.05.02.01 (Dividendos e JCP a Pagar) + 2.01.05.02.02 (mínimo obrigatório)
        rows = conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND (codigo LIKE '2.01.05.02.01%' OR codigo LIKE '2.01.05.02.02%')
                AND meses=12
                ORDER BY data_fim_exerc DESC
                LIMIT ?""",
            (*empresa_ids, periods * 2),
        ).fetchall()

        if not rows:
            return {"status": "not_found",
                    "error": f"No BPP 2.01.05.02.* payable data found for '{company}'"}

        periods_data: dict[str, list] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = []
            # [v1.0.1] parse_escala handles "MIL", "MILHOES", "UNIDADE" strings
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key].append({
                "codigo": r["codigo"],
                "descricao": r["descricao"],
                "valor_brl": valor_brl,
            })

        return {
            "status": "ok",
            "company": company_name,
            "periods": [
                {"data_fim_exerc": date, "accounts": periods_data[date]}
                for date in sorted(periods_data.keys(), reverse=True)
            ],
        }
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()


# ── Mode: announcements (CVM IPE) ────────────────────────────────────────────

def announcements(company: str = "", limit: int = 20) -> dict:
    """Official CVM IPE filings related to dividends.

    Searches IPE for events with keyword "dividendo" (case-insensitive) in the
    assunto (subject) field. Also accepts company filter.

    Delegates to data_sources.cvm.ipe.query_engine.query.
    """
    from data_sources.cvm.ipe.query_engine import query as ipe_query
    return ipe_query(company=company, keyword="dividendo", limit=limit)


# ── Mode: summary (combined) ─────────────────────────────────────────────────

def summary(company: str = "") -> dict:
    """Combined: recent dividend events + annual trend + last payable.

    Aggregates from B3 (history) + DFP (annual, payable). Each section is
    best-effort — if a data source is missing, the summary still returns
    what's available.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # 1. Recent dividend events (B3) — best-effort
    try:
        hist = history(company=company, limit=10)
        if hist.get("status") == "ok":
            result["sections"]["recent_events"] = {
                "ticker": hist.get("ticker", ""),
                "count": hist.get("count", 0),
                "events": hist.get("dividends", [])[:5],
            }
        else:
            result["sections"]["recent_events"] = {"status": hist.get("status"),
                                                   "error": hist.get("error", "")}
    except Exception as e:
        result["sections"]["recent_events"] = {"status": "error", "error": str(e)}

    # 2. Annual declared totals (DFP DVA) — best-effort
    try:
        ann = annual(company=company, periods=3)
        if ann.get("status") == "ok":
            result["sections"]["annual_trend"] = {
                "company": ann.get("company", ""),
                "periods": ann.get("periods", []),
            }
        else:
            result["sections"]["annual_trend"] = {"status": ann.get("status"),
                                                  "error": ann.get("error", "")}
    except Exception as e:
        result["sections"]["annual_trend"] = {"status": "error", "error": str(e)}

    # 3. Latest payable (DFP BPP) — best-effort
    try:
        pay = payable(company=company, periods=1)
        if pay.get("status") == "ok" and pay.get("periods"):
            result["sections"]["payable"] = pay["periods"][0]
        else:
            result["sections"]["payable"] = {"status": pay.get("status"),
                                             "error": pay.get("error", "")}
    except Exception as e:
        result["sections"]["payable"] = {"status": "error", "error": str(e)}

    return result
