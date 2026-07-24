<- Back to [B3 Data Sources](../B3.md)

# 📜 COTAHIST — B3 Official Historical Trade Data

B3's official historical trade data. Annual ZIP files contain every daily quote (OHLCV) for every B3-listed security (stocks, bonds, funds, options, FIIs) since 1986. We sync 2010-present (matching CVM DFP).

**Key characteristics:**
- **Official source** — B3's own historical data, not third-party
- **Full coverage** — every traded security (equities, bonds, funds, options, FIIs)
- **Fixed-width format** — 245-byte records, 26 columns, latin1 encoding
- **Bulk download** — one ZIP per year (~87MB compressed → ~765MB TXT)
- **No rate limits** — bulk file download, not paginated API
- **Best for** — backtesting, historical analysis, instrument metadata, charts

---

## 🚀 Quick Start

```powershell
# Sync a single year (~2-5 min download + parse)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# Sync multiple years
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(years=[2023,2024,2025]))"

# Sync full history (2010-present, ~30-60 min total)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync_full_history; print(sync_full_history())"

# Query PETR4 historical OHLCV
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.query_engine import query; r=query(ticker='PETR4', year=2025, limit=5); [print(row['refdate'], row['close']) for row in r.get('rows',[])]"
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| COTAHIST DB | `memory_db/b3/cotahist.db` |

| Source | URL |
|--------|-----|
| Annual ZIP | `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP` |

No env vars required. No auth. No rate limits.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](cotahist/ARCHITECTURE.md) | Fixed-width layout, parsing, design decisions *(TODO)* |
| [API.md](cotahist/API.md) | 3 modes: sync, query, status *(TODO)* |
| [CHANGELOG.md](cotahist/CHANGELOG.md) | Version history *(TODO)* |
| [INSTRUCTIONS.md](cotahist/INSTRUCTIONS.md) | AI editing rules *(TODO)* |

---

*Last updated: 2026-07-24 (v1.0).*
