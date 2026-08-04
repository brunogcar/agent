"""skills/cvm/insider/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the summary() + history() + by_role() results into a multi-tab
dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}
  - Chart section:  {"title", "type": "chart", "chart_data": <Chart.js config>}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


# ── Brand colors for chart builders ──────────────────────────────────────────
_TEAL = "#0d9488"
_ORANGE = "#f59e0b"
_RED = "#ef4444"
_BLUE = "#3b82f6"
_PURPLE = "#a855f7"


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _cell(label: str, tooltip: str = "") -> dict | str:
    """Wrap a label in a dict cell carrying a tooltip when non-empty.

    Returns ``{"text": label, "tooltip": tooltip}`` when ``tooltip`` is
    truthy, otherwise returns ``label`` unchanged.
    """
    return {"text": label, "tooltip": tooltip} if tooltip else label


# ── Insider movement type tooltips (v3) ──────────────────────────────────────
# Maps the VLMO ``Tipo_Movimentacao`` value (lowercased for fuzzy match) to a
# PT-BR explanation of what each transaction type means. Used as cell-level
# tooltip on the "Tipo" column of the Recent Transactions tab.
_MOVIMENTACAO_TOOLTIPS: dict[str, str] = {
    "compra":           "Compra = aquisição de ações por insider (sentimento positivo).",
    "venda":            "Venda = alienação de ações por insider (sentimento negativo).",
    "doacao":           "Doação = transferência sem contraprestação.",
    "transferencia":    "Transferência = movimentação entre contas do mesmo titular.",
    "exercicio":        "Exercício = exercício de opção/bspread de ações.",
    "amortizacao":      "Amortização = amortização de valor de aportes.",
}

# Tooltip for the "Net Volume" column — same explanation for every cell.
_NET_VOLUME_TOOLTIP = (
    "Net Volume = Volume Comprado − Volume Vendido (R$). Positivo = insiders "
    "comprando (sentimento positivo); negativo = insiders vendendo."
)


def _movimentacao_tooltip(tipo: str) -> str:
    """Return the tooltip for a Tipo_Movimentacao value (fuzzy match)."""
    if not tipo:
        return ""
    key = tipo.strip().lower()
    for k, v in _MOVIMENTACAO_TOOLTIPS.items():
        if k in key:
            return v
    return ""


def _num(v: Any) -> Any:
    """Coerce numeric strings/values to int or float (passthrough None)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _kpi(label: str, value: Any, spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted via apply_fmt so the adapter can pass it
    through verbatim. When value is None, falls back to "—".
    """
    if value is None:
        return {"label": label, "value": "—", "unit": unit}
    return {"label": label, "value": _fmt(value, spec), "unit": unit}


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(summary_result: dict) -> list[dict]:
    """Build 4 KPI cards for the dashboard top-level kpis list.

    Cards (from the summary() result):
      - Sentimento       — sentiment string uppercased ("BUYING"/"SELLING"/
                            "NEUTRAL"/"—") as text
      - Volume Comprado  — total_volume_bought formatted as brl
      - Volume Vendido   — total_volume_sold formatted as brl
      - Net Volume       — net_volume formatted as brl
    """
    sentiment = (summary_result.get("sentiment") if _ok(summary_result)
                 else None)
    if isinstance(sentiment, str) and sentiment:
        sentiment_kpi_value = sentiment.upper()
    elif sentiment is None or not sentiment:
        sentiment_kpi_value = "—"
    else:
        sentiment_kpi_value = str(sentiment).upper()

    total_bought = (summary_result.get("total_volume_bought")
                    if _ok(summary_result) else None)
    total_sold = (summary_result.get("total_volume_sold")
                  if _ok(summary_result) else None)
    net_volume = (summary_result.get("net_volume")
                  if _ok(summary_result) else None)

    return [
        {"label": "Sentimento",      "value": sentiment_kpi_value, "unit": "text"},
        _kpi("Volume Comprado", total_bought, "brl", "brl"),
        _kpi("Volume Vendido",  total_sold,   "brl", "brl"),
        _kpi("Net Volume",      net_volume,   "brl", "brl"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(summary_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the insider data.

    Multi-line text showing company, total transactions, total bought/sold,
    net volume, and the sentiment interpretation.
    """
    company = (summary_result.get("company", "") if _ok(summary_result)
               else "")
    cnpj = (summary_result.get("cnpj", "") if _ok(summary_result)
            else "")

    if _ok(summary_result):
        monthly = summary_result.get("monthly") or []
        total_transactions = sum(m.get("transaction_count", 0) for m in monthly)
        total_bought = summary_result.get("total_volume_bought")
        total_sold = summary_result.get("total_volume_sold")
        net_volume = summary_result.get("net_volume")
        sentiment = summary_result.get("sentiment", "")
    else:
        total_transactions = "—"
        total_bought = None
        total_sold = None
        net_volume = None
        sentiment = ""

    if isinstance(sentiment, str) and sentiment:
        sentiment_label = sentiment.upper()
    else:
        sentiment_label = "—"

    text_lines = [
        f"Company: {company}",
        f"CNPJ: {cnpj or '—'}",
        f"Total de Transações: {total_transactions}",
        f"Volume Comprado: {_fmt(total_bought, 'brl')}",
        f"Volume Vendido: {_fmt(total_sold, 'brl')}",
        f"Net Volume: {_fmt(net_volume, 'brl')}",
        f"Sentimento: {sentiment_label}",
    ]
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Recent Transactions tab section (history table) ─────────────────────────

def build_recent_transactions_section(history_result: dict) -> dict:
    """Build the Recent Transactions tab table from the history() result.

    Columns: Data, Cargo, Tipo, Ativo, Qtd, Preço, Volume
    Limited to the 10 most recent transactions (history() already returns
    newest-first).

    [v3] The "Tipo" column cell now carries a tooltip explaining what each
    Tipo_Movimentacao value means (compra = purchase, venda = sale, ...).
    """
    movements = (history_result.get("movements")
                 if _ok(history_result) else []) or []

    # Limit to 10 most recent rows (history() returns newest-first).
    recent = movements[:10]

    columns = ["Data", "Cargo", "Tipo", "Ativo", "Qtd", "Preço", "Volume"]
    rows = []
    for m in recent:
        tipo = m.get("Tipo_Movimentacao", "") or "—"
        tipo_cell = _cell(tipo, _movimentacao_tooltip(tipo))
        rows.append([
            m.get("Data_Movimentacao", "") or "—",
            m.get("Tipo_Cargo", "") or "—",
            tipo_cell,
            m.get("Tipo_Ativo", "") or "—",
            m.get("Quantidade") if m.get("Quantidade") is not None else "—",
            m.get("Preco_Unitario") if m.get("Preco_Unitario") is not None else "—",
            m.get("Volume") if m.get("Volume") is not None else "—",
        ])

    formats = {
        "Data": "text", "Cargo": "text", "Tipo": "text",
        "Ativo": "text", "Qtd": "num", "Preço": "brl_full",
        "Volume": "brl",
    }

    return {
        "title": f"Insider Transactions ({len(recent)} recent)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Movimentações recentes de insiders (newest-first).",
    }


# ── By Role tab section ──────────────────────────────────────────────────────

def build_by_role_section(by_role_result: dict) -> dict:
    """Build the By Role tab table from the by_role() result.

    Columns: Cargo, Transações, Qtd Comprada, Qtd Vendida,
             Vol Comprado, Vol Vendido, Net Volume

    [v3] The "Net Volume" column cell now carries a tooltip explaining
    the formula (bought - sold) and how to interpret the sign.
    """
    roles = (by_role_result.get("by_role")
             if _ok(by_role_result) else []) or []

    columns = ["Cargo", "Transações", "Qtd Comprada", "Qtd Vendida",
               "Vol Comprado", "Vol Vendido", "Net Volume"]
    rows = []
    for r in roles:
        vol_bought = r.get("volume_bought") or 0
        vol_sold = r.get("volume_sold") or 0
        net_vol = (vol_bought - vol_sold) if (vol_bought is not None
                                                and vol_sold is not None) else None
        rows.append([
            r.get("Tipo_Cargo", "") or "—",
            r.get("transaction_count") if r.get("transaction_count") is not None else "—",
            r.get("total_bought") if r.get("total_bought") is not None else "—",
            r.get("total_sold") if r.get("total_sold") is not None else "—",
            vol_bought if vol_bought is not None else "—",
            vol_sold if vol_sold is not None else "—",
            _cell(net_vol, _NET_VOLUME_TOOLTIP) if net_vol is not None else "—",
        ])

    formats = {
        "Cargo": "text", "Transações": "int",
        "Qtd Comprada": "num", "Qtd Vendida": "num",
        "Vol Comprado": "brl", "Vol Vendido": "brl",
        "Net Volume": "brl",
    }

    return {
        "title": f"Insider Trading by Role ({len(roles)} roles)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Movimentações agrupadas por cargo (Tipo_Cargo).",
    }


# ── Monthly Net tab section ──────────────────────────────────────────────────

def build_monthly_section(summary_result: dict) -> dict:
    """Build the Monthly Net tab table from the summary() result.

    Columns: Mês, Transações, Comprado, Vendido,
             Vol Comprado, Vol Vendido, Net Volume

    [v3] The "Net Volume" column cell now carries a tooltip explaining
    the formula (bought - sold) and how to interpret the sign.
    """
    monthly = (summary_result.get("monthly")
               if _ok(summary_result) else []) or []

    columns = ["Mês", "Transações", "Comprado", "Vendido",
               "Vol Comprado", "Vol Vendido", "Net Volume"]
    rows = []
    for m in monthly:
        net_vol = m.get("net_volume")
        rows.append([
            m.get("month", "") or "—",
            m.get("transaction_count") if m.get("transaction_count") is not None else "—",
            m.get("bought") if m.get("bought") is not None else "—",
            m.get("sold") if m.get("sold") is not None else "—",
            m.get("volume_bought") if m.get("volume_bought") is not None else "—",
            m.get("volume_sold") if m.get("volume_sold") is not None else "—",
            _cell(net_vol, _NET_VOLUME_TOOLTIP) if net_vol is not None else "—",
        ])

    formats = {
        "Mês": "text", "Transações": "int",
        "Comprado": "num", "Vendido": "num",
        "Vol Comprado": "brl", "Vol Vendido": "brl",
        "Net Volume": "brl",
    }

    return {
        "title": f"Insider Net Buy/Sell per Month ({len(monthly)} months)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Resumo mensal de compra/venda de insiders.",
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"


# ── Monthly Net chart (v1.2) ──────────────────────────────────────────────────

def build_monthly_net_chart(summary_result: dict) -> dict | None:
    """Build a bar chart showing monthly net insider buy/sell volume.

    A single-dataset bar chart where each bar's color encodes the direction:
      - green (teal)  for net buying months (net_volume > 0)
      - red           for net selling months (net_volume < 0)

    Args:
        summary_result: summary() result dict (must contain a "monthly" list
                        with month/net_volume keys).

    Returns None if there is no monthly data or no valid net volumes.
    """
    monthly = (summary_result.get("monthly")
               if _ok(summary_result) else []) or []
    if not monthly:
        return None

    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for m in monthly:
        net = m.get("net_volume")
        if net is None:
            continue
        try:
            v = float(net)
        except (TypeError, ValueError):
            continue
        labels.append(m.get("month", "") or "—")
        values.append(round(v, 2))
        colors.append(_TEAL if v >= 0 else _RED)

    if not labels:
        return None

    return {
        "title": "Monthly Net Insider Volume",
        "description": (
            "Volume líquido mensal (R$) de compras menos vendas por insiders. "
            "Barras verdes (teal) indicam meses de compra líquida; vermelhas, "
            "meses de venda líquida."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Net Volume (R$)",
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": colors,
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Monthly Net Insider Volume"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


# ── Cumulative chart (v1.2) ──────────────────────────────────────────────────

def build_cumulative_chart(transactions: dict) -> dict | None:
    """Build a line chart showing cumulative insider trading volume over time.

    Walks the transactions list (newest-first by convention from history())
    in chronological order, accumulating the signed volume (positive for buys,
    negative for sells) and plotting a line chart.

    Args:
        transactions: history() result dict (must contain a "movements" list
                      with Data_Movimentacao/Tipo_Movimentacao/Volume keys).

    Returns None if there are fewer than 2 transactions or no valid volumes.
    """
    movements = (transactions.get("movements")
                 if _ok(transactions) else []) or []
    if len(movements) < 2:
        return None

    # Oldest-first so cumulative makes sense.
    chronological = sorted(
        [m for m in movements if m.get("Data_Movimentacao")],
        key=lambda m: m.get("Data_Movimentacao", ""),
    )

    labels: list[str] = []
    cumulative: list[float] = []
    running = 0.0
    for m in chronological:
        vol = m.get("Volume")
        if vol is None:
            continue
        try:
            v = float(vol)
        except (TypeError, ValueError):
            continue
        tipo = (m.get("Tipo_Movimentacao") or "").lower()
        # Sell reduces cumulative net volume; buy increases it.
        signed = -v if "venda" in tipo else v
        running += signed
        labels.append(m.get("Data_Movimentacao", "") or "—")
        cumulative.append(round(running, 2))

    if len(labels) < 2:
        return None

    return {
        "title": "Cumulative Insider Net Volume",
        "description": (
            "Volume líquido acumulado (R$) das transações de insiders ao "
            "longo do tempo. Compras somam; vendas subtraem."
        ),
        "type": "chart",
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Cumulative Net Volume (R$)",
                    "data": cumulative,
                    "borderColor": _BLUE,
                    "backgroundColor": "rgba(59, 130, 246, 0.15)",
                    "borderWidth": 2,
                    "tension": 0.3,
                    "fill": True,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Cumulative Insider Net Volume"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


# ── Buy vs Sell volume per Cargo grouped chart (v3) ──────────────────────────

def build_by_role_chart(by_role_result: dict) -> dict | None:
    """Build a grouped bar chart showing buy vs sell volume per Cargo (role).

    Each Cargo (Tipo_Cargo) gets two bars side-by-side: Vol Comprado
    (teal, purchases) and Vol Vendido (red, sales). Useful to spot which
    insider roles are net buyers vs net sellers.

    Returns None when by_role() returned no roles or no role has a numeric
    volume_bought/volume_sold value.
    """
    roles = (by_role_result.get("by_role")
             if _ok(by_role_result) else []) or []
    if not roles:
        return None

    labels: list[str] = []
    bought: list[float] = []
    sold: list[float] = []
    for r in roles:
        vol_bought = r.get("volume_bought")
        vol_sold = r.get("volume_sold")
        if vol_bought is None and vol_sold is None:
            continue
        try:
            bv = float(vol_bought) if vol_bought is not None else 0.0
        except (TypeError, ValueError):
            bv = 0.0
        try:
            sv = float(vol_sold) if vol_sold is not None else 0.0
        except (TypeError, ValueError):
            sv = 0.0
        labels.append(r.get("Tipo_Cargo", "") or "—")
        bought.append(round(bv, 2))
        sold.append(round(sv, 2))

    if not labels:
        return None

    return {
        "title": "Buy vs Sell Volume per Cargo (R$)",
        "description": (
            "Volume comprado (teal) vs vendido (vermelho) por cargo "
            "(Tipo_Cargo). Cargos com barras teal maiores são compradores "
            "líquidos; cargos com barras vermelhas maiores são vendedores "
            "líquidos. Valores em BRL."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Vol Comprado (BRL)",
                        "data": bought,
                        "backgroundColor": _TEAL,
                        "borderColor": _TEAL,
                        "borderWidth": 1,
                    },
                    {
                        "label": "Vol Vendido (BRL)",
                        "data": sold,
                        "backgroundColor": _RED,
                        "borderColor": _RED,
                        "borderWidth": 1,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Buy vs Sell Volume per Cargo (R$)"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }
