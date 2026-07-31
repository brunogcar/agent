# 🗺️ Roadmap — Financials Skill

Inspired by the private financial analysis spreadsheet. Items are
prioritized by impact + effort.

---

## P0 — Standalone statement modes

Create standalone modes for each CVM financial statement (matching the DVA
standalone mode pattern). Each would return the full statement for N periods
(annual + quarterly), structured by account code.

| Mode | Statement | CVM grupo | Codes | Status |
|------|-----------|-----------|-------|--------|
| `dva` | Demonstração do Valor Adicionado | DVA | 1-7, 8.1-8.4 | ✅ Done (v1.7) |
| `bpa` | Balanço Patrimonial Ativo | BPA | 1, 1.01, 1.02, ... | TODO |
| `bpp` | Balanço Patrimonial Passivo | BPP | 2, 2.01, 2.02, 2.03, ... | TODO |
| `dre` | Demonstração do Resultado | DRE | 3.01-3.11 | TODO |
| `dfc` | Demonstração do Fluxo de Caixa | DFC_MI/DFC_MD | 6.01-6.03 | TODO |

Each standalone mode would:
- Accept `company`, `periods`, `consolidado`, `quarterly` params (same as DVA)
- Query DFP (annual) + ITR (quarterly cumulative)
- Return `{status, company, period_type, periods: [{data_fim_exerc, meses, accounts}]}`
- Support `quarterly=1` for ITR-backed quarterly data

---

## P1 — Additional cash flow metrics

The spreadsheet surfaces these DFC values we don't currently include:

| Metric | Description | Engine status |
|--------|-------------|---------------|
| FCT | Total Cash Flow (FCO + FCI + FCF) | ❌ Not computed — easy to add as sum |
| FCL | Free Cash Flow (FCO - CAPEX) | ⚠️ We have `fcf` engine but it's financing CF, not free CF |
| Saldo Inicial | Cash balance at start of period | ❌ Need new engine (BPA code 1.01.01 prior period) |
| Saldo Final | Cash balance at end of period | ❌ Same engine, current period |
| CAPEX | Capital expenditure | ✅ Engine exists (`capex_at`) but not surfaced in financials modes |

---

## P1 — Additional calculations metrics

Inspired by the spreadsheet's "Indicadores fundamentalistas" section:

| Metric | Description | Status |
|--------|-------------|--------|
| ROI | Return on Investment (different from ROA) | ❌ Need to define formula — sheet shows ROI=0.93 vs ROA=8.63% |
| COE | Cost of Equity (CAPM) | ❌ Need Beta + risk-free rate + market premium |
| CAGR | Compound Annual Growth Rate (5-period) | ❌ We have simple growth (3M/1Y/5Y) but not CAGR |
| Earnings Yield | 1 / P/L | ❌ Easy to add — inverse of P/L |
| Margins over time | 3M/1Y/5Y averages for Bruta, Líquida | ❌ We have point-in-time margins but not time-averaged |

---

## P2 — Dashboard reorganization (Tier 4)

Restructure the financials + valuation dashboards to match the spreadsheet's
category structure:

### Financials dashboard tabs (proposed):
1. **Overview** — market data + key KPIs (price, Market Cap, EV, Free Float)
2. **Indicadores** — ALL ratios in one big table, organized by type (valuation,
   profitability, leverage, liquidity, efficiency) — like the spreadsheet's
   "Indicadores fundamentalistas" section
3. **Crescimento** — 3M/1Y/5Y growth + CAGR table
4. **Balanço** — balance sheet snapshot (BPA + BPP key accounts)
5. **DRE** — TTM + 3M side by side (like the spreadsheet's "Dados DRE")
6. **DFC** — TTM + 3M + CAPEX + Saldo Inicial/Final
7. **DVA** — value added statement (generation + distribution)

### Valuation dashboard tabs (proposed):
1. **Overview** — price + Market Cap + EV + Beta + key KPIs
2. **Multiples** — P/L, P/VPA, P/EBIT, P/EBITDA, EV/EBIT, EV/EBITDA, PSR,
   P/Ativos, P/Passivos, P/Result Bruto, P/Cap.Giro, P/Dív.Bruta
3. **Per-share** — LPA, VPA, DPA, RPA, RBPA, CGPA, DBPA, APA, PPA
4. **Profitability** — ROE, ROA, ROIC, ROI, margins
5. **Liquidity & Leverage** — Liquidez Corrente, A/P, A/PL, Div Br/Patrim,
   Alavancagem, DL/EBIT, DL/EBITDA
6. **Efficiency & Growth** — Giro Ativos, Crescimento 3M/1Y/5Y, CAGR

---

## P3 — New data sources / skills

The spreadsheet includes data we don't have in any skill:

| Data | Source | Skill | Status |
|------|--------|-------|--------|
| IBOV participation + rank | B3 index data | New `b3_index` skill | ❌ TODO |
| Small cap participation | B3 index data | New `b3_index` skill | ❌ TODO |
| Beta (5-year) | B3 COTAHIST | `valuation` or new `b3_market` skill | ❌ TODO |
| Options (Call/Put counts, PM, ratio) | B3 derivatives | New `b3_options` skill | ❌ TODO |
| Price volatility (Daily/Weekly/Monthly min/max/avg) | B3 COTAHIST | New `b3_volatility` skill | ❌ TODO |
| Annual returns history (per-year) | B3 COTAHIST | New `b3_returns` skill | ❌ TODO |
| Macro indicators (Selic, CDI, IPCA, IGP-M) | BCB SGS API | New `bcb_macro` skill | ❌ TODO |
| Dollar/Euro rates | BCB SGS API | `bcb_macro` skill | ❌ TODO |

---

## P3 — Report adapter for DVA

Create a `financials_dva` report adapter that renders the DVA statement as a
2-section table (generation + distribution) with % of total columns, matching
the spreadsheet's layout.

---

*Last updated: 2026-07-30 (v1.7 — created after DVA mode + spreadsheet analysis).*
