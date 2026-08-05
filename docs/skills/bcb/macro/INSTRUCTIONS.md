<- Back to [MACRO](../MACRO.md)

# 🤖 Macro — AI Editing Instructions

Rules for AI agents editing the BCB macro skill. Follow these to avoid breaking the dashboard rendering contract.

## NEVER DO

1. **NEVER use `label` as the tab field name** — use `name`. The `dashboard.html` template reads `tab.name`. Using `label` causes the sidebar to show empty tab names.
2. **NEVER put `kpis` inside individual tabs** — KPIs go at the top level of the dashboard dict (`result["kpis"]`). The template renders them in a universal header above tabs.
3. **NEVER annualize the CDI KPI** — show the daily rate (`% a.d.`). Per user request: "on top boxes, display CDI not anualizado, but current for the day". Selic KPI stays annualized.
4. **NEVER emit separate `labels` + `values` arrays** on chart sections — use `chart_data` (a Chart.js config dict). The template does `new Chart(canvas, chart_data)`; separate arrays are ignored.
5. **NEVER use list-of-dicts for table `rows`** — use list of lists: `[["2024-01-02", "0.001234"], ...]`. The template's `data_table` macro iterates cells with `{% for cell in row %}`.
6. **NEVER use em-dashes (—) or en-dashes (–)** in Python strings. Use ASCII hyphens (-). The test suite runs with `-W error`.
7. **NEVER add `__init__.py` to test directories** or a root-level `conftest.py`.
8. **NEVER remove the `_registry.py` standalone fallback** — it lets the skill work without `skills/_base.py` (for `bcb-sgs-v3/` standalone testing). When merged into the agent tree, the `try` branch succeeds and the fallback is never used.
9. **NEVER import `skills._base` inside mode files** — import from `skills.bcb.macro._registry` instead. The `_registry.py` handles the fallback transparently.

## ALWAYS DO

1. **ALWAYS use `name` for tab fields** — `{"name": "Resumo", "group": "...", "sections": [...]}`.
2. **ALWAYS put KPIs at the top level** — `result["kpis"] = [{"label": "...", "value": "..."}, ...]`.
3. **ALWAYS emit `chart_data`** on chart sections — a Chart.js config: `{"type": "line", "data": {"labels": [...], "datasets": [{"label": ..., "data": [...], "borderColor": ...}]}, "options": {...}}`.
4. **ALWAYS use list-of-lists for table `rows`** — `[["2024-01-02", "0.001234"], ...]`.
5. **ALWAYS show CDI as daily `% a.d.`** in the dashboard KPI (NOT annualized).
6. **ALWAYS show Selic as annualized `% a.a.`** in the dashboard KPI (daily × 252).
7. **ALWAYS include real data in chart/table sections** — no placeholder `labels`/`values` with empty arrays. Query the DB and populate `chart_data.data.datasets[0].data` with actual observation values.
8. **ALWAYS use descriptive PT-BR tab names** — Resumo, Juros, Inflacao, Cambio, Atividade (not "Tab 1", "Tab 2", etc.).
9. **ALWAYS run tests with `pytest tests/data_sources/bcb/ tests/skills/bcb/ -v -W error`** before committing.

## Dashboard Section Shapes (reference)

```python
# KPI (top-level only, NOT inside tabs)
{"label": "Selic (anualizada)", "value": "13.15%", "raw": 0.052531, "unit": "% a.a."}

# Chart section
{
    "type": "chart",
    "title": "Selic diaria - ultimos 30 dias",
    "description": "Variacao diaria...",
    "chart_data": {
        "type": "line",
        "data": {
            "labels": ["2024-01-02", "2024-01-03", ...],
            "datasets": [{"label": "Selic diaria", "data": [0.001234, ...],
                          "borderColor": "#0d9488", "fill": False, "tension": 0.3}]
        },
        "options": {"responsive": True, "maintainAspectRatio": False, ...}
    }
}

# Table section
{
    "type": "table",
    "title": "Selic diaria - tabela",
    "columns": ["Data", "Valor"],
    "rows": [["2024-01-02", "0.001234"], ["2024-01-03", "0.001235"], ...]
}

# Text section
{"type": "text", "title": "Visao geral", "body": "..."}
```

---

*Last updated: 2026-07-24 (v3.0).*
