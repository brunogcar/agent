<- Back to [TERM](../TERM.md)

# Architecture

## Purpose
3-tab dashboard for B3 term contracts (a termo).

## Source Code Reference
```
skills/b3/term/
├── __init__.py        MANIFEST + route + REQUIRED_SOURCES=["cotahist"]
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
  ▼  ensure_fresh(["cotahist"])  ← route() wrapper, sync guard
  │
  ▼  dashboard mode (modes/dashboard.py)
  │  1. term_chain(ticker)         → data_sources.b3.cotahist.derivatives_query
  │  2. term_history(ticker, days) → data_sources.b3.cotahist.derivatives_query
  │  3. spot price (query_engine)  → data_sources.b3.cotahist.query_engine
  │  4. Build 3 tabs: Contratos Ativos / Spread Termo vs Spot / Volume Histórico
  │  5. Return {status, ticker, title, tabs}
```
