"""Mode: summary -- combined: top shareholders + free float + latest equity total.

Aggregates data from FRE (shareholders, free_float) + DFP (equity_structure
latest period only). Each section is best-effort — if one data source is
missing, the summary still returns what's available.

Registered as "summary" in skills.cvm.shareholders._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from typing import Any

from skills.cvm.shareholders._registry import register_mode
# Sibling mode functions used to compose the summary. Aliased to avoid
# name clash with the `summary` mode name + to keep call sites short.
from skills.cvm.shareholders.modes.shareholders import shareholders as _shareholders
from skills.cvm.shareholders.modes.free_float import free_float as _free_float
from skills.cvm.shareholders.modes.equity_structure import equity_structure as _equity_structure


@register_mode(
    "summary",
    description="Combined: top shareholders + free float + latest equity total.",
    include_in_all=True,
    params={
        "company": "str. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="shareholders", mode="summary", params=\'{"company":"PETR4"}\')',
    ],
)
def summary(company: str = "") -> dict:
    """Combined summary: top shareholders + free float + latest equity total.

    Aggregates data from FRE (shareholders, free_float) + DFP (equity_structure
    latest period only). Each section is best-effort — if one data source is
    missing, the summary still returns what's available.

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # 1. Top shareholders (FRE) — best-effort
    try:
        sh = _shareholders(company=company, limit=10)
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
        ff = _free_float(company=company)
        if ff.get("status") == "ok" and ff.get("periods"):
            latest = ff["periods"][0]
            pct_ff = latest.get("pct_total_circulacao")
            qtd_pf = latest.get("qtd_acionistas_pf")
            qtd_pj = latest.get("qtd_acionistas_pj")
            qtd_inst = latest.get("qtd_acionistas_inst")

            # [v5] Fallback: if pct_total_circulacao is None (CVM FRE CSV column
            # name mismatch for some years -> stored as NULL), compute it from
            # posicao_acionaria: free_float = 100 - sum(pct_total for all
            # named shareholders). This gives an approximate free float %.
            #
            # [v6] Truncation guard: if shareholders() returned exactly 50 rows
            # (the limit), the sum may be incomplete (there could be more
            # shareholders not fetched). In that case, the computed pct_ff is
            # approximate — we still return it but the dashboard will show
            # a note. This is rare (most companies have <50 named shareholders
            # in a single filing).
            if pct_ff is None:
                try:
                    # [v1.2] Raised limit from 50 to 500 for the fallback sum
                    # (Qwen + Claude finding). The display tab still uses 10,
                    # but the fallback needs a wider net to compute 100 - named
                    # accurately. Most companies have <50 named shareholders,
                    # but complex ownership structures can exceed that.
                    sh = _shareholders(company=company, limit=500)
                    if sh.get("status") == "ok" and sh.get("shareholders"):
                        named_pct = sum(
                            (s.get("pct_total") or 0) for s in sh["shareholders"]
                        )
                        if named_pct > 0:
                            pct_ff = max(0.0, 100.0 - named_pct)
                            # [v6] Flag if the shareholder list was truncated.
                            if len(sh["shareholders"]) >= 500:
                                result["sections"]["_free_float_approximate"] = True
                except Exception:
                    pass

            # [v5] Fallback: if shareholder counts are None, sum from
            # posicao_acionaria isn't possible (it only has named shareholders).
            # Leave as None — the dashboard will show "—".

            result["sections"]["free_float"] = {
                "data_referencia": latest.get("data_referencia", ""),
                "pct_total_circulacao": pct_ff,
                "qtd_acionistas_pf": qtd_pf,
                "qtd_acionistas_pj": qtd_pj,
                "qtd_acionistas_inst": qtd_inst,
            }
        else:
            result["sections"]["free_float"] = {"status": ff.get("status"),
                                                "error": ff.get("error", "")}
    except Exception as e:
        result["sections"]["free_float"] = {"status": "error", "error": str(e)}

    # 3. Latest equity total (DFP BPP 2.03) — best-effort
    try:
        eq = _equity_structure(company=company, periods=1)
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
