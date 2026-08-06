<- Back to [MACRO](../MACRO.md)

# 🏗️ Macro Architecture

## File Map

```text
skills/bcb/macro/
├── __init__.py            # MANIFEST + route (make_route with required_sources=["sgs"])
├── _registry.py           # MODES + register_mode (make_registry pattern, with standalone fallback)
├── helpers.py             # format_value, annualize_rate, compute_stats, build_observation_rows, accumulate_12m
├── report.py              # build_kpi_card, build_chart_section, build_table_section, build_text_section
└── modes/
    ├── __init__.py        # Empty marker
    ├── dashboard.py       # @register_mode("dashboard") 5-tab composition
    ├── rates.py           # @register_mode("rates") Selic/CDI/TR/Copom/Selic-acum
    ├── inflation.py       # @register_mode("inflation") IPCA/IGP-M with 12m acumulado
    └── fx.py              # @register_mode("fx") USD/BRL diaria + mensal
```

---

## Mode Dispatch Flow

```text
skill(domain="bcb", sub_domain="macro", mode="dashboard", params='{"days":30}')
  ↓
skills/bcb/__init__.py route(sub_domain="macro", mode="dashboard", ...)
  ↓
skills/bcb/macro/__init__.py route(mode="dashboard", ...)
  ↓ (make_route generates this)
sync guard: ensure_fresh(["sgs"])  ← P2 limitation: "sgs" not in sync_map, records error + proceeds
  ↓
_dispatch(mode="dashboard", kwargs={"days":30})
  ↓
MODES["dashboard"].fn(days=30)  ← dashboard.dashboard(days=30)
  ↓
composes rates() + inflation() + fx() + _build_resumo_kpis() + _build_atividade_sections()
  ↓
returns {"status":"ok", "tabs":[...], "kpis":[...]}
```

---

## Design Decisions

1. **Modular skill pattern** — `_registry.py` + `helpers.py` + `report.py` + `modes/` + `@register_mode`. Mirrors `skills/cvm/financials/` exactly. Adding a mode = drop a file in `modes/` + `@register_mode(...)`.
2. **Standalone fallback in `_registry.py`** — tries `from skills._base import ...` first (agent tree); falls back to an inline `ModeSpec` + `make_registry` + `make_route` + `auto_discover_modes` for standalone testing in `bcb-sgs-v3/`. The fallback omits the sync guard (the "sgs" source isn't wired into `sync_map` anyway — documented P2 limitation).
3. **Pure helpers** — `helpers.py` functions take already-fetched values (lists/dicts/floats) and return formatted strings or derived numbers. No I/O. Trivially testable.
4. **Pure-data report builders** — `report.py` functions take observations + return section dicts. No DB access. The dashboard template's expected shapes are encoded here.
5. **Chart.js config in `chart_data`** — chart sections emit a Chart.js config dict (`{type, data: {labels, datasets}, options}`) so `dashboard.html` can render via `new Chart(canvas, config)`.
6. **List-of-lists table rows** — table sections use `rows: [[date, value], ...]` (NOT list of dicts) so the template's `data_table` macro can iterate cells directly.
7. **Top-level KPIs** — KPIs are at the dashboard's top level (rendered in the universal header above tabs), NOT per-tab. The template reads `kpis` from the data dict root.

---

## Adding a New Mode

1. Create `skills/bcb/macro/modes/<mode>.py`:
   ```python
   from skills.bcb.macro._registry import register_mode
   from data_sources.bcb.sgs.query_engine import series as query_series

   @register_mode(
       "my_mode",
       description="...",
       params={"days": "int. Default: 30."},
       include_in_all=True,
       examples=['skill(domain="bcb", sub_domain="macro", mode="my_mode")'],
   )
   def my_mode(days: int = 30) -> dict:
       ...
       return {"status": "ok", "mode": "my_mode", "kpis": [...], "sections": [...]}
   ```
2. No edits to `__init__.py` or `_registry.py` needed — `auto_discover_modes` picks it up.

---

*Last updated: 2026-08-06 (v1.1).*
