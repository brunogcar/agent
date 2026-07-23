<- Back to [CVM Overview](../../CVM.md)

# 📋 Instructions

## Quick Start

### 1. Prerequisites

The bridge depends on two other data sources being synced:

```
# CAD (company register) — provides cd_cvm → CNPJ + names
data_source(domain="cvm", sub_domain="cad", mode="sync")

# Dividends — provides ticker → codeCVM (fetched on-demand by the bridge)
# No pre-sync needed; the bridge calls dividends sync automatically.
```

### 2. Bridge a ticker

```
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')
```

This will:
1. Check if PETR4 is already in bridge.db (skip if yes, unless `force:true`)
2. Ensure dividends data exists (fetch from B3 API if not already synced)
3. Read `codeCVM` from dividends.company_info
4. Look up CNPJ + names + status + sector in CAD by cd_cvm
5. Upsert the full identity record into bridge.db

### 3. Query CVM financials by ticker

After bridging, all CVM sub-domains accept the ticker directly:

```
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="itr", mode="query", params='{"company":"VALE3"}')
data_source(domain="cvm", sub_domain="fre", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="ipe", mode="search", params='{"company":"PETR4"}')
```

The resolver (`_bridge.py`) translates the ticker → CNPJ (or cd_cvm fallback)
→ empresa_ids automatically.

## Bridging Multiple Tickers

```
data_source(domain="cvm", sub_domain="bridge", mode="sync",
  params='{"tickers":["PETR4","VALE3","ITUB4","BBDC4","ABEV3"]}')
```

Already-bridged tickers are skipped (unless `force:true`). The dividends API
is called once per ticker (it's a per-ticker endpoint, not bulk).

## When to Re-sync

| Situation | Action |
|-----------|--------|
| New ticker never bridged | `sync(ticker="WEGE3")` |
| CAD was refreshed (new companies) | `sync(ticker="PETR4", force=true)` to re-join |
| Dividends data is stale | `sync(ticker="PETR4", force=true)` re-fetches from API |
| Everything looks fine | No action — re-syncing a bridged ticker returns `skipped` |

## Checking Bridge Health

```
data_source(domain="cvm", sub_domain="bridge", mode="status")
```

Key metrics:
- `total_tickers` — how many tickers are bridged
- `with_cnpj` — how many have a CAD-resolved CNPJ
- `cnpj_coverage_pct` — `with_cnpj / total_tickers * 100`
- `log.no_cad` — tickers whose cd_cvm wasn't found in CAD (stale CAD or unregistered)

If `cnpj_coverage_pct` is low, re-sync CAD then re-bridge with `force:true`.

## Looking Up a Company

```
# By ticker
data_source(domain="cvm", sub_domain="bridge", mode="lookup", params='{"ticker":"PETR4"}')

# By CNPJ
data_source(domain="cvm", sub_domain="bridge", mode="lookup", params='{"cnpj":"33000167000101"}')

# By CD_CVM
data_source(domain="cvm", sub_domain="bridge", mode="lookup", params='{"cd_cvm":"9512"}')

# Fuzzy name search
data_source(domain="cvm", sub_domain="bridge", mode="resolve", params='{"query":"petro"}')
```

## What's NOT in the Bridge

- **mkt_cap (market capitalization)** — lives in instruments.db, which may not
  be fully synced. Use `data_source(domain="b3", sub_domain="api", mode="lookup_ticker")`
  for market data.
- **ISIN** — not needed for CVM resolution. Available via instruments.db if synced.
- **Governance level, segment, specification code** — B3 instrument metadata,
  available via instruments.db. The bridge is identity-only.

## Troubleshooting

### "dividends sync succeeded but no codeCVM in response"

The B3 dividends API returned data but `codeCVM` was empty. This is rare —
retry with `force:true`. If it persists, the ticker may not have a CVM-registered
issuer.

### "cd_cvm not in cad.db (partial bridge entry)"

The dividends API returned a codeCVM, but CAD doesn't have that cd_cvm.
Causes: stale cad.db (re-sync CAD), or the company is very new (not yet in
the weekly CSV). The bridge stores the ticker + cd_cvm (no CNPJ). The resolver
will use the cd_cvm fallback to find the company in DFP/ITR.

### Ticker not found in CVM query after bridging

1. Check `data_source(domain="cvm", sub_domain="bridge", mode="lookup", params='{"ticker":"PETR4"}')` — does it return `status: "ok"`?
2. Check `data_source(domain="cvm", sub_domain="dfp", mode="status")` — is dfp.db synced?
3. The company may not have DFP/ITR filings (e.g., newly listed). Check CAD: `data_source(domain="cvm", sub_domain="cad", mode="lookup", params='{"cd_cvm":"9512"}')`.

---

*Last updated: 2026-07-23 (v1.0).*
