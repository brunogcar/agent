<- Back to [VALUATION Overview](../VALUATION.md)

# 📝 API Reference

## 🔧 Skill Signature

```
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
```

| Param | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | `str` | **Yes** | Always `"cvm"` |
| `sub_domain` | `str` | **Yes** | Always `"valuation"` |
| `mode` | `str` | **Yes** | `ratios`, `summary`, `dashboard`, or `historical_valuation` |
| `params` | `str` (JSON) | **Yes** | JSON string: `{"company":"PETR4"}` |

---

## ⚡ Modes

### `mode="ratios"` (default)

Compute all valuation ratios from b3 price + CVM TTM financials + FRE shares.

**Manual ratios** (NOT in calculations registry):
- **P/L** = market_cap / lucro_liquido. Market-cap-based (v1.0.9) — correct for both regular and UNIT tickers.
- **P/VPA** = market_cap / patrimonio_liquido. None when PL ≤ 0.
- **EV** = market_cap + divida_bruta - caixa.
- **PSR** = market_cap / receita_liquida.
- **P/EBIT** = market_cap / ebit.
- **P/FCO** = market_cap / fco.
- **P/FCF** = market_cap / fcf (where fcf = fco + fci).
- **Dividend Yield** = dpa / price (dpa from dividends engine, TTM).
- **Market Cap** = brapi_market_cap (authoritative for units) → price × shares fallback.

**Calculations-backed ratios** (60 metrics via `compute_all_ratios()`):
ROE, ROA, ROIC, Graham Number, margins (gross/operating/net/EBITDA/OCF/FCF), liquidity (current/quick/cash/working_capital), leverage (debt_equity/net_debt_ebitda/interest_coverage/cash_flow_to_debt), efficiency (asset/inventory/receivables/fixed_asset turnover, capex_revenue), growth (retention_ratio/sustainable_growth/revenue_growth_3m/1y/5y/net_income_growth_3m/1y/5y/gross_profit_growth_3m/1y/5y), EV multiples (ev_ebitda/ev_ebit/ev_fcf/ev_sales), per-share (lpa/vpa/dpa/rps/apa/ppa/rbpa/cgpa/dbpa), price ratios (p_ebit/p_ebitda/p_ev/p_fcf/p_fco/p_l/p_vpa/psr/price_to_tangible_book), tax (effective_tax_rate), valuation (graham_number/magic_number/altman_z/dupont), market risk (coe/beta), DCF (dcf_intrinsic_value/dcf_margin_of_safety/irr/wacc).

**Data freshness** — `data_freshness` field shows last-sync timestamp for each database.

Returns:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "ratios": {
    "price": 40.87,
    "price_date": "2026-08-09",
    "unit_ticker": false,
    "market_cap": 531310000000.0,
    "market_cap_source": "brapi",
    "p_l": 4.17,
    "p_vpa": 1.43,
    "ev": 570500000000.0,
    "ev_ebitda": 6.71,
    "psr": 1.79,
    "dividend_yield": 0.0481,
    "roe": 0.28,
    "roic": 0.18,
    "graham_number": 75.0,
    "eps": 9.23,
    "vpa": 26.92,
    "dpa": 1.85,
    "apa": 32.40,
    "ppa": 8.60,
    "rbpa": 18.50,
    "...": "..."
  },
  "sources": {
    "price": {"status": "ok", "source": "brapi"},
    "financials": {"status": "ok", "source": "calculations_engines", "period": "ttm"},
    "shares": {"status": "ok", "source": "calculations_engine"}
  },
  "data_freshness": {
    "dfp": "2026-08-09T14:26:04",
    "itr": "2026-08-09T14:39:21",
    "fre": "2026-08-09T14:41:08",
    "cotahist": "2026-08-09"
  }
}
```

### `mode="summary"`

Ratios + data source availability. Calls `ratios()` internally + adds a
`data_availability` block.

**Note (v1.3+):** The `headline_v13_metrics` block was REMOVED in v1.3 —
all metrics are now in `ratios()` directly via `compute_all_ratios()`, so a
separate headline block was redundant.

Returns:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "ratios": { "...": "..." },
  "sources": { "...": "..." },
  "data_availability": {
    "price": "ok",
    "price_source": "brapi",
    "dfp_ttm": "ok",
    "fre_shares": "ok"
  }
}
```

### `mode="dashboard"` (v1.10 — 6-tab multi-tab dashboard)

Multi-tab valuation dashboard optimized for the report tool's `dashboard`
action. Calls `ratios()` ONCE and passes the resulting dict to every tab
builder. Each tab builder is independently try/except-wrapped via
`_safe_build()` so a failure in one tab degrades to an error section, not
a crash. The entire dashboard body is wrapped in `engine_cache_scope()` so
DCF sensitivity + history charts reuse cached engines.

**Returns:** `{"status": "ok", "company": ..., "tabs": [...], "kpis": [...]}`
where `kpis` is a 6-card top-level list (P/L, P/VPA, EV/EBITDA, Div Yield,
Market Cap, ROE) rendered above all tabs by the dashboard template.

**6 tabs (v1.10) in 3 sidebar groups:**

| # | Tab | Group | Sections |
|---|-----|-------|----------|
| 1 | **Overview** | Resumo | Company header (FCA/CAD/COTAHIST) + historical price chart (Tudo/5A/1A/1M) + 3 metric tables (Mercado, Resultado TTM, Balanço) + Valor Intrínseco summary |
| 2 | **Múltiplos** | Resumo | Subtabs: Preço (7 price multiples table + bar chart + per-share table + P/L-LPA-P/VP-VPA 5Y history chart [v1.10]), EV (5 EV multiples table + bar chart), Menos Comuns (P/Ativos, P/Passivos, P/RB, P/CG, P/DB, P/Tangible Book table — all with values + tooltips [v1.10 fix]) |
| 3 | **Valor Intrínseco** | Resumo | DCF Intrinsic Value + Margin of Safety + TIR (IRR) + WACC + TIR-WACC spread table + DCF Sensitivity Analysis (5 scenarios table + bar chart) [v1.9] |
| 4 | **Rentabilidade** | Fundamentos | Subtabs: Retornos (ratio_grid + ROIC/ROE/ROA 5Y step-line history chart [v1.10 rewrite]), Margens (ratio_grid + bar chart) |
| 5 | **Liquidez e Alavancagem** | Fundamentos | Subtabs: Liquidez (ratio_grid + bar chart), Endividamento (ratio_grid + detailed table) |
| 6 | **Eficiência e Crescimento** | Crescimento | Subtabs: Eficiência (efficiency table + growth tables for Receita/Luco Bruto/Luco Líquido with charts), Crescimento (growth tables) |

**Section types used** (all supported by the dashboard template):
- `{"type": "table", ...}` — for tabular metrics
- `{"type": "ratio_grid", "categories": [...]}` — for categorized metric cards
- `{"type": "chart", "chart_data": {...}}` — Chart.js line/bar chart
- `{"type": "subtabs", "tabs": [{name, sections}]}` — nested sub-tabs within a tab
- `{"type": "company_info", "company_header": {...}}` — company header card
- `{"type": "text", "text": ...}` — for error sections

**v1.10 chart details:**
- **P/L, LPA, P/VP, VPA 5Y history chart** — step-line chart in Múltiplos > Preço. Merges `lpa_history()` + `vpa_history()`. LPA/VPA step quarterly (stepped:'after'), P/L and P/VP vary daily. Colors: P/L dark blue, LPA light blue, P/VP red, VPA pink.
- **ROIC/ROE/ROA 5Y history chart** — step-line chart in Rentabilidade > Retornos. Uses `roe_history()`/`roa_history()`/`roic_history()` (quarterly step data, ~20 points over 5Y). Colors: ROIC dark green, ROE olive, ROA bright green. Forward-filled to carry forward last known value.
- **Graham Number overlay REMOVED** — the Overview price chart now uses the default shared `build_price_chart()` output unmodified.

**Example:**

```
skill(domain="cvm", sub_domain="valuation", mode="dashboard",
      params='{"company":"PETR4"}')
```

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "company_header": {"name": "Petrobras", "...": "..."},
  "kpis": [
    {"label": "P/L",            "value": "4,17"},
    {"label": "P/VPA",          "value": "1,43"},
    {"label": "EV/EBITDA",      "value": "6,71"},
    {"label": "Dividend Yield", "value": "4,81%"},
    {"label": "Market Cap",     "value": "R$ 531,31 B"},
    {"label": "ROE",            "value": "28,00%"}
  ],
  "tabs": [
    {"name": "Overview",                "group": "Resumo",      "sections": [...]},
    {"name": "Múltiplos",               "group": "Resumo",      "sections": [...]},
    {"name": "Valor Intrínseco",        "group": "Resumo",      "sections": [...]},
    {"name": "Rentabilidade",           "group": "Fundamentos", "sections": [...]},
    {"name": "Liquidez e Alavancagem",  "group": "Fundamentos", "sections": [...]},
    {"name": "Eficiência e Crescimento","group": "Crescimento", "sections": [...]}
  ],
  "freshness_footer": "DFP: 2026-08-09 (até 2025-12-31) • ITR: 2026-08-09 (até 2026-03-31) • ..."
}
```

### `mode="historical_valuation"` (v1.8)

Historical valuation multiples time series (5Y default). Fetches daily
history for 9 metrics via the calculations registry's `*_history()`
functions: EV/EBITDA, EV/EBIT, EV/Sales, P/EBIT, P/EBITDA, Earnings Yield,
Graham Number, ROE, ROIC.

**Params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `company` | `str` | (required) | B3 ticker |
| `years` | `int` | `5` | Number of years of history |

**Returns:** `{"status": "ok", "company": ..., "metrics": [...], "series": [...]}`
where `metrics` is a list of `{"label", "key"}` for charting and `series`
is a list of `{"date", "<metric_key>": value, ...}` sorted oldest-first.

**Example:**

```
skill(domain="cvm", sub_domain="valuation", mode="historical_valuation",
      params='{"company":"PETR4", "years": 5}')
```

---

## 🔢 Metric Formulas

| Metric | Formula | Notes |
|--------|---------|-------|
| P/L | market_cap / lucro_liquido | Market-cap-based (v1.0.9). Correct for UNIT tickers. |
| P/VPA | market_cap / patrimonio_liquido | None when PL ≤ 0 |
| EV | market_cap + divida_bruta - caixa | |
| EV/EBITDA | ev / ebitda | From calculations registry |
| PSR | market_cap / receita_liquida | |
| ROIC | NOPAT / Invested Capital | Uses actual tax rate (not flat 34%) |
| Graham Number | sqrt(22.5 × eps × vpa) | Only when EPS > 0 and VPA > 0 |
| Dividend Yield | dpa / price | dpa from dividends engine (TTM) |
| P/Ativo (APA) | price / (total_assets / shares) | From calculations registry (v1.10) |
| P/Passivo (PPA) | price / ((total_assets - pl) / shares) | From calculations registry (v1.10) |
| P/RB (RBPA) | price / (gross_profit / shares) | From calculations registry (v1.10) |
| DCF Intrinsic Value | Σ FCF/(1+WACC)^t + TV | v1.9 |
| IRR (TIR) | rate where NPV(price) = 0 | v1.9 |
| WACC | COE × E/(D+E) + Kd×(1-tax) × D/(D+E) | v1.9 |

---

## 🔌 Report Adapters

| Adapter | What it tables |
|---------|----------------|
| `valuation_ratios` | KPI strip (Preço, P/L, P/VPA, EV/EBITDA, ROIC, Graham, Div Yield, Market Cap) + full indicator table |
| `valuation_summary` | Ratios table + data-source availability table |
| `valuation_dashboard` | Multi-tab dashboard (6 tabs, 3 sidebar groups) — used by `mode="dashboard"` |

---

*Last updated: 2026-08-12 (v2.0).*
