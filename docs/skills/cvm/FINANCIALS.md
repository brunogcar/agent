<- Back to [CVM Skills](../CVM.md)

# 📊 FINANCIALS — Financial Statements + Ratios Skill

The `financials` skill combines DFP (annual) + ITR (quarterly cumulative) + DVA to produce rapina-style financial summaries with standalone quarters + ratios.

**Key characteristics:**
- **Standalone quarter derivation** — ITR stores cumulative (Q1=3meses, Q2=6, Q3=9). This skill derives standalone: Q2 = cum6 − cum3, Q4 = DFP annual − cum9.
- **EBITDA computed** — EBIT (DRE 3.05) + D&A (DFC 6.01.01.02). D&A comes from the cash flow statement.
- **Ratios** — margins (bruta, EBITDA, EBIT, líquida), ROA/ROE (annualized for quarterly), debt ratios, payout.
- **Default: quarterly** — designed to analyze new financials as companies release them. Default 8 quarters.
- **8 modes** — quarterly (default), annual, complete, summary, dashboard, bpa, dva, dre.
- **[v1.9] BPA mode + DRE integration** — new `bpa` mode (full Balanço Patrimonial Ativo / Balance Sheet Assets, annual + quarterly via ITR); DRE codes `3.02` (COGS), `3.04` (operating expenses), `3.08` (income tax) added to `_extract_metrics` (were in SUMMARY_CODES but never extracted); BPA asset sub-codes `1.01.03` (Contas a Receber), `1.01.04` (Estoques), `1.02.03` (Imobilizado), `1.02.04` (Intangível) added to `SUMMARY_CODES` + `_extract_metrics` + `KEY_CODES_BY_GRUPO["BPA"]` (expanded from 6 to 16 codes covering both OLD and NEW CVM chart formats). New statement chart-of-accounts doc at [DFP ARCHITECTURE → BPA.md](dfp/architecture/BPA.md).
- **[v1.8] DRE mode** — new `dre` mode (full Demonstração do Resultado, annual + quarterly via ITR); DRE code `3.07` (Resultado Líquido das Operações Continuadas) added to `SUMMARY_CODES` + `KEY_CODES_BY_GRUPO` + `_extract_metrics`. New statement chart-of-accounts docs at [DFP ARCHITECTURE](dfp/ARCHITECTURE.md).
- **[v1.7] DVA integration** — new `dva` mode (full Value Added Statement, annual + quarterly via ITR); `complete` mode DVA section expanded from 3 proventos codes to full 15-code statement; 5 key DVA metrics (codes 7, 8.1-8.4) added to `annual`/`quarterly` SUMMARY_CODES.
- **Modular file structure (v1.6)** — split into `_registry.py` + `modes/` (5 files) + `fetchers.py` + `helpers.py` + `report.py` + `metrics.py`. `__init__.py` auto-discovers modes via importlib (same pattern as `tools/git_ops/actions/`). Public API unchanged. See [ARCHITECTURE.md](financials/ARCHITECTURE.md) for the file map.
- **Read-only** — no sync. Calls DFP/ITR query engines directly.
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
| [API.md](financials/API.md) | 8 modes: quarterly, annual, complete, summary, dashboard, bpa, dva, dre |
| [CHANGELOG.md](financials/CHANGELOG.md) | Version history + roadmap (xlsx export, charts, TTM ratios) |
| [INSTRUCTIONS.md](financials/INSTRUCTIONS.md) | AI editing rules — what NOT to break |
| [dfp/ARCHITECTURE.md](dfp/ARCHITECTURE.md) | [v1.9] DFP statement charts of accounts (BPA 1.xx, DRE 3.01-3.11, DVA 7.xx) — used by `bpa` + `dre` + `dva` modes |

---

*Last updated: 2026-07-30 (v1.9 — added `bpa` mode + DRE integration; see CHANGELOG.md).*
