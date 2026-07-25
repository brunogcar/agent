"""adapters/insider.py — Flatten insider skill JSON → table data.

Adapters:
  insider_history   — recent transactions table (date, role, type, qty, price, volume)
  insider_by_role   — per-role summary table (bought/sold/net per role)
  insider_summary   — monthly net buy/sell table + KPI strip (sentiment)
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


@register_adapter("insider_history")
def history(result: dict) -> dict:
    """Flatten insider.history result into a transactions table."""
    if not _ok(result):
        return _error_table(result, title="Insider History")

    movements = result.get("movements") or []
    if not movements:
        return _error_table(result, title="Insider History")

    columns = ["Data", "Cargo", "Tipo", "Ativo", "Qtd", "Preço", "Volume", "Descrição"]
    rows = []
    for m in movements:
        rows.append([
            m.get("Data_Movimentacao", ""),
            m.get("Tipo_Cargo", ""),
            m.get("Tipo_Movimentacao", ""),
            m.get("Tipo_Ativo", ""),
            m.get("Quantidade"),
            m.get("Preco_Unitario"),
            m.get("Volume"),
            m.get("Descricao_Movimentacao", ""),
        ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Insider Transactions ({len(movements)} recent)",
            "columns": columns,
            "rows": rows,
            "formats": {
                "Data": "text", "Cargo": "text", "Tipo": "text",
                "Ativo": "text", "Qtd": "num", "Preço": "brl_full",
                "Volume": "brl", "Descrição": "text",
            },
        }],
        "kpis": [],
        "sources": [],
    }


@register_adapter("insider_by_role")
def by_role(result: dict) -> dict:
    """Flatten insider.by_role result into a per-role summary table."""
    if not _ok(result):
        return _error_table(result, title="Insider by Role")

    roles = result.get("by_role") or []
    if not roles:
        return _error_table(result, title="Insider by Role")

    columns = ["Cargo", "Transações", "Qtd Comprada", "Qtd Vendida",
               "Volume Comprado", "Volume Vendido", "Net Volume", "Início", "Fim"]
    rows = []
    for r in roles:
        vol_bought = r.get("volume_bought") or 0
        vol_sold = r.get("volume_sold") or 0
        rows.append([
            r.get("Tipo_Cargo", ""),
            r.get("transaction_count"),
            r.get("total_bought"),
            r.get("total_sold"),
            vol_bought,
            vol_sold,
            vol_bought - vol_sold,
            r.get("earliest_date", ""),
            r.get("latest_date", ""),
        ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Insider Trading by Role ({len(roles)} roles)",
            "columns": columns,
            "rows": rows,
            "formats": {
                "Cargo": "text", "Transações": "int",
                "Qtd Comprada": "num", "Qtd Vendida": "num",
                "Volume Comprado": "brl", "Volume Vendido": "brl",
                "Net Volume": "brl", "Início": "text", "Fim": "text",
            },
        }],
        "kpis": [],
        "sources": [],
    }


@register_adapter("insider_summary")
def summary(result: dict) -> dict:
    """Flatten insider.summary result into a monthly net table + KPI strip."""
    if not _ok(result):
        return _error_table(result, title="Insider Summary")

    monthly = result.get("monthly") or []
    if not monthly:
        return _error_table(result, title="Insider Summary")

    columns = ["Mês", "Transações", "Comprado", "Vendido", "Vol Comprado", "Vol Vendido", "Net Volume"]
    rows = []
    for m in monthly:
        rows.append([
            m.get("month", ""),
            m.get("transaction_count"),
            m.get("bought"),
            m.get("sold"),
            m.get("volume_bought"),
            m.get("volume_sold"),
            m.get("net_volume"),
        ])

    # KPI strip
    sentiment = result.get("sentiment", "neutral")
    kpis = [
        {"label": "Sentimento", "value": sentiment.upper()},
        {"label": "Volume Comprado", "value": result.get("total_volume_bought"), "format": "brl"},
        {"label": "Volume Vendido", "value": result.get("total_volume_sold"), "format": "brl"},
        {"label": "Net Volume", "value": result.get("net_volume"), "format": "brl"},
    ]

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Insider Net Buy/Sell per Month ({len(monthly)} months)",
            "columns": columns,
            "rows": rows,
            "formats": {
                "Mês": "text", "Transações": "int",
                "Comprado": "num", "Vendido": "num",
                "Vol Comprado": "brl", "Vol Vendido": "brl",
                "Net Volume": "brl",
            },
        }],
        "kpis": kpis,
        "sources": [],
    }
