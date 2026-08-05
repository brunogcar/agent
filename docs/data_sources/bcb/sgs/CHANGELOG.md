<- Back to [SGS](../SGS.md)

# 📋 SGS Changelog

## v3.0 — 2026-07-24

**Fixes ALL issues from v1 + v2.**

### Required Summary

- **12 series** in SERIES_CATALOG (was 11 in v2 — TR 226 dropped in v2 is added back).
- **v1 sync_state schema** restored: `(series_code, last_date, synced_at, row_count)` instead of v2's `(key, value, synced_at)`.
- **DROP TABLE IF EXISTS sync_state** before CREATE in `ensure_schema` — migrates old v1/v2 DBs automatically (CREATE TABLE IF NOT EXISTS alone doesn't update existing tables).
- **`ref_date` field name** used consistently in all query_engine return payloads (v2 was inconsistent).
- **conftest.py** added in `tests/data_sources/bcb/sgs/` with a real temp SQLite DB fixture (not a mock).
- **helpers.py** syntax fixed: `monthly_values[max(0, i - 11): i + 1]` (v1 had `monthly_valuesax(0, i - 11): i + 1]`).

### Series Catalog (12 series)

| Code | Name | Category |
|------|------|----------|
| 11 | Selic diaria | Juros |
| 12 | CDI diaria | Juros |
| **226** | **TR (Taxa Referencial)** | **Juros (added back in v3)** |
| 432 | Meta Selic Copom | Juros |
| 4389 | Selic acumulada mes base 252 | Juros |
| 4390 | Selic acumulada mes | Juros |
| 433 | IPCA mensal | Inflacao |
| 189 | IGP-M mensal | Inflacao |
| 1 | USD/BRL ptax venda | Cambio |
| 24369 | USD/BRL ptax mensal | Cambio |
| 4380 | PIB nominal trimestral | Atividade |
| 1619 | Salario minimo mensal | Atividade |

### Architecture Choices (7)

1. Public API, no auth — plain `httpx.get`, no headers.
2. Thread-safe fetcher — `Semaphore(5)` + `_cache_lock` (mirrors brapi v1.1).
3. Strict date normalization — `DD/MM/YYYY` → `YYYY-MM-DD` at ingest boundary.
4. String-to-float parsing — Portuguese comma decimals → float.
5. Idempotent sync — `INSERT OR REPLACE` on `(series_code, ref_date)` PK.
6. v1 sync_state schema with DROP TABLE migration.
7. 12 curated series (TR 226 restored).

### Modes (8)

sync_all, sync_series, sync_series_range, series, last, search, summary, status.

(v2 had 9 modes — the redundant `range` mode was removed; `series` already accepts `start`/`end` for windowed queries.)

### Dashboard (5 tabs)

Resumo, Juros, Inflacao, Cambio, Atividade — with proper `name` field (v2 used `label`), top-level KPIs (v2 had per-tab KPIs), Chart.js `chart_data` (v2 used separate `labels`/`values`), list-of-lists table rows (v2 used list of dicts), and CDI daily KPI (v2 had CDI annualized).

---

## v2.0 — 2026-07-23

(Replaced by v3 — see v2 zip for details.)

## v1.0 — 2026-07-22

(Replaced by v2 — original 11-series catalog with `(series_code, last_date, synced_at, row_count)` sync_state schema. v3 restores this schema.)

---

*Last updated: 2026-07-24 (v3.0).*
