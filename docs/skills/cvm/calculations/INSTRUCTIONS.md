<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🛡️ AI Instructions

This library is the **pattern template** for central auto-discovery + registry architecture. Follow these rules when editing this library OR when copying the pattern to a new skill.

**Current scope (v1.5):** 30 engines in 7 categories (market, shares, dre, bpa, bpp, dfc, dva) + 37 metrics in 2 types (9 per-share+ratio and 28 fundamental ratio) tagged across 8 metric categories (valuation, profitability, liquidity, leverage, efficiency, growth, per_share, tax).

## ❌ NEVER DO

1. **Never import a metric from an engine** — Engines are below metrics in the dependency graph. A metric imports engines; never the reverse. Violating this creates circular dependencies. Example: `engines/da.py` must NOT import `from skills.cvm.calculations.metrics.ebitda_margin import ebitda_margin_at`.
2. **Never query CVM/B3 directly from a metric** — That's the engine's job. Metrics compose engines; they don't fetch data. If you need a new data source, add an ENGINE first, then import it from the metric. Example: `metrics/ev_ebitda.py` must NOT call `connect_dfp()` directly — it imports `ebit_at()` and `da_at()`.
3. **Never name an engine after a ratio** — `engines/vpa.py` is WRONG. VPA is a ratio (metric), not a raw quantity. The engine produces PL (a raw quantity); the metric computes VPA from it. See naming convention below.
4. **Never name a metric after a raw quantity** — `metrics/pl.py` is WRONG. PL is a raw quantity (engine). The metric computes a ratio from PL. Use the per-share quantity name: `metrics/vpa.py` (VPA = PL/shares).
5. **Never compute TTM/PL for each day individually** — TTM changes quarterly, PL changes quarterly, shares change annually. Use `*_periods()` to get the step function, then do O(1) lookups per day. Example: `for date in trading_days: shares = next(p["shares"] for p in reversed(shares_periods) if p["date"] <= date)`.
6. **Never forget `parse_escala`** — DFP/ITR store raw values with escala ("MIL", "MILHOES", "MILHÃO", "UNIDADE"). Always apply `parse_escala(r["escala"])` (or an inline `CASE c.escala WHEN 'MIL' THEN 1000 ...` expression) before using values. Forgetting it produces values 1000× or 1,000,000× too small.
7. **Never return a ratio when the denominator <= 0** — P/L with negative earnings, P/VPA with negative equity, Payout with negative earnings, ROE/ROA/ROIC with negative earnings/equity/EBIT, Gross/Operating/Net Margin with negative gross_profit/EBIT/earnings/revenue. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number). See [API.md](API.md#error-handling) for the full guard table.
8. **Never put auto-discovery code in `engines/__init__.py` or `metrics/__init__.py`** — auto-discovery is in the CENTRAL `_registry.py` (top level). The `__init__.py` files in `engines/` and `metrics/` are minimal docstrings. Adding code there defeats the single-source-of-truth principle.
9. **Never edit `engines/__init__.py` or `metrics/__init__.py` to add an engine/metric to a manual inventory list** — there is NO manual inventory. The registry (`list_engines()` / `list_metrics()`) is the source of truth. Adding a file + `register_*()` is all you need. Editing `__init__.py` for inventory defeats the purpose of auto-discovery.
10. **Never make `MetricSpec` or `EngineSpec` frozen** — tests need to `monkeypatch.setattr(spec, "history_fn", fake_fn)` to mock registry-captured functions. Use `@dataclass` (not `@dataclass(frozen=True)`). Frozen dataclasses raise `FrozenInstanceError` on setattr. See anti-patterns (v1.2 lesson).
11. **Never mock the module function in tests** — `_metric_history()` (in consumer skills) calls `spec.history_fn` (captured at registration time). Mock the registry spec: `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Patching the module function (`metrics.lpa.lpa_history`) doesn't work because the spec already holds a reference to the original.
12. **Never forget to mock ALL engines a metric composes** (v1.9 lesson) — not just some. If a metric calls `cash_at` (like ROIC does), mock it too — even if the metric has a `try/except` wrapper. Otherwise you're either hitting the real DB in tests, OR silently testing the fallback path instead of the v1.9 behavior. The `engines=[...]` field on MetricSpec is your checklist.
13. **Never use description-based search in metrics** — the `da` and `capex` engines search the DFC by `descricao LIKE '%deprec%' OR '%amort%'` (or `'%imobilizado%' OR '%intangivel%'`) because D&A and CapEx have no fixed CVM code. This pattern stays in ENGINES only. Metrics compose engines via their `at_fn`/`periods_fn` and should never re-query raw CVM data with description filters. If you need a new description-searched quantity, add an ENGINE for it.

---

## ✅ ALWAYS DO

1. **Always use step-function optimization** — Precompute TTM/PL/shares/cash/debt/EBIT/D&A/CapEx periods via `*_periods()`, then do O(1) lookups per day. Don't recompute for 1200 days. (Exception: DPA TTM is a rolling 365-day window recomputed per day via a single SQL query — but it's still O(1) in the metric, the engine does the work.)
2. **Always follow the engine contract** — `<quantity>_at(company, date) -> float | None` + `<quantity>_periods(company) -> list[dict]` + `register_engine(EngineSpec(...))` at module level. Every engine must have all three.
3. **Always follow the metric contract** — For per-share+ratio metrics (Type 1): `<name>_at` (per-share) + `<ratio>_at` (ratio) + optional `<bonus>_at` + `<name>_history` + `register_metric(MetricSpec(...))`. For fundamental ratios (Type 2): `<ratio>_at` + `<name>_history` + `register_metric(MetricSpec(..., per_share_*=None))`. Every metric must have `history_fn` + `ratio_fn` + `register_metric`.
4. **Always set `category` when registering an engine** — one of `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc`, `dva`, or `other`. The default is `"other"` but should be overridden for every real engine. `list_engines(category="dre")` relies on this for backtest discovery.
5. **Always set `category` when registering a metric** (v1.5) — one of: `valuation`, `profitability`, `liquidity`, `leverage`, `efficiency`, `growth`, `per_share`, `tax`, or `other`. The default is `"other"` but should be overridden for every real metric. `list_metrics_by_category("liquidity")` + `compute_all_ratios(company, date, categories=[...])` rely on this for filtered discovery. All 37 existing metrics are tagged as of v1.5 — new metrics MUST set a category at registration time so consumer skills' `compute_all_ratios()` calls continue to discover them automatically.
6. **Always include aliases (Portuguese + English)** — `["pe", "pl", "p/l", "preco_lucro"]` for lpa, `["dy", "dividend_yield", "yld", "payout", "rendimento", "rendimento_dividendo", "div_yield"]` for dpa, `["return_on_equity", "retorno_pl", "retorno_patrimonio"]` for roe. Users expect to call `summary(metric="retorno_pl")`, not just `summary(metric="roe")`.
7. **Always set `per_share_label=None` for fundamental ratios** — and `per_share_key=None`, `per_share_fn=None`. Consumer skills' chart adapters + summary adapters inspect `per_share_label`: if `None`, single-dataset chart + skip per-share KPI/row.
8. **Always mock the registry spec in tests** — `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Not the module function. See NEVER DO #11.
9. **Always import from the central `_registry.py`** — `from skills.cvm.calculations._registry import MetricSpec, register_metric`. NOT from `metrics._registry` (old v1.2 location, deleted in v1.3). The central registry at `skills/cvm/calculations/_registry.py` is the ONLY location.
10. **Always use `compute_all_ratios()` in consumer skills** (v1.5) — never hardcode N individual metric imports. `from skills.cvm.calculations._registry import compute_all_ratios` then `ratios = compute_all_ratios(company, date)`. Use `categories=[...]` to fetch a subset (e.g. `categories=["liquidity", "leverage"]` for a balance-sheet panel) or `exclude=[...]` to drop a few. New metrics added to `metrics/` + `register_metric()` appear automatically in the returned dict — no consumer edits required.

---

## 📐 Naming Convention

| Layer | File name | Based on | Example |
|-------|-----------|----------|---------|
| Engine | `<quantity>.py` | The raw quantity it produces | `price.py`, `earnings.py`, `shares.py`, `pl.py`, `da.py`, `debt.py`, `cash.py`, `capex.py`, `total_assets.py`, `current_liabilities.py` |
| Metric (Type 1) | `<per_share>.py` | The per-share quantity | `lpa.py` (LPA = earnings/shares), `rps.py` (RPS = revenue/shares), `ev_ebitda.py` (EV/EBITDA + EBITDA/Ação) |
| Metric (Type 2) | `<ratio_snake_case>.py` | The ratio name | `roe.py`, `roic.py`, `gross_margin.py`, `operating_margin.py`, `net_margin.py`, `ebitda_margin.py`, `debt_equity.py`, `net_debt_ebitda.py`, `asset_turnover.py`, `capex_revenue.py`, `current_ratio.py` |

**Rule:** Engine file names are nouns (the raw quantity). Per-share+ratio metric file names are per-share quantity names. Fundamental-ratio metric file names are the ratio name in snake_case. Never mix them — `engines/vpa.py` or `metrics/pl.py` are both WRONG.

**JSON keys in series entries:**
- Per-share value (Type 1 only): metric name (`lpa`, `vpa`, `dpa`, `rps`, `ebitda_ps`, `tangible_book_ps`)
- Ratio: traditional abbreviation (`pe` for P/L, `pvpa` for P/VPA, `dy` for Div Yield, `psr`, `ev_ebitda`, `p_ebit`, `p_fco`, `p_fcf`, `p_tangible_book`, `roe`, `roa`, `roic`, `gross_margin`, `operating_margin`, `net_margin`, `ebitda_margin`, `debt_equity`, `net_debt_ebitda`, `asset_turnover`, `capex_revenue`, `current_ratio`, `graham_number`, `effective_tax_rate`, `ev_sales`, `ev_fcf`, `cash_ratio`, `ocf_margin`, `fcf_margin`, `working_capital`, `cash_flow_to_debt`, `retention_ratio`, `sustainable_growth`, `quick_ratio`, `interest_coverage`, `inventory_turnover`, `receivables_turnover`, `fixed_asset_turnover`)
- Engine quantities: `price`, `ttm_earnings`, `shares`, `pl`, `ttm_rev`, `ttm_gp`, `ttm_ebit`, `ttm_ebt`, `ttm_tax`, `ttm_da`, `ttm_capex`, `ttm_fco`, `ttm_fci`, `ttm_fcf`, `current_assets`, `cash`, `total_assets`, `debt`, `current_liabilities`, `receivables`, `inventory`, `ppe`, `intangibles`, `payables`, `ttm_cogs`, `ttm_financial_result`, `ttm_interest_paid`, `ttm_total_tax`, `ttm_value_added`

---

## 📐 Dependency Graph Rule

```text
calculations/_registry.py  (CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories)
       │
       ├── engines/  (30 engines — LEAVES, never import each other or metrics)
       │     ├── market: price, dividends
       │     ├── shares: shares
       │     ├── dre:    earnings, revenue, gross_profit, ebit, ebt, tax, cogs, financial_result
       │     ├── bpa:    current_assets, cash, total_assets, receivables, inventory, ppe, intangibles
       │     ├── bpp:    pl, debt, current_liabilities, payables
       │     ├── dfc:    da, capex, operating_cf, investing_cf, financing_cf
       │     └── dva:    interest_paid, total_tax, value_added
       │
       └── metrics/  (37 metrics — compose engines, never point at other metrics)
             ├── lpa.py             → price + earnings + shares                       (Type 1)
             ├── vpa.py             → price + pl + shares                              (Type 1)
             ├── dpa.py             → price + dividends + earnings + shares           (Type 1, +payout)
             ├── rps.py             → price + revenue + shares                        (Type 1)
             ├── ev_ebitda.py       → price + shares + debt + cash + ebit + da        (Type 1, 6 engines)
             ├── p_ebit.py          → price + ebit + shares                            (Type 1)
             ├── p_fco.py           → price + operating_cf + shares                    (Type 1)
             ├── p_fcf.py           → price + operating_cf + investing_cf + shares     (Type 1, 4 engines)
             ├── price_to_tangible_book.py → price + pl + intangibles + shares        (Type 1, 4 engines, v1.3)
             ├── roe.py             → earnings + pl                                    (Type 2)
             ├── roa.py             → earnings + total_assets                          (Type 2, v1.2: total_assets)
             ├── roic.py            → ebit + tax + ebt + pl + debt + cash              (Type 2, 6 engines, v2.0 EBT-based NOPAT)
             ├── gross_margin.py    → gross_profit + revenue                           (Type 2)
             ├── operating_margin.py → ebit + revenue                                 (Type 2)
             ├── net_margin.py      → earnings + revenue                               (Type 2)
             ├── ebitda_margin.py   → ebit + da + revenue                              (Type 2)
             ├── debt_equity.py     → debt + pl                                        (Type 2)
             ├── net_debt_ebitda.py → debt + cash + ebit + da                          (Type 2, 4 engines)
             ├── asset_turnover.py  → revenue + total_assets                          (Type 2, v1.2: total_assets)
             ├── capex_revenue.py   → capex + revenue                                  (Type 2)
             ├── current_ratio.py   → current_assets + current_liabilities            (Type 2, v1.2: current_assets)
             ├── graham_number.py   → earnings + pl + shares                           (Type 2)
             ├── effective_tax_rate.py → tax + ebt                                     (Type 2, v2.0)
             ├── ev_sales.py        → price + shares + debt + cash + revenue           (Type 2, 5 engines, v1.3)
             ├── ev_fcf.py          → price + shares + debt + cash + operating_cf + investing_cf (Type 2, 6 engines, v1.3)
             ├── cash_ratio.py      → cash + current_liabilities                       (Type 2, v1.3)
             ├── ocf_margin.py      → operating_cf + revenue                           (Type 2, v1.3)
             ├── fcf_margin.py      → operating_cf + investing_cf + revenue            (Type 2, 3 engines, v1.3)
             ├── working_capital.py → current_assets + current_liabilities             (Type 2, BRL value, v1.3)
             ├── cash_flow_to_debt.py → operating_cf + debt                            (Type 2, v1.3)
             ├── retention_ratio.py → dividends + earnings                             (Type 2, v1.3)
             ├── sustainable_growth.py → roe + retention_ratio                         (Type 2, composes metrics, v1.3)
             ├── quick_ratio.py     → cash + receivables + current_liabilities         (Type 2, v1.3)
             ├── interest_coverage.py → ebit + financial_result                        (Type 2, v1.3 approximation)
             ├── inventory_turnover.py → cogs + inventory                              (Type 2, v1.3)
             ├── receivables_turnover.py → revenue + receivables                       (Type 2, v1.3)
             └── fixed_asset_turnover.py → revenue + ppe                               (Type 2, v1.3)

       (engines never point upward — they're leaves)
```

**Acyclic. Always points downward.** If you find yourself wanting an engine to import a metric, or a metric to import another metric, stop — you're creating coupling. Refactor instead.

**Exception (v1.9 — ROIC + cash):** ROIC imports the `cash` engine *lazily inside a function body* with `try/except Exception:` so tests that don't mock `cash_at` still pass. This is the ONLY metric→engine lazy import; all other metrics import their engines at module top. The pattern is reserved for metrics that ADD an engine to an existing composition (like ROIC adding cash in v1.9). Document it clearly in the metric's docstring.

---

## 📐 Auto-Discovery Rules

1. **`_registry.py` (top level)** — the CENTRAL auto-discovery module (this is rule #1). Globs `engines/*.py` AND `metrics/*.py` (excluding `__init__.py`). Imports each via `importlib.import_module()`. This triggers `register_engine()` and `register_metric()` calls. Idempotent (uses `_done` flag). Also holds `list_engines(category=...)`, `list_metrics()`, `list_all_metric_names()`, `list_engine_categories()`, `list_metric_categories()`, `list_metrics_by_category(category)`, `resolve_metric()`, and `compute_all_ratios(company, date, categories=None, exclude=None)` (v1.5 — single entry point for consumer skills).
2. **`engines/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory). Auto-discovery is in the central `_registry.py`.
3. **`metrics/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory). Auto-discovery is in the central `_registry.py`.
4. **Adding an engine = 1 file in `engines/` + `register_engine()`.** It's immediately available for metrics to import. No edits to `_registry.py`, `engines/__init__.py`, or consumer skills.
5. **Adding a metric = 1 file in `metrics/` + `register_metric()`.** The calculations library itself needs no other edits. Consumer skills (historical, future valuation/financials/backtest) auto-generate their per-skill integration from the registry — see each consumer skill's ARCHITECTURE.md for what auto-generates there.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.9 — ROIC tests broke when cash_at wasn't mocked
> - **What happened:** ROIC was updated in v1.9 to subtract cash from invested capital (`IC = PL + Debt - Cash`). This added `cash_at` to ROIC's composition (now 5 engines). Existing ROIC tests from v1.8 only mocked `ebit + tax + pl + debt` — they didn't mock `cash_at`. The new ROIC code called `cash_at(company, date)` which tried to hit the real DFP/ITR DB and either crashed or returned wrong values.
> - **Why it matters:** Adding an engine to an existing metric's composition breaks every test that doesn't mock the new engine. Without protection, you'd have to update every test the moment you touch the metric.
> - **Fix:** Wrap the `cash_at` call in `try/except Exception:` and fall back to `PL + Debt` (v1.8 behavior) when cash is unavailable. This makes ROIC robust when cash data is missing OR not mocked. BUT: tests that exercise the v1.9 cash-subtraction path MUST mock all 5 engines — otherwise they're silently testing the fallback. Documented in INSTRUCTIONS rules #12 (NEVER) + #7 (ALWAYS).

### v1.7 — Fundamental ratios needed None per-share fields
> - **What happened:** When ROE was added (the first fundamental ratio), the existing `MetricSpec` required `per_share_label`, `per_share_key`, `per_share_fn` as positional fields. ROE has no per-share value — it's just `earnings/PL`. Forcing ROE to set dummy per-share values would have broken the chart adapter (dual-axis with a non-existent per-share) and summary adapter (per-share KPI/row with no value).
> - **Why it matters:** The MetricSpec shape has to support BOTH metric types cleanly, not just the original per-share+ratio type.
> - **Fix:** Made `per_share_label`, `per_share_key`, `per_share_fn` optional (`None` default). The chart adapter + summary adapter inspect `per_share_label`: if `None`, single-dataset chart + skip per-share KPI/row. ROE, ROA, ROIC, all margins, leverage, turnover, liquidity ratios all use this pattern.

### v1.4.1 — Manual inventory in __init__.py defeated auto-discovery
> - **What happened:** A contributor added a new engine but also edited `engines/__init__.py` to add the engine to a manual inventory docstring list. Later, when the engine was renamed, the docstring list went stale while the registry stayed correct — contributors got confused about which was the source of truth.
> - **Why it matters:** Two sources of truth (manual inventory + registry) drift over time. The registry auto-discovers everything; the manual list is redundant and error-prone.
> - **Fix:** Removed the manual inventory from `engines/__init__.py` and `metrics/__init__.py`. Both files are now minimal docstrings pointing to the registry: `list_engines()` / `list_metrics()` are the source of truth. Documented in INSTRUCTIONS rules #8 + #9 (NEVER).

### v1.3 — Registry scattered across subfolders
> - **What happened:** In v1.2, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.
> - **Why it matters:** The pattern wasn't consistent. `list_engines()` didn't exist, so the backtest skill couldn't discover engines programmatically. Adding an engine required editing metrics that needed it, with no central inventory.
> - **Fix:** Moved `_registry.py` to the skill top level (`skills/cvm/calculations/_registry.py` in v1.3; `skills/cvm/calculations/_registry.py` in v1.0 of the calculations library). It now handles BOTH engines and metrics auto-discovery. New `EngineSpec` dataclass + `register_engine()`. Both layers self-register. `list_engines()` enables backtest discovery. `engines/__init__.py` and `metrics/__init__.py` simplified to minimal docstrings.

### v1.2 — Frozen MetricSpec broke tests
> - **What happened:** `MetricSpec` was `@dataclass(frozen=True)`. Tests tried to `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)` to mock the history function. Frozen dataclasses raise `FrozenInstanceError` on setattr.
> - **Why it matters:** Consumer skills call `spec.history_fn` (captured at registration time). If we can't patch the spec, we can't mock the history function in tests. Patching the module function (`metrics.lpa.lpa_history`) doesn't work because the spec already holds a reference to the original.
> - **Fix:** Changed `MetricSpec` to `@dataclass` (not frozen). Tests now patch `METRICS["lpa"].history_fn` directly. Documented in INSTRUCTIONS rules #10 (NEVER) + #7 (ALWAYS).

### v1.2 — Engine/metric name confusion (from v1.1)
> - **What happened:** The original stub was named `metrics/pvpa.py`, but when implementing it, the instinct was to create `engines/vpa.py`. This mixes the layers — VPA is a ratio (metric), not a raw quantity. The raw quantity is PL (Patrimônio Líquido).
> - **Why it matters:** If engines and metrics share names, the dependency graph becomes ambiguous. Future contributors won't know whether `vpa` refers to the engine or the metric. The backtest skill reuses engines — it needs to import `pl_at()`, not `vpa_at()` (which is a ratio requiring price + shares too).
> - **Fix:** Engine produces PL → `engines/pl.py` with `pl_at()` / `pl_periods()`. Metric computes P/VPA → `metrics/vpa.py` with `vpa_at()` / `pvpa_at()` / `vpa_history()`. Clear separation. Documented the naming convention.

---

## 📐 Pattern Template Checklist (when copying to a new skill)

If you're creating a new skill that follows this pattern:

- [ ] **`_registry.py` (top level)** — `EngineSpec` (with `category`) + `MetricSpec` (with optional `per_share_*` AND `category` — v1.5) + `register_engine` + `register_metric` + auto-discovery (globs both `engines/` and `metrics/`) + `resolve_metric` + `list_engines(category=...)` + `list_metrics()` + `list_all_metric_names()` + `list_engine_categories()` + `list_metric_categories()` + `list_metrics_by_category(category)` + `compute_all_ratios(company, date, categories=None, exclude=None)` (v1.5) + aliases
- [ ] **`engines/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory list)
- [ ] **`engines/<quantity>.py`** — one per raw quantity, follows engine contract + `register_engine(EngineSpec(..., category="..."))` at module level. Categories are domain-specific (calculations uses `market`/`shares`/`dre`/`bpa`/`bpp`/`dfc`; your skill picks its own)
- [ ] **`metrics/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory list)
- [ ] **`metrics/<name>.py`** — one per metric, calls `register_metric(MetricSpec(..., category="..."))` at module level (v1.5: `category` is required — one of valuation, profitability, liquidity, leverage, efficiency, growth, per_share, tax, other). Use `per_share_*=None` for fundamental ratios. Include Portuguese + English aliases.
- [ ] **`<skill>.py`** — `_metric_history()` reads from registry, auto-generates `<metric>_history` functions. Handle BOTH Type 1 and Type 2 metrics via `spec.per_share_key` None-check.
- [ ] **`__init__.py`** (skill manifest) — MANIFEST modes auto-generate from registry
- [ ] **`adapters/<skill>.py`** — chart adapters auto-register from registry. Inspect `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
- [ ] **Tests** — mock the registry spec (not the module function): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Mock ALL engines a metric composes (or use `try/except` if the metric supports missing engines).
- [ ] **Docs** — document the central registry + engine/metric separation + auto-discovery + categories + metric types (Type 1 per-share+ratio, Type 2 fundamental). Include the dependency graph showing how metrics compose engines.

**Do NOT share `_registry.py` across skills.** Each skill has its own `_registry.py` at its own top level. The calculations library is shared by all CVM skills, but other skill areas (e.g., a future `skills/screener/` with its own extensibility needs) should copy the pattern, not import from calculations.

---

## 📐 Consumer Skill Pattern (financials v1.6 / valuation v1.4)

Consumer skills that surface calculations metrics — currently `skills/cvm/financials/` (v1.6) and `skills/cvm/valuation/` (v1.4) — follow a related but distinct modular pattern. They do **not** use the calculations library's `engines/ + metrics/` split (they're not extensible metric libraries — they expose a fixed set of modes per skill). Instead, each consumer skill is split as:

```text
skills/cvm/<skill>/
├── __init__.py       manifest + route() dispatch (auto-discovery via importlib on modes/*.py)
├── _registry.py      ModeSpec + register_mode + MODES dict (mirrors calculations' _registry.py shape,
│                     but for modes instead of engines/metrics)
├── modes/            one file per mode, auto-discovered
│   ├── __init__.py   minimal package marker
│   └── <mode>.py     @register_mode("mode", ...) def <mode>(...): ...
├── fetchers.py       internal data fetching from DBs / calculations engines
├── helpers.py        shared utilities (_safe_call, _safe_div, _safe_get, etc.)
├── report.py         dashboard/report section builders (composition logic for dashboard modes)
└── metrics.py        (financials only) ratio computation operating on raw statement dicts
```

**Same auto-discovery principle as calculations:** adding a new mode = drop a file in `modes/` + `@register_mode(...)`, no edits to `__init__.py` or `_registry.py`. The dispatcher's `route()` looks up `MODES[mode]` and dispatches via `spec.fn(**filtered)`.

**Differences from the calculations pattern:**
- `modes/` (one fn per file) instead of `engines/` + `metrics/` (two layers). Consumer skills have no engine/metric split — their modes are top-level user-facing entry points.
- `fetchers.py` + `helpers.py` + `report.py` are the consumer-skill equivalent of calculations' engine leaves — but they're flat modules, not a registry-extensible folder. New fetchers/helpers/sections are added by editing those files (not by dropping new files into a registry-scanned folder).
- `_registry.py` uses `ModeSpec` (with `name`, `description`, `fn`, `include_in_all`) instead of `EngineSpec`/`MetricSpec`. `include_in_all` controls whether the mode shows up in the manifest's default mode list.

When editing `skills/cvm/financials/` or `skills/cvm/valuation/`, follow this consumer-skill pattern. Do **not** introduce a new `<skill>.py` monolith or hardcode mode dispatch tables in `__init__.py` — the auto-discovery pattern is the source of truth.

---

*Last updated: 2026-07-29 (v1.5). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [API.md](API.md) for function signatures, [ROADMAP.md](ROADMAP.md) for deferred items, [CHANGELOG.md](CHANGELOG.md) for version history.*
