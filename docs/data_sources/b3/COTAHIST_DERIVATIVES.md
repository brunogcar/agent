<- Back to [COTAHIST Overview](COTAHIST.md)

# 📜 COTAHIST_DERIVATIVES — B3 Options & Term Trade Data

B3 derivatives trade data extracted from the standard COTAHIST ZIP files.
Stored as a separate `cotahist_derivatives` table in the SAME `cotahist.db`
used by equities — populated during the standard COTAHIST sync pass (the
sync engine writes to both tables row-by-row in one ZIP parse).

**Key characteristics:**
- **Same source ZIP** — derived from the same annual COTAHIST ZIPs as
  equities. No separate download, no separate sync command.
- **BDI-filtered** — only derivatives BDI codes: 78 (calls), 82 (puts),
  83 (index calls), 84 (index puts), 26 (term/forward). The equities BDI
  filter {02, 12, 14, 96} writes to the `cotahist` table; this sub-domain
  reads the OTHER BDI codes into a separate table.
- **Derived columns** — `underlying`, `option_type`, `expiration_month`,
  `strike_parsed` are parsed from the option ticker during sync (not in
  the raw COTAHIST record). This makes per-underlying + per-strike queries
  fast (indexed) without runtime ticker parsing.
- **No rate limits / no auth** — bulk file download (inherits from COTAHIST).
- **Best for** — options chain queries, put/call ratio, volume-by-strike
  analytics, options dashboard.

---

## 🚀 Quick Start

```powershell
# Sync (same command as equities — populates BOTH tables in one pass)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# Query the PETR options chain (nearest maturity)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist_derivatives.query_engine import options_chain; r=options_chain(underlying='PETR'); print(r['status'], r.get('count'), r.get('maturity'))"

# List all available maturities for VALE
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist_derivatives.query_engine import available_maturities; print(available_maturities(underlying='VALE'))"

# Put/call ratio (90-day window)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist_derivatives.query_engine import put_call_ratio; r=put_call_ratio(underlying='PETR', days=90); print(r['count'], 'observations')"

# DB stats
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist_derivatives.status_reporter import stats; import json; print(json.dumps(stats(), indent=2, default=str))"
```

---

## 🔧 Sync

There is NO separate sync command for derivatives. The standard COTAHIST
sync populates BOTH tables in one pass:

```powershell
# Single year (writes to cotahist + cotahist_derivatives)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# Full history 2010-present (~5 min)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync_full_history; print(sync_full_history())"
```

See [COTAHIST.md](COTAHIST.md) for sync details. The derivatives path is
wired into `data_sources/b3/cotahist/sync_engine.py` (DELETE + INSERT into
`cotahist_derivatives` per year, ticker parsed during the same pass).

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| COTAHIST_DERIVATIVES table | `memory_db/b3/cotahist.db` → table `cotahist_derivatives` (shared with equities) |

| Source | URL |
|--------|-----|
| Annual ZIP (same as equities) | `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP` |

No env vars required. No auth. No rate limits.

**BDI codes stored (derivatives):**
| Code | Label |
|------|-------|
| 78 | CALL (stock options) |
| 82 | PUT (stock options) |
| 83 | CALL (index options) |
| 84 | PUT (index options) |
| 26 | TERM (forward contracts) |

**Underlying normalization:** every query function accepts both the 4-letter
code (`"PETR"`) and the full ticker (`"PETR4"`) — trailing digits are
stripped automatically. The `underlying` column in the DB stores the
4-letter code (e.g. `"PETR"`).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](cotahist_derivatives/ARCHITECTURE.md) | File map, DB schema, BDI codes, ticker parser, design decisions |
| [API.md](cotahist_derivatives/API.md) | 4 query functions: `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike` |
| [CHANGELOG.md](cotahist_derivatives/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](cotahist_derivatives/INSTRUCTIONS.md) | AI editing rules — what NOT to break, ALWAYS DO |

> **No sync_engine.py** — derivatives are populated by the standard
> COTAHIST sync (same ZIP parse writes to both tables). See
> [ARCHITECTURE.md](cotahist_derivatives/ARCHITECTURE.md).

---

*Last updated: 2026-08-18 (v1.0).*
