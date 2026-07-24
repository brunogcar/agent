<- Back to [B3 Data Sources](../B3.md)

# 📡 BRAPI — brapi.dev API (quotes, OHLCV, tickers)

brapi.dev is a Brazilian-market REST API aggregator. Free tier covers PETR4, VALE3, ITUB4, MGLU3 without token. Full coverage with free signup.

**Key characteristics:**
- **Current quotes** — 15-min delay (vs B3 API's next-business-day). Returns price + market cap + P/E + EPS + volume.
- **Historical OHLCV** — daily bars (open, high, low, close, adjusted close, volume). Supports ranges from 1d to max.
- **Ticker list** — 1,796 tickers in 1 call (replaces 7,138-page InstrumentsConsolidated sync).
- **6 modes** — sync_tickers, sync_history, quote, history, tickers, status.

---

## 🚀 Quick Start

```powershell
# Sync the full ticker list (1 call, ~1,796 tickers)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.brapi.sync_engine import sync_tickers; print(sync_tickers())"

# Sync historical OHLCV for PETR4 (1 year of daily bars)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.brapi.sync_engine import sync_history; print(sync_history(ticker='PETR4', range='1y'))"

# Get current quote (tries local DB first, then live)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.brapi.query_engine import quote; print(quote(ticker='PETR4'))"
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| brapi DB | `memory_db/b3/brapi.db` |

| Source | URL |
|--------|-----|
| API | `https://brapi.dev/api` |

Optional: Set `BRAPI_TOKEN` env var for full ticker coverage (free signup at brapi.dev).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](brapi/ARCHITECTURE.md) | API flow, schema, design decisions *(TODO)* |
| [API.md](brapi/API.md) | 6 modes: sync_tickers, sync_history, quote, history, tickers, status *(TODO)* |
| [CHANGELOG.md](brapi/CHANGELOG.md) | Version history *(TODO)* |
| [INSTRUCTIONS.md](brapi/INSTRUCTIONS.md) | AI editing rules *(TODO)* |

---

*Last updated: 2026-07-24 (v1.0).*
