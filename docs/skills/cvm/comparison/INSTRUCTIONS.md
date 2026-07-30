<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never query the database directly from comparison** — comparison orchestrates the 3 existing skills. If you need a new metric, add it to the underlying skill (financials/valuation/dividends), then reference it in the column lists here. No SQL in comparison.py.
2. **Never fail the whole comparison on a per-ticker error** — `_fetch_all()` wraps each skill call in try/except. A ticker failing one source gets `None` cells, not a raised exception. The `errors` list captures what failed.
3. **Never change a `dict_key` without checking the source skill** — the `dict_key` in `_VALUATION_COLS` / `_FINANCIALS_COLS` / `_DIVIDENDS_COLS` must match the key the underlying skill emits. If you rename a key in valuation.ratios, update `_VALUATION_COLS` in the same commit.
4. **Never add a column with a different unit to an existing section** — each section is unit-homogeneous (all BRL, all %, all multiples). A mixed-unit section breaks per-column format specs. Add a new section instead.
5. **Never collide dict_keys across sources in summary mode** — `summary()` merges valuation + financials + dividends dicts. If two sources emit the same key (e.g. `dividend_yield`), the later one overwrites. `dividend_yield` comes from valuation, not dividends — don't add it to `_DIVIDENDS_COLS`.
6. **Never register adapters outside `tools/report_ops/adapters/`** — `adapters/__init__.py` imports the comparison module to trigger `@register_adapter`. New adapter files must be added there.
7. **[v1.3] Never import calculations directly from comparison** — comparison consumes calculations metrics transitively via `valuation.ratios()`. If a metric is needed that valuation doesn't expose, extend `valuation.ratios()` to expose it (then add the column here). Direct `from skills.cvm.calculations.metrics.X import Y` imports in comparison.py break the orchestration boundary — comparison should talk to valuation, not to calculations.
8. **[v1.3] Never reuse a column label within a single section** — `_build_section` builds a `formats` dict keyed by label. Two columns with the same label would collide. The v1.3 additions use the `(val)` suffix (e.g. `ROE (val)`) precisely to avoid colliding with the financials section's `ROE` if they ever end up in the same section.

## ✅ ALWAYS DO

9. **Always update both skill tests and adapter tests** when changing column lists — `tests/skills/cvm/comparison/test_side_by_side.py` checks column names + values; `tests/tools/report/test_report_adapters.py` checks adapter pass-through.
10. **Always keep `errors` list populated** — if a per-ticker skill fails, append to `entry["error"]` and let it flow to `r["errors"]`. The caller needs to know data is partial.
11. **Always uppercase tickers** — `tickers = [t.strip().upper() for t in tickers]` at the start of each mode. Underlying skills expect uppercase.
12. **Always reuse `_build_section()`** for new sections — it handles the columns/rows/formats construction. Don't hand-build section dicts.
13. **[v1.3] Always split tests by mode** — `tests/skills/cvm/comparison/` follows the per-mode pattern: one `test_<mode>.py` per skill mode (validation / side_by_side / summary / growth / route) + a `conftest.py` with shared fixtures. Don't put new tests in a monolithic `test_comparison.py` — that file no longer exists.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.3 — Transitive calculations integration
> - **What happened:** Phase 2B refactored `valuation.ratios()` to delegate to calculations engines + metrics, enriching its `ratios` dict with ~10 new keys (roe, roa, margem_bruta, margem_operacional, margem_liquida, divida_pl, giro_ativos, liquidez_corrente, roic, graham_number, p_ebit, p_fco, p_fcf). Comparison already consumed the full ratios dict via `entry["valuation"] = r.get("ratios", {})`, so the new keys were already in the per-ticker dict — but no columns surfaced them.
> - **Why it matters:** The LLM was fetching the data but never seeing it. The whole point of the calculations library is to make canonical metric values available downstream; if comparison doesn't expose them, the integration is invisible to the end user.
> - **v1.3 fix:** Added 5 column entries to `_VALUATION_COLS` — `("ROE (val)", "roe", "pct")`, etc. No new data fetching, no new helper functions, no new imports. The `(val)` suffix distinguishes them from the financials section's same-named columns (which use the annual statement value via `compute_ratios`, not the TTM calculations snapshot).
> - **Lesson:** When an upstream skill enriches its output, downstream skills that already consume the full dict pick up the new fields "for free" — but only if they have column definitions that surface them. Audit column lists whenever an upstream skill ships new fields.

### v1.2.1–v1.2.2 — Growth guard philosophy
> - **What happened:** v1.1 growth mode showed 3612% (SUZB3) and -395% (KLBN11) for Lucro QoQ — clearly noise. v1.2.1 added a `|result| >= 500%` magnitude guard, but it was TOO AGGRESSIVE — it suppressed legitimate extreme values too (both tickers showed None, hiding real data).
> - **Why it matters:** The LLM needs to see real data, even when it's extreme. Hiding everything behind None makes the growth table useless.
> - **v1.2.2 fix:** Removed the magnitude guard entirely. Only sign-change guards remain: `prev <= 0` (negative base = meaningless) and `curr * prev < 0` (opposite signs = sign change, % is meaningless). Extreme same-sign growth (e.g. 600%) passes through — the LLM can judge whether it's meaningful.
> - **Lesson:** Don't suppress data based on magnitude — the LLM is smart enough to interpret "600% growth" as "probably tiny base, check absolute values." Only suppress when the math is genuinely meaningless (sign changes, division by zero).

### v1.2 — Sector tagging via CAD
> - **What happened:** Added `sectors` field to all comparison modes — resolves SETOR_ATIV from CAD via bridge → CNPJ.
> - **Why it matters:** Enables "same sector?" grouping (SUZB3 vs KLBN11 = both "Papel e Celulose"). Without it, the LLM has no way to know if a comparison is apples-to-apples.
> - **Lesson:** Best-effort per ticker — if CAD/bridge lookup fails, sector is "" (empty string), not an error. The comparison never fails on sector resolution.

- **v2.0 lesson:** _registry.py + __init__.py now delegate to `skills/_base.py` (shared ModeSpec + make_registry + make_route + auto_discover_modes). The duplicated ~97-line _registry.py + ~88-line __init__.py boilerplate is gone — each skill's _registry.py is now ~16 lines, __init__.py is ~50 lines. Adding a new mode = drop a file in `modes/` + `@register_mode(...)` (unchanged). Adding a new skill = 3 files (_registry.py + __init__.py + modes/) following the pattern in [SKILLS.md → How to Create a New Skill](../../SKILLS.md). Bug fixes to the dispatch infrastructure now only need to be made in ONE place.

---

*Last updated: 2026-07-30 (v2.0).*
