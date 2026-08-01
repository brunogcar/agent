<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🗺️ Comparison ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | C1 — Metric toggle for peer comparison chart | Add a `chart_metric` param so the user can pick which metric drives the Valuation chart (ROE, EV/EBITDA, etc.) |
| P2 | C2 — Radar chart of normalized metrics | Multi-axis radar chart comparing tickers across normalized P/L, ROE, Div Yield, growth |
| P3 | C3 — Historical comparison | Compare tickers at a past date (e.g. "PETR4 vs VALE3 as of 2022-12-31") |
| Done | v1.2 dashboard reorg | Peer comparison chart (P/L) added to Valuation tab + new Ratio Grid tab; detailed `[comparison]` print output |
| Done | v2.0 _base.py extraction | _registry + __init__ delegate to shared `skills/_base.py` |
| Done | v1.5 modular split | Modes split into `modes/` + `report.py` + dashboard mode |
| Done | v1.3 calculations integration | 5 new metrics (ROE, ROA, Marg. Líq., Dívida/PL, Liquidez Corrente) surfaced in side_by_side |

---

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### C1 — Metric toggle for peer comparison chart

**Priority:** P2

Add a `chart_metric` parameter to the dashboard mode (default `p_l`) so
the user can choose which metric drives the peer comparison bar chart on
the Valuation tab. Currently hardcoded to P/L; allowing ROE / EV/EBITDA /
Div Yield would let the LLM visually compare tickers on different
dimensions without rerunning the whole dashboard.

`build_peer_comparison_chart` already supports any metric in
`_PEER_METRIC_DEFS` — only the dashboard mode needs the new param.

### C2 — Radar chart of normalized metrics

**Priority:** P2

A multi-axis radar chart showing each ticker's normalized score across
P/L (inverted), P/VPA (inverted), ROE, Div Yield, Marg. Líquida, and
Revenue Growth. Each axis is normalized 0-100 against the cohort's min/max
so tickers with very different scales (P/L ~5 vs ROE ~0.20) can be
plotted on the same chart. Useful for "overall quality at a glance".

**Blocker:** Needs a normalization helper + the report template must
support radar chart type (currently only line/bar/doughnut). The Chart.js
config is straightforward; the template work is the gating item.

### C3 — Historical comparison

**Priority:** P3

Compare tickers at a past date (e.g. "PETR4 vs VALE3 as of 2022-12-31").
Currently comparison uses the latest financials + today's prices; a
historical view would let the LLM answer "how did these two compare
before the 2023 rally". Needs COTAHIST historical prices + point-in-time
financials (the engines already support date params, but the dashboard
mode doesn't expose them).

### C4 — Valuation-only mode

**Priority:** P3

A `valuation_only` mode that skips financials/dividends (faster for quick
P/L screens across many tickers). Additive — won't change existing modes.
Useful when the LLM only needs valuation multiples (e.g. "find the
cheapest P/L among PETR4, VALE3, ITUB4") without waiting for full
financials + dividends fetches.

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg). See [CHANGELOG.md](CHANGELOG.md) for version history.*
