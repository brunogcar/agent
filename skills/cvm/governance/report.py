"""skills/cvm/governance/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the score() + practices() + by_chapter() results into a multi-tab
dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


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


# ── Governance practice adoption tooltips (v3) ──────────────────────────────
# Maps the raw CGVN ``Pratica_Adotada`` value to a PT-BR explanation of what
# the adoption level means. Used as cell-level tooltip on the "Adotada"
# column of the Practices tab so the user can hover to see the meaning of
# Sim / Parcialmente / Não.
_ADOPTED_TOOLTIPS: dict[str, str] = {
    "Sim":          "Sim = prática totalmente adotada pela companhia.",
    "Parcialmente": "Parcialmente = prática adotada em parte; alguns critérios atendidos.",
    "Não":          "Não = prática não adotada pela companhia.",
}


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


# ── Compliance level helper ──────────────────────────────────────────────────

def _compliance_level(score_pct: float | None) -> str:
    """Translate a governance score (0-1 fraction of Sim) into a compliance
    level label.

      - score_pct >= 0.80  -> "Alto" (High)
      - 0.50 <= score < 0.80 -> "Médio" (Medium)
      - score_pct < 0.50   -> "Baixo" (Low)
      - None               -> "—"
    """
    if score_pct is None:
        return "—"
    try:
        s = float(score_pct)
    except (TypeError, ValueError):
        return "—"
    if s >= 0.80:
        return "Alto"
    if s >= 0.50:
        return "Médio"
    return "Baixo"


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(
    score_result: dict,
    practices_result: dict,
) -> list[dict]:
    """Build 3 KPI cards for the dashboard top-level kpis list.

    Cards (from the score() + practices() results):
      - Governance Score  — score_pct formatted as pct (from score())
      - Practices Count   — total_practices as int (from score())
                            (falls back to practices()['count'] when score
                             is unavailable)
      - Compliance Level  — derived label (Alto/Médio/Baixo) from score_pct
    """
    # 1. Governance Score
    score_pct = score_result.get("score_pct") if _ok(score_result) else None

    # 2. Practices Count — prefer score()['total_practices']; fall back to
    #    practices()['count'] when score() is unavailable.
    total_practices: int | None = None
    if _ok(score_result):
        total_practices = score_result.get("total_practices")
    if total_practices is None and _ok(practices_result):
        total_practices = practices_result.get("count")

    # 3. Compliance Level
    compliance = _compliance_level(score_pct)

    return [
        _kpi("Governance Score", score_pct, "pct", "pct"),
        _kpi("Practices Count",  total_practices, "int", "int"),
        _kpi("Compliance Level", compliance, "text", "text"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(
    score_result: dict,
    practices_result: dict,
) -> dict:
    """Build the Overview tab's text section summarizing the governance data.

    Multi-line text showing company, CNPJ, data_referencia, total practices,
    adopted/partial/not-adopted counts, and the compliance level.
    """
    company = (score_result.get("company")
               if _ok(score_result)
               else practices_result.get("company", ""))
    cnpj = (score_result.get("cnpj")
            if _ok(score_result)
            else practices_result.get("cnpj", ""))
    data_ref = (score_result.get("data_referencia")
                if _ok(score_result)
                else practices_result.get("data_referencia", ""))

    if _ok(score_result):
        total = score_result.get("total_practices", 0)
        sim = score_result.get("adopted_sim", 0)
        parcial = score_result.get("adopted_parcialmente", 0)
        nao = score_result.get("adopted_nao", 0)
        score_pct = score_result.get("score_pct")
    else:
        total = practices_result.get("count", 0)
        sim = parcial = nao = "—"
        score_pct = None

    compliance = _compliance_level(score_pct if isinstance(score_pct, (int, float)) else None)

    text_lines = [
        f"Company: {company}",
        f"CNPJ: {cnpj or '—'}",
        f"Data de Referência: {data_ref or '—'}",
        f"Total de Práticas: {total}",
        f"Adotadas (Sim): {sim}",
        f"Parcialmente: {parcial}",
        f"Não Adotadas: {nao}",
        f"Nível de Conformidade: {compliance}",
    ]
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Practices tab section (full practices table) ────────────────────────────

def build_practices_section(practices_result: dict) -> dict:
    """Build the Practices tab table from the practices() result.

    Columns: Item, Capítulo, Princípio, Prática Recomendada, Adotada, Explicação

    [v3] The "Adotada" column cell is now a dict cell carrying a tooltip
    that explains what each adoption level means (Sim = fully adopted,
    Parcialmente = partial, Não = not adopted).
    """
    practices_list = (practices_result.get("practices")
                      if _ok(practices_result) else []) or []

    columns = ["Item", "Capítulo", "Princípio",
               "Prática Recomendada", "Adotada", "Explicação"]
    rows = []
    for p in practices_list:
        adopted = p.get("Pratica_Adotada", "") or "—"
        rows.append([
            p.get("ID_Item", "") or "—",
            p.get("Capitulo", "") or "—",
            p.get("Principio", "") or "—",
            p.get("Pratica_Recomendada", "") or "—",
            _cell(adopted, _ADOPTED_TOOLTIPS.get(adopted, "")),
            p.get("Explicacao", "") or "—",
        ])

    formats = {c: "text" for c in columns}

    return {
        "title": f"Governance Practices ({len(practices_list)} practices)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (f"{len(practices_list)} prática(s) recomendada(s) com "
                 "respectivo status de adoção (Sim/Parcialmente/Não)."),
    }


# ── By Chapter tab section ───────────────────────────────────────────────────

def build_by_chapter_section(by_chapter_result: dict) -> dict:
    """Build the By Chapter tab table from the by_chapter() result.

    Columns: Capítulo, Total, Adotadas, Parciais, Não Adotadas, Score %
    """
    chapters = (by_chapter_result.get("by_chapter")
                if _ok(by_chapter_result) else []) or []

    columns = ["Capítulo", "Total", "Adotadas", "Parciais",
               "Não Adotadas", "Score %"]
    rows = []
    for ch in chapters:
        total = ch.get("total", 0)
        adopted = ch.get("adopted", 0)
        score_pct = adopted / total if total > 0 else 0
        rows.append([
            ch.get("Capitulo", "") or "—",
            total,
            adopted,
            ch.get("partial", 0),
            ch.get("not_adopted", 0),
            _fmt(score_pct, "pct"),
        ])

    formats = {
        "Capítulo": "text", "Total": "int", "Adotadas": "int",
        "Parciais": "int", "Não Adotadas": "int", "Score %": "text",
    }

    return {
        "title": f"Governance by Chapter ({len(chapters)} chapters)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Práticas agrupadas por capítulo (Capitulo) com contagens de adoção.",
    }


# ── By Chapter horizontal bar chart (v3) ─────────────────────────────────────

def build_by_chapter_chart(by_chapter_result: dict) -> dict | None:
    """Build a horizontal bar chart showing Score % by Chapter.

    Each chapter is a row; the bar length is the % of fully-adopted practices
    (Adopted / Total). Bars are colored by compliance level: teal for
    Alto (>=80%), orange for Médio (50–80%), red for Baixo (<50%).

    Returns None when there are no chapters or no chapter has a positive
    Total count.
    """
    chapters = (by_chapter_result.get("by_chapter")
                if _ok(by_chapter_result) else []) or []
    if not chapters:
        return None

    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for ch in chapters:
        total = ch.get("total", 0) or 0
        adopted = ch.get("adopted", 0) or 0
        if total <= 0:
            continue
        score_pct = (adopted / total) * 100.0  # 0..100
        labels.append(ch.get("Capitulo", "") or "—")
        values.append(round(score_pct, 2))
        if score_pct >= 80.0:
            colors.append(_TEAL)
        elif score_pct >= 50.0:
            colors.append(_ORANGE)
        else:
            colors.append(_RED)

    if not labels:
        return None

    return {
        "title": "Governance Score % by Chapter",
        "description": (
            "Percentual de práticas totalmente adotadas (Sim) por capítulo. "
            "Barras em teal (Alto ≥ 80%), laranja (Médio 50–80%) ou "
            "vermelha (Baixo < 50%). Quanto mais longa a barra, maior a "
            "adesão às práticas recomendadas do capítulo."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Score % (Adotadas / Total)",
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": colors,
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "indexAxis": "y",  # horizontal bar chart (chapter names on Y)
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Governance Score % by Chapter"},
                },
                "scales": {
                    "x": {"min": 0, "max": 100,
                          "grid": {"color": "rgba(128,128,128,0.1)"},
                          "ticks": {"callback": "function(v){return v+'%'}"}},
                    "y": {"grid": {"display": False}},
                },
            },
        },
    }


# ── Chart builders (v1.2) ────────────────────────────────────────────────────
# Each chart builder returns {"type": "chart", "chart_data": <Chart.js config>}
# or None when no data. The dashboard template passes chart_data verbatim to
# `new Chart(ctx, chart_data)`.

# Brand palette (matches the report theme).
_TEAL   = "#0d9488"
_ORANGE = "#f59e0b"
_RED    = "#ef4444"
_BLUE   = "#3b82f6"
_PURPLE = "#a855f7"

# Map CGVN Pratica_Adotada raw values to dashboard-friendly labels.
# CGVN stores: "Sim", "Parcialmente", "Não" — the chart renames them to
# Adequado / Parcialmente / Não Adequado per the governance terminology.
_ADOPTED_LABELS = {
    "Sim":          "Adequado",
    "Parcialmente": "Parcialmente",
    "Não":          "Não Adequado",
}

# Doughnut segment colors (one per compliance level).
_ADOPTED_COLORS = {
    "Adequado":     _TEAL,
    "Parcialmente": _ORANGE,
    "Não Adequado": _RED,
}


def build_practices_doughnut(practices_data: Any) -> dict | None:
    """Build a Chart.js doughnut chart showing distribution of practice
    compliance levels (Adequado / Parcialmente / Não Adequado).

    practices_data is the practices() result dict (which contains a
    ``practices`` list of rows with ``Pratica_Adotada`` values). When
    passed a list directly, treats it as the practices list.

    Returns None when there are no practices or no recognizable adoption
    values, so the dashboard can skip the section gracefully.
    """
    # Accept either a practices() result dict or a raw list.
    if isinstance(practices_data, dict):
        practices_list = practices_data.get("practices") or []
    elif isinstance(practices_data, list):
        practices_list = practices_data
    else:
        return None

    if not practices_list:
        return None

    # Count by Pratica_Adotada raw value.
    raw_counts: dict[str, int] = {}
    for p in practices_list:
        if not isinstance(p, dict):
            continue
        val = (p.get("Pratica_Adotada") or "").strip()
        if not val:
            continue
        raw_counts[val] = raw_counts.get(val, 0) + 1

    if not raw_counts:
        return None

    # Build ordered labels (Adequado first, then Parcialmente, then Não
    # Adequado), then any unknown values appended at the end.
    ordered_labels = ["Sim", "Parcialmente", "Não"]
    seen = set()
    label_seq: list[str] = []
    for k in ordered_labels:
        if k in raw_counts:
            label_seq.append(k)
            seen.add(k)
    for k in raw_counts:
        if k not in seen:
            label_seq.append(k)
            seen.add(k)

    labels = [_ADOPTED_LABELS.get(k, k) for k in label_seq]
    counts = [raw_counts[k] for k in label_seq]
    colors = [_ADOPTED_COLORS.get(lbl, _BLUE) for lbl in labels]

    return {
        "title": "Practices Compliance Distribution",
        "description": (
            "Distribuição das práticas de governança por nível de adoção "
            "(Adequado / Parcialmente / Não Adequado)."
        ),
        "type": "chart",
        "chart_data": {
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Practices",
                    "data": counts,
                    "backgroundColor": colors,
                    "borderColor": "#ffffff",
                    "borderWidth": 2,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Practices Compliance Distribution"},
                },
                "cutout": "60%",
            },
        },
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"
