<- Back to [SGS](../SGS.md)

# 📡 SGS API — 8 Modes

## 1. `sync_all`

Sync every series in `SERIES_CATALOG` concurrently (Semaphore(5), ~12 HTTP calls). Idempotent via `INSERT OR REPLACE`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | bool | false | Re-fetch even if recently synced. |

```python
data_source(domain="bcb", sub_domain="sgs", mode="sync_all")
```

Returns: `{"status": "ok"|"partial", "series_synced": N, "series_failed": N, "rows_total": N, "results": {code: {...}}, "synced_at": iso}`

---

## 2. `sync_series`

Sync one series (full available history). Idempotent.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | int | — | BCB SGS series code (e.g. 11 = Selic). **Required.** |
| `force` | bool | false | Re-fetch even if recently synced. |

```python
data_source(domain="bcb", sub_domain="sgs", mode="sync_series", params='{"code":11}')
```

Returns: `{"status": "ok", "code": 11, "rows": N, "synced_at": iso}`

---

## 3. `sync_series_range`

Sync one series for a specific date window `[start, end]`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | int | — | **Required.** |
| `start` | str | — | YYYY-MM-DD. **Required.** |
| `end` | str | — | YYYY-MM-DD. **Required.** |
| `force` | bool | false | |

```python
data_source(domain="bcb", sub_domain="sgs", mode="sync_series_range",
            params='{"code":11,"start":"2024-01-01","end":"2024-12-31"}')
```

Returns: `{"status": "ok", "code": 11, "rows": N, "start": "...", "end": "...", "synced_at": iso}`

---

## 4. `series`

Query observations for a series (most-recent N or windowed).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | int | — | **Required.** |
| `days` | int | 30 | Number of most-recent obs. |
| `start` | str | "" | Optional window start (YYYY-MM-DD). |
| `end` | str | "" | Optional window end (YYYY-MM-DD). |

```python
data_source(domain="bcb", sub_domain="sgs", mode="series", params='{"code":11,"days":90}')
```

Returns: `{"status": "ok", "code": 11, "name": "Selic diaria", "count": N, "observations": [{"ref_date": "...", "value": float}, ...]}`

---

## 5. `last`

Get the most recent observation for a series.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | int | — | **Required.** |

```python
data_source(domain="bcb", sub_domain="sgs", mode="last", params='{"code":11}')
```

Returns: `{"status": "ok", "code": 11, "name": "Selic diaria", "ref_date": "2024-...", "value": float}`

---

## 6. `search`

Search the series catalog by name fragment (case-insensitive LIKE).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | str | — | Name fragment. **Required.** |
| `limit` | int | 10 | Max results. |

```python
data_source(domain="bcb", sub_domain="sgs", mode="search", params='{"query":"Selic"}')
```

Returns: `{"status": "ok", "count": N, "series": [{"code", "name", "frequency", "unit", "category"}, ...]}`

---

## 7. `summary`

Catalog overview: every series sorted by `(category, code)`.

```python
data_source(domain="bcb", sub_domain="sgs", mode="summary")
```

Returns: `{"status": "ok", "count": 12, "series": [{...}, ...]}`

---

## 8. `status`

Show `sgs.db` stats: per-series row counts + last sync timestamps.

```python
data_source(domain="bcb", sub_domain="sgs", mode="status")
```

Returns: `{"status": "ok", "path": "...", "db_size_kb": N, "series_count": 12, "total_rows": N, "series": [{code, name, rows, last_ref_date, last_sync, ...}, ...]}`

---

*Last updated: 2026-07-24 (v3.0).*
