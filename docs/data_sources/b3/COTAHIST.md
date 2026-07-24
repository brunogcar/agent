<- Back to [B3 Data Sources](../B3.md)

# 📜 COTAHIST — B3 Official Historical Trade Data

B3's official historical trade data. Annual ZIP files contain every daily quote (OHLCV) for every B3-listed security since 1986. We sync 2010-present (matching CVM DFP).

**Key characteristics:**
- **Official source** — B3's own historical data, not third-party
- **BDI-filtered** — only equities (02), FIIs (12), ETFs (14), fractional (96). Reduces DB from ~5.7GB to ~1GB.
- **Fixed-width format** — 245-byte records, 26 columns, latin1 encoding
- **Bulk download** — one ZIP per year (~10-89MB compressed)
- **No rate limits** — bulk file download, not paginated API
- **Best for** — backtesting, historical analysis, instrument metadata, charts

**Stats after BDI filter (2010-2026):** 3.8M rows, 4,959 distinct tickers, 1.0GB DB.

---

## 🚀 Quick Start

```powershell
# Sync a single year (~5-30s)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# Sync multiple years
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(years=[2023,2024,2025]))"

# Sync full history (2010-present, ~5 min total)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync_full_history; print(sync_full_history())"

# Query PETR4 historical OHLCV
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.query_engine import query; r=query(ticker='PETR4', year=2025, limit=5); [print(row['refdate'], row['close']) for row in r.get('rows',[])]"
```

---

## 🔧 Sync Commands

```powershell
# Sync single year
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# Sync all years 2010-present
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync_full_history; print(sync_full_history())"

# Force re-sync (re-download + re-parse)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025, force=True))"
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

**BDI Filter:** Only BDI codes 02 (equities), 12 (FIIs), 14 (ETFs), 96 (fractional) are stored. Options, bonds, warrants, and other instrument types are skipped during sync to reduce DB size by ~85%.

**Query Default:** `market_type=10` (lote padrão). Filters out fractional market to avoid duplicate rows per ticker per day. Pass `market_type=0` to include all market types.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](cotahist/ARCHITECTURE.md) | Fixed-width layout, parsing, design decisions *(TODO)* |
| [API.md](cotahist/API.md) | 3 modes: sync, query, status *(TODO)* |
| [CHANGELOG.md](cotahist/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](cotahist/INSTRUCTIONS.md) | AI editing rules *(TODO)* |

---

*Last updated: 2026-07-24 (v1.0.1).*
