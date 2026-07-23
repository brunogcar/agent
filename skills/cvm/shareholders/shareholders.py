"""skills/cvm/shareholders/shareholders.py -- Shareholder + equity structure skill.

Combines two CVM data sources:
  1. FRE posicao_acionaria + distribuicao_capital -- named shareholders, free float
  2. DFP BPP 2.03.*                                -- equity structure in BRL

MODES
-----
  shareholders  -- named shareholders with ownership % (FRE)
  free_float     -- free float % + shareholder counts (FRE)
  equity_structure -- equity breakdown in BRL over N periods (DFP BPP)
  summary        -- combined: top shareholders + free float + equity total

RESOLUTION
----------
All modes accept `company` (B3 ticker, name fragment, or CNPJ). The underlying
data_source query engines call resolve_company() with auto_sync=True, so the
first query for a new ticker auto-syncs the bridge transparently.

NO SYNC
-------
This skill is read-only. It assumes fre.db + dfp.db are already synced.
If they're not, queries return not_synced / not_found.
"""

from __future__ import annotations

from typing import Any


# ── Mode: shareholders (FRE posicao_acionaria) ───────────────────────────────

def shareholders(company: str = "", limit: int = 50) -> dict:
    """Query named shareholders with ownership % from FRE.

    Delegates to data_sources.cvm.fre.query_engine.shareholders.
    Returns: list of shareholders (name, CNPJ/CPF, ON/PN/total %, controlling).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.fre.query_engine import shareholders as fre_shareholders
    return fre_shareholders(company=company, limit=limit)


# ── Mode: free_float (FRE distribuicao_capital) ──────────────────────────────

def free_float(company: str = "") -> dict:
    """Query free float % + shareholder counts from FRE.

    Delegates to data_sources.cvm.fre.query_engine.free_float.
    Returns: circulation % (ON/PN/total), shareholder counts (PF/PJ/inst).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.fre.query_engine import free_float as fre_free_float
    return fre_free_float(company=company)


# ── Mode: equity_structure (DFP BPP 2.03.*) ──────────────────────────────────

def equity_structure(company: str = "", periods: int = 5) -> dict:
    """Query equity structure breakdown from DFP BPP 2.03.* over N periods.

    Returns total equity + components (capital social, reservas, lucros
    acumulados, minority interest) in BRL for the last N fiscal years.

    Codes (BPP 2.03.*):
      2.03      Patrimônio Líquido (total)
      2.03.01   Capital Social Realizado
      2.03.02   Reservas de Capital
      2.03.04   Reservas de Lucros
      2.03.05   Lucros/Prejuízos Acumulados
      2.03.09   Participação Não Controladores (minority interest)
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

        # [v1.2.1] CNPJ may be formatted in dfp.db — use REPLACE for robust match
        # resolve_company already handles this, so empresa_ids are correct.

        # BPP 2.03.* codes to fetch
        codes = ["2.03", "2.03.01", "2.03.02", "2.03.04", "2.03.05", "2.03.09"]
        placeholders_ids = ",".join("?" * len(empresa_ids))
        placeholders_codes = ",".join("?" * len(codes))

        # Get the last N distinct fiscal years (by data_fim_exerc)
        year_rows = conn.execute(
            f"SELECT DISTINCT data_fim_exerc FROM contas "
            f"WHERE id_empresa IN ({placeholders_ids}) "
            f"AND codigo IN ({placeholders_codes}) "
            f"AND meses=12 "
            f"ORDER BY data_fim_exerc DESC LIMIT ?",
            (*empresa_ids, *codes, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found",
                    "error": f"No BPP 2.03.* equity data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        placeholders_dates = ",".join("?" * len(target_dates))

        # Fetch all rows for those dates
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

        # Organize by period
        periods_data: dict[str, dict] = {}
        code_labels = {
            "2.03": "Patrimônio Líquido Total",
            "2.03.01": "Capital Social Realizado",
            "2.03.02": "Reservas de Capital",
            "2.03.04": "Reservas de Lucros",
            "2.03.05": "Lucros/Prejuízos Acumulados",
            "2.03.09": "Participação Não Controladores",
        }

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


# ── Mode: summary (combined) ─────────────────────────────────────────────────

def summary(company: str = "") -> dict:
    """Combined summary: top shareholders + free float + latest equity total.

    Aggregates data from FRE (shareholders, free_float) + DFP (equity_structure
    latest period only). Each section is best-effort — if one data source is
    missing, the summary still returns what's available.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # 1. Top shareholders (FRE) — best-effort
    try:
        sh = shareholders(company=company, limit=10)
        if sh.get("status") == "ok":
            result["sections"]["shareholders"] = {
                "data_referencia": sh.get("data_referencia", ""),
                "cnpj": sh.get("cnpj", ""),
                "top": sh.get("shareholders", [])[:5],
            }
        else:
            result["sections"]["shareholders"] = {"status": sh.get("status"),
                                                  "error": sh.get("error", "")}
    except Exception as e:
        result["sections"]["shareholders"] = {"status": "error", "error": str(e)}

    # 2. Free float (FRE) — best-effort
    try:
        ff = free_float(company=company)
        if ff.get("status") == "ok" and ff.get("periods"):
            latest = ff["periods"][0]
            result["sections"]["free_float"] = {
                "data_referencia": latest.get("data_referencia", ""),
                "pct_total_circulacao": latest.get("pct_total_circulacao"),
                "qtd_acionistas_pf": latest.get("qtd_acionistas_pf"),
                "qtd_acionistas_pj": latest.get("qtd_acionistas_pj"),
                "qtd_acionistas_inst": latest.get("qtd_acionistas_inst"),
            }
        else:
            result["sections"]["free_float"] = {"status": ff.get("status"),
                                                "error": ff.get("error", "")}
    except Exception as e:
        result["sections"]["free_float"] = {"status": "error", "error": str(e)}

    # 3. Latest equity total (DFP BPP 2.03) — best-effort
    try:
        eq = equity_structure(company=company, periods=1)
        if eq.get("status") == "ok" and eq.get("periods"):
            latest = eq["periods"][0]
            accounts = latest.get("accounts", {})
            total_pl = accounts.get("2.03", {}).get("valor_brl", 0)
            minority = accounts.get("2.03.09", {}).get("valor_brl", 0)
            result["sections"]["equity"] = {
                "data_fim_exerc": latest.get("data_fim_exerc", ""),
                "patrimonio_liquido_total": total_pl,
                "minority_interest": minority,
                "components": {k: v["valor_brl"] for k, v in accounts.items()},
            }
        else:
            result["sections"]["equity"] = {"status": eq.get("status"),
                                            "error": eq.get("error", "")}
    except Exception as e:
        result["sections"]["equity"] = {"status": "error", "error": str(e)}

    return result
