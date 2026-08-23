<- Back to [VALUATION Overview](../VALUATION.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

```text
skills/cvm/valuation/
├── __init__.py        manifest + route() dispatch (auto-discovery) + REQUIRED_SOURCES
├── _registry.py       ModeSpec + register_mode + MODES dict (delegates to skills._base)
├── modes/             one file per mode, auto-discovered via importlib
│   ├── __init__.py    minimal package marker
│   ├── ratios.py      @register_mode("ratios")      — include_in_all=True (default)
│   ├── summary.py     @register_mode("summary")     — include_in_all=False
│   ├── dashboard.py   @register_mode("dashboard")   — include_in_all=False (v2.0 6-tab)
│   └── historical_valuation.py  @register_mode("historical_valuation") — v1.8, 5Y daily history
├── fetchers.py        price fetching (_get_price / _get_price_brapi /
│                     _get_price_investsite / _get_latest_price — b3 trades.db fallback)
├── helpers.py         _safe_call, _safe_div (shared utilities)
└── report/            [v2.0] Split from monolithic report.py into package
    ├── __init__.py    thin re-exports all 13 public builders (backward compat)
    ├── _helpers.py    _safe_get, _fmt, _safe_div, _derive_*, all constants
    ├── overview.py    build_overview_kpis, build_overview_sections,
    │                  build_valuation_radar, build_valuation_heatmap
    ├── multiples.py   build_multiples_sections, build_per_share_sections
    ├── profitability.py  build_profitability_section, build_margin_trend_chart
    ├── liquidity.py   build_liquidity_leverage_sections
    ├── efficiency.py  build_efficiency_growth_sections
    ├── intrinsic.py   _dcf_at_growth, build_dcf_sensitivity_section
    └── history_charts.py  build_pl_lpa_pvp_vpa_history_chart, build_roe_trend_chart
```

**v2.0 report split:** The monolithic `report.py` (1859 lines) was split into a `report/` package (9 files). Each file contains builders for one dashboard tab/concern. The `__init__.py` re-exports all 13 public builders, so `from skills.cvm.valuation.report import build_overview_kpis` still works without changes. This pattern can be applied to financials/historical when they bump to 2.0.

**v1.10 changes:**
- `build_roe_trend_chart` signature changed from `(company, annual_periods)` to `(company)` — now uses `roe_history()`/`roa_history()`/`roic_history()` instead of annual_periods.
- New `build_pl_lpa_pvp_vpa_history_chart(company)` — merges `lpa_history()` + `vpa_history()` into a 4-dataset step-line chart.
- `_compute_roic_from_metrics` removed (dead code — `roic_history()` provides the data).
- `_derive_multiples` no longer returns None for `p_ativos`/`p_passivos`/`p_rb` (they come from the registry now).
- `_MULTIPLES_LESS_COMMON` keys fixed: `p_ativos`→`apa`, `p_passivos`→`ppa`, `p_rb`→`rbpa` (the actual registered metric names).
- Graham Number overlay removed from `dashboard.py` — price chart uses default shared `build_price_chart()` output.

**v1.9 changes:**
- `build_dcf_sensitivity_section` added — 5 growth-rate scenarios (base ±2.5%, ±5%).
- `Valor Intrínseco` tab added (6th tab) — DCF, IRR, WACC, Margin of Safety, TIR-WACC spread.
- Subtabs added to all 4 main tabs (Múltiplos, Rentabilidade, Liquidez, Eficiência).
- `engine_cache_scope()` wraps the ENTIRE dashboard (ratios fetch + section building + DCF sensitivity share one cache).

**v1.8 changes:**
- `modes/historical_valuation.py` added — 5Y daily history for 9 metrics.
- Company header + price chart reuses `build_company_header` + `build_price_chart` from `_shared_report`.
- Sidebar groups (3 groups: Resumo, Fundamentos, Crescimento).
- Per-share tab merged into Multiples.
- Tooltips on all ratio_grid items via `get_tooltip` from `_shared_report`.

**v1.7 changes:**
- `REQUIRED_SOURCES = ["dfp", "itr", "fca", "cotahist", "brapi", "bridge"]` declared in `__init__.py`.
- `make_route(required_sources=REQUIRED_SOURCES)` wires the sync guard — `ensure_fresh()` runs before each dispatch.

**v1.5 reorg (2026-07-29):** `dashboard.py` + `report.py` rewritten to produce 6 tabs (was 5). Each tab builder is independently try/except-wrapped via the `_safe_build()` helper in `dashboard.py` so a failure in one tab degrades to an error section in that tab, not a crash of the whole dashboard. `ratios()` is called ONCE in `dashboard()` and the resulting dict is passed to every tab builder.

**v1.4 split (2026-07-29):** the 528-line `valuation.py` was split into the structure above + a new `dashboard` mode was added. `__init__.py` auto-discovers modes by globbing `modes/*.py` (sorted) + `importlib.import_module()` — same pattern as `skills/cvm/financials/`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`, no edits to `__init__.py` or `_registry.py`.

| External File | Purpose |
|------|---------|
| `core/br_validator.py` | `validate_ticker()`, `parse_escala()` — shared parsing |
| `skills/_base/` | Phase 3 C2 package (was `skills/_base.py`) — `make_registry` + `auto_discover_modes` (`registry.py`), `make_route` (`route.py`), `@engine_cached` + `engine_cache_scope` (`engine_cache.py`), `ensure_fresh` + sync guard (`sync_guard.py`), `_auto_generate_html` (`html_gen.py`). Shared skill infrastructure. |
| `skills/cvm/_shared_report/` | `build_company_header`, `build_price_chart`, `get_tooltip` — shared dashboard builders |
| `skills/cvm/calculations/` | 60 metrics via `compute_all_ratios()` + `*_history()` functions + engines |

## Data Flow

```
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
  │
  ▼  1. route() wrapper calls ensure_fresh() [v1.7]
  │     → checks DFP/ITR/FCA/COTAHIST/bridge freshness
  │     → force-syncs if any source >24h stale
  │
  ▼  2. validate_ticker("PETR4") → "PETR4"  [core/br_validator]
  │
  ▼  3. _get_price("PETR4")  [fetchers.py]
  │     → brapi → investsite → b3 trades.db fallback chain
  │     → returns {last_price, date, source, market_cap, pe_ratio, p_vpa}
  │
  ▼  4. Parallel calculations engine calls [v1.22 parallel fetch]
  │     → ThreadPoolExecutor(max_workers=5) runs 11 engines concurrently:
  │       ttm_earnings_at, revenue_at, ebit_at, pl_at, debt_at, cash_at,
  │       da_at, operating_cf_at, investing_cf_at, shares_at, dividends_at
  │     → each wrapped in _safe_call (FileNotFoundError → None)
  │     → @engine_cached decorator caches results per (company, date)
  │
  ▼  5. Compute manual ratios (NOT in calculations registry)
  │     → Market Cap = price × shares (or brapi_market_cap)
  │     → EPS = lucro_liquido / shares → P/L = market_cap / lucro_liquido
  │     → VPA = PL / shares → P/VPA = market_cap / PL
  │     → EV = Market Cap + divida_bruta - caixa
  │     → P/EBIT = market_cap / ebit
  │     → P/FCO = market_cap / fco
  │     → PSR = market_cap / receita_liquida
  │     → Dividend Yield = dpa / price
  │
  ▼  6. compute_all_ratios(ticker, today) [v1.5]
  │     → walks METRICS registry (60 metrics auto-discovered)
  │     → returns {metric_name: value_or_None} for ALL 60 metrics
  │     → OVERRIDES some manual keys (ev_ebitda, p_ebit, etc.) — registry wins
  │     → manual keys with NO registry counterpart preserved (p_l, p_vpa, ev, psr, etc.)
  │
  ▼  7. Restore per-share values + PT aliases [v1.5]
  │     → ratios_result["vpa"] = vpa  (per-share, not P/VPA ratio)
  │     → ratios_result["dpa"] = dpa  (per-share, not Div Yield ratio)
  │     → Portuguese aliases: margem_bruta, divida_pl, etc.
  │
  ▼  8. add_freshness(result)  [v1.0.14]
  │     → adds data_freshness dict with last-sync timestamps
  │
  ▼  9. Return result
       → {"status":"ok", "ticker":..., "ratios":{...}, "sources":{...}, "data_freshness":{...}}
```

## Ratio Formulas

| Ratio | Formula | Source |
|-------|---------|--------|
| Market Cap | price × total_shares | b3 trades + fre shares |
| EPS (LPA) | lucro_liquido / total_shares | DFP 3.11 (TTM) |
| P/L (P/E) | market_cap / lucro_liquido | Market-cap-based (v1.0.9) |
| VPA | patrimonio_liquido / total_shares | DFP 2.03 |
| P/VPA (P/B) | market_cap / patrimonio_liquido | Market-cap-based |
| EV | market_cap + divida_bruta - caixa | Market Cap + DFP 2.01.04 + 2.02.01 + 1.01.01 |
| P/EBIT | market_cap / ebit | b3 trades + DFP 3.05 |
| P/FCO | market_cap / fco | b3 trades + DFP 6.01 |
| P/Ativo (APA) | price / (total_assets / shares) | calculations registry (apa metric) |
| P/Passivo (PPA) | price / ((total_assets - pl) / shares) | calculations registry (ppa metric) |
| P/RB (RBPA) | price / (gross_profit / shares) | calculations registry (rbpa metric) |
| Dividend Yield | dpa / price | dividends engine (TTM) |
| ROE | lucro_liquido / patrimonio_liquido | calculations registry |
| ROIC | NOPAT / Invested Capital | calculations registry (actual tax rate) |
| Graham Number | sqrt(22.5 × EPS × VPA) | calculations registry |
| DCF Intrinsic Value | Σ FCF/(1+WACC)^t + TV | calculations registry (v1.9) |
| IRR (TIR) | rate where NPV(price) = 0 | calculations registry (v1.9) |
| WACC | COE × E/(D+E) + Kd×(1-tax) × D/(D+E) | calculations registry (v1.9) |

## Data Source Requirements

| Source | What | Required for |
|--------|------|-------------|
| brapi / investsite / b3 trades.db | Latest price + market_cap | All market-cap-based ratios |
| cvm/dfp dfp.db | Annual financials (meses=12) | EPS, VPA, EV, P/EBIT, P/FCO |
| cvm/itr itr.db | Quarterly financials (TTM computation) | TTM earnings, revenue, EBIT, etc. |
| cvm/fre fre.db | Shares outstanding (distribuicao_capital) | Market Cap, EPS, VPA, per-share ratios |
| cvm/fca fca.db | Company info (header) | Company name, CNPJ, sector |
| cvm/bridge bridge.db | ticker → CNPJ | FRE lookup (shares) |
| b3/cotahist | Daily prices | Price history chart, beta, price_at engine |
| bcb/sgs | Selic, CDI, IPCA | COE (CAPM), WACC, DCF terminal growth |

If any source is missing, the affected ratios return `None` with a note.

## Uses core/br_validator

This skill uses `validate_ticker()` and `parse_escala()` from `core/br_validator.py`.
**All financial skills MUST use br_validator** for consistent BRL/date/ticker handling.

---

*Last updated: 2026-08-12 (v2.0 — Graham overlay removed, P/L-LPA history chart, ROE trend rewrite, Menos Comuns fix, doc cleanup). See [CHANGELOG.md](CHANGELOG.md) for version history.*
