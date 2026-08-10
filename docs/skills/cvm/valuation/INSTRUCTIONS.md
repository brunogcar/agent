<- Back to [VALUATION Overview](../VALUATION.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never fetch price from the web** — Use b3 trades.db (local). The investsite skill is for web data; this skill uses local databases only.
2. **Never compute ratios without checking for None** — Use `_safe_div()` for all divisions. Returns None on zero/None denominator.
3. **Never change the ratio formulas** — P/L = market_cap/lucro_liquido, P/VPA = market_cap/PL, EV = Market Cap + Debt - Cash. These are market-cap-based (v1.0.9) — correct for both regular and UNIT tickers. Do NOT revert to per-share (price/EPS) — it breaks units.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr. (Exception: `print(..., flush=True)` for progress messages is OK — the dashboard mode uses these for user-facing progress.)
7. **Never use substring matching for investsite keys** — investsite's `precos_relativos` has keys like "Valor de Mercado" (market cap) AND "Valor de Mercado / Receita" (PSR). Substring "mercado" matches both. Use EXACT key match (`key.lower().strip() in {"valor de mercado", ...}`). See v1.0.12 lesson.
8. **Never add the Graham Number overlay back to the price chart** — Removed in v1.10 by user request. The price chart uses the default shared `build_price_chart()` output unmodified.
9. **Never call `ratios()` per-tab in the dashboard** — Call it ONCE at the top of `dashboard()` and pass the dict to every builder. 6 calls = 6× the engine load.
10. **Never make the dashboard crash on a single builder failure** — Wrap each tab builder in `_safe_build()` (try/except) so a failure degrades to an error section in that tab.
11. **Never use unregistered metric keys in the Less Common Multiples table** — The keys must match the `MetricSpec.name` field. `p_ativos`/`p_passivos`/`p_rb` are NOT registered — use `apa`/`ppa`/`rbpa` instead. (v1.10 fix.)

### ALWAYS DO

1. **Always use `core/br_validator`** for BRL/date/ticker parsing — `validate_ticker()`, `parse_escala()`, `parse_brl()`. Financial skills MUST use br_validator for consistency.
2. **Always include underlying values in the response** — price, EPS, VPA, shares, etc. so callers can verify the ratio computation.
3. **Always return data source status** — If b3 trades.db or fre.db is missing, return `None` for affected ratios + a note explaining what's missing.
4. **Always use `parse_escala()` for DFP escala values** — DFP stores escala as Portuguese words ("MIL", "MILHOES").
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.
6. **Always declare `REQUIRED_SOURCES` in `__init__.py`** (v1.7) — `REQUIRED_SOURCES = ["dfp", "itr", "fca", "cotahist", "brapi", "bridge"]` + pass to `make_route(required_sources=REQUIRED_SOURCES)`. The sync guard checks freshness before each dispatch + force-syncs if stale. Tests use `CVM_SKIP_SYNC=1` (set in conftest). Per-call bypass: `route(..., skip_sync=True)`.
7. **Always wrap the entire dashboard body in `engine_cache_scope()`** (v1.9) — The ratios fetch + section building + DCF sensitivity + history charts all share one cache. Without this, the 5 DCF sensitivity calls re-query the DB 5× each.
8. **Always use the calculations registry's `*_history()` functions for historical charts** (v1.10) — NOT `annual_periods`. The `*_history()` functions return step-function data (fundamentals change quarterly, price changes daily) which produces the correct staircase visual. See `build_pl_lpa_pvp_vpa_history_chart` + `build_roe_trend_chart` for the pattern.
9. **Always use `stepped: 'after'` for fundamental-driven chart lines** (v1.10) — LPA, VPA, ROE, ROA, ROIC are step functions (hold constant between quarterly filings). Price-driven lines (P/L, P/VP) use `tension: 0` without `stepped` (they vary daily).
10. **Always check the metric name in `MetricSpec.name`** before referencing it in the dashboard — unregistered keys render as "—". See v1.10 Menos Comuns fix.

---

### Anti-patterns & Lessons Learned

#### v1.0.9 — UNIT ticker market-cap mismatch
> - **What happened:** For UNIT tickers (suffix 11: KLBN11, TAEE11), price is per-unit but total_shares (from FRE) is individual shares. `price × total_shares` overstates market cap ~5x. P/L = price/EPS was inflated (KLBN11 showed 65 instead of ~13).
> - **Why it matters:** UNIT tickers are common in B3 (pulp, utilities, banks). Wrong P/L on all of them.
> - **Fix:** Compute P/L, P/VPA, P/EBIT, P/FCO from `market_cap` (not per-share): `P/L = market_cap / lucro_liquido`. Mathematically identical for regular stocks AND correct for units. Prefer brapi's `market_cap` (authoritative for units).

#### v1.0.10–v1.0.12 — investsite market_cap fallback (3 iterations)
> - **What happened:** brapi free tier doesn't cover all tickers (KLBN11). When brapi fails, valuation falls back to investsite. But investsite price doesn't include market_cap — so the v1.0.9 fix didn't work for units when brapi was unavailable.
> - **v1.0.10:** Extracted investsite's pre-computed P/L + P/VPA as fallback. But market_cap key scan used hardcoded names ("Valor de Mercado") that didn't match → market_cap_source stayed "computed" (wrong for units).
> - **v1.0.11:** Switched to substring scan ("mercado" in key). TOO BROAD — matched "Valor de Mercado / Receita" (PSR = 3.13) instead of market cap. KLBN11 showed Market Cap = 3.13 (a ratio, not BRL).
> - **v1.0.12 (final):** EXACT key match (`key.lower().strip() in {"valor de mercado", "market cap", "valor mercado"}`) + handle list values (investsite returns lists for Consolidado+Individual rows; take first).
> - **Lesson:** investsite keys are NOT predictable enough for substring matching. Use exact match. Always handle lists — investsite's parser returns lists when rows have multiple value columns.

#### v1.5 — Dashboard reorg: call ratios() ONCE, wrap each builder in try/except
> - **What changed:** The v1.4 dashboard had 5 tabs built by separate `build_*_section()` helpers, each called with the ratios dict. The v1.5 dashboard has 6 tabs + charts + collapsibles. The v1.4 structure worked but had no defensive wrapping — a single builder exception would crash the whole dashboard.
> - **Rule:** Call `ratios()` ONCE at the top of `dashboard()` and pass the resulting dict to every tab builder. Do NOT call `ratios()` per-tab (6 calls = 6× the engine load). Wrap each tab builder in `_safe_build()` (try/except) so a failure degrades to an error section in that tab, not a crash.
> - **Lesson:** The dashboard's value is its resilience — even if every engine fails, the dashboard payload must still build (with all-None values) so the report tool renders a "missing data" page instead of erroring out.

#### v1.5 — Derived metrics via _derive_*() helpers (no new engine calls)
> - **What changed:** The v1.5 Multiples tab lists 16 price ratios, but only ~10 are directly in `ratios_dict`. The remaining 6 (P/EBITDA, EV/EBIT, P/EV, P/CG, P/DB, etc.) are computable from components already in `ratios_dict` (market_cap, ebit, ebitda, ev, working_capital, divida_bruta).
> - **Rule:** For metrics NOT in `ratios_dict` but computable from existing keys, use a `_derive_*()` helper in `report.py`. Do NOT add new engine calls inside the dashboard — that breaks the "call ratios() once" rule. For metrics requiring NEW data sources, return None and track in ROADMAP.md.
> - **Lesson:** The dashboard is a VIEW layer, not a data-fetching layer. If a metric needs new data, it goes in ROADMAP.md and stays as '—' until an engine exists.

#### v1.9 — engine_cache_scope wraps the ENTIRE dashboard
> - **What happened:** The Valor Intrínseco tab calls DCF + IRR + WACC + 5 DCF sensitivity scenarios. Without a shared cache, each of these re-queried FCF/WACC/shares from the DB — the sensitivity alone took 5× the DCF time.
> - **Fix:** Wrap the entire `dashboard()` body in `engine_cache_scope()`. The `@engine_cached` decorator on each engine function checks the ContextVar cache first. All 5 sensitivity scenarios now reuse the cached FCF/WACC/shares from the ratios fetch.
> - **Lesson:** When the dashboard makes multiple calls that share underlying engines, wrap the whole body in `engine_cache_scope()`. The scope is re-entrancy-safe (nested scopes reuse the outer cache).

#### v1.10 — Menos Comuns showing "—" (key mismatch)
> - **What happened:** The `_MULTIPLES_LESS_COMMON` table referenced keys `p_ativos`/`p_passivos`/`p_rb` — but these were never registered. The actual metric names are `apa`/`ppa`/`rbpa` (the `MetricSpec.name` field). The `_derive_multiples` helper even hardcoded them to None.
> - **Why it matters:** 3 of 6 rows in the Menos Comuns tab showed "—" even though the engines + metrics existed.
> - **Fix:** Changed the keys to `apa`/`ppa`/`rbpa`. Removed the None hardcodes from `_derive_multiples`. Added tooltips for `apa`/`ppa`/`rbpa`/`p_cg`/`p_db` in `tooltips.py`.
> - **Lesson:** The `_MULTIPLES_LESS_COMMON` table key must match `MetricSpec.name` in the calculations registry. Grep the registry (`grep "register_metric" skills/cvm/calculations/metrics/*.py`) before adding a key to a dashboard table.

#### v1.10 — ROE trend chart: use *_history() not annual_periods
> - **What happened:** The v1.9 `build_roe_trend_chart` used `annual_periods` from `financials.modes.annual()` — only 6 data points (one per year). The chart looked sparse and didn't show quarterly dynamics.
> - **Fix:** Rewrote to use `roe_history()`/`roa_history()`/`roic_history()` from the calculations registry. These return quarterly step-function data (~20 points over 5Y). Forward-filled to carry forward last known value between reporting dates.
> - **Lesson:** For historical evolution charts, use the calculations registry's `*_history()` functions — they're optimized (step functions, quarterly granularity) and already handle the date-axis union + lookup. `annual_periods` is for annual snapshot tables, not time-series charts.

#### v1.10 — Graham Number overlay removed by user request
> - **What happened:** The v1.9 Graham Number overlay added a red dashed horizontal line to the price chart. The user found it visually noisy and asked for removal.
> - **Fix:** Removed the entire overlay block from `dashboard.py`. The price chart now uses the default shared `build_price_chart()` output unmodified.
> - **Lesson:** Don't mutate shared builder output (`build_price_chart`) in the consumer (`dashboard.py`). If you need an overlay, build a separate chart section — don't patch the shared one. This keeps the shared builder reusable.

---

*Last updated: 2026-08-10 (v1.10 — added v1.7-v1.10 lessons: sync guard, engine_cache_scope, Menos Comuns key fix, ROE trend rewrite, Graham overlay removal).*
