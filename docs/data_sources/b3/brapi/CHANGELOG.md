<- Back to [BRAPI Overview](../BRAPI.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-08-05 | **Thread safety + batch fetch (Phase 3 perf).** `fetcher.py` is now safe to call from multiple threads concurrently — required by the screener + comparison skills which now use `ThreadPoolExecutor(max_workers=5)` to parallelize per-ticker/per-peer fetches (see [screener CHANGELOG](../../../skills/cvm/screener/CHANGELOG.md) v1.3 + [comparison CHANGELOG](../../../skills/cvm/comparison/CHANGELOG.md) v1.3). Two changes: (1) **`threading.Lock` around the in-memory quote cache** — v1.0's cache was a plain `dict` mutated without synchronization; concurrent workers could corrupt the dict or trigger a `KeyError` race between the `if ticker not in cache` check + the `cache[ticker] = ...` write. The Lock wraps both the read + write paths of the cache (held for the duration of the cache mutation only — never held across the HTTP call). (2) **`threading.Semaphore(5)` for concurrency control** — replaces the v1.0 global `time.sleep(0.5)` rate-limit pause. The Semaphore allows up to 5 concurrent brapi HTTP requests in flight; the 6th blocks until one finishes. This caps brapi throughput at the same effective rate as the old 0.5s sleep (1 req / 0.5s = 2 req/s per worker × 5 workers ≈ 10 req/s burst, but bounded by the Semaphore to 5 in-flight) without forcing sequential workers to sleep when the API could handle more. Removed the global `time.sleep(0.5)` rate-limit entirely — the Semaphore is the single source of truth for concurrency. (3) **New `fetch_quotes(tickers)` batch function** — takes a list of tickers + returns a `{ticker: quote_dict}` mapping. Internally uses the same Lock-gated cache + Semaphore-gated HTTP path as the single-ticker `fetch_quote()`; callers that need N quotes should prefer `fetch_quotes()` over N× `fetch_quote()` because the cache lookup is done in one critical section. Used by the screener + comparison skills' ThreadPoolExecutor workers. No API changes to existing `fetch_quote()` — it now also goes through the Lock + Semaphore transparently. No new tests (the existing brapi tests mock the HTTP layer so threading is transparent). |
| v1.0 | 2026-07-24 | **Initial implementation.** 6 modes: sync_tickers (1,796 tickers in 1 call), sync_history (OHLCV), quote (live + cached), history (local query), tickers (list), status. Free tier covers PETR4/VALE3/ITUB4/MGLU3. Replaces 7,138-page B3 InstrumentsConsolidated sync. Rate limiting (0.5s) + in-memory cache (1h TTL). |

---

*Last updated: 2026-08-05 (v1.1 — thread safety + batch fetch).*
