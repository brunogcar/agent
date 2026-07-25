"""adapters/governance.py — Flatten governance skill JSON → table data.

Adapters:
  governance_practices  — all practices table (recommended, adopted, chapter)
  governance_score      — KPI strip (score %, adopted, partial, not adopted) + summary table
  governance_by_chapter — per-chapter adoption table
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


@register_adapter("governance_practices")
def practices(result: dict) -> dict:
    """Flatten governance.practices result into a practices table."""
    if not _ok(result):
        return _error_table(result, title="Governance Practices")

    practices_list = result.get("practices") or []
    if not practices_list:
        return _error_table(result, title="Governance Practices")

    columns = ["Item", "Capítulo", "Princípio", "Prática Recomendada", "Adotada", "Explicação"]
    rows = []
    for p in practices_list:
        rows.append([
            p.get("ID_Item", ""),
            p.get("Capitulo", ""),
            p.get("Principio", ""),
            p.get("Pratica_Recomendada", ""),
            p.get("Pratica_Adotada", ""),
            p.get("Explicacao", ""),
        ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Governance Practices ({len(practices_list)} practices, {result.get('data_referencia','')})",
            "columns": columns,
            "rows": rows,
            "formats": {c: "text" for c in columns},
        }],
        "kpis": [],
        "sources": [],
    }


@register_adapter("governance_score")
def score(result: dict) -> dict:
    """Flatten governance.score result into a KPI strip + summary table."""
    if not _ok(result):
        return _error_table(result, title="Governance Score")

    total = result.get("total_practices", 0)
    sim = result.get("adopted_sim", 0)
    nao = result.get("adopted_nao", 0)
    parcial = result.get("adopted_parcialmente", 0)

    columns = ["Status", "Count", "%"]
    rows = [
        ["Sim (Adotada)", sim, apply_fmt(result.get("score_pct"), "pct")],
        ["Parcialmente", parcial, apply_fmt(result.get("partial_pct"), "pct")],
        ["Não (Não Adotada)", nao, apply_fmt(result.get("not_adopted_pct"), "pct")],
        ["Total", total, "100%"],
    ]

    kpis = [
        {"label": "Score", "value": apply_fmt(result.get("score_pct"), "pct")},
        {"label": "Parcial", "value": apply_fmt(result.get("partial_pct"), "pct")},
        {"label": "Não Adotada", "value": apply_fmt(result.get("not_adopted_pct"), "pct")},
        {"label": "Total Práticas", "value": total, "format": "int"},
    ]

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Governance Score ({result.get('data_referencia','')})",
            "columns": columns,
            "rows": rows,
            "formats": {"Status": "text", "Count": "int", "%": "text"},
        }],
        "kpis": kpis,
        "sources": [],
    }


@register_adapter("governance_by_chapter")
def by_chapter(result: dict) -> dict:
    """Flatten governance.by_chapter result into a per-chapter table."""
    if not _ok(result):
        return _error_table(result, title="Governance by Chapter")

    chapters = result.get("by_chapter") or []
    if not chapters:
        return _error_table(result, title="Governance by Chapter")

    columns = ["Capítulo", "Total", "Adotadas", "Parciais", "Não Adotadas", "Score %"]
    rows = []
    for ch in chapters:
        total = ch.get("total", 0)
        adopted = ch.get("adopted", 0)
        score_pct = adopted / total if total > 0 else 0
        rows.append([
            ch.get("Capitulo", ""),
            total,
            adopted,
            ch.get("partial", 0),
            ch.get("not_adopted", 0),
            apply_fmt(score_pct, "pct"),
        ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Governance by Chapter ({len(chapters)} chapters)",
            "columns": columns,
            "rows": rows,
            "formats": {
                "Capítulo": "text", "Total": "int", "Adotadas": "int",
                "Parciais": "int", "Não Adotadas": "int", "Score %": "text",
            },
        }],
        "kpis": [],
        "sources": [],
    }
