<- Back to [B3 Data Sources](../B3.md)

# 📊 INDEX — B3 Index Composition & Historical Values

B3 official indices (IBOV, SMLL, BDRX, IFIX, IDIV + 26 catalogued). Provides current composition (constituents + weights) and historical values (open/high/low/close/variation).

**Key characteristics:**
- **5 active indices** — IBOV (Ibovespa), SMLL (Small Cap), BDRX (BDRs), IFIX (FIIs), IDIV (Dividendos).
- **26 total catalogued** — full catalog includes ISE, IBOV_BR, IBRA, IBXL, IGC, IEE, IFNC, IMAT, IMOB, INDX, IVBX, SMLL, BDRX, IFIX, IDIV, etc. Only 5 are active by default (configurable via `ACTIVE_INDICES` in `catalog.py`).
- **Composition + history** — `constituents` table holds current weights; `history` table holds daily OHLCV bars per index.
- **Sync guard integration** — skills using index data declare `required_sources=["index"]` in `__init__.py`. The `route()` wrapper calls `ensure_fresh()` before dispatch.
- **8 modes** — sync_index, sync_all, index, search, summary, history, ticker, status.

---

## 🚀 Quick Start

```python
# Sync a single index (IBOV — most liquid)
data_source(domain="b3", sub_domain="index", mode="sync_index", params='{"index":"IBOV"}')

# Sync all 5 active indices
data_source(domain="b3", sub_domain="index", mode="sync_all")

# Query current IBOV composition
data_source(domain="b3", sub_domain="index", mode="index", params='{"index":"IBOV"}')

# Which indices does PETR4 belong to?
data_source(domain="b3", sub_domain="index", mode="ticker", params='{"ticker":"PETR4"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| INDEX DB | `memory_db/b3/index.db` |

| Source | URL |
|--------|-----|
| Composition JSON | `https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64}` |
| Historical values | `https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetStockIndex/{base64}` |

No env vars required. No auth. Active indices configurable in `catalog.py` (`ACTIVE_INDICES` + `CATALOG`).

---

## 🔧 Sync Commands

```powershell
# Sync IBOV composition + history
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.index.sync_engine import sync_index; print(sync_index(index='IBOV'))"

# Sync all 5 active indices (~30s)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.index.sync_engine import sync_all; print(sync_all())"

# Force re-sync (re-download + re-parse)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.index.sync_engine import sync_index; print(sync_index(index='IBOV', force=True))"
```

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](index/ARCHITECTURE.md) | File map, 3-table schema, design decisions |
| [API.md](index/API.md) | 8 modes: sync_index, sync_all, index, search, summary, history, ticker, status |
| [CHANGELOG.md](index/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](index/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-08-05 (v1.0).*
