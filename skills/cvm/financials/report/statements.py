"""skills/cvm/financials/report/statements.py -- Shared statement table builders.

Hosts the multi-period comparison table builder used by all 4 statement
tabs (Balanço / DRE / DFC / DVA) plus the period_toggle wrapper that
switches between annual + quarterly (and optionally TTM) views.

Public builders:
  - ``build_multi_period_table(title, periods, statement_type)`` — side-by-side
    comparison table for up to 20 periods.

Private helpers (imported by ``report/balanco.py``, ``report/dre.py``,
``report/dfc.py``, ``report/dva.py``):
  - ``_statement_table_section(title, accounts_dict)`` — single-period table
    (legacy, kept for fallback).
  - ``_merge_bpa_bpp_periods(bpa_periods, bpp_periods)`` — merge BPA + BPP
    periods for the Balanço "Completo" sub-tab.
  - ``_build_period_toggle_sections(...)`` — wraps annual + quarterly (+ TTM)
    tables (and optional charts) in a ``type: "period_toggle"`` section.
    [v2.1] TTM (trailing twelve months) is an optional 3rd panel for flow
    statements (DRE/DFC/DVA). When ``ttm_periods`` + ``ttm_chart`` are
    provided, the section emits ``ttm_sections`` alongside
    ``annual_sections`` + ``quarterly_sections``. The TTM panel shows a
    small metrics table (built via ``build_ttm_table``) + the TTM chart(s).
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _format_period_label, _period_sort_key
from skills.cvm.financials.report.periods import build_ttm_table


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
    ttm_periods: list[dict] | None = None,
    ttm_chart: dict | list[dict] | None = None,
) -> list[dict]:
    """[v1.25 v3 / v2.1] Build a section list with optional period toggle.

    - When ``quarterly_periods`` is non-empty: returns a single
      ``type: "period_toggle"`` section wrapping two ``build_multi_period_table``
      calls (annual + quarterly) PLUS optional charts. Quarterly visible by default.
    - When ``quarterly_periods`` is empty/None: returns just the annual
      multi-period table + annual chart (no toggle).
    - [v2.1] When ``ttm_periods`` (or ``ttm_chart``) is provided: the section
      ALSO emits a ``ttm_sections`` key — a 3rd panel showing a small TTM
      metrics table (built via ``build_ttm_table``) + the TTM chart(s). Used
      by flow-statement tabs (DRE/DFC/DVA) so the user can switch between
      annual / TTM / quarterly views. Skipped for snapshot tabs (BPA/BPP)
      because TTM for snapshots = latest snapshot (no value-add).

    Args:
        label: statement label used in table titles.
        annual_periods: annual period dicts.
        quarterly_periods: quarterly period dicts, or None/[] when unavailable.
        statement_type: BPA / BPP / DRE / DFC / DVA.
        annual_chart: optional chart section(s) for the annual panel.
        quarterly_chart: optional chart section(s) for the quarterly panel.
        ttm_periods: [v2.1] optional list of TTM period dicts (from
            ``ttm_result["periods"]``). When non-empty, a TTM metrics table
            is added to a 3rd toggle panel.
        ttm_chart: [v2.1] optional chart section(s) for the TTM panel.

    Returns:
        List of 0-1 sections. The ``period_toggle`` section's shape:
        ``{type, annual_sections, quarterly_sections, ttm_sections?}`` —
        ``ttm_sections`` is present only when TTM data was provided.
    """
    annual_table = build_multi_period_table(
        f"{label} — Comparativo Anual", annual_periods, statement_type)

    # Normalize charts to lists
    def _as_list(x):
        if not x:
            return []
        return x if isinstance(x, list) else [x]

    annual_charts = _as_list(annual_chart)
    quarterly_charts = _as_list(quarterly_chart)
    ttm_charts = _as_list(ttm_chart)

    # [v2.1] Build a small TTM metrics table from the raw TTM periods.
    # TTM periods don't have ``accounts`` (they have ``metrics``), so the
    # multi-period table builder can't be reused. ``build_ttm_table`` from
    # ``report/periods.py`` handles the metrics shape directly. Returns None
    # when ``ttm_periods`` is empty.
    ttm_table = build_ttm_table(ttm_periods) if ttm_periods else None

    has_ttm = bool(ttm_table) or bool(ttm_charts)

    if quarterly_periods or has_ttm:
        quarterly_table = build_multi_period_table(
            f"{label} — Comparativo Trimestral", quarterly_periods, statement_type
        ) if quarterly_periods else None
        if annual_table or quarterly_table or has_ttm:
            annual_secs = ([annual_table] if annual_table else []) + annual_charts
            quarterly_secs = ([quarterly_table] if quarterly_table else []) + quarterly_charts
            ttm_secs = ([ttm_table] if ttm_table else []) + ttm_charts
            section: dict = {
                "type": "period_toggle",
                "annual_sections": annual_secs,
                "quarterly_sections": quarterly_secs,
            }
            if ttm_secs:
                section["ttm_sections"] = ttm_secs
            return [section]
        return []

    if annual_table:
        return [annual_table] + annual_charts
    return []
