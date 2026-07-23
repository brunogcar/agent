<- Back to [CVM Overview](../../CVM.md)

# 🌉 The B3-CVM Bridge — Overview

## What Is the Bridge?

The bridge connects **B3 tickers** (PETR4, VALE3) to **CVM company identity**
(CNPJ, CD_CVM, official names). This lets you query CVM financial statements
using a ticker instead of a CNPJ or company name.

Without the bridge, CVM queries accept only CNPJ or company name. With the
bridge, you can do:

```
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
```

## How It Works (2-Source Chain + Fallback)

```
                         ┌─────────────────────────────────────┐
                         │           PRIMARY PATH              │
                         │  (dividends API → CAD)              │
  ticker ───────────────►│                                     │
  (PETR4)                │  1. dividends API → codeCVM (9512)  │
                         │  2. CAD by cd_cvm → CNPJ + names    │
                         └──────────────┬──────────────────────┘
                                        │
                                   success?
                                   ├─ YES → bridge.db populated ✓
                                   │
                                   NO (dividends API down / no codeCVM)
                                   │
                         ┌──────────▼──────────────────────────┐
                         │         FALLBACK PATH               │
                         │  (ISIN ZIP → CAD by CNPJ)           │
                         │                                     │
                         │  1. dividends.db.cash_dividends     │
                         │     → ISIN (BRPETRACNPR6)           │
                         │  2. B3 ISIN ZIP → ISIN → CNPJ       │
                         │  3. CAD by cnpj → cd_cvm + names    │
                         └──────────────┬──────────────────────┘
                                        │
                                   bridge.db populated ✓
```

### Why Two Sources?

| Source | What it provides | When it's used |
|--------|-----------------|----------------|
| **b3/dividends API** | ticker → codeCVM (direct) | Primary — always tried first |
| **B3 ISIN ZIP** | ISIN → CNPJ (300k entries) | Fallback — when dividends has no codeCVM |

The dividends API is the simplest path (one HTTP call returns codeCVM directly).
The ISIN ZIP is a robust fallback that covers all 300k B3 instruments. It needs
an ISIN to start from, which comes from prior dividends sync (cash_dividends
table stores isin_code per ticker).

## Auto-Sync-on-Demand (v1.2)

The resolver (`_bridge.py`) automatically syncs the bridge when a ticker isn't
in bridge.db. This means you **never need to pre-sync the bridge** — the first
query for any ticker populates it transparently:

```
User: data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"WEGE3"}')

  1. DFP query_engine calls resolve_company("WEGE3")
  2. resolve_company checks bridge.db → WEGE3 not found
  3. resolve_company auto-syncs: bridge.sync("WEGE3")
     → fetches dividends for WEGE3 (codeCVM=5410)
     → CAD lookup by cd_cvm → CNPJ=33042556000104
     → upserts bridge.db
  4. resolve_company retries bridge lookup → found!
  5. DFP query proceeds with empresa_ids
```

Subsequent queries for WEGE3 are instant (bridge.db cache hit).

**Disable auto-sync**: `resolve_company(conn, "WEGE3", auto_sync=False)` — for
batch operations or tests where you don't want network calls.

## Data Flow Summary

| Step | Source | Data | Storage |
|------|--------|------|---------|
| 1 | b3/dividends API | ticker → codeCVM + ISIN + trading_name | `memory_db/b3/dividends.db` |
| 2a (primary) | cvm/cad | cd_cvm → CNPJ + names + status + sector | `memory_db/cvm/cad.db` |
| 2b (fallback) | B3 ISIN ZIP | ISIN → CNPJ (300k entries, cached 24h) | `memory_db/b3/isin_index.db` |
| 3 | bridge | ticker → cd_cvm + cnpj + names (joined) | `memory_db/cvm/bridge.db` |

## What's NOT in the Bridge

- **mkt_cap (market cap)** — lives in instruments.db, which may not be fully
  synced. Use `data_source(domain="b3", sub_domain="api", mode="lookup_ticker")`
  for market data.
- **ISIN** — not stored in bridge.db (it's an intermediate, not identity).
- **Governance level, segment** — B3 instrument metadata, not identity.

## Comparison with Legacy `skills/b3/b3_cvm/`

| Aspect | Legacy (4-source) | New (2-source + fallback) |
|--------|-------------------|--------------------------|
| Sources | instruments.db + ISIN ZIP + CVM CSV + dfp_itr.db | dividends API + CAD (+ ISIN ZIP fallback) |
| Bulk downloads | ISIN ZIP (6.9MB) + CVM CSV (1.5MB) | ISIN ZIP only (on fallback, cached 24h) |
| instruments dependency | Required (full sync needed) | None |
| mkt_cap | Yes (from instruments, often stale) | No (identity-only) |
| Per-ticker sync | No (bulk only) | Yes (on-demand or explicit) |
| Auto-sync | No | Yes (resolver auto-syncs on miss) |
| Fallback | None | ISIN ZIP (300k ISIN→CNPJ entries) |

## File Layout

```
data_sources/cvm/bridge/
├── __init__.py        # Manifest + route (4 modes: sync/status/lookup/resolve)
├── catalog.py         # SCHEMA_SQL (ticker_map + sync_log), connect(), ensure_schema()
├── sync_engine.py     # sync() — primary path + ISIN fallback + CAD join
├── isin_fetcher.py    # B3 ISIN ZIP download + parse + cache (24h TTL)
└── query_engine.py    # lookup(), status(), resolve()

data_sources/cvm/
└── _bridge.py         # resolve_company() — auto-sync-on-demand + cd_cvm fallback
```

## Quick Start

```
# 1. Sync CAD (one-time, weekly)
data_source(domain="cvm", sub_domain="cad", mode="sync")

# 2. Query financials for PETR4 (bridge auto-syncs on first hit)
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')

# Or explicitly sync the bridge first:
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')

# 3. Check bridge status
data_source(domain="cvm", sub_domain="bridge", mode="status")
```

---

*Last updated: 2026-07-23 (v1.2 — ISIN fallback + auto-sync-on-demand).*
