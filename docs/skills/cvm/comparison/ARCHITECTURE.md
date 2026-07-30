<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `skills/cvm/comparison/__init__.py` | MANIFEST + route() — 4 modes (auto-discovery via importlib on `modes/*.py`) |
| `skills/cvm/comparison/_registry.py` | `MODES` dict + `@register_mode` decorator + `build_manifest_modes()` |
| `skills/cvm/comparison/modes/side_by_side.py` | `side_by_side()` — 3 sections (valuation, financials, dividends), tickers as rows. [v1.3] `_VALUATION_COLS` extended with 5 calculations-sourced metrics (roe, roa, margem_liquida, divida_pl, liquidez_corrente) returned by valuation.ratios(). [v1.4] `_VALUATION_COLS` further extended with 15 v1.4 calculations-sourced metrics (ev_sales, ev_fcf, cash_ratio, quick_ratio, ocf_margin, fcf_margin, working_capital, cash_flow_to_debt, retention_ratio, sustainable_growth, interest_coverage, inventory_turnover, receivables_turnover, fixed_asset_turnover, price_to_tangible_book) — comparison surfaces them transitively via valuation.ratios(). |
| `skills/cvm/comparison/modes/summary.py` | `summary()` — single quick-compare table (10 KPIs) |
| `skills/cvm/comparison/modes/growth.py` | `growth()` — QoQ + YoY % change + TTM ratios |
| `skills/cvm/comparison/modes/dashboard.py` | `dashboard()` — 5-tab dashboard (Overview/Valuation/Financials/Dividends/Growth) (v1.5) |
| `skills/cvm/comparison/fetchers.py` | `_fetch_all()` — calls financials + valuation + dividends per ticker (best-effort) |
| `skills/cvm/comparison/helpers.py` | Column-set constants (`_VALUATION_COLS`, `_FINANCIALS_COLS`, `_DIVIDENDS_COLS`, `_SUMMARY_COLS`) + `_build_section()` + `_pct_change()` |
| `skills/cvm/comparison/report.py` | Report wiring helpers for the comparison skill |
| `tools/report_ops/adapters/comparison.py` | 3 report adapters: comparison_side_by_side, comparison_summary, comparison_growth |
| `tools/report_ops/adapters/comparison_dashboard.py` | 1 report adapter: comparison_dashboard (v1.5 — 5-tab dashboard adapter) |
| `tests/skills/cvm/comparison/conftest.py` | Shared fixtures — synthetic VAL_* / FIN_* / DIV_* data + `mock_skills` + `petr_vale_env` helpers |
| `tests/skills/cvm/comparison/test_validation.py` | TestValidation (5 tests) — input validation across all modes |
| `tests/skills/cvm/comparison/test_side_by_side.py` | TestSideBySide (8 tests) + TestExtractDividendMetrics (3 tests) |
| `tests/skills/cvm/comparison/test_summary.py` | TestSummary (2 tests) |
| `tests/skills/cvm/comparison/test_growth.py` | TestGrowthMode (6 tests) + TestPctChange (9 tests) |
| `tests/skills/cvm/comparison/test_dashboard.py` | TestDashboard (14 tests) — dashboard mode 5-tab composition (v1.5) |
| `tests/skills/cvm/comparison/test_route.py` | TestRoute (9 tests) |
| `tests/tools/report/test_report_adapters.py` | Adapter tests (TestComparisonAdapters + TestComparisonGrowthAdapter + TestComparisonDashboardAdapter classes) |

### Test module tree

```
tests/skills/cvm/comparison/
├── conftest.py            # mock_skills, petr_vale_env, VAL_*, FIN_*, DIV_* fixtures
├── test_validation.py     # 5 tests — TestValidation
├── test_side_by_side.py   # 11 tests — TestSideBySide (8) + TestExtractDividendMetrics (3)
├── test_summary.py        # 2 tests  — TestSummary
├── test_growth.py         # 15 tests — TestGrowthMode (6) + TestPctChange (9)
├── test_dashboard.py      # 14 tests — TestDashboard  (v1.5)
└── test_route.py          # 9 tests  — TestRoute
                          # 56 tests total
```

[v1.5] Migrated from a single-file `comparison.py` (518 lines) to the standard
modular `modes/ + _registry.py` pattern (mirroring `financials` v1.6 +
`valuation` v1.4 + `calculations`). Adding a new mode = drop a file in `modes/`
+ `@register_mode(...)`; no edits to `__init__.py`.

---

## 🔀 Data Flow

```mermaid
graph TD
    A["skill(domain='cvm', sub_domain='comparison', mode='side_by_side', params='{\"tickers\":[\"SUZB3\",\"KLBN11\"]}')"]
    A --> B["comparison.side_by_side(tickers)"]
    B --> C["_fetch_all(tickers)"]
    C --> D1["valuation.ratios(SUZB3)"]
    C --> D2["financials.summary(SUZB3)"]
    C --> D3["dividends.summary(SUZB3)"]
    C --> E1["valuation.ratios(KLBN11)"]
    C --> E2["financials.summary(KLBN11)"]
    C --> E3["dividends.summary(KLBN11)"]
    D1 & D2 & D3 & E1 & E2 & E3 --> F["per_ticker list (best-effort)"]
    F --> G["_build_section(Valuation, cols, per_ticker)"]
    F --> H["_build_section(Financials, cols, per_ticker)"]
    F --> I["_build_section(Dividends, cols, per_ticker)"]
    G & H & I --> J["{status, tickers, sections: {valuation, financials, dividends}, errors}"]
    D1 -.->|v1.3| K["valuation.ratios() now calls calculations engines/metrics → returns roe, roa, margem_liquida, divida_pl, liquidez_corrente, roic, graham_number, p_ebit, p_fco, p_fcf"]
    K -.->|transitive| G
```

[v1.3] The dashed edge marks the transitive calculations integration. Comparison does NOT import calculations directly — it just consumes the enriched `ratios` dict that `valuation.ratios()` returns after Phase 2B.

---

## 💡 Key Design Decisions

- **Orchestration only** — comparison imports and calls the 3 existing skills. No database, no sync, no duplicate SQL. If financials/valuation/dividends change, comparison picks up the changes automatically.
- **Best-effort per ticker** — `_fetch_all()` wraps each skill call in try/except. A ticker failing one source gets `None` cells in that section but still appears in the others. The `errors` list collects what failed so the caller knows data is partial. The comparison never raises on a per-ticker failure.
- **Tickers as rows, metrics as columns** — each section is unit-homogeneous (all valuation ratios are multiples/fractions, all financials are BRL/%, all dividends are BRL/fractions). This lets the table builder use per-**column** format specs (the existing mechanism) — no per-row format concept needed.
- **Column sets are module-level constants** (`_VALUATION_COLS`, `_FINANCIALS_COLS`, `_DIVIDENDS_COLS`, `_SUMMARY_COLS`) — each entry is `(label, dict_key, spec)`. Adding a column = one line in the list. The `_build_section()` helper is generic over any column list.
- **Summary mode merges dicts** — `summary()` merges each ticker's valuation + financials + dividends dicts into one row, then builds a single section from `_SUMMARY_COLS`. This is why `dict_key`s must not collide across the 3 sources (e.g. `dividend_yield` comes from valuation, not dividends).
- **[v1.3] Transitive calculations integration** — comparison does NOT import calculations directly. It consumes the enriched `ratios` dict that `valuation.ratios()` returns (which since Phase 2B calls the calculations engines + metrics internally). This keeps the orchestration boundary clean: comparison talks to valuation, valuation talks to calculations. If a metric is needed that valuation doesn't expose, the right fix is to extend valuation.ratios() to expose it — not to have comparison call calculations directly. See `Deferred / Out of Scope` in CHANGELOG.md.

### Calculations Integration (v1.3)

The valuation section's new columns come from calculations engines/metrics via `valuation.ratios()`:

| Column label | `ratios` key | Calculations source | Notes |
|--------------|--------------|---------------------|-------|
| ROE (val) | `roe` | `metrics.roe.roe_at` | TTM earnings / equity snapshot. Distinct from the financials section's `ROE` (which uses `compute_ratios` on the annual statement dict). |
| ROA (val) | `roa` | `metrics.roa.roa_at` | TTM earnings / total assets. |
| Marg. Líq. (val) | `margem_liquida` | `metrics.net_margin.net_margin_at` | TTM net income / TTM revenue. Distinct from financials' `Marg. Líquida` (annual). |
| Dívida/PL | `divida_pl` | `metrics.debt_equity.debt_equity_at` | Gross debt / equity (point-in-time snapshot). |
| Liquidez Corrente | `liquidez_corrente` | `metrics.current_ratio.current_ratio_at` | Current assets / current liabilities. |

Both the valuation column (calculations TTM snapshot) and the financials column (annual statement value) are kept deliberately — they cross-check each other. A material gap between the two signals a recent equity raise, debt payoff, or earnings surprise.

---

## 📊 Column Definitions

### Valuation (from `valuation.ratios`)
| Column | dict_key | spec |
|--------|----------|------|
| Preço | `price` | brl_full |
| Market Cap | `market_cap` | brl |
| EV | `ev` | brl |
| P/L | `p_l` | num |
| P/VPA | `p_vpa` | num |
| P/EBIT | `p_ebit` | num |
| EV/EBITDA | `ev_ebitda` | num |
| PSR | `psr` | num |
| Div Yield | `dividend_yield` | pct |
| DPA | `dpa` | brl_full |
| EPS | `eps` | brl_full |
| VPA | `vpa` | brl_full |
| Total Ações | `total_shares` | int |
| ROE (val) | `roe` | pct |
| ROA (val) | `roa` | pct |
| Marg. Líq. (val) | `margem_liquida` | pct |
| Dívida/PL | `divida_pl` | num |
| Liquidez Corrente | `liquidez_corrente` | num |
| EV/Sales | `ev_sales` | num |
| EV/FCF | `ev_fcf` | num |
| Cash Ratio | `cash_ratio` | num |
| Quick Ratio | `quick_ratio` | num |
| OCF Margin | `ocf_margin` | pct |
| FCF Margin | `fcf_margin` | pct |
| Working Capital | `working_capital` | brl |
| Cash Flow to Debt | `cash_flow_to_debt` | num |
| Retention Ratio | `retention_ratio` | pct |
| Sustainable Growth | `sustainable_growth` | pct |
| Interest Coverage | `interest_coverage` | num |
| Inventory Turnover | `inventory_turnover` | num |
| Receivables Turnover | `receivables_turnover` | num |
| Fixed Asset Turnover | `fixed_asset_turnover` | num |
| P/Tangible Book | `price_to_tangible_book` | num |

[v1.3] Rows 14-18 (ROE (val) through Liquidez Corrente) are sourced from calculations metrics via `valuation.ratios()`. The `(val)` suffix distinguishes them from the same-named columns in the financials section (which use the annual statement value, not the TTM calculations snapshot).

[v1.4] Rows 19-33 (EV/Sales through P/Tangible Book) are sourced from calculations metrics via `valuation.ratios()` (v1.4 wired them in via `_safe_call`). Comparison surfaces them transitively — no new data fetching. Format specs: `num` for multiples/turnover/coverage, `pct` for margins/growth/retention, `brl` for working capital.

### Financials (from `financials.summary` → `latest_annual`)
| Column | dict_key | spec |
|--------|----------|------|
| Receita Líquida | `receita_liquida` | brl |
| Lucro Bruto | `lucro_bruto` | brl |
| EBIT | `ebit` | brl |
| EBITDA | `ebitda` | brl |
| Lucro Líquido | `lucro_liquido` | brl |
| Ativo Total | `ativo_total` | brl |
| Patrimônio Líq. | `patrimonio_liquido` | brl |
| Caixa | `caixa` | brl |
| Dívida Bruta | `divida_bruta` | brl |
| FCO | `fco` | brl |
| Marg. Bruta | `marg_bruta` | pct |
| Marg. EBITDA | `marg_ebitda` | pct |
| Marg. Líquida | `marg_liquida` | pct |
| ROE | `roe` | pct |
| ROA | `roa` | pct |

### Dividends (from `dividends.summary`)
| Column | dict_key | spec |
|--------|----------|------|
| Eventos (B3) | `event_count` | int |
| DPA (B3 médio) | `b3_dpa_avg` | brl_full |
| Dividendos (últ ano) | `annual_dividendos` | brl |
| JCP (últ ano) | `annual_jcp` | brl |
| Total Remun. (últ a) | `annual_total` | brl |
| Payout | `payout` | pct |

---

*Last updated: 2026-07-29 (v1.5).*
