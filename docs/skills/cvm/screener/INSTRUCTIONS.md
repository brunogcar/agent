<- Back to [SCREENER Overview](../SCREENER.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never query the database directly from screener** — screener orchestrates CAD + bridge + valuation. If you need a new metric, add it to the underlying skill, then reference it here. No SQL in screener.py.
2. **Never fail the whole screener on a per-company error** — companies without a ticker or with failed valuation are skipped. The `errors` list captures what was skipped.
3. **Never change the sort order** — peers are sorted by P/L cheapest-first. This is intentional for value investors. None P/L goes last.
4. **Never compute medians with None values** — use `statistics.median()` over non-None values only. If a metric is None for all peers, median is None.
5. **Never register adapters outside `tools/report_ops/adapters/`** — `adapters/__init__.py` imports the screener module to trigger `@register_adapter`.
6. **[v1.2] Never import calculations directly from screener** — screener consumes calculations metrics transitively via `valuation.ratios()`. If a metric is needed that valuation doesn't expose, extend `valuation.ratios()` to expose it (then reference it here). Direct `from skills.cvm.calculations.metrics.X import Y` imports in screener.py break the orchestration boundary — screener should talk to valuation, not to calculations.
7. **[v1.2] Never derive ROE from `lucro_liquido` / `patrimonio_liquido` in valuation's ratios dict** — those keys are not reliably populated in `valuation.ratios()` output (they live in `financials.summary` instead). Use `ratios.get("roe")` directly. The old `_roe_from_ratios` derivation was a v1.0 workaround that's no longer needed since Phase 2B made `roe` a first-class key.

## ✅ ALWAYS DO

8. **Always reuse `sector()` from `compare()`** — compare mode calls sector() to get peers + medians, then builds the comparison. Don't duplicate the peer-fetching logic.
9. **Always uppercase tickers** — `ticker = company.strip().upper()`.
10. **Always include `vs_sector` label** — "cheap"/"expensive" for P/L, P/VPA, EV/EBITDA, **divida_pl**; "above"/"below" for ROE, **roa**, **margem_liquida**, dividend_yield. This is what the LLM reads to judge valuation.
11. **[v1.2] Always split tests by mode** — `tests/skills/cvm/screener/` follows the per-mode pattern: one `test_<mode>.py` per skill mode (validation / sector / compare / route) + a `conftest.py` with shared fixtures. Don't put new tests in a monolithic `test_screener.py` — that file no longer exists.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.2 — ROE derivation removed
> - **What happened:** v1.0's `_roe_from_ratios(ratios)` computed ROE as `ratios["lucro_liquido"] / ratios["patrimonio_liquido"]` because `valuation.ratios()` didn't return `roe` directly. But `lucro_liquido` and `patrimonio_liquido` aren't actually in `valuation.ratios()` output — they live in `financials.summary`. The derivation worked in tests (because the test mock happened to include those keys) but failed silently in production (returned None for every peer).
> - **Why it matters:** A "ROE median" of None for an entire sector is worse than no ROE column at all — the LLM might trust the None and conclude "no data" when the real issue was the derivation path.
> - **v1.2 fix:** Since Phase 2B, `valuation.ratios()` returns `roe` directly (computed by `calculations.metrics.roe_at` from TTM earnings + equity snapshot). The helper is now just `ratios.get("roe")`. The v1.0 derivation was dead code in production.
> - **Lesson:** When an upstream skill doesn't expose a metric, prefer extending the upstream skill over deriving it downstream. Derivation logic that works in tests (where mocks include the keys) but not production (where the keys aren't actually emitted) is a silent test/prod skew.

### v1.2 — Transitive calculations integration
> - **What happened:** Phase 2B refactored `valuation.ratios()` to delegate to calculations engines + metrics, enriching its `ratios` dict with new keys (roe, roa, margem_liquida, divida_pl, etc.). Screener already consumed the full ratios dict via `peer.update({...})`, so the new keys were available — but the peer dict + medians + comparison weren't extended to use them.
> - **v1.2 fix:** Added 3 entries to each of: peer dict, `_compute_medians()`, `_build_comparison()`. No new data fetching, no new helper functions, no new imports. The new medians keys are additive — all v1.1 keys preserved.
> - **Lesson:** When an upstream skill enriches its output, downstream skills that already consume the full dict pick up the new fields "for free" — but only if they have explicit field references that surface them. Audit peer/medians/comparison field lists whenever an upstream skill ships new fields.

---

*Last updated: 2026-07-27 (v1.2).*
