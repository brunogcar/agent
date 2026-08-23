# 🧩 BCB Skills

BCB skills are analytical views that combine BCB data sources (SGS) with domain reasoning to produce macro-economic dashboards. They are read-only — no sync.

## Sub-Domains

| Sub-Domain | What | Landing Page |
|------------|------|--------------|
| **macro** | 5-tab dashboard (Resumo / Juros / Inflacao / Cambio / Atividade) + 3 focused modes (rates, inflation, fx). Reads from `data_sources/bcb/sgs`. | [MACRO.md](bcb/MACRO.md) |

---

## 🚀 Quick Start

```python
# Full dashboard (5 tabs + top-level KPIs)
skill(domain="bcb", sub_domain="macro", mode="dashboard")

# Focused modes
skill(domain="bcb", sub_domain="macro", mode="rates")
skill(domain="bcb", sub_domain="macro", mode="inflation")
skill(domain="bcb", sub_domain="macro", mode="fx")
```

**Prerequisite:** Sync the SGS data source first:
```python
data_source(domain="bcb", sub_domain="sgs", mode="sync_all")
```

---

## 🏗️ Architecture

```text
skills/
└── bcb/                           # BCB skills domain
    ├── __init__.py                # Domain hub (auto-discovers sub-domains)
    └── macro/                     # Macro skill
        ├── __init__.py            # MANIFEST + route (make_route)
        ├── _registry.py           # MODES + register_mode (make_registry pattern)
        ├── helpers.py             # format_value, annualize_rate, compute_stats, accumulate_12m
        ├── report.py              # build_kpi_card, build_chart_section, build_table_section
        └── modes/
            ├── dashboard.py       # 5-tab composition
            ├── rates.py           # Selic / CDI / TR / Meta Copom / Selic acumulada
            ├── inflation.py       # IPCA / IGP-M (with 12m acumulado)
            └── fx.py              # USD/BRL ptax diaria + mensal
```

Skills follow the **modular skill pattern** from `skills/_base/` (same as CVM financials): `_registry.py` + `helpers.py` + `report.py` + `modes/` + `@register_mode`. (Phase 3 C2 split the old `skills/_base.py` into the `_base/` package — `make_registry` lives in `registry.py`, `make_route` in `route.py`, `ensure_fresh` in `sync_guard.py`; `from skills._base import X` still works via `__init__.py` re-exports.)

---

## 🔒 Force Sync (24h Window)

The macro skill declares `required_sources=["sgs"]`. The `route()` wrapper
(from `skills/_base/route.py`, the `make_route()` factory) calls `ensure_fresh(["sgs"])`
(defined in `skills/_base/sync_guard.py`) before each dispatch.

**BCB sources use a 24h freshness window** (unlike CVM sources which always
HEAD-check). If the last SGS sync is older than 24h (or missing), it triggers
`sync_all(force=True)` which re-fetches all stale series. If the last sync is
within 24h, it skips:

```
  [sync] sgs: fresh (2h ago)                          ← within 24h, skip
  [sync] sgs: stale (>24h) → force-sync              ← older than 24h, sync
  [sync] Force-syncing sgs (kwargs: {'force': True})...
  [sync] sgs done.
```

**Escape hatches:** `CVM_SKIP_SYNC=1` env var or `skip_sync=True` kwarg.

## 📄 Auto-HTML Generation

Every `route(mode="dashboard", ...)` call **auto-generates an HTML file** —
the result dict includes an `html_path` key. See [CVM.md](CVM.md) for details.

**Escape hatch:** `CVM_SKIP_HTML=1` env var (set automatically in tests).

---

*Last updated: 2026-09-15 (Phase 3 doc sweep — updated `skills/_base.py` references to the split `_base/` package modules). Prior: v5 — auto-HTML + force-sync visibility.*
