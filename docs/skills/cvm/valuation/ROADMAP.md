<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Valuation ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | ROI metric | Return on Investment (NOPAT / Invested Capital at book). Reuses ebit, pl, debt, cash engines. |
| P2 | CAGR metric | Compound Annual Growth Rate over 3Y/5Y windows. Needs historical earnings + revenue + equity engines. |
| P2 | Margin trend chart | 5Y margins line chart (gross / operating / net / EBITDA) in Profitability tab. Needs historical DRE periods. |
| P3 | D3 — Cash flow metrics | FCT (Total Cash Flow = FCO+FCI+FCF), FCL (Free Cash Flow = FCO − CAPEX), Saldo Inicial/Final (cash balance start/end of period) |
| P3 | D6 — Report adapters | valuation_bpa/bpp/dre/dfc/dva/macro |
| P3 | Statement sub-tab | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs (mirror financials v1.12 Balanço pattern) |
| P3 | Peer Comparison tab | Side-by-side multiples vs sector peers (reuse comparison skill) |
| P3 | TypedDict for ratios | Define `ValuationRatios` TypedDict for mypy + autocomplete |
| P3 | Telemetry | Count null_rate per metric in summary() |

> **Note:** Completed items live in [CHANGELOG.md](CHANGELOG.md). This file
> lists only true backlog + in-progress items.

---

## 📋 Backlog

### ROI — Return on Investment metric

**Status:** Not started.

ROI = NOPAT / Invested Capital (at book value). Like ROIC but uses
invested-capital-at-book. Reuses `ebit`, `pl`, `debt`, `cash` engines.
Wire into `skills/cvm/calculations/metrics/roi.py` so it flows through
`compute_all_ratios()` automatically.

### CAGR — Compound Annual Growth Rate metric

**Status:** Not started.

CAGR = (V_end / V_start)^(1/n) − 1, per metric, over 3Y / 5Y windows.
Needs historical earnings + revenue + equity engines. Wire into
`skills/cvm/calculations/metrics/cagr.py`.

### Margin trend chart

**Status:** Not started.

5Y margins line chart (gross / operating / net / EBITDA) in the
Profitability > Margens subtab. Needs historical DRE periods. Mirrors
the P/L-LPA history chart pattern (v1.10) — use the calculations
registry's `*_history()` functions.

### D3 — Cash flow metrics

**Status:** Not started.

| Metric | Formula | Notes |
|--------|---------|-------|
| **FCT** (Total Cash Flow) | FCO + FCI + FCF (financing) | FCF (financing CF) engine exists at `calculations/engines/dfc/financing_cf.py` — not yet consumed by a metric. |
| **FCL** (Free Cash Flow = FCO − CAPEX) | FCO − capex | `capex` engine exists — not yet consumed by a metric. |
| **Saldo Inicial / Saldo Final** | snapshot at t-1 / t | From DFC account 5.05 (Caixa Líquido). |

### D6 — Report tool adapters

**Status:** Not started.

| Adapter | What it tables |
|---------|----------------|
| `valuation_bpa` | Latest BPA accounts (Ativo) + P/Ativos, P/Tangible Book derived |
| `valuation_bpp` | Latest BPP accounts (Passivo + PL) + P/Passivos, D/E, Gross D/E |
| `valuation_dre` | Latest DRE accounts + P/RB, P/EBIT, P/EBITDA, margins |
| `valuation_dfc` | Latest DFC accounts + P/FCO, P/FCF, FCT, FCL, Saldo Inicial/Final |
| `valuation_dva` | Latest DVA accounts + wealth distribution doughnut chart |
| `valuation_macro` | Macro indicators (Selic / CDI / IPCA / IGP-M / USD-BRL / EUR-BRL) snapshot |

### D5 — Dashboard enhancements (remaining)

**Status:** Partially done. Sub-tabs, price trend, growth trend, collapsibles,
Graham overlay (removed v1.10), ROE trend (rewritten v1.10) are DONE.

Remaining:

| Enhancement | Tab | Notes |
|-------------|-----|-------|
| **Margin trend chart** | Profitability > Margens | 5Y margins line chart. Needs historical DRE periods. |
| **Statement sub-tab** | New tab "Statements" | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs. Mirrors `financials.dashboard()` v1.12 Balanço tab. |
| **Comparison mode** | New tab "Peer Comparison" | Side-by-side multiples vs sector peers (reuses `comparison` skill). |

### D7 — Performance & quality (remaining)

**Status:** Mostly done. F7 engine cache (v1.9) + persistent DB cache (v1.10
fix) provide cross-run caching. Remaining:

| Item | Priority | Notes |
|------|----------|-------|
| ~~Per-call engine caching~~ | ~~P1~~ | ✅ Done (v1.9 F7) — `@engine_cached` + `engine_cache_scope`. |
| ~~Persistent cross-run cache~~ | ~~P1~~ | ✅ Done (engine_cache.db — fixed in v1.10 `import json` fix). Warm run ~90s vs cold ~8min. |
| ~~Cache ratios() per (ticker, day)~~ | ~~P2~~ | ✅ Done — engine cache DB covers this (fingerprints invalidate on new filings). |
| **Type-hint the ratios dict** | P3 | Define `ValuationRatios` TypedDict for mypy + autocomplete. |
| **Telemetry** | P3 | Count null_rate per metric in summary(). |

---

## 🚫 Deferred / Out of Scope

- **Options data** (Call/Put counts, PM, ratio) — B3 `OpcaoInformativo` not synced. Would need a new data source.
- **Price volatility windows** — Can be computed from COTAHIST but no engine exists. Low priority.
- **Annual returns history** (YTD/1Y/3Y/5Y total return) — Needs COTAHIST + dividends composition. Low priority.
- **TIR (IRR) from CVM data** — Not feasible. Requires cash flow timing. (Note: `irr_at` metric EXISTS — it computes IRR from DCF assumptions vs current price, not from CVM cash flow timing.)
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.
- **Materialized ratios table** — F8 was implemented (v1.10) then removed (v1.10.3) because it only cached ~20 of 49 metrics + added overhead. F7 engine cache provides the real speedup. Will not revisit.

---

*Last updated: 2026-08-10 (v1.10). See [CHANGELOG.md](CHANGELOG.md) for version history.*
