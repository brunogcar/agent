<- Back to [SCREENER Overview](../SCREENER.md)

# 🗺️ Screener ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | S1 — Custom metric selection | Let the LLM specify which metrics to include (e.g. only P/L + ROE) |
| P2 | S2 — Metric toggle for top companies chart | Add a `chart_metric` param so the user can pick which metric drives the Peers chart (ROE, Div Yield, etc.) |
| P3 | S3 — Historical comparison | Compare a ticker's current P/L vs its own historical P/L range (needs COTAHIST + historical financials) |
| Done | v1.2 dashboard reorg | Top companies chart (P/L) added to Peers tab; detailed `[screener]` print output |
| Done | v2.0 _base.py extraction | _registry + __init__ delegate to shared `skills/_base.py` |
| Done | v1.4 modular split | Modes split into `modes/` + `report.py` + dashboard mode |
| Done | v1.2 calculations integration | v1.4 calculations metrics (roa, margem_liquida, divida_pl + 9 more) surfaced in peers |

---

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### S1 — Custom metric selection

**Priority:** P2

Let the LLM specify which metrics to include in the Peers + Comparison
tables via a `metrics` param (e.g. `metrics=["p_l", "roe", "dividend_yield"]`).
Currently both tables show a fixed column set (13 in Peers, 8 in
Comparison); a custom selection would let the LLM focus on the metrics it
cares about for a given question.

**Blocker:** None — the data is already fetched per peer; only the column
projection in `build_peers_section` / `build_comparison_section` needs to
accept a filter.

### S2 — Metric toggle for top companies chart

**Priority:** P2

Add a `chart_metric` parameter to the dashboard mode (default `p_l`) so
the user can choose which metric drives the top companies bar chart on
the Peers tab. Currently hardcoded to P/L; allowing ROE / Div Yield /
EV/EBITDA would let the LLM quickly find "best ROE in the sector" or
"highest yielders" visually.

`build_top_companies_chart` already supports any metric in
`_TOP_METRIC_DEFS` — only the dashboard mode needs the new param.

### S3 — Historical comparison

**Priority:** P3

Compare a ticker's current P/L (and other multiples) against its own
historical P/L range (5Y min / median / max). Currently screener compares
the ticker vs sector peers at the current date; a historical view would
show whether the ticker is cheap vs its own history. Needs COTAHIST
historical prices + historical financials (already covered by the
historical skill).

### S4 — Cross-sector peer discovery

**Priority:** P3

Allow the user to specify a peer list explicitly (e.g. `peers=["PETR4",
"VALE3", "SUZB3"]`) instead of deriving peers from the ticker's own
sector. Useful when comparing companies across sectors by business model
(e.g. "all dividend aristocrats regardless of sector").

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg). See [CHANGELOG.md](CHANGELOG.md) for version history.*
