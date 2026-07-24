<- Back to [BRIDGE Overview](../BRIDGE.md)

# 🏗️ Architecture

## Purpose

The bridge resolves B3 trading tickers (PETR4, VALE3) to CVM company identity
(CNPJ, CD_CVM, official names) so that CVM financial queries can accept a
ticker as input.

## The Resolution Chain

### Primary Path (dividends API → CAD)

```
  ticker (PETR4)
    │
    ▼  b3/dividends per-ticker API  (data_sources.b3.dividends)
    │  dividends.company_info.code_cvm = "9512"
    ▼
  cd_cvm ("9512")
    │
    ▼  cvm/cad lookup  (data_sources.cvm.cad)
    │  cia_aberta WHERE CD_CVM='9512' → CNPJ, names, status, sector
    ▼
  bridge.db ticker_map: PETR4 → cd_cvm=9512, cnpj=33000167000101, ...
```

### Fallback Path (ISIN ZIP → CAD by CNPJ) — v1.2

When the primary path fails (dividends API down, or no codeCVM in response),
the bridge falls back to the B3 ISIN ZIP:

```
  ticker (PETR4)
    │
    ▼  dividends.db.cash_dividends (prior sync data)
    │  first row → isin_code = "BRPETRACNPR6"
    ▼
  ISIN ("BRPETRACNPR6")
    │
    ▼  B3 ISIN ZIP → isin_index.db (300k entries, cached 24h)
    │  isin_cnpj WHERE isin='BRPETRACNPR6' → cnpj = "33000167000101"
    ▼
  CNPJ ("33000167000101")
    │
    ▼  cvm/cad lookup by cnpj
    │  cia_aberta WHERE CNPJ='33000167000101' → cd_cvm=9512, names, status
    ▼
  bridge.db ticker_map: PETR4 → cd_cvm=9512, cnpj=33000167000101, ...
       (sync_log action = 'linked_isin')
```

### Auto-Sync-on-Demand (v1.2)

During a CVM query (e.g., DFP), the resolver auto-syncs if needed:

```
  resolve_company("PETR4")
    │
    ▼  _bridge.py: _resolve_via_bridge("PETR4") → (cnpj, cd_cvm)
    │  1a. Try cnpj → empresas WHERE cnpj=?  (preferred)
    │  1b. Fallback: cd_cvm → empresas WHERE cd_cvm=?  (if cnpj empty)
    │  1c. [v1.2] If both None (ticker not in bridge) + auto_sync=True:
    │      → _auto_sync_bridge("PETR4") → bridge.sync_engine.sync()
    │      → retries bridge lookup → found!
    ▼
  empresa_ids → contas → financial statements
```

## Why Not the Legacy 4-Source Approach?

The legacy `skills/b3/b3_cvm/` bridge joined 4 sources:

| # | Source | Problem |
|---|--------|---------|
| 1 | instruments.db (local) | Requires full sync (7138 pages, ~20min, often incomplete) |
| 2 | B3 ISIN ZIP (download) | Fragile — CDN checks Referer/Origin, 403 without browser headers |
| 3 | CVM CSV (download) | Redundant — CAD already has cd_cvm → CNPJ |
| 4 | dfp_itr.db (local) | Not needed — the resolver queries this live |

The new approach replaces sources 2+3 with the **dividends per-ticker API**
(returns `codeCVM` directly) + **CAD** (cd_cvm → CNPJ). No bulk downloads,
no ISIN ZIP, no instruments dependency.

## Design Decisions

### No mkt_cap

Market cap lives in instruments.db, which may not be fully synced. The bridge
is for **identity resolution**, not market data. Including mkt_cap would create
a dependency on a partially-synced source and produce stale/missing values.

### No instruments.db dependency

The bridge never reads instruments.db. Tickers are provided explicitly by the
caller. This means the bridge works even with zero instruments sync.

### Per-ticker, on-demand sync

The bridge syncs one ticker at a time (or a list). There is no "sync all"
because we don't have a complete ticker list without instruments.db. The
dividends API is per-ticker anyway.

### cd_cvm fallback in the resolver

If CAD doesn't have the cd_cvm (stale cad.db, very new listing), the bridge
stores the ticker with cd_cvm but empty cnpj. The resolver (`_bridge.py`)
falls back to `empresas.cd_cvm` (the DFP/ITR empresas table has a cd_cvm
column), so resolution still works without CNPJ.

### Reuses existing data sources

The bridge does NOT duplicate HTTP fetch or parsing logic:
- **Dividends sync**: delegates to `data_sources.b3.dividends.sync_engine.sync`
  (which checks its own `sync_state` cache and only fetches if needed)
- **CAD lookup**: delegates to `data_sources.cvm.cad.query_engine.lookup`

## Schema

### ticker_map (one row per ticker)

| Column | Source | Notes |
|--------|--------|-------|
| ticker (PK) | input | B3 trading symbol e.g. "PETR4" |
| issuing | derived | First 4 chars of ticker e.g. "PETR" |
| cd_cvm | dividends API | `company_info.code_cvm` e.g. "9512" |
| trading_name | dividends API | `company_info.trading_name` |
| cnpj | CAD | 14-digit, from `cia_aberta.CNPJ_CIA` |
| denom_social | CAD | Official legal name |
| denom_comerc | CAD | Commercial name |
| sit | CAD | ATIVO / CANCELADO / SUSPENSO |
| setor_ativ | CAD | Economic sector |
| tp_merc | CAD | BOVESPA / BALCAO |
| synced_at | bridge | ISO timestamp |

### sync_log (audit trail)

| Column | Notes |
|--------|-------|
| id (PK) | Autoincrement |
| synced_at | ISO timestamp |
| ticker | B3 ticker |
| action | `linked` / `linked_isin` / `no_cvm` / `no_cad` / `error` |
| cd_cvm | CVM code (if known) |
| cnpj | CNPJ (if resolved) |
| detail | Human-readable detail |

## File Layout

```
data_sources/cvm/bridge/
├── __init__.py       # Manifest + route (4 modes)
├── catalog.py        # SCHEMA_SQL (ticker_map + sync_log), connect(), ensure_schema()
├── sync_engine.py    # sync() — primary (dividends→CAD) + ISIN fallback + upsert
├── isin_fetcher.py   # B3 ISIN ZIP download + parse + cache (24h TTL) + lookup_isin()
└── query_engine.py   # lookup(), status(), resolve()
```

Consumed by:
- `data_sources/cvm/_bridge.py` — `resolve_company()` reads `ticker_map`
- All CVM sub-domains (dfp, itr, fre, ipe) use `resolve_company()` for ticker input

---

*Last updated: 2026-07-23 (v1.2 — ISIN fallback + auto-sync-on-demand).*
