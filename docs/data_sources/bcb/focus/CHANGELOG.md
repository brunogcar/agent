<- Back to [FOCUS](../FOCUS.md)

# 📋 FOCUS Changelog

## v1.0 -- 2026-08-22

**Initial release -- BCB Focus (Boletim Focus) market expectations via Olinda OData.**

### Required Summary

- **4 curated indicators** x frequency: IPCA (monthly), Selic (annual), PIB (annual), Cambio (monthly).
- **7 modes** -- sync_all, sync_expectations, sync_indicator, expectations, last, summary, status.
- **Thread-safe fetcher** -- `Semaphore(5)` caps concurrent HTTP; 5-min Lock-guarded in-memory cache. Mirrors the sgs fetcher pattern.
- **Strict date normalization** -- Olinda returns ISO `YYYY-MM-DD` (sometimes with `T00:00:00` time component); the fetcher truncates to the date part.
- **Idempotent sync** -- `INSERT OR REPLACE` on the composite PK per table.
- **2 tables** -- `expectations_monthly` (PK: indicador, data, data_referencia, base_calculo) + `expectations_annual` (PK: indicador, data, data_referencia).
- **OData query convention** -- `$filter=Indicador eq 'IPCA'`, `$orderby=Data desc`, `$top=N`, `$format=json`.
- **Auto-discovery** -- `data_sources/bcb/__init__.py`'s `_discover_sub_domains()` picks up `focus/` automatically (no parent edits needed).

### Indicator Catalog (4 indicators)

| Indicador | Frequency | Unit | Description |
|-----------|-----------|------|-------------|
| IPCA | monthly | % | Inflacao - IPCA mensal (% no mes) |
| Selic | annual | % a.a. | Juros - Meta Selic (% a.a.) |
| PIB | annual | % | Atividade - PIB (% var. real anual) |
| Cambio | monthly | R$ | Cambio - USD/BRL (R$ por dolar, fim mes) |

### Architecture Choices (10)

1. Public API, no auth -- plain `httpx.get`, `Accept: application/json`.
2. Thread-safe fetcher -- `Semaphore(5)` + `_cache_lock` (mirrors sgs fetcher).
3. Strict date normalization -- Olinda ISO dates truncated to YYYY-MM-DD.
4. Defensive number parsing -- handles JSON numbers, nulls, string edge cases.
5. Idempotent sync -- `INSERT OR REPLACE` on composite PK.
6. Two tables, not one -- monthly + annual have different `DataReferencia` formats + PK requirements.
7. 4 curated indicators -- covers Juros / Inflacao / Atividade / Cambio.
8. OData query convention -- single-quote filter values, `$orderby=Data desc`, `$top=N`.
9. Cache key = (indicador, frequency, top) -- different `top` values don't collide.
10. Auto-discovery -- `focus/` is picked up by `data_sources/bcb/__init__.py` automatically.

### Modes (7)

sync_all, sync_expectations, sync_indicator, expectations, last, summary, status.

### Integration

- `skills/bcb/macro/__init__.py` `REQUIRED_SOURCES` extended to `["sgs", "focus"]`.
- `skills/_base.py` `_trigger_sync.sync_map` extended with a `"focus"` entry pointing to `data_sources.bcb.focus.sync_engine.sync_all` with `lambda: {"force": True}`.
- `skills/bcb/macro/modes/expectations.py` reads from `data_sources.bcb.focus.query_engine`.
- `skills/bcb/macro/modes/dashboard.py` adds a 7th "Expectativas Focus" tab (group: Analise) that calls the expectations mode.

---

*Last updated: 2026-08-22 (v1.0).*
