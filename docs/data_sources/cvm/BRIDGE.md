<- Back to [CVM Data Sources](CVM.md)

# 🌉 BRIDGE — B3-CVM Identity Bridge

The bridge resolves B3 trading tickers (PETR4, VALE3) to CVM company identity (CNPJ, CD_CVM, official names) so that CVM financial queries can accept a ticker as input.

**Key characteristics:**
- **2-source chain** — dividends API (ticker → codeCVM) + CAD (cd_cvm → CNPJ + names). No bulk downloads, no instruments.db dependency.
- **ISIN fallback** — when dividends returns no codeCVM, falls back to B3 ISIN ZIP (300k ISIN→CNPJ entries, 24h cache).
- **Auto-sync-on-demand** — the resolver (`_bridge.py`) auto-syncs the bridge when a ticker isn't in bridge.db. First query for any ticker populates it transparently.
- **No mkt_cap** — market cap lives in instruments.db (may be partial). The bridge is identity-only.
- **4 modes** — sync (per-ticker or list), status, lookup (ticker/cnpj/cd_cvm), resolve (fuzzy name).

---

## 🚀 Quick Start

```
# Bridge a ticker (fetches dividends + joins CAD)
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')

# Query DFP financials by ticker (bridge auto-syncs on first hit)
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')

# Check bridge status
data_source(domain="cvm", sub_domain="bridge", mode="status")
```

---

## ⚙️ Configuration

No bridge-specific env vars. Uses `MEMORY_ROOT` (shared with all CVM data sources).

| Storage | Path |
|---------|------|
| Bridge DB | `memory_db/cvm/bridge.db` |
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
