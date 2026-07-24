<- Back to [B3 Data Sources](../B3.md)

# 📡 API — B3 Market Data (Instruments, Trades, Derivatives)

B3 market data via the paginated JSON API. Contains instruments (tickers, ISIN, company names, segment), trades (daily prices, volume, VWAP), after-hours trades, and derivatives open positions.

**Key characteristics:**
- **Paginated JSON API** — B3 migrated from the old broken 3-step CSV download to a React SPA with `/tabelas/table/{name}/{date}/{page}`. 20 rows per page, JSON format, no auth.
- **4 tables** — instruments, trades, after_hours, derivatives. Each in its own `.db` file.
- **Dynamic schema** — columns are created from the API response (not hardcoded).
- **Concurrent sync** — `ThreadPoolExecutor(10 workers)` + batch commit (every 500 pages) + resume from last committed page.
- **5 modes** — sync, status, query, lookup_ticker, search_company.

---

## 🚀 Quick Start

```
# Sync instruments (7138 pages, ~20min for full sync)
data_source(domain="b3", sub_domain="api", mode="sync", params='{"table":"instruments"}')

# Look up a ticker
data_source(domain="b3", sub_domain="api", mode="lookup_ticker", params='{"ticker":"PETR4"}')

# Search by company name
data_source(domain="b3", sub_domain="api", mode="search_company", params='{"name":"PETROBRAS"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| Instruments DB | `memory_db/b3/instruments.db` |
| Trades DB | `memory_db/b3/trades.db` |
| After-hours DB | `memory_db/b3/after_hours.db` |
| Derivatives DB | `memory_db/b3/derivatives.db` |

| Source | URL |
|--------|-----|
| API | `https://arquivos.b3.com.br/tabelas/table/{tableName}/{date}/{page}` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](api/ARCHITECTURE.md) | API flow, 4-table registry, concurrent sync, design decisions |
| [API.md](api/API.md) | 5 modes: sync, status, query, lookup_ticker, search_company |
| [CHANGELOG.md](api/CHANGELOG.md) | Version history (v1.0 → v1.0.4) |
| [INSTRUCTIONS.md](api/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0.4).*
