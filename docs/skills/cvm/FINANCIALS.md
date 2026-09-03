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
- **Modular file structure (v1.6 + v2.0)** — split into `_registry.py` + `modes/` (10 files: quarterly, annual, complete, summary, dashboard, bpa, bpp, dre, dfc, dva + `_statement_sections.py` shared helper) + `fetchers.py` + `helpers.py` + `metrics.py` + `report/` PACKAGE (13 files since v2.0 — was monolithic `report.py`: 3,981 lines, 47 functions; `report/__init__.py` re-exports all 34 public builders + 18 private helpers for backward compat). `__init__.py` auto-discovers modes via importlib (same pattern as `tools/git_ops/actions/`). Public API unchanged. See [ARCHITECTURE.md](financials/ARCHITECTURE.md) for the file map.
- **Read-only** — no sync. Calls DFP/ITR query engines directly.
- **[v1.12] Dashboard reorg** — `dashboard` mode reorganized from 5 tabs to 7 tabs (Overview / Indicadores / Crescimento / Balanço / DRE / DFC / DVA) with sub-tabs (BPA + BPP under Balanço) and charts (growth bar, margin trend line, FCO/FCI/FCF stacked bar, DVA doughnut). Calls the 5 standalone statement modes for raw account data instead of duplicating SQL queries.
- **[v1.3] Calculations integration** — `summary` mode now delegates point-in-time ratios (ROIC, Graham, EV/EBITDA, P/FCF, P/EBIT, P/FCO) to `skills.cvm.calculations.metrics.*`. Statement rendering (quarterly/annual/complete) keeps its own per-period `compute_ratios()` because it operates on raw statement dicts, not point-in-time engine snapshots.
- **[v1.21] WACC + DuPont + Altman Z** — 3 new Overview sections (value-creation assessment, DuPont decomposition, Altman Z-Score zone classification). Wired via `list_metrics_by_category()` auto-discovery.
- **[v1.17] Statement single-fetch** — `_fetch_all_statements_annual()` in `fetchers.py` fetches all 5 statements (BPA/BPP/DRE/DFC/DVA) in ONE SQL query against DFP, partitioned in Python by `grupo`. ~80% SQL round-trip reduction per dashboard call.
- **[v1.22] Radar + Heatmap + Balanço stacked charts** — 6-axis radar chart (Rentabilidade/Crescimento/Liquidez/Alavancagem/Margem/Eficiência), 10-metric color-coded heatmap table, and 6 stacked-bar Balanço charts (absolute + percentage for Completo/BPA/BPP). Also fixed Selic 1400% bug (BCB SGS `parse_brl`).
- **[v1.23] Price overlay + multi-period tables + trend charts** — COTAHIST year-end price overlay (dual Y-axis) on Overview trend + DRE/DFC/DVA trend charts. Multi-column annual statement tables (4 years side-by-side). Tooltips on Overview/WACC/Altman Z tables.
- **[v1.24] Quarterly statement tables + period selector** — `_fetch_all_statements_quarterly()` (ITR+DFP for ALL KEY_CODES; BPA/BPP snapshot carry-forward, DRE/DFC/DVA standalone). `period_toggle` section type wraps annual + quarterly tables. Frontend `togglePeriod` JS swaps visibility. Period labels `"2T2026"`. Up to 20 quarterly periods.
- **[v1.25] ALL charts inside period_toggle** — DRE margins+abs+trend, DFC stacked+FCOvsLL+trend, Balanço 6 stacked-bar charts ALL inside `period_toggle` (both annual + quarterly versions pre-rendered). Point-in-time charts (DVA doughnut, generation, DFC quality, DVA sustainability) stay OUTSIDE. CAGR Receita/Resultado Bruto fix. Cache `import json` fix (happened TWICE — same bug as v1.10). TTM 20 periods (was 8).
- **[v2.3] Dashboard overhaul** — comprehensive Períodos/Séries Temporais tables (9 sub-tables: Balanço/DRE/DFC/Crescimento/CAGR/Margens/Liquidez/Disponibilidades/EBIT-EBITDA-CAPEX) via new `report/comprehensive.py`. Unified chart color scheme (Receita=orange, EBITDA=magenta, Lucro=purple, DFC=cyan/orange/rose). DRE/DFC line→bar revamp with `_fixedYWidth`+`_absMillions`. Overview tab split into 4 subtabs (Cotação & Resumo / Trajetória Anual / Análise de Risco / Visão Multidimensional). Trimestral YoY per-quarter subtabs (T1-T4). 3 new indicator bar charts per tab. Frozen Código+Descrição columns with sticky section headers. Quarterly Trend Δ% columns. Extended `KEY_CODES_BY_GRUPO` (Estoques, Fornecedores, Participação NC, Atribuído NC, Saldo). Annual fetch 6 → 10 periods.
- **[v2.4] Bugfixes + Quality of Earnings + real CapEx** — (1) Trajetória Anual chart revamped to bars + unified colors + GREEN price line on right Y-axis (was line + old teal/orange/blue). (2) Red Flags collapsible fix: `collapsible` macro now renders nested `sections` (body was empty since v2.0 — latent bug exposed by v2.3 subtab split). (3) Quarterly Trend delta direction fixed (was inverted + shifted by one row; now correct QoQ vs older period). (4) Real CapEx engine wired into comprehensive tables + indicator chart via new `capex_map` kwarg (was FCI proxy; engine does description-search: imobilizado/intangivel, scoped to DFC 6.02.%, TTM-derived). (5) F16 Quality of Earnings: new `build_quality_of_earnings_section` + chart in the Análise de Risco subtab — NI vs FCO over 5Y with accruals ratio red flag.

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
| [API.md](financials/API.md) | 11 modes: quarterly, annual, complete, summary, dashboard (11-tab with period toggle + price overlay + radar/heatmap), bpa, bpp, dre, dfc, dva, ttm, yoy_quarterly |
| [CHANGELOG.md](financials/CHANGELOG.md) | Version history (v2.0 — report/ package split; v1.17-v1.25 features) |
| [ROADMAP.md](financials/ROADMAP.md) | Backlog + priorities (F2 comparison tab, F5 cross-skill dashboard, F6 verification script; F3 + F4 DONE) |
| [INSTRUCTIONS.md](financials/INSTRUCTIONS.md) | AI editing rules — what NOT to break (v2.0 split-pattern lesson + v1.25 cache/ITR/CAGR/chart-toggle lessons) |

---

*Last updated: 2026-08-13 (v2.0 — report/ package split + v1.17 single-fetch + v1.22 radar/heatmap + v1.23 price overlay + v1.24 quarterly tables + period toggle + v1.25 ALL charts toggle + cache fix; see CHANGELOG.md).*
