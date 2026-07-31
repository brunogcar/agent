"""adapters/financials_statement.py — Generic statement adapter.

Single adapter for all 5 standalone statement modes (bpa / bpp / dre / dfc /
dva). All 5 share the same output shape:

    {status, company, period_type, statement, periods: [
        {data_fim_exerc, meses, period, year, quarter,
         accounts: {codigo: {label, section, valor_brl}}}
    ]}

The adapter:
  - Checks `status == "ok"` (otherwise delegates to `_error_table`).
  - Extracts the latest period's `accounts` dict.
  - Groups accounts by their `section` field (e.g., Geração / Distribuição
    for DVA, Ativo Circulante / Ativo Não Circulante for BPA, etc.).
  - Renders each section as a `type: "table"` section with columns
    [Código, Descrição, Valor (BRL)] and one row per account.
  - Numeric values are pre-formatted with the `brl` spec via `apply_fmt`
    (compact BRL with B/T/M suffixes) so the dashboard template renders
    them as ready-to-display strings.

Usage:
    report(action="table", data=<statement result>,
           config={"adapter": "financials_statement"})

The adapter is intentionally dumb about which statement it received: the
`statement` field on the input is surfaced as a top-level label, but the
table-building logic is identical across all 5 modes.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# Pretty PT-BR labels for the statement identifier (matches the `statement`
# field set by reshape_statement_periods in modes/_statement_sections.py).
_STATEMENT_LABELS = {
    "BPA": "Balanço Patrimonial — Ativo",
    "BPP": "Balanço Patrimonial — Passivo",
    "DRE": "Demonstração do Resultado do Exercício",
    "DFC": "Demonstração dos Fluxos de Caixa",
    "DVA": "Demonstração do Valor Adicionado",
}


def _format_value(value: Any) -> str:
    """Format an account value as compact BRL (apply_fmt)."""
    from tools.report_ops.formats import apply_fmt
    if value is None:
        return "—"
    try:
        return apply_fmt(_safe_num(value), "brl")
    except Exception:
        return str(value)


def _build_section(section_label: str, accounts: list[tuple[str, dict]]) -> dict:
    """Build a single `type: "table"` section from a list of (codigo, account).

    Args:
        section_label: Human-readable section name (e.g., "Ativo Circulante").
        accounts: list of (codigo, account_dict) pairs in this section.
            Each account_dict has {label, section, valor_brl}.

    Returns:
        Section dict shaped for the dashboard template's `data_table` macro:
            {title, type, columns, rows, formats}
    """
    rows = []
    for codigo, acc in accounts:
        rows.append([
            codigo,
            acc.get("label") or codigo,
            _format_value(acc.get("valor_brl")),
        ])
    return {
        "title": section_label,
        "type": "table",
        "columns": ["Código", "Descrição", "Valor (BRL)"],
        "rows": rows,
        "formats": {"Código": "text", "Descrição": "text", "Valor (BRL)": "text"},
    }


@register_adapter("financials_statement")
def financials_statement(result: dict) -> dict:
    """Flatten a bpa/bpp/dre/dfc/dva result into a grouped table payload.

    The latest period's accounts are extracted from `result["periods"][0]`
    (periods are newest-first in the standalone-statement-mode shape), then
    grouped by their `section` field. Each section becomes a `type: "table"`
    block in the output's `sections` list.

    Args:
        result: dict from one of the standalone statement modes (bpa/bpp/dre/
            dfc/dva). Must have `status == "ok"` and at least one period.

    Returns:
        Dict shaped ``{"company": ..., "sections": [...], "kpis": [], "sources": []}``
        on success, or the standard `_error_table` shape on error/empty input.
    """
    if not _ok(result):
        statement = (result.get("statement") or "Statement") if isinstance(result, dict) else "Statement"
        return _error_table(result, title=_STATEMENT_LABELS.get(statement, statement))

    periods = result.get("periods") or []
    if not periods:
        statement = result.get("statement") or "Statement"
        return _error_table({"status": "not_found",
                             "error": f"No periods in {statement} result"},
                            title=_STATEMENT_LABELS.get(statement, statement))

    latest = periods[0]
    accounts_dict = latest.get("accounts") or {}
    if not accounts_dict:
        statement = result.get("statement") or "Statement"
        return _error_table({"status": "not_found",
                             "error": f"No accounts in latest {statement} period"},
                            title=_STATEMENT_LABELS.get(statement, statement))

    # Group accounts by section, preserving insertion order within each section.
    grouped: dict[str, list[tuple[str, dict]]] = {}
    for codigo, acc in accounts_dict.items():
        section = acc.get("section") or "Outros"
        grouped.setdefault(section, []).append((codigo, acc))

    sections: list[dict] = []
    for section_label, accounts in grouped.items():
        sections.append(_build_section(section_label, accounts))

    statement = result.get("statement") or "Statement"
    title = _STATEMENT_LABELS.get(statement, statement)
    period_label = (latest.get("period")
                    or latest.get("data_fim_exerc")
                    or str(latest.get("year") or ""))

    return {
        "company": result.get("company", ""),
        "sections": sections,
        "kpis": [
            {"label": "Demonstração",
             "value": title,
             "format": "text"},
            {"label": "Período",
             "value": period_label or "—",
             "format": "text"},
            {"label": "Contas",
             "value": len(accounts_dict),
             "format": "int"},
        ],
        "sources": [],
    }
