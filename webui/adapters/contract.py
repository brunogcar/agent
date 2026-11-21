"""webui/adapters/contract.py — the section payload contract.

[v1.7] Formalizes the ad-hoc section-dict pattern the WebUI has used since
v1.4 (Valuation) and v1.6 (Proventos): server builders produce plain dicts,
ONE generic client renderer (renderValSubtab + valSectionsHtml +
renderValChart in app.js) draws them. Improving a subtab = adding sections
server-side, zero client rework.

This module is the CONTRACT — the single source of truth for every shape
the generic renderer understands. New tabs (v1.8: Opções, Histórico,
Macro, …) build payloads through these helpers and get validated at
dispatch time; a payload that violates the contract is flagged in the
server log with `_contract_violations` attached (the client ignores
unknown keys, so a minor deviation degrades loudly in dev, not silently).

PAYLOAD SHAPES (exactly one per subtab response)
------------------------------------------------
1. FLAT (generic renderer, no pills):
     {"ticker": "PETR4", "status": "ok",
      "kpis": [KPI, …],               # optional, renders the KPI grid
      "sections": [Section, …]}       # 0+ sections in order
2. GROUPED (nested subtab pills):
     {"ticker": "PETR4", "status": "ok",
      "groups": [{"name": "Rentabilidade",
                  "subsections": [{"name": "Retornos", "sections": […]}, …],
                  "sections": […]}, …]}    # sections OR subsections
   ALL-METRICS variant (collapsible category list):
     {"ticker": "PETR4", "status": "ok",
      "groups": [{"name": "Mercado", "metrics": [KPI, …]}, …]}
3. ERROR (any shape):
     {"ticker": "PETR4", "_error": "mensagem PT-BR"}

SECTION TYPES
-------------
  chart       {type, title, description?, chart_data: {type, data}}
              chart_data is a plain Chart.js config subset: "type" (line,
              bar, radar, …) + "data" {labels, datasets}. Options are
              rebuilt client-side with chartTheme() — server-side options
              are intentionally discarded (except y.beginAtZero, stacked).
  table       {type, title?, description?, columns: [str, …],
               rows: [[cell, …], …], note?}
              cell = str | {text, tooltip}
  two_column  {type, left_title, left_rows: [KPI, …],
               right_title, right_rows: [KPI, …]}
  ratio_grid  {type, title?, description?,
               categories: [{items: [KPI, …]}, …]}
  heatmap     {type, title?, description?, columns: [str, …],
               rows: [[label, {text, bg, color, tooltip?}, …], …]}

KPI = {"label": str, "value": str, "tooltip": str?}
      value is a PRE-FORMATTED PT-BR string (apply_fmt) — the client only
      colorizes (negative red, % green/red/yellow).
"""
from __future__ import annotations

from typing import Any

# Section types the generic renderer (app.js valSectionHtml) understands.
SECTION_TYPES = ("chart", "table", "two_column", "ratio_grid", "heatmap")


# ── builders ────────────────────────────────────────────────────────────────
# Thin, typed constructors. They normalize optionals (drop empty
# description/note keys) so payloads stay minimal — but they do NOT
# silently fix wrong shapes: dispatch-time validation reports those.

def kpi(label: str, value: Any, tooltip: str = "") -> dict[str, Any]:
    """One KPI card / table row cell pair. `value` should be a formatted
    string (use tools.report_ops.formats.apply_fmt specs upstream)."""
    out: dict[str, Any] = {"label": label, "value": value}
    if tooltip:
        out["tooltip"] = tooltip
    return out


def chart_section(title: str, chart_data: dict[str, Any],
                  description: str = "") -> dict[str, Any]:
    """Chart.js section. chart_data = {"type": "line|bar|radar|…",
    "data": {"labels": […], "datasets": […]}} (options are client-side)."""
    out: dict[str, Any] = {"type": "chart", "title": title,
                           "chart_data": chart_data}
    if description:
        out["description"] = description
    return out


def table_section(title: str, columns: list[str], rows: list[list[Any]],
                  description: str = "", note: str = "") -> dict[str, Any]:
    """Table section. Cells are strings or {text, tooltip} dicts."""
    out: dict[str, Any] = {"type": "table", "title": title,
                           "columns": columns, "rows": rows}
    if description:
        out["description"] = description
    if note:
        out["note"] = note
    return out


def two_column_section(left_title: str, left_rows: list[dict[str, Any]],
                       right_title: str,
                       right_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Two side-by-side label/value blocks (rows are KPI-shaped)."""
    return {"type": "two_column", "left_title": left_title,
            "left_rows": left_rows, "right_title": right_title,
            "right_rows": right_rows}


def ratio_grid_section(title: str, categories: list[dict[str, Any]],
                       description: str = "") -> dict[str, Any]:
    """Stacked label/value tables under one title.
    categories = [{"items": [KPI, …]}, …]."""
    out: dict[str, Any] = {"type": "ratio_grid", "title": title,
                           "categories": categories}
    if description:
        out["description"] = description
    return out


def heatmap_section(title: str, columns: list[str],
                    rows: list[list[Any]],
                    description: str = "") -> dict[str, Any]:
    """Heatmap table. Row = [label, {text, bg, color, tooltip?}, …]."""
    out: dict[str, Any] = {"type": "heatmap", "title": title,
                           "columns": columns, "rows": rows}
    if description:
        out["description"] = description
    return out


def error_payload(ticker: str, message: str) -> dict[str, Any]:
    """Canonical error shape — every renderer shows data._error verbatim."""
    return {"ticker": (ticker or "").upper(), "_error": message}


# ── validation ──────────────────────────────────────────────────────────────

def _is_kpi(v: Any) -> bool:
    return (isinstance(v, dict) and "label" in v and "value" in v)


def validate_section(sec: Any, path: str = "section") -> list[str]:
    """Structural validation of ONE section. Returns violation strings
    (empty list = valid). Mirrors what the client renderer actually reads:
    a section the renderer ignores (unknown type) is a contract violation."""
    issues: list[str] = []
    if not isinstance(sec, dict):
        return [f"{path}: not a dict"]
    t = sec.get("type")
    if t not in SECTION_TYPES:
        issues.append(f"{path}: unknown type {t!r} (expected one of "
                      f"{', '.join(SECTION_TYPES)})")
        return issues
    if t == "chart":
        cd = sec.get("chart_data")
        if not isinstance(cd, dict) or not isinstance(cd.get("type"), str):
            issues.append(f"{path}.chart_data: needs {{type: str, data: …}}")
        elif not isinstance(cd.get("data"), dict):
            issues.append(f"{path}.chart_data.data: missing dict "
                          "(needs labels + datasets)")
        elif "datasets" not in cd["data"]:
            issues.append(f"{path}.chart_data.data.datasets: missing")
    elif t == "table":
        if not isinstance(sec.get("columns"), list):
            issues.append(f"{path}.columns: missing list")
        rows = sec.get("rows")
        if not isinstance(rows, list):
            issues.append(f"{path}.rows: missing list")
        elif any(not isinstance(r, list) for r in rows):
            issues.append(f"{path}.rows: every row must be a list")
    elif t == "two_column":
        for side in ("left_rows", "right_rows"):
            if not isinstance(sec.get(side), list):
                issues.append(f"{path}.{side}: missing list")
    elif t == "ratio_grid":
        cats = sec.get("categories")
        if not isinstance(cats, list):
            issues.append(f"{path}.categories: missing list")
        elif any(not isinstance(c, dict) or not isinstance(c.get("items"), list)
                 for c in cats):
            issues.append(f"{path}.categories: every item needs 'items'")
    elif t == "heatmap":
        if not isinstance(sec.get("rows"), list):
            issues.append(f"{path}.rows: missing list")
    return issues


def validate_payload(payload: Any) -> list[str]:
    """Validate a full subtab payload (flat / grouped / all-metrics /
    error). Returns violation strings (empty = valid)."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["payload: not a dict"]
    if "_error" in payload:
        return issues  # error shape is always valid

    if "groups" in payload:
        groups = payload["groups"]
        if not isinstance(groups, list):
            return ["payload.groups: not a list"]
        for gi, g in enumerate(groups):
            gp = f"groups[{gi}]"
            if not isinstance(g, dict) or not isinstance(g.get("name"), str):
                issues.append(f"{gp}: needs a name")
                continue
            if "metrics" in g:  # all-metrics variant
                if not isinstance(g["metrics"], list):
                    issues.append(f"{gp}.metrics: not a list")
                elif any(not _is_kpi(m) for m in g["metrics"]):
                    issues.append(f"{gp}.metrics: every item needs "
                                  "label + value")
            elif "subsections" in g:
                subs = g["subsections"]
                if not isinstance(subs, list):
                    issues.append(f"{gp}.subsections: not a list")
                    continue
                for si, s in enumerate(subs):
                    sp = f"{gp}.subsections[{si}]"
                    if not isinstance(s, dict) or not s.get("name"):
                        issues.append(f"{sp}: needs a name")
                        continue
                    for sec in s.get("sections") or []:
                        issues.extend(validate_section(sec, f"{sp}.section"))
            elif "sections" in g:
                for sec in g["sections"] or []:
                    issues.extend(validate_section(sec, f"{gp}.section"))
            else:
                issues.append(f"{gp}: needs sections, subsections or metrics")
        return issues

    # FLAT shape
    if "kpis" in payload:
        kpis = payload["kpis"]
        if not isinstance(kpis, list):
            issues.append("payload.kpis: not a list")
        elif any(not _is_kpi(k) for k in kpis):
            issues.append("payload.kpis: every item needs label + value")
    if "sections" in payload:
        sections = payload["sections"]
        if not isinstance(sections, list):
            issues.append("payload.sections: not a list")
        else:
            for i, sec in enumerate(sections):
                issues.extend(validate_section(sec, f"sections[{i}]"))
    elif "kpis" not in payload:
        issues.append("payload: needs kpis and/or sections (or groups)")
    return issues
