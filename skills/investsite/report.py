"""skills/investsite/report.py -- Dashboard composition helpers.

[v2.1] Improvements:
  - Split DRE/DFC/Balanço tables by prefix (x.xx grouping)
  - More charts: DRE bar, DFC bar, Balanço structure, Experimental bar
  - Tooltips on ALL metrics (expanded _INVESTSITE_TOOLTIPS)
  - Statement sections grouped by account prefix
  - Reorder: Balanço first in Demonstrações
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _num(v: Any) -> Any:
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
    if value is None:
        return {"label": label, "value": "—", "unit": unit}
    return {"label": label, "value": _fmt(value, spec), "unit": unit}


def _fv(v: Any) -> Any:
    if isinstance(v, list):
        for item in v:
            if item is not None:
                return item
        return None
    return v


def _ok(result: dict) -> bool:
    return isinstance(result, dict) and result.get("status") == "ok"


def _cell(label: str, tooltip: str = "") -> dict:
    return {"text": label, "tooltip": tooltip} if tooltip else label


# ── Expanded tooltips ────────────────────────────────────────────────────────

_INVESTSITE_TOOLTIPS = {
    "Preco/Lucro": "P/L = Preço / Lucro por Ação. Quanto o mercado paga por R$1 de lucro.",
    "Preco/VPA": "P/VPA = Preço / Valor Patrimonial por Ação.",
    "EV/EBITDA": "EV/EBITDA = (Market Cap + Dívida Líquida) / EBITDA.",
    "Dividend Yield": "Dividend Yield = Dividendo por Ação / Preço.",
    "Preco/Receita": "PSR = Preço / Receita por Ação.",
    "Preco/FCO": "P/FCO = Preço / Fluxo de Caixa Operacional por Ação.",
    "Preco/FCF": "P/FCF = Preço / Fluxo de Caixa Livre por Ação.",
    "Preco/EBIT": "P/EBIT = Preço / EBIT por Ação.",
    "Preco/EBITDA": "P/EBITDA = Preço / EBITDA por Ação.",
    "Preco/Ativo": "P/Ativo = Preço / Ativo Total por Ação.",
    "Preco/Capital Giro": "P/Capital de Giro = Preço / Capital de Giro por Ação.",
    "Preco/Divida Bruta": "P/Dívida Bruta = Preço / Dívida Bruta por Ação.",
    "Valor de Mercado": "Market Cap = Preço × Total de Ações.",
    "Enterprise Value (EV)": "EV = Market Cap + Dívida Bruta - Caixa.",
    "Retorno s/ Patrimonio Liquido": "ROE = Lucro Líquido / Patrimônio Líquido.",
    "Retorno s/ Ativo": "ROA = Lucro Líquido / Ativo Total.",
    "Margem EBITDA": "Margem EBITDA = EBITDA / Receita Líquida.",
    "Margem Liquida": "Margem Líquida = Lucro Líquido / Receita Líquida.",
    "Margem Bruta": "Margem Bruta = Lucro Bruto / Receita Líquida.",
    "Margem Operacional": "Margem Operacional = EBIT / Receita Líquida.",
    "Divida Liquida/EBITDA": "Dív. Líq/EBITDA = (Dívida Bruta - Caixa) / EBITDA.",
    "Divida Liquida/Patrimonio Liquido": "Dív. Líq/PL = (Dívida Bruta - Caixa) / PL.",
    "Divida Bruta/Patrimonio Liquido": "Dívida Bruta/PL = Dívida Bruta / PL.",
    "ROIC": "ROIC = NOPAT / Capital Investido.",
    "Receita Liquida": "Receita total após deduções (DRE 3.01).",
    "Receita Bruta": "Receita antes de deduções (DRE 3.01 original).",
    "Lucro Bruto": "Lucro Bruto = Receita - CMV (DRE 3.03).",
    "EBIT": "EBIT = Resultado Operacional (DRE 3.05).",
    "EBITDA": "EBIT + D&A (Depreciação e Amortização).",
    "Lucro Liquido": "Lucro/Prejuízo Consolidado (DRE 3.11).",
    "Patrimonio Liquido": "Capital próprio dos acionistas (BPP 2.03).",
    "Caixa": "Caixa e Equivalentes (BPA 1.01.01).",
    "Divida Bruta": "Empréstimos Circ + Não Circ.",
    "Divida Liquida": "Dívida Líquida = Dívida Bruta - Caixa.",
    "Ativo Total": "Total de ativos (BPA 1).",
    "FCO": "Fluxo de Caixa Operacional (DFC 6.01).",
    "FCI": "Fluxo de Caixa de Investimento (DFC 6.02).",
    "FCF": "Fluxo de Caixa de Financiamento (DFC 6.03).",
    "CAPEX": "Capital Expenditure — investimentos em ativos imobilizados.",
    "Fluxo de Caixa Livre": "FCF Livre = FCO - CAPEX.",
    "LPA": "Lucro por Ação = Lucro Líquido / Total de Ações.",
    "VPA": "Valor Patrimonial por Ação = PL / Total de Ações.",
    "Quantidade de Acoes": "Total de ações outstanding.",
}

def _tip(key: str) -> str:
    return _INVESTSITE_TOOLTIPS.get(key, "")


# ── Company header from dados_basicos ────────────────────────────────────────

def build_company_header(indicators_result: dict) -> dict:
    header: dict[str, Any] = {
        "ticker": "", "name": "", "trade_name": "", "sector": "",
        "market_cap": "", "shares": "", "price": None, "isin": "",
    }
    if not _ok(indicators_result):
        return header
    sections = indicators_result.get("sections", {}) or {}
    dados = sections.get("dados_basicos", {}) or {}
    precos = sections.get("precos_relativos", {}) or {}
    header["ticker"] = indicators_result.get("ticker", "")
    header["name"] = dados.get("Empresa") or dados.get("Razao Social") or ""
    header["sector"] = dados.get("Setor") or dados.get("Subsetor") or ""
    mc = _fv(dados.get("Valor de Mercado"))
    if mc is not None:
        header["market_cap"] = _fmt(mc, "brl")
    sh = _fv(dados.get("Quantidade de Acoes"))
    if sh is not None:
        header["shares"] = _fmt(sh, "int")
    price = _fv(precos.get("Preco"))
    if price is not None:
        try:
            header["price"] = float(str(price).replace(",", "."))
        except (TypeError, ValueError):
            pass
    return header


# ── KPI cards ────────────────────────────────────────────────────────────────

_KPI_SPECS = [
    ("P/L",             "precos_relativos",  ["Preco/Lucro", "P/L", "PL"],                                  "num", "num"),
    ("P/VPA",           "precos_relativos",  ["Preco/VPA", "P/VPA", "PVPA", "Preco/Valor Patrimonial"],     "num", "num"),
    ("EV/EBITDA",       "precos_relativos",  ["EV/EBITDA", "EV Ebitda", "Enterprise Value/EBITDA"],         "num", "num"),
    ("ROE",             "retornos_margens",  ["Retorno s/ Patrimonio Liquido", "ROE"],                       "pct", "pct"),
    ("Dividend Yield",  "precos_relativos",  ["Dividend Yield", "Div Yield", "DY"],                          "pct", "pct"),
]


def build_overview_kpis(indicators_result: dict) -> list[dict]:
    if not _ok(indicators_result):
        sections: dict = {}
    else:
        sections = indicators_result.get("sections", {}) or {}
    kpis: list[dict] = []
    for label, section_key, metric_keys, spec, unit in _KPI_SPECS:
        sec = sections.get(section_key, {}) or {}
        value = None
        for mk in metric_keys:
            v = _fv(sec.get(mk))
            if v is not None:
                value = v
                break
        kpis.append(_kpi(label, value, spec, unit))
    return kpis


# ── Helper: build a split table from a dict section ──────────────────────────

def _build_split_tables(section_data: dict, section_title: str) -> list[dict]:
    """Split a flat dict into multiple tables grouped by key prefix.

    Groups keys by their first segment (e.g., "Receita" vs "Lucro" vs "Margem").
    Each group becomes its own table.
    """
    if not section_data:
        return []

    # Group keys by prefix (first word or first segment before /)
    groups: dict[str, list[tuple[str, Any]]] = {}
    for key, val in section_data.items():
        if key == "caption":
            continue
        # Determine group: first word or prefix before "/"
        if "/" in key:
            prefix = key.split("/")[0].strip()
        elif " " in key:
            prefix = key.split(" ")[0].strip()
        else:
            prefix = "Outros"
        groups.setdefault(prefix, []).append((key, val))

    # Build one table per group
    tables: list[dict] = []
    for group_name, items in groups.items():
        rows = []
        for key, val in items:
            v = _fv(val)
            spec = "pct" if "Yield" in key or "Margem" in key or "Retorno" in key else "brl" if isinstance(v, (int, float)) and abs(v) > 1000 else "num"
            formatted = _fmt(v, spec) if isinstance(v, (int, float)) else str(v or "—")
            rows.append([_cell(key, _tip(key)), formatted])
        if rows:
            tables.append({
                "title": f"{section_title} — {group_name}",
                "type": "table",
                "columns": ["Indicador", "Valor"],
                "rows": rows,
            })

    return tables


# ── Overview tab: split tables + charts ──────────────────────────────────────

def build_overview_sections(indicators_result: dict) -> list[dict]:
    """Build Overview tab: split tables + charts."""
    if not _ok(indicators_result):
        return [{"type": "text", "text": "Dados indisponíveis."}]
    sections = indicators_result.get("sections", {}) or {}
    result: list[dict] = []

    # Table 1: Dados Básicos (single table — it's company info)
    dados = sections.get("dados_basicos", {}) or {}
    if dados:
        rows = []
        for key, val in dados.items():
            if key == "caption":
                continue
            v = _fv(val)
            spec = "brl" if isinstance(v, (int, float)) and abs(v) > 1000 else "text"
            rows.append([_cell(key, _tip(key)), _fmt(v, spec) if isinstance(v, (int, float)) else str(v or "—")])
        result.append({"title": "Dados Básicos", "type": "table", "columns": ["Indicador", "Valor"], "rows": rows})

    # Table 2+: Preços Relativos (split by prefix)
    precos = sections.get("precos_relativos", {}) or {}
    result.extend(_build_split_tables(precos, "Preços Relativos"))

    # Table 3+: Retornos e Margens (split by prefix)
    retornos = sections.get("retornos_margens", {}) or {}
    result.extend(_build_split_tables(retornos, "Retornos e Margens"))

    return result


# ── DRE sections: split by prefix + chart ────────────────────────────────────

def build_dre_sections(indicators_result: dict) -> list[dict]:
    """Build DRE tables — TTM + Quarterly, split by prefix + bar chart."""
    if not _ok(indicators_result):
        return [{"type": "text", "text": "DRE indisponível."}]
    sections = indicators_result.get("sections", {}) or {}
    result: list[dict] = []

    for section_key, title_suffix in [("dre_ttm", "TTM"), ("dre_quarterly", "Trimestral")]:
        dre = sections.get(section_key, {}) or {}
        result.extend(_build_split_tables(dre, f"DRE {title_suffix}"))

    # Add DRE bar chart (TTM values)
    dre_ttm = sections.get("dre_ttm", {}) or {}
    chart = _build_section_chart(dre_ttm, "DRE TTM — Comparativo", "Valores do DRE trailing 12 meses.")
    if chart:
        result.append(chart)

    return result


# ── DFC sections: split by prefix + chart ────────────────────────────────────

def build_dfc_sections(indicators_result: dict) -> list[dict]:
    """Build DFC tables — TTM + Quarterly, split by prefix + bar chart."""
    if not _ok(indicators_result):
        return [{"type": "text", "text": "DFC indisponível."}]
    sections = indicators_result.get("sections", {}) or {}
    result: list[dict] = []

    for section_key, title_suffix in [("fluxo_caixa_ttm", "TTM"), ("fluxo_caixa_quarterly", "Trimestral")]:
        dfc = sections.get(section_key, {}) or {}
        result.extend(_build_split_tables(dfc, f"DFC {title_suffix}"))

    # Add DFC bar chart
    dfc_ttm = sections.get("fluxo_caixa_ttm", {}) or {}
    chart = _build_section_chart(dfc_ttm, "DFC TTM — Comparativo", "Valores do Fluxo de Caixa trailing 12 meses.")
    if chart:
        result.append(chart)

    return result


# ── Balanço Patrimonial summary + chart ──────────────────────────────────────

def build_balanco_section(indicators_result: dict) -> list[dict]:
    """Build Balanço Patrimonial: split tables + chart."""
    if not _ok(indicators_result):
        return [{"type": "text", "text": "Balanço indisponível."}]
    sections = indicators_result.get("sections", {}) or {}
    balanco = sections.get("balanco_patrimonial", {}) or {}
    if not balanco:
        return [{"type": "text", "text": "Balanço indisponível."}]

    result = _build_split_tables(balanco, "Balanço Patrimonial")

    # Add bar chart
    chart = _build_section_chart(balanco, "Balanço Patrimonial — Comparativo", "Valores do Balanço Patrimonial.")
    if chart:
        result.append(chart)

    return result if result else [{"type": "text", "text": "Balanço indisponível."}]


# ── Experimental + chart ─────────────────────────────────────────────────────

def build_experimental_section(indicators_result: dict) -> list[dict]:
    """Build Experimental: split table + bar chart."""
    if not _ok(indicators_result):
        return [{"type": "text", "text": "Dados experimentais indisponíveis."}]
    sections = indicators_result.get("sections", {}) or {}
    exp = sections.get("experimental", {}) or {}
    if not exp:
        return [{"type": "text", "text": "Dados experimentais indisponíveis."}]

    result = _build_split_tables(exp, "Experimental (CAPEX + FCF)")

    # Add bar chart
    chart = _build_section_chart(exp, "Experimental — Comparativo", "CAPEX + Fluxo de Caixa Livre.")
    if chart:
        result.append(chart)

    return result if result else [{"type": "text", "text": "Dados experimentais indisponíveis."}]


# ── Statement table (from statements mode) with section grouping ─────────────

def build_statement_section(statements_result: dict, label: str) -> dict:
    """Build a table section from a statements() result, grouped by prefix."""
    if not _ok(statements_result):
        return {"type": "text", "text": f"{label} indisponível."}

    accounts = statements_result.get("accounts") or []
    period_headers = statements_result.get("period_headers") or []

    columns = ["Código", "Descrição"]
    for ph in period_headers:
        columns.append(ph)

    # Group accounts by prefix (x.xx → section header)
    rows: list[list[str]] = []
    last_prefix = ""
    for acc in accounts:
        codigo = acc.get("codigo", "")
        # Extract prefix: first 1-2 digits before first "."
        parts = codigo.split(".")
        prefix = parts[0] if parts else codigo
        if prefix != last_prefix and prefix:
            # Add a separator row
            rows.append([f"— {prefix}.xx —", "", ""] + [""] * (len(period_headers) - 1))
            last_prefix = prefix

        row = [codigo, acc.get("descricao", "")]
        for p in acc.get("periods", []):
            val = p.get("value", "")
            pct = p.get("pct_total", "")
            if pct and pct != "—":
                row.append(f"{val} ({pct})")
            else:
                row.append(val)
        rows.append(row)

    return {
        "title": f"{label} — {len(accounts)} contas",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }


# ── Events table ─────────────────────────────────────────────────────────────

def build_events_section(events_result: dict) -> dict:
    events = (events_result.get("events") if _ok(events_result) else []) or []
    columns = ["Data Entrega", "Data Ref.", "Categoria", "Tipo", "Espécie", "Assuntos"]
    rows = []
    for e in events:
        rows.append([
            e.get("data_entrega", "") or "—",
            e.get("data_referencia", "") or "—",
            e.get("categoria", "") or "—",
            e.get("tipo", "") or "—",
            e.get("especie", "") or "—",
            e.get("assuntos", "") or "—",
        ])
    return {
        "title": f"Eventos ({len(events)} registros)",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }


# ── Shares sections (custom parser) ──────────────────────────────────────────

def build_shares_sections(shares_html: str) -> list[dict]:
    """Build shares sections from raw HTML (3 tables: Total, Treasury, Outstanding)."""
    if not shares_html:
        return [{"type": "text", "text": "Dados de ações indisponíveis."}]
    from skills.investsite.parsers import _extract_tables, _try_parse_brl
    tables = _extract_tables(shares_html)
    if not tables:
        return [{"type": "text", "text": "Dados de ações indisponíveis."}]

    sections: list[dict] = []
    for table in tables[:3]:
        caption = table.get("caption", "Ações")
        headers = table.get("headers", ["Tipo", "Quantidade"])
        rows_raw = table.get("rows", [])
        if not rows_raw:
            continue
        rows = []
        for row in rows_raw:
            formatted_row = []
            for cell in row:
                v = _try_parse_brl(cell)
                if isinstance(v, (int, float)):
                    formatted_row.append(_fmt(v, "int"))
                else:
                    formatted_row.append(cell)
            rows.append(formatted_row)
        sections.append({"title": caption, "type": "table", "columns": headers[:2], "rows": rows})

    return sections if sections else [{"type": "text", "text": "Dados de ações indisponíveis."}]


# ── Chart builders ───────────────────────────────────────────────────────────

def _build_section_chart(section_data: dict, title: str, description: str) -> dict | None:
    """Build a multi-color bar chart from a section dict (key → value)."""
    labels = []
    values = []
    colors = ["#0d9488", "#f59e0b", "#3b82f6", "#a855f7", "#22c55e", "#ef4444", "#3b82f6", "#f59e0b"]
    for key, val in section_data.items():
        if key == "caption":
            continue
        v = _fv(val)
        if v is not None and isinstance(v, (int, float)):
            labels.append(key[:20])  # Truncate long labels
            values.append(v)

    if len(labels) < 2:
        return None

    return {
        "type": "chart",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{"label": title, "data": values,
                              "backgroundColor": colors[:len(labels)]}],
            },
            "options": {"responsive": True, "maintainAspectRatio": False,
                        "scales": {"y": {"beginAtZero": True}}},
        },
    }


def build_multiples_chart(indicators_result: dict) -> dict | None:
    if not _ok(indicators_result):
        return None
    sections = indicators_result.get("sections", {}) or {}
    precos = sections.get("precos_relativos", {}) or {}

    labels = []
    values = []
    colors = ["#0d9488", "#f59e0b", "#3b82f6", "#a855f7", "#22c55e", "#ef4444"]
    for label, key in [("P/L", "Preco/Lucro"), ("P/VPA", "Preco/VPA"),
                       ("EV/EBITDA", "EV/EBITDA"), ("PSR", "Preco/Receita"),
                       ("P/EBIT", "Preco/EBIT"), ("P/EBITDA", "Preco/EBITDA")]:
        v = _fv(precos.get(key))
        if v is not None:
            try:
                labels.append(label)
                values.append(float(str(v).replace(",", ".")))
            except (TypeError, ValueError):
                pass

    if not labels:
        return None

    return {
        "type": "chart",
        "title": "Múltiplos de Mercado — Comparativo",
        "description": "P/L, P/VPA, EV/EBITDA, PSR, P/EBIT, P/EBITDA. Menor = mais barato.",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{"label": "Múltiplos", "data": values,
                              "backgroundColor": colors[:len(labels)]}],
            },
            "options": {"responsive": True, "maintainAspectRatio": False,
                        "scales": {"y": {"beginAtZero": True}}},
        },
    }


def build_returns_margins_chart(indicators_result: dict) -> dict | None:
    if not _ok(indicators_result):
        return None
    sections = indicators_result.get("sections", {}) or {}
    retornos = sections.get("retornos_margens", {}) or {}

    labels = []
    values = []
    colors = ["#22c55e", "#3b82f6", "#f59e0b", "#a855f7", "#ef4444", "#0d9488"]
    for label, key in [
        ("ROE", "Retorno s/ Patrimonio Liquido"),
        ("ROA", "Retorno s/ Ativo"),
        ("Marg. EBITDA", "Margem EBITDA"),
        ("Marg. Líquida", "Margem Liquida"),
        ("Marg. Bruta", "Margem Bruta"),
        ("Marg. Operacional", "Margem Operacional"),
    ]:
        v = _fv(retornos.get(key))
        if v is not None:
            try:
                val = float(str(v).replace(",", "."))
                labels.append(label)
                values.append(val * 100 if abs(val) < 1 else val)
            except (TypeError, ValueError):
                pass

    if not labels:
        return None

    return {
        "type": "chart",
        "title": "Retornos e Margens — Comparativo",
        "description": "ROE, ROA, margens. Maior = melhor.",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{"label": "Retornos/Margens (%)", "data": values,
                              "backgroundColor": colors[:len(labels)]}],
            },
            "options": {"responsive": True, "maintainAspectRatio": False,
                        "scales": {"y": {"beginAtZero": True}}},
        },
    }
