<- Back to [FOCUS](../FOCUS.md)

# 📡 FOCUS API -- 7 Modes

## 1. `sync_all`

Sync every (indicador, frequency) in `DEFAULT_INDICATORS` concurrently (Semaphore(5), ~4 HTTP calls). Idempotent via `INSERT OR REPLACE`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | bool | false | Re-fetch even if recently synced. |
| `top` | int | 100 | Max records per fetch (Olinda `$top`). |

```python
data_source(domain="bcb", sub_domain="focus", mode="sync_all")
```

Returns: `{"status": "ok"|"partial", "indicators_synced": N, "indicators_failed": N, "rows_total": N, "results": {(indicador, frequency): {...}}, "synced_at": iso}`

---

## 2. `sync_expectations`

Sync one (indicador, frequency) pair (most-recent top N). Idempotent.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `indicador` | str | -- | 'IPCA', 'Selic', 'PIB', 'Cambio'. **Required.** |
| `frequency` | str | -- | 'monthly' or 'annual'. **Required.** |
| `top` | int | 100 | Max records. |
| `force` | bool | false | Re-fetch even if recently synced. |

```python
data_source(domain="bcb", sub_domain="focus", mode="sync_expectations",
            params='{"indicador":"IPCA","frequency":"monthly"}')
```

Returns: `{"status": "ok", "indicador": "IPCA", "frequency": "monthly", "rows": N, "synced_at": iso}`

---

## 3. `sync_indicator`

Sync one indicator using its primary frequency from `DEFAULT_INDICATORS`. Convenience wrapper.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `indicador` | str | -- | **Required.** |
| `force` | bool | false | |
| `top` | int | 100 | |

```python
data_source(domain="bcb", sub_domain="focus", mode="sync_indicator",
            params='{"indicador":"Selic"}')
```

Returns: same shape as `sync_expectations`.

---

## 4. `expectations`

Query the most recent N expectations for an indicator.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `indicador` | str | -- | **Required.** |
| `frequency` | str | -- | 'monthly' or 'annual'. **Required.** |
| `limit` | int | 50 | Max results. |

```python
data_source(domain="bcb", sub_domain="focus", mode="expectations",
            params='{"indicador":"IPCA","frequency":"monthly","limit":20}')
```

Returns: `{"status": "ok", "indicador": "IPCA", "frequency": "monthly", "count": N, "observations": [{data, data_referencia, media, mediana, minimo, maximo, numero_respondentes, base_calculo}, ...]}`

---

## 5. `last`

Get the most recent expectation for an indicator.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `indicador` | str | -- | **Required.** |
| `frequency` | str | -- | **Required.** |

```python
data_source(domain="bcb", sub_domain="focus", mode="last",
            params='{"indicador":"Selic","frequency":"annual"}')
```

Returns: `{"status": "ok", "indicador": "Selic", "frequency": "annual", "name": "...", "unit": "...", "data": "YYYY-MM-DD", "data_referencia": "YYYY", "media": float, "mediana": float, "minimo": float, "maximo": float, "numero_respondentes": int, "base_calculo": int}`

---

## 6. `summary`

Catalog overview: every (indicador, frequency) pair + row counts.

```python
data_source(domain="bcb", sub_domain="focus", mode="summary")
```

Returns: `{"status": "ok", "count": 4, "indicators": [{indicador, frequency, description, unit, rows, last_data, last_sync, synced_rows}, ...]}`

---

## 7. `status`

Show `focus.db` stats: per-indicator row counts + last sync timestamps.

```python
data_source(domain="bcb", sub_domain="focus", mode="status")
```

Returns: `{"status": "ok", "path": "...", "db_size_kb": N, "indicator_count": 4, "total_rows": N, "monthly_rows": N, "annual_rows": N, "indicators": [{indicador, frequency, rows, last_data, last_sync, ...}, ...]}`

---

*Last updated: 2026-08-22 (v1.0).*
