"""skills/cvm/financials/report/statements.py -- Shared statement table builders.

Hosts the multi-period comparison table builder used by all 4 statement
tabs (Balanço / DRE / DFC / DVA) plus the period_toggle wrapper that
switches between annual + quarterly views.

Public builders:
  - ``build_multi_period_table(title, periods, statement_type)`` — side-by-side
    comparison table for up to 20 periods.

Private helpers (imported by ``report/balanco.py``, ``report/dre.py``,
``report/dfc.py``, ``report/dva.py``):
  - ``_statement_table_section(title, accounts_dict)`` — single-period table
    (legacy, kept for fallback).
  - ``_merge_bpa_bpp_periods(bpa_periods, bpp_periods)`` — merge BPA + BPP
    periods for the Balanço "Completo" sub-tab.
  - ``_build_period_toggle_sections(...)`` — wraps annual + quarterly tables
    (and optional charts) in a ``type: "period_toggle"`` section.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _format_period_label, _period_sort_key


def _statement_table_section(title: str, accounts_dict: dict) -> dict:
    """Build a `type: "table"` section from a {codigo: {label, section, valor_brl}} dict.

    Groups by section, with one row per account code. Values are pre-formatted
    as compact BRL.
    """
    rows: list[list[str]] = []
    # Preserve insertion order; group by section visually via a header row.
    last_section: str | None = None
    for codigo, acc in accounts_dict.items():
        section = acc.get("section") or ""
        if section and section != last_section:
            rows.append([f"— {section} —", ""])
            last_section = section
        rows.append([
            codigo,
            acc.get("label") or codigo,
            _fmt(acc.get("valor_brl"), "brl"),
        ])
    return {
        "title": title,
        "type": "table",
        "columns": ["Código", "Descrição", "Valor (BRL)"],
        "rows": rows,
    }


def build_multi_period_table(
    title: str, periods: list[dict], statement_type: str,
) -> dict | None:
    """[v1.23 F3 / v1.24] Build a multi-period comparison table for a statement.

    Shows up to 20 periods (annual OR quarterly) side-by-side so users can
    compare each account code across periods without flipping tabs. Used as
    the FIRST section in each of the Balanço / DRE / DFC / DVA tabs.

    [v1.24] Changes vs v1.23:
      - Cap raised from 4 → 20 periods (quarterly mode fetches up to 5Y).
      - Period labels now derived via ``_format_period_label``: "2023" for
        annual, "2T2026" for quarterly.
      - ``wide: True`` flag set on the section when >6 periods so the
        template wraps the table in ``overflow-x: auto``.
      - Note caption is period-aware ("anuais" vs "trimestrais").

    Args:
        title: table title.
        periods: list of period dicts (each has ``period`` label + ``accounts``
            dict of ``{codigo: {label, section, valor_brl}}``). Periods are
            assumed to be newest-first (the standard statement-mode order).
        statement_type: "BPA" / "BPP" / "DRE" / "DFC" / "DVA" — used for the
            note caption.

    Returns:
        A ``type: "table"`` section, or None when no periods / no accounts.
    """
    # [v1.25 v5] Don't filter out periods with empty accounts — include ALL
    # periods so the table has consistent column count (20 quarters) across
    # all tabs. Periods with no data show "—" for each code.
    valid_periods = [p for p in (periods or []) if p.get("data_fim_exerc") or p.get("period")]
    if not valid_periods:
        return None
    # [v1.25 v2] Sort newest-first (descending) using _period_sort_key.
    # Was relying on caller order which was inconsistent (quarterly asc, annual desc).
    valid_periods.sort(key=_period_sort_key, reverse=True)
    # Cap at 20 periods (newest-first).
    valid_periods = valid_periods[:20]

    period_labels = [_format_period_label(p) for p in valid_periods]
    columns = ["Código", "Descrição"] + period_labels

    # Build a unified code→{label, section} map preserving first-seen order.
    code_meta: dict[str, dict] = {}
    for p in valid_periods:
        for codigo, acc in (p.get("accounts") or {}).items():
            if codigo not in code_meta:
                code_meta[codigo] = {
                    "label": acc.get("label") or codigo,
                    "section": acc.get("section") or "",
                }

    rows: list[list] = []
    last_section: str | None = None
    n_periods = len(valid_periods)
    for codigo, meta in code_meta.items():
        section = meta["section"]
        if section and section != last_section:
            # Section header row — span all columns.
            header_row = [f"— {section} —", ""]
            header_row.extend([""] * n_periods)
            rows.append(header_row)
            last_section = section
        row: list = [codigo, meta["label"]]
        for p in valid_periods:
            acc = (p.get("accounts") or {}).get(codigo) or {}
            val = acc.get("valor_brl")
            row.append(_fmt(val, "brl") if val is not None else "—")
        rows.append(row)

    # Detect period type for the caption
    is_quarterly = any(p.get("quarter") is not None for p in valid_periods)
    period_word = "trimestrais" if is_quarterly else "anuais"

    return {
        "title": title,
        "type": "table",
        "columns": columns,
        "rows": rows,
        # [v1.24] Wrap wide tables (≥7 columns → "Código" + "Descrição" + 5+ periods)
        # in a horizontally-scrollable container so the layout doesn't blow out.
        "wide": n_periods > 5,
        "note": (
            f"Comparativo de {n_periods} período(s) {period_word} ({statement_type}). "
            "Valores em R$ (formato compacto)."
        ),
    }


def _merge_bpa_bpp_periods(
    bpa_periods: list[dict], bpp_periods: list[dict],
) -> list[dict]:
    """[v1.24] Merge BPA + BPP periods into a single list with combined accounts.

    For each period present in EITHER input, merge the accounts dicts (BPA
    accounts first, then BPP accounts — same order as the Completo sub-tab
    visual: Ativo section first, then Passivo). Periods are returned
    newest-first, keyed by ``period`` (or ``data_fim_exerc`` as fallback).

    Used by the Balanço "Completo" sub-tab so the multi-period comparison
    table shows both sides of the balance sheet side-by-side across periods.
    """
    by_period: dict[str, dict] = {}
    for p in bpa_periods + bpp_periods:
        period_key = p.get("period") or p.get("data_fim_exerc") or ""
        if not period_key:
            continue
        if period_key not in by_period:
            by_period[period_key] = {
                "period": period_key,
                "data_fim_exerc": p.get("data_fim_exerc"),
                "year": p.get("year"),
                "quarter": p.get("quarter"),
                "accounts": {},
            }
        # Merge accounts (BPA first, then BPP — preserves visual grouping)
        for codigo, acc in (p.get("accounts") or {}).items():
            by_period[period_key]["accounts"][codigo] = acc

    return sorted(
        by_period.values(),
        key=lambda p: (p.get("year") or 0, p.get("quarter") or 0),
        reverse=True,
    )


def _build_period_toggle_sections(
    label: str,
    annual_periods: list[dict],
    quarterly_periods: list[dict] | None,
    statement_type: str,
    annual_chart: dict | list[dict] | None = None,
    quarterly_chart: dict | list[dict] | None = None,
) -> list[dict]:
    """[v1.25 v3] Build a section list with optional period toggle.

    - When ``quarterly_periods`` is non-empty: returns a single
      ``type: "period_toggle"`` section wrapping two ``build_multi_period_table``
      calls (annual + quarterly) PLUS optional charts. Quarterly visible by default.
    - When ``quarterly_periods`` is empty/None: returns just the annual
      multi-period table + annual chart (no toggle).

    Args:
        label: statement label used in table titles.
        annual_periods: annual period dicts.
        quarterly_periods: quarterly period dicts, or None/[] when unavailable.
        statement_type: BPA / BPP / DRE / DFC / DVA.
        annual_chart: optional chart section(s) for the annual panel.
        quarterly_chart: optional chart section(s) for the quarterly panel.

    Returns:
        List of 0-1 sections.
    """
    annual_table = build_multi_period_table(
        f"{label} — Comparativo Anual", annual_periods, statement_type)

    # Normalize charts to lists
    annual_charts = []
    if annual_chart:
        annual_charts = annual_chart if isinstance(annual_chart, list) else [annual_chart]
    quarterly_charts = []
    if quarterly_chart:
        quarterly_charts = quarterly_chart if isinstance(quarterly_chart, list) else [quarterly_chart]

    if quarterly_periods:
        quarterly_table = build_multi_period_table(
            f"{label} — Comparativo Trimestral", quarterly_periods, statement_type)
        if annual_table or quarterly_table:
            annual_secs = ([annual_table] if annual_table else []) + annual_charts
            quarterly_secs = ([quarterly_table] if quarterly_table else []) + quarterly_charts
            return [{
                "type": "period_toggle",
                "annual_sections": annual_secs,
                "quarterly_sections": quarterly_secs,
            }]
        return []

    if annual_table:
        return [annual_table] + annual_charts
    return []
