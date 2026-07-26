<- Back to [CVM Data Sources](CVM.md)

# 🌉 BRIDGE — B3-CVM Identity Bridge

The bridge resolves B3 trading tickers (PETR4, VALE3) to CVM company identity (CNPJ, CD_CVM, official names) so that CVM financial queries can accept a ticker as input.

**Key characteristics:**
- **[v1.3] FCA-first resolution** — FCA (fca.db) is the PRIMARY resolver: ticker → CNPJ in one local query (no network). Falls back to bridge.db, then B3 dividends API + CAD, then ISIN ZIP.
- **4-tier resolution chain** — FCA → bridge.db → B3 dividends API + CAD → ISIN ZIP. All tiers are fallbacks — if FCA has the ticker, no network is needed.
- **Auto-sync-on-demand** — the resolver (`_bridge.py`) auto-syncs the bridge when a ticker isn't in FCA or bridge.db. First query for any ticker populates it transparently.
- **Bulk populate from FCA** — sync all ~995 FCA tickers into bridge.db in seconds (no network). See [FCA](FCA.md) for the bulk script.
- **ISIN fallback** — when dividends returns no codeCVM AND FCA misses, falls back to B3 ISIN ZIP (300k ISIN→CNPJ entries, 24h cache).
- **No mkt_cap** — market cap lives in instruments.db (may be partial). The bridge is identity-only.
- **4 modes** — sync (per-ticker or list), status, lookup (ticker/cnpj/cd_cvm), resolve (fuzzy name).

---

## 🚀 Quick Start

```
# Sync a single ticker (FCA first, then B3 API fallback)
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')

# Bulk sync multiple tickers
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"tickers":["PETR4","VALE3","ITUB4"]}')

# Query DFP financials by ticker (bridge auto-resolves via FCA first)
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')

# Check bridge status
data_source(domain="cvm", sub_domain="bridge", mode="status")
```

---

## 🔀 Resolution Chain (v1.3)

```
ticker (PETR4)
  │
  ▼  1. FCA (fca.db) — LOCAL, no network (PRIMARY)
  │     fca_valor_mobiliario.Codigo_Negociacao → CNPJ
  │     fca_geral.CNPJ → CD_CVM, names, sector
  │     ✅ If found: done! <1ms
  │
  ▼  2. bridge.db (ticker_map) — LOCAL, cached from prior sync
  │     ticker_map WHERE ticker='PETR4' → cnpj, cd_cvm
  │     ✅ If found: done! <1ms
  │
  ▼  3. B3 dividends API (network) + CAD join
  │     dividends.company_info.code_cvm → CAD → CNPJ + names
  │     ✅ If found: upsert bridge.db, done!
  │
  ▼  4. ISIN fallback (dividends.db ISIN → ISIN ZIP → CNPJ → CAD)
  │     ✅ If found: upsert bridge.db, done!
  │
  ❌ All failed → store partial row (ticker only), return error
```

**Sync log actions:** `linked_fca` (via FCA), `linked` (via dividends+CAD), `linked_isin` (via ISIN fallback), `no_cad` (cd_cvm not in CAD), `no_cvm` (no codeCVM from dividends or ISIN), `error`.

---

## ⚙️ Configuration

No bridge-specific env vars. Uses `MEMORY_ROOT` (shared with all CVM data sources).

| Storage | Path |
|---------|------|
| Bridge DB | `memory_db/cvm/bridge.db` |
| FCA DB (primary resolver) | `memory_db/cvm/fca.db` |
| ISIN index cache | `memory_db/b3/isin_index.db` (24h TTL) |

---

## 🔧 Sync Commands

```powershell
# Sync bridge for a single ticker (fetches dividends + CAD lookup)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.sync_engine import sync; print(sync(ticker='PETR4'))"

# Sync multiple tickers at once
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.sync_engine import sync; print(sync(tickers=['PETR4','VALE3','ITUB4']))"

# Force re-sync (re-fetch dividends + re-join CAD)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.sync_engine import sync; print(sync(ticker='PETR4', force=True))"

# Sync ISIN index (B3 ISIN ZIP — 300k entries, 24h cache)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.isin_fetcher import sync; print(sync())"
```

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](bridge/ARCHITECTURE.md) | Resolution chain (primary + fallback), schema, design decisions |
| [API.md](bridge/API.md) | 4 modes: sync, status, lookup, resolve — full parameter reference |
| [CHANGELOG.md](bridge/CHANGELOG.md) | Version history (v1.0 → v1.2.1) |
| [INSTRUCTIONS.md](bridge/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.2.1).*
