<- Back to [VALUATION Overview](../VALUATION.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never fetch price from the web** — Use b3 trades.db (local). The investsite skill is for web data; this skill uses local databases only.
2. **Never compute ratios without checking for None** — Use `_safe_div()` for all divisions. Returns None on zero/None denominator.
3. **Never change the ratio formulas** — P/L = market_cap/lucro_liquido, P/VPA = market_cap/PL, EV = Market Cap + Debt - Cash. These are market-cap-based (v1.0.9) — correct for both regular and UNIT tickers. Do NOT revert to per-share (price/EPS) — it breaks units.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.
7. **Never use substring matching for investsite keys** — investsite's `precos_relativos` has keys like "Valor de Mercado" (market cap) AND "Valor de Mercado / Receita" (PSR). Substring "mercado" matches both. Use EXACT key match (`key.lower().strip() in {"valor de mercado", ...}`). See v1.0.12 lesson.

### ALWAYS DO

1. **Always use `core/br_validator`** for BRL/date/ticker parsing — `validate_ticker()`, `parse_escala()`, `parse_brl()`. Financial skills MUST use br_validator for consistency.
2. **Always include underlying values in the response** — price, EPS, VPA, shares, etc. so callers can verify the ratio computation.
3. **Always return data source status** — If b3 trades.db or fre.db is missing, return `None` for affected ratios + a note explaining what's missing.
4. **Always use `parse_escala()` for DFP escala values** — DFP stores escala as Portuguese words ("MIL", "MILHOES").
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.

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
> - **Rule:** For metrics NOT in `ratios_dict` but computable from existing keys, use a `_derive_*()` helper in `report.py` (e.g. `_derive_multiples()`, `_derive_per_share()`, `_derive_detailed_leverage()`). Do NOT add new engine calls inside the dashboard — that breaks the "call ratios() once" rule. For metrics requiring NEW data sources (total_assets, total_liabilities, gross_revenue), return None and track in ROADMAP.md.
> - **Lesson:** The dashboard is a VIEW layer, not a data-fetching layer. If a metric needs new data, it goes in ROADMAP.md (D1 / D2) and stays as '—' until an engine exists.

---

*Last updated: 2026-07-29 (v1.5 — 6-tab dashboard reorg; added v1.5 instructions for ratios()-once + try/except + _derive_*() helpers).*
