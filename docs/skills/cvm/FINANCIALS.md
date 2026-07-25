<- Back to [CVM Skills](../CVM.md)

# 📊 FINANCIALS — Financial Statements + Ratios Skill

The `financials` skill combines DFP (annual) + ITR (quarterly cumulative) + DVA to produce rapina-style financial summaries with standalone quarters + ratios.

**Key characteristics:**
- **Standalone quarter derivation** — ITR stores cumulative (Q1=3meses, Q2=6, Q3=9). This skill derives standalone: Q2 = cum6 − cum3, Q4 = DFP annual − cum9.
- **EBITDA computed** — EBIT (DRE 3.05) + D&A (DFC 6.01.01.02). D&A comes from the cash flow statement.
- **Ratios** — margins (bruta, EBITDA, EBIT, líquida), ROA/ROE (annualized for quarterly), debt ratios, payout.
- **Default: quarterly** — designed to analyze new financials as companies release them. Default 8 quarters.
- **4 modes** — quarterly (default), annual, complete, summary.
- **Read-only** — no sync. Calls DFP/ITR query engines directly.

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
| [API.md](financials/API.md) | 4 modes: quarterly, annual, complete, summary |
| [CHANGELOG.md](financials/CHANGELOG.md) | Version history + roadmap (xlsx export, charts, TTM ratios) |
| [INSTRUCTIONS.md](financials/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-25 (v1.0.1 + report wiring).*
