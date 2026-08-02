<- Back to [CVM Skills](../CVM.md)

# 📊 FINANCIALS — Financial Statements + Ratios Skill

The `financials` skill combines DFP (annual) + ITR (quarterly cumulative) + DVA to produce rapina-style financial summaries with standalone quarters + ratios.

**Key characteristics:**
- **Standalone quarter derivation** — ITR stores cumulative (Q1=3meses, Q2=6, Q3=9). This skill derives standalone: Q2 = cum6 − cum3, Q4 = DFP annual − cum9.
- **EBITDA computed** — EBIT (DRE 3.05) + D&A (DFC 6.01.01.02). D&A comes from the cash flow statement.
- **Ratios** — margins (bruta, EBITDA, EBIT, líquida), ROA/ROE (annualized for quarterly), debt ratios, payout.
- **Default: quarterly** — designed to analyze new financials as companies release them. Default 8 quarters.
- **5 modes** — quarterly (default), annual, complete, summary, dashboard.
- **[v1.12] 10 modes** — quarterly (default), annual, complete, summary, dashboard (7-tab), bpa, bpp, dre, dfc, dva. The 5 new standalone statement modes (bpa/bpp/dre/dfc/dva) are thin wrappers over `complete(grupo=...)` that reshape the per-period accounts into a dict-keyed shape with `section` labels, used by the v1.12 dashboard's Balanço/DRE/DFC/DVA tabs and the generic `financials_statement` adapter.
- **Modular file structure (v1.6)** — split into `_registry.py` + `modes/` (10 files: quarterly, annual, complete, summary, dashboard, bpa, bpp, dre, dfc, dva + `_statement_sections.py` shared helper) + `fetchers.py` + `helpers.py` + `report.py` + `metrics.py`. `__init__.py` auto-discovers modes via importlib (same pattern as `tools/git_ops/actions/`). Public API unchanged. See [ARCHITECTURE.md](financials/ARCHITECTURE.md) for the file map.
- **Read-only** — no sync. Calls DFP/ITR query engines directly.
- **[v1.12] Dashboard reorg** — `dashboard` mode reorganized from 5 tabs to 7 tabs (Overview / Indicadores / Crescimento / Balanço / DRE / DFC / DVA) with sub-tabs (BPA + BPP under Balanço) and charts (growth bar, margin trend line, FCO/FCI/FCF stacked bar, DVA doughnut). Calls the 5 standalone statement modes for raw account data instead of duplicating SQL queries.
- **[v1.3] Calculations integration** — `summary` mode now delegates point-in-time ratios (ROIC, Graham, EV/EBITDA, P/FCF, P/EBIT, P/FCO) to `skills.cvm.calculations.metrics.*`. Statement rendering (quarterly/annual/complete) keeps its own per-period `compute_ratios()` because it operates on raw statement dicts, not point-in-time engine snapshots.

---

## 🚀 Quick Start

```
# Quarterly summary (default 8 quarters) — analyze new releases
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')

# Annual summary (default 5 years)
skill(domain="cvm", sub_domain="financials", mode="annual", params='{"company":"PETR4"}')

# Full DRE statements (key codes, annual)
skill(domain="cvm", sub_domain="financials", mode="complete", params='{"company":"PETR4","period":"annual","grupo":"DRE"}')

# Combined summary
skill(domain="cvm", sub_domain="financials", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Read-only over already-synced data sources:
- `data_sources/cvm/dfp` (dfp.db — annual)
- `data_sources/cvm/itr` (itr.db — quarterly cumulative)
- `data_sources/cvm/bridge` (bridge.db — auto-syncs on ticker query)

[v1.3] `summary` mode additionally consults (best-effort via `_safe_call`, returns None on missing DB):
- `data_sources/cvm/fre` (fre.db — shares outstanding, via calculations `shares` engine) — for Graham, P/EBIT, P/FCO, P/FCF, EV/EBITDA
- `b3/cotahist.db` (daily close, via calculations `price` engine) — for price-based ratios

---

## 📊 Rendering & Export

Pipe a `financials` result into the `report` tool to render a table or export
to Excel (adapters: `financials_quarterly`, `financials_annual`,
`financials_summary`):

```
report(action="table", title="PETR4 Financials",
       data=<financials JSON>, config={"adapter":"financials_quarterly"})
report(action="export", title="PETR4 Financials",
       data=<financials JSON>, config={"format":"xlsx","adapter":"financials_annual"})
```

See [CVM Skills — Report Integration](../CVM.md#-report-integration-v12) and
[report API](../../tools/report/API.md#adapters-skill-json--table-data).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](financials/ARCHITECTURE.md) | Standalone quarter derivation, EBITDA formula, mode → source mapping |
| [API.md](financials/API.md) | 11 modes: quarterly, annual, complete, summary, dashboard (11-tab), bpa, bpp, dre, dfc, dva, ttm, yoy_quarterly |
| [CHANGELOG.md](financials/CHANGELOG.md) | Version history (v1.16 — dashboard v3 bugfix sprint) |
| [ROADMAP.md](financials/ROADMAP.md) | Backlog + priorities (F1-F7: chart serialization, comparison tab, price overlay, period selector, cross-skill dashboard, verification script, company header) |
| [INSTRUCTIONS.md](financials/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-08-01 (v1.16 — dashboard v3 bugfix sprint: 3T2025 skip fix, sidebar groups, DVA pie taxonomy, Crescimento 3M/1Y/5Y, chart titles+descriptions, indicator tooltips, Crescimento subtab split, YoY by year, 4 new charts; see CHANGELOG.md).*
