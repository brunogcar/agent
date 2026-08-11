<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Valuation ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P3 | D3 — Cash flow metrics (remaining) | Saldo Inicial/Final (cash balance start/end of period from DFC 5.05). FCT + FCL done v1.11. |
| P3 | D6 — Report adapters | valuation_bpa/bpp/dre/dfc/dva/macro |
| P3 | Statement sub-tab | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs (mirror financials v1.12 Balanço pattern) |
| P3 | Peer Comparison tab | Side-by-side multiples vs sector peers (reuse comparison skill) |
| P3 | TypedDict for ratios | Define `ValuationRatios` TypedDict for mypy + autocomplete |
| P3 | Telemetry | Count null_rate per metric in summary() |

> **Note:** Completed items live in [CHANGELOG.md](CHANGELOG.md). This file
> lists only true backlog + in-progress items.

---

## 📋 Backlog

### D3 — Cash flow metrics (remaining)

**Status:** FCT + FCL done in v1.11. Saldo Inicial/Final remaining.

| Metric | Formula | Status | Notes |
|--------|---------|--------|-------|
| **FCT** (Total Cash Flow) | FCO + FCI + FCF (financing) | ✅ Done (v1.11) | `metrics/fct.py` |
| **FCL** (Free Cash Flow = FCO − CAPEX) | FCO − |CapEx| | ✅ Done (v1.11) | `metrics/fcl.py` |
| **Saldo Inicial / Saldo Final** | snapshot at t-1 / t | Not started | From DFC account 5.05 (Caixa Líquido). Needs a new engine. |

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

**Status:** Sub-tabs, price trend, growth trend, P/L-LPA history chart, ROE
trend chart, margin trend chart, Graham overlay (removed v1.10) are DONE.

Remaining:

| Enhancement | Tab | Notes |
|-------------|-----|-------|
| **Statement sub-tab** | New tab "Statements" | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs. Mirrors `financials.dashboard()` v1.12 Balanço tab. |
| **Comparison mode** | New tab "Peer Comparison" | Side-by-side multiples vs sector peers (reuses `comparison` skill). |

### D7 — Performance & quality (remaining)

**Status:** Mostly done. F7 engine cache (v1.9) + persistent DB cache (v1.10
fix) + per-(ticker,day) cache (engine cache DB) all done. Remaining:

| Item | Priority | Notes |
|------|----------|-------|
| **Type-hint the ratios dict** | P3 | Define `ValuationRatios` TypedDict for mypy + autocomplete. |
| **Telemetry** | P3 | Count null_rate per metric in summary(). |

---

## 🚫 Deferred / Out of Scope

- **Options data** (Call/Put counts, PM, ratio) — B3 `OpcaoInformativo` not synced. Would need a new data source.
- **Price volatility windows** — Can be computed from COTAHIST but no engine exists. Low priority.
- **Annual returns history** (YTD/1Y/3Y/5Y total return) — Needs COTAHIST + dividends composition. Low priority.
- **TIR (IRR) from CVM cash flow timing** — Not feasible. (Note: `irr_at` metric EXISTS — it computes IRR from DCF assumptions vs current price, not from CVM cash flow timing.)
- **Sector benchmarks** — ✅ Done via `screener` skill.
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.
- **Materialized ratios table** — F8 was implemented (v1.10) then removed (v1.10.3) because it only cached ~20 of 49 metrics + added overhead. F7 engine cache provides the real speedup. Will not revisit.

---

*Last updated: 2026-08-10 (v1.11). See [CHANGELOG.md](CHANGELOG.md) for version history.*
