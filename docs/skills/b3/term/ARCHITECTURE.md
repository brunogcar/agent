<- Back to [TERM](../TERM.md)

# Architecture

## Purpose
3-tab dashboard for B3 term contracts (a termo).

## Source Code Reference
```
skills/b3/term/
├── __init__.py        MANIFEST + route + REQUIRED_SOURCES=["cotahist",
│                                                       "b3-api-derivatives",
│                                                       "b3-api-instruments"]
├── _registry.py       ModeSpec + register_mode + MODES dict
├── modes/
│   ├── __init__.py    empty marker
│   └── dashboard.py   @register_mode("dashboard") — 3-tab dashboard
├── report.py          section builders (chart, table, text, error)
└── helpers.py         format_value, format_brl, format_int
```

## Data Flow
```
skill(domain="b3", sub_domain="term", mode="dashboard", params='{"ticker":"PETR4"}')
  │
  ▼  ensure_fresh(["cotahist", "b3-api-derivatives", "b3-api-instruments"])
  │  ← route() wrapper, sync guard
  │
  ▼  dashboard mode (modes/dashboard.py)
  │  1. term_chain(ticker)         → data_sources.b3.cotahist.derivatives_query
  │  2. term_history(ticker, days) → data_sources.b3.cotahist.derivatives_query
  │  3. spot price (query_engine)  → data_sources.b3.cotahist.query_engine
  │  4. [v6] If COTAHIST has no term data (stock ticker):
  │     forward_positions(ticker)  → data_sources.b3.api.query_engine
  │       - Constructs forward ticker: {TICKER}T (PETR4 → PETR4T)
  │       - Queries derivatives.db WHERE SgmtNm = 'EQUITY FORWARD'
  │       - Joins instruments.db for company name, ISIN, security category
  │       - Computes forward_price_per_share = FwdPric / CurQty
  │     Show forward snapshot KPI + spot price + spread (3 tabs)
  │  5. Build 3 tabs: Contratos Ativos / Spread Termo vs Spot / Volume Histórico
  │  6. Return {status, ticker, title, tabs}
```

## Data Sources

| Source | DB | Table | Used for |
|--------|----|----|----------|
| `cotahist` | `cotahist.db` | `cotahist_derivatives` | Index term (IBOV, BDI 74) — chain + history + volume |
| `cotahist` | `cotahist.db` | `cotahist_equities` | Spot price (last 5 closes + 90-day chart) |
| `b3-api-derivatives` | `derivatives.db` | `derivatives` | EQUITY FORWARD snapshot (stock term fallback) |
| `b3-api-instruments` | `instruments.db` | `instruments` | Company name, ISIN, security category, specification (forward join) |
