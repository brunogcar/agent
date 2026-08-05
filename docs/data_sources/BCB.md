# 🏦 BCB Data Sources

BCB = Banco Central do Brasil (Brazilian Central Bank). Public, free, no-auth macro-economic time series via the SGS API (Sistema Gerenciador de Series Temporais).

## Sub-Domains

| Sub-Domain | What | Landing Page |
|------------|------|--------------|
| **SGS** | 12 curated macro series: Selic, CDI, TR, IPCA, IGP-M, USD/BRL, PIB, Salario minimo. 4 categories (Juros / Inflacao / Cambio / Atividade). | [SGS.md](bcb/SGS.md) |

---

## 🚀 Quick Start

```python
# Sync all 12 series concurrently (Semaphore(5), ~12 HTTP calls)
data_source(domain="bcb", sub_domain="sgs", mode="sync_all")

# Query the latest Selic observation
data_source(domain="bcb", sub_domain="sgs", mode="last", params='{"code":11}')

# Query last 90 days of CDI
data_source(domain="bcb", sub_domain="sgs", mode="series", params='{"code":12,"days":90}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| SGS DB | `memory_db/bcb/sgs.db` |

| Source | URL |
|--------|-----|
| SGS API | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados` |

No env vars required — data sources use the existing `cfg.memory_root` from `core/config`.

---

## 🔧 Sync Commands

```bash
# Sync all 12 series (~10s, concurrent)
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_all; print(sync_all())"

# Sync one series (e.g. Selic 11)
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_series; print(sync_series(code=11))"

# Sync a date range
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_series_range; print(sync_series_range(code=11, start='2024-01-01', end='2024-12-31'))"
```

---

## 🏗️ Architecture

```text
data_sources/
└── bcb/                           # BCB domain
    ├── __init__.py                # Domain hub (auto-discovers sub-domains)
    └── sgs/                       # SGS sub-domain
        ├── __init__.py            # MANIFEST + route (8 modes)
        ├── catalog.py             # SERIES_CATALOG (12 series) + schema
        ├── fetcher.py             # HTTP fetcher (thread-safe, Semaphore(5))
        ├── sync_engine.py         # sync_series / sync_all / sync_series_range
        ├── query_engine.py        # series / last_value / range / search / summary
        └── status_reporter.py     # DB stats
```

---

## 📐 Design Decisions

1. **Public API, no auth** — BCB SGS is free and requires no token. The fetcher uses a plain `httpx.get` with no headers.
2. **Thread-safe fetcher** — `Semaphore(5)` caps concurrent HTTP requests; `_cache_lock` guards the in-memory cache dict. Mirrors the brapi v1.1 pattern.
3. **Strict date normalization** — BCB returns dates as `DD/MM/YYYY`. The fetcher normalizes to `YYYY-MM-DD` at the ingest boundary so nothing downstream ever sees a `DD/MM/YYYY` string.
4. **String-to-float parsing** — BCB returns `valor` as a string with Portuguese comma decimals (`"10,234567"`). The fetcher replaces comma with dot and `float()`-parses.
5. **Idempotent sync** — `INSERT OR REPLACE` on `(series_code, ref_date)` primary key. Re-syncing replaces existing rows rather than appending duplicates.
6. **v1 sync_state schema** — `sync_state (series_code, last_date, synced_at, row_count)` gives structured per-series metadata. The `DROP TABLE IF EXISTS sync_state` in `ensure_schema` migrates old v1/v2 DBs automatically.
7. **12 curated series** — Covers the 4 macro categories (Juros / Inflacao / Cambio / Atividade). Includes TR (226) which was dropped in v2.

---

*Last updated: 2026-07-24 (v3.0).*
