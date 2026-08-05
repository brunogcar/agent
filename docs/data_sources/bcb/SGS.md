<- Back to [BCB Data Sources](../BCB.md)

# 📈 SGS — Sistema Gerenciador de Series Temporais

SGS is the Brazilian Central Bank's public time-series API. Free, no auth, no token. Returns daily / monthly / quarterly macro-economic observations as JSON (`[{"data":"DD/MM/YYYY","valor":"<string>"}, ...]`).

**Key characteristics:**
- **12 curated series** covering 4 categories: Juros (5), Inflacao (2), Cambio (2), Atividade (2).
- **8 modes** — sync_all, sync_series, sync_series_range, series, last, search, summary, status.
- **Thread-safe fetcher** — `Semaphore(5)` caps concurrent HTTP; 5-min Lock-guarded in-memory cache.
- **Idempotent sync** — `INSERT OR REPLACE` on `(series_code, ref_date)` PK.
- **v3 schema** — `sync_state (series_code, last_date, synced_at, row_count)` with `DROP TABLE` migration for old DBs.

---

## 📊 Series Catalog (12 series)

| Code | Name | Frequency | Unit | Category |
|------|------|-----------|------|----------|
| 11 | Selic diaria | daily | % a.d. | Juros |
| 12 | CDI diaria | daily | % a.d. | Juros |
| 226 | TR (Taxa Referencial) | daily | % | Juros |
| 432 | Meta Selic Copom | daily | % a.a. | Juros |
| 4389 | Selic acumulada mes base 252 | daily | % a.a. | Juros |
| 4390 | Selic acumulada mes | monthly | % | Juros |
| 433 | IPCA mensal | monthly | % | Inflacao |
| 189 | IGP-M mensal | monthly | % | Inflacao |
| 1 | USD/BRL ptax venda | daily | R$ | Cambio |
| 24369 | USD/BRL ptax mensal | monthly | R$ | Cambio |
| 4380 | PIB nominal trimestral | quarterly | R$ mil | Atividade |
| 1619 | Salario minimo mensal | monthly | R$ | Atividade |

---

## 🚀 Quick Start

```python
# Sync all 12 series concurrently
data_source(domain="bcb", sub_domain="sgs", mode="sync_all")

# Sync one series
data_source(domain="bcb", sub_domain="sgs", mode="sync_series", params='{"code":11}')

# Sync a date range
data_source(domain="bcb", sub_domain="sgs", mode="sync_series_range", params='{"code":11,"start":"2024-01-01","end":"2024-12-31"}')

# Query last 30 observations
data_source(domain="bcb", sub_domain="sgs", mode="series", params='{"code":11,"days":30}')

# Get the latest observation
data_source(domain="bcb", sub_domain="sgs", mode="last", params='{"code":11}')

# Search the catalog
data_source(domain="bcb", sub_domain="sgs", mode="search", params='{"query":"Selic"}')

# Catalog overview
data_source(domain="bcb", sub_domain="sgs", mode="summary")

# DB stats
data_source(domain="bcb", sub_domain="sgs", mode="status")
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| SGS DB | `memory_db/bcb/sgs.db` |

| Source | URL |
|--------|-----|
| JSON data | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados` |
| Last-N | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}` |

Query params: `formato=json`, `dataInicial=DD/MM/YYYY`, `dataFinal=DD/MM/YYYY`.

---

## 🔧 Sync Commands

```bash
# Sync all 12 series (~10s, concurrent via Semaphore(5))
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_all; print(sync_all())"

# Sync one series
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_series; print(sync_series(code=11))"

# Sync a date range
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_series_range; print(sync_series_range(code=11, start='2024-01-01', end='2024-12-31'))"
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](sgs/ARCHITECTURE.md) | File map, 3-table schema, design decisions, data flow |
| [API.md](sgs/API.md) | 8 modes documented with params + examples |
| [CHANGELOG.md](sgs/CHANGELOG.md) | Version history (v3.0) |
| [INSTRUCTIONS.md](sgs/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-24 (v3.0).*
