<- Back to [B3 Data Sources](../B3.md)

# 📜 COTAHIST — B3 Official Historical Trade Data

B3's official historical trade data. Annual ZIP files contain every daily quote (OHLCV) for every B3-listed security since 1986. We sync 2010-present (matching CVM DFP).

**Key characteristics:**
- **Official source** — B3's own historical data, not third-party
- **Dual-table storage** — equities (BDI 02/12/14/96) → `cotahist` table;
  derivatives (BDI 78/82/83/84/26 — options + term) → `cotahist_derivatives`
  table in the SAME `cotahist.db`. One sync pass writes to both. See
  [COTAHIST_DERIVATIVES.md](COTAHIST_DERIVATIVES.md).
- **BDI-filtered** — equities (02), FIIs (12), ETFs (14), fractional (96) for
  the `cotahist` table. Derivatives BDI codes {78, 82, 83, 84, 26} are written
  to the separate `cotahist_derivatives` table (no longer skipped).
- **Fixed-width format** — 245-byte records, 26 columns, latin1 encoding
- **Bulk download** — one ZIP per year (~10-89MB compressed)
- **No rate limits** — bulk file download, not paginated API
- **Best for** — backtesting, historical analysis, instrument metadata, charts,
  options analytics (via the derivatives table)

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

**BDI Filter:** The standard COTAHIST sync dispatches each row by BDI code:
- **Equities table** (`cotahist`): BDI codes 02 (equities), 12 (FIIs), 14 (ETFs),
  96 (fractional).
- **Derivatives table** (`cotahist_derivatives`): BDI codes 78 (calls), 82
  (puts), 83 (index calls), 84 (index puts), 26 (term). See
  [COTAHIST_DERIVATIVES.md](COTAHIST_DERIVATIVES.md).

Rows with BDI codes outside both sets (bonds, warrants, etc.) are still
skipped — they have no analytical use case yet.

**Query Default:** `market_type=10` (lote padrão). Filters out fractional market to avoid duplicate rows per ticker per day. Pass `market_type=0` to include all market types.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](cotahist/ARCHITECTURE.md) | Fixed-width layout, parsing, design decisions |
| [API.md](cotahist/API.md) | 3 modes: sync, query, status |
| [CHANGELOG.md](cotahist/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](cotahist/INSTRUCTIONS.md) | AI editing rules |

### Related: derivatives sub-domain

The `cotahist_derivatives` table (options + term) lives in the same
`cotahist.db` and is populated during the same sync pass. It has its own
query engine + docs:

| File | Purpose |
|------|---------|
| [COTAHIST_DERIVATIVES.md](COTAHIST_DERIVATIVES.md) | Landing page for the derivatives sub-domain |
| [cotahist_derivatives/ARCHITECTURE.md](cotahist_derivatives/ARCHITECTURE.md) | File map, DB schema, BDI codes, ticker parser |
| [cotahist_derivatives/API.md](cotahist_derivatives/API.md) | 4 query functions: `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike` |
| [cotahist_derivatives/CHANGELOG.md](cotahist_derivatives/CHANGELOG.md) | Version history |
| [cotahist_derivatives/INSTRUCTIONS.md](cotahist_derivatives/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-08-18 (v1.1 — added cotahist_derivatives table mention).*
