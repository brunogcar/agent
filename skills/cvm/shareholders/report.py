"""skills/cvm/shareholders/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the summary() result into a multi-tab dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any
from datetime import date

from tools.report_ops.formats import apply_fmt


# ── Staleness warning helper ──────────────────────────────────────────────────

def _staleness_note(data_referencia: str, threshold_days: int = 730) -> str:
    """Return a warning string if data_referencia is older than threshold_days.

    [v1.2] Added threshold_days parameter (default 730 = 2 years) so callers
    can customize per data source. FRE (annual) uses 730; VLMO (continuous)
    would use 60; ITR (quarterly) would use 365.

    Returns "" if the date is recent, missing, or unparseable.
    CVM filing gaps happen for smaller/less-liquid companies — this gives
    the user a heads-up that the data may be stale without breaking the
    dashboard.
    """
    if not data_referencia or not isinstance(data_referencia, str):
        return ""
    try:
        ref = date.fromisoformat(data_referencia.strip()[:10])
    except (ValueError, TypeError):
        return ""
    age_days = (date.today() - ref).days
    if age_days > threshold_days:
        if threshold_days >= 365:
            years = age_days // 365
            return f"⚠️ Data from {data_referencia} ({years}+ years old) — may be stale."
        else:
            months = age_days // 30
            return f"⚠️ Data from {data_referencia} ({months}+ months old) — may be stale."
    return ""


# ── BPP 2.03.* code -> display label ─────────────────────────────────────────
# Mirrors the _EQUITY_CODES list from tools/report_ops/adapters/shareholders.py
# so the dashboard's Equity tab labels match the existing equity_structure
# adapter column headers exactly.
_EQUITY_CODES = [
    ("2.03",    "PL Total"),
    ("2.03.01", "Capital Social"),
    ("2.03.02", "Reservas de Capital"),
    ("2.03.04", "Reservas de Lucros"),
    ("2.03.05", "Lucros Acumulados"),
    ("2.03.09", "Minority Interest"),
]


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


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


def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"


# ── Section accessors ────────────────────────────────────────────────────────

def _section(summary_result: dict, name: str) -> dict:
    """Return a sub-section dict from summary_result['sections'][name].

    Returns an empty dict when summary_result or the section is missing —
    callers can then safely call .get() on it without crashing.
    """
    if not isinstance(summary_result, dict):
        return {}
    sections = summary_result.get("sections") or {}
    return sections.get(name) or {}


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(summary_result: dict) -> list[dict]:
    """Build 3 KPI cards for the dashboard top-level kpis list.

    Cards (all sourced from summary_result['sections']):
      - % Free Float     — pct_raw format (FRE stores 71.1 = 71.1% as-is)
                           from sections['free_float']['pct_total_circulacao']
      - Total Acionistas — int format (sum of PF + PJ + Inst.)
                           from sections['free_float']
      - PL Total         — brl format (Patrimônio Líquido total, BPP 2.03)
                           from sections['equity']['components']['2.03']
                            (or patrimonio_liquido_total fallback)
    """
    ff = _section(summary_result, "free_float")
    eq = _section(summary_result, "equity")

    # 1. % Free Float
    pct_ff = ff.get("pct_total_circulacao")

    # 2. Total Acionistas — sum of PF + PJ + Inst. counts when present
    pf = _num(ff.get("qtd_acionistas_pf")) or 0
    pj = _num(ff.get("qtd_acionistas_pj")) or 0
    inst = _num(ff.get("qtd_acionistas_inst")) or 0
    try:
        total_owners = int(pf) + int(pj) + int(inst)
    except (TypeError, ValueError):
        total_owners = None
    # If none of the counts were available, render as dash.
    if total_owners == 0 and pf == 0 and pj == 0 and inst == 0 and \
            ff.get("qtd_acionistas_pf") is None and \
            ff.get("qtd_acionistas_pj") is None and \
            ff.get("qtd_acionistas_inst") is None:
        total_owners = None

    # 3. PL Total — prefer components["2.03"]; fall back to patrimonio_liquido_total
    components = eq.get("components") or {}
    pl_total = components.get("2.03")
    if pl_total is None:
        pl_total = eq.get("patrimonio_liquido_total")

    return [
        _kpi("% Free Float",    pct_ff,      "pct_raw", "pct_raw"),
        _kpi("Total Acionistas", total_owners, "int",     "int"),
        _kpi("PL Total",         pl_total,    "brl",     "brl"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(summary_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the shareholders data.

    Multi-line text showing company, data de referência, % free float,
    total acionistas, and PL total.
    """
    company = (summary_result.get("company") if isinstance(summary_result, dict)
               else "") or ""
    ff = _section(summary_result, "free_float")
    eq = _section(summary_result, "equity")

    data_ref = ff.get("data_referencia") or eq.get("data_fim_exerc") or "—"
    pct_ff = ff.get("pct_total_circulacao")
    pct_ff_str = _fmt(pct_ff, "pct_raw") if pct_ff is not None else "—"

    pf = _num(ff.get("qtd_acionistas_pf")) or 0
    pj = _num(ff.get("qtd_acionistas_pj")) or 0
    inst = _num(ff.get("qtd_acionistas_inst")) or 0
    try:
        total_owners = int(pf) + int(pj) + int(inst)
    except (TypeError, ValueError):
        total_owners = 0
    if total_owners == 0 and pf == 0 and pj == 0 and inst == 0 and \
            ff.get("qtd_acionistas_pf") is None and \
            ff.get("qtd_acionistas_pj") is None and \
            ff.get("qtd_acionistas_inst") is None:
        total_owners_str = "—"
    else:
        total_owners_str = str(total_owners)

    components = eq.get("components") or {}
    pl_total = components.get("2.03")
    if pl_total is None:
        pl_total = eq.get("patrimonio_liquido_total")
    pl_total_str = _fmt(pl_total, "brl") if pl_total is not None else "—"

    text_lines = [
        f"Company: {company or '—'}",
        f"Data de Referência: {data_ref}",
        f"% Free Float: {pct_ff_str}",
        f"Total Acionistas: {total_owners_str}",
        f"PL Total: {pl_total_str}",
    ]
    # [v3] Show section errors so the user knows WHY KPIs are "—"
    sh = _section(summary_result, "shareholders")
    if not _ok(sh) and sh.get("error"):
        text_lines.append(f"Shareholders Error: {sh.get('error')}")
    if not _ok(ff) and ff.get("error"):
        text_lines.append(f"Free Float Error: {ff.get('error')}")
    if not _ok(eq) and eq.get("error"):
        text_lines.append(f"Equity Error: {eq.get('error')}")
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Top Shareholders tab section ─────────────────────────────────────────────

def build_top_shareholders_section(summary_result: dict) -> dict:
    """Build the Top Shareholders tab table from the summary() result.

    Columns: Acionista, % Total, Qtde Total, Controlador
    One row per shareholder in sections['shareholders']['top'].
    """
    sh = _section(summary_result, "shareholders")
    top = sh.get("top") or []

    columns = ["Acionista", "% Total", "Qtde Total", "Controlador"]
    rows = []
    for s in top:
        rows.append([
            s.get("acionista", "") or "—",
            _num(s.get("pct_total")),
            _num(s.get("qtd_total")),
            "Sim" if s.get("controlador") else "Não",
        ])

    formats = {
        "Acionista":    "text",
        "% Total":      "pct_raw",
        "Qtde Total":   "int",
        "Controlador":  "text",
    }

    return {
        "title": f"Principais Acionistas ({len(top)} acionistas)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (f"Data de referência: {sh.get('data_referencia', '—')}. "
                 "Top 5 acionistas por % total."
                 + (_staleness_note(sh.get('data_referencia', '')) and
                    f" {_staleness_note(sh.get('data_referencia', ''))}" or '')),
    }


# ── Free Float tab section ───────────────────────────────────────────────────

def build_free_float_section(summary_result: dict) -> dict:
    """Build the Free Float tab table from the summary() result.

    Columns: % Free Float, Acionistas PF, Acionistas PJ, Acionistas Inst.
    Single row sourced from sections['free_float'] scalars.

    [v4] When the free_float section has an error status (FRE not synced or
    no distribuicao_capital rows for this company), show a note with the
    error message instead of just rendering "—" values silently.
    """
    ff = _section(summary_result, "free_float")

    # [v4] If free_float section has an error, show it in the note.
    if not _ok(ff) and ff.get("error"):
        return {
            "title": "Free Float / Distribuição de Acionistas",
            "type": "table",
            "columns": ["% Free Float", "Acionistas PF", "Acionistas PJ", "Acionistas Inst."],
            "rows": [["—", "—", "—", "—"]],
            "formats": {"% Free Float": "text", "Acionistas PF": "text",
                        "Acionistas PJ": "text", "Acionistas Inst.": "text"},
            "note": f"Error: {ff.get('error')}. FRE database may not have "
                    f"distribuicao_capital data for this company.",
        }

    columns = ["% Free Float", "Acionistas PF", "Acionistas PJ", "Acionistas Inst."]
    rows = [[
        _num(ff.get("pct_total_circulacao")),
        _num(ff.get("qtd_acionistas_pf")),
        _num(ff.get("qtd_acionistas_pj")),
        _num(ff.get("qtd_acionistas_inst")),
    ]]
    formats = {
        "% Free Float":     "pct_raw",
        "Acionistas PF":    "int",
        "Acionistas PJ":    "int",
        "Acionistas Inst.": "int",
    }

    return {
        "title": "Free Float / Distribuição de Acionistas",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (f"Data de referência: {ff.get('data_referencia', '—')}. "
                 "% Free Float = pct_total_circulacao (ON+PN)."
                 + (_staleness_note(ff.get('data_referencia', '')) and
                    f" {_staleness_note(ff.get('data_referencia', ''))}" or '')
                 + (" (approximate — shareholder list truncated at 50)"
                    if summary_result.get("sections", {}).get("_free_float_approximate")
                    else "")),
    }


# ── Equity Structure tab section ─────────────────────────────────────────────

def build_equity_section(summary_result: dict) -> dict:
    """Build the Equity Structure tab table from the summary() result.

    Columns: Componente, Valor BRL
    One row per BPP 2.03.* code present in sections['equity']['components'].
    Component labels come from _EQUITY_CODES (2.03=PL Total, etc.).
    """
    eq = _section(summary_result, "equity")
    components = eq.get("components") or {}
    label_map = dict(_EQUITY_CODES)

    columns = ["Componente", "Valor BRL"]
    rows = []
    for code, label in _EQUITY_CODES:
        if code in components:
            rows.append([label, _num(components.get(code))])

    formats = {
        "Componente": "text",
        "Valor BRL":  "brl",
    }

    return {
        "title": f"Composição do PL ({eq.get('data_fim_exerc', '—')})",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": ("Valores de balanço (snapshot) em BRL por exercício. "
                 "BPP 2.03.* — Patrimônio Líquido e componentes."),
    }
