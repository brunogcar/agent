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

### v1.4 — Modular split + dashboard composition
> - **What happened:** The 356-line monolithic `screener.py` was the LAST CVM skill to use the legacy single-file structure. All 7 other CVM skills (financials, valuation, backtest, comparison, dividends, governance, historical) had already been split into `_registry.py` + `modes/*.py` + `report.py` + (optional) `helpers.py`. Adding a new mode to screener required editing both `__init__.py`'s MANIFEST dict + `dispatch` table AND adding the function to `screener.py` — 3 edits per new mode, with the dispatch table being a manual `{"sector": sector, "compare": compare}` dict that could silently go stale.
> - **v1.4 fix:** Split `screener.py` into `_registry.py` (ModeSpec + register_mode + MODES + build_manifest_modes — verbatim from governance/_registry.py) + `helpers.py` (4 internal helpers: `_roe_from_ratios`, `_pct_change`, `_compute_medians`, `_build_comparison`) + `report.py` (NEW dashboard composition helpers) + `modes/{sector,compare,dashboard}.py` (3 mode files, each decorated with `@register_mode`). `__init__.py` now auto-discovers `modes/*.py` via `importlib.glob` + builds `MANIFEST["modes"]` from the registry. Adding a new mode = drop a file in `modes/` + `@register_mode()` — zero edits to `__init__.py` or `_registry.py`. The new `dashboard` mode is a thin composition of `compare()` (which internally calls `sector()`), reshaping the result into a 3-tab payload + 5 top-level KPI cards.
> - **Why it matters:** The dashboard mode gives the LLM a single-call answer to "tell me everything about SUZB3 vs its sector" — Overview summary + Peers table + Comparison table in one structured payload, optimized for the report tool's `dashboard` action. Previously the LLM would have had to call `compare()` + `sector()` separately and then mentally combine the two JSON outputs.
> - **Lesson:** When a skill exposes multiple related modes that all read from the same underlying data, add a `dashboard` mode that composes them. The dashboard mode should be a thin orchestrator — gather data from existing modes via try/except-wrapped calls (so partial failures degrade gracefully) + use `report.py` builders to shape the result. NEVER duplicate the data-fetching logic — the dashboard mode should only call existing modes + reshape their output. The `report.py` builders are reusable across modes + tests, keeping the dashboard module itself small (under 150 lines).

- **v2.0 lesson:** _registry.py + __init__.py now delegate to `skills/_base/` (shared ModeSpec + make_registry + make_route + auto_discover_modes). The duplicated ~97-line _registry.py + ~88-line __init__.py boilerplate is gone — each skill's _registry.py is now ~16 lines, __init__.py is ~50 lines. Adding a new mode = drop a file in `modes/` + `@register_mode(...)` (unchanged). Adding a new skill = 3 files (_registry.py + __init__.py + modes/) following the pattern in [SKILLS.md → How to Create a New Skill](../../SKILLS.md). Bug fixes to the dispatch infrastructure now only need to be made in ONE place.

---

*Last updated: 2026-07-30 (v2.0).*
