<- Back to [COMPARISON Overview](../COMPARISON.md)

# 📝 API Reference

## 🔧 Skill Signature

```
skill(domain="cvm", sub_domain="comparison", mode="...", params='{"tickers":[...]}')
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | `str` | **Yes** | Always `"cvm"` |
| `sub_domain` | `str` | **Yes** | Always `"comparison"` |
| `mode` | `str` | **Yes** | `side_by_side` or `summary` |
| `params` | `str` (JSON) | **Yes** | JSON string with mode-specific args |

---

## ⚡ Modes

### `mode="side_by_side"` (default)

Compare N tickers across 3 sections (valuation, financials, dividends). Each section: rows = tickers, columns = metrics.

[v1.3] The valuation section now includes 5 calculations-sourced columns: ROE (val), ROA (val), Marg. Líq. (val), Dívida/PL, Liquidez Corrente. These come from `valuation.ratios()` which delegates to calculations metrics (roe_at, roa_at, net_margin_at, debt_equity_at, current_ratio_at). The `(val)` suffix distinguishes them from the same-named columns in the financials section (which use the annual statement value, not the TTM calculations snapshot).

[v1.4] The valuation section now also includes 15 v1.4 calculations-sourced columns grouped by family: EV/Sales, EV/FCF (EV multiples); Cash Ratio, Quick Ratio (liquidity); OCF Margin, FCF Margin (margins); Working Capital, Cash Flow to Debt (capital structure); Retention Ratio, Sustainable Growth (growth); Interest Coverage (coverage); Inventory Turnover, Receivables Turnover, Fixed Asset Turnover (turnover); P/Tangible Book (price/tangible). All come from `valuation.ratios()` (v1.4 wired them in via `_safe_call`); comparison picks them up transitively. See [calculations CHANGELOG](../calculations/CHANGELOG.md) v1.3 for the metric definitions.

```python
params = '{"tickers":["SUZB3","KLBN11"],"consolidado":1}'
```

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `tickers` | `list[str]` | **Yes** | — | B3 tickers, min 2 |
| `consolidado` | `int` | No | `1` | 1=consolidated, 0=individual |

**Returns:**
```python
{
    "status": "ok",
    "tickers": ["SUZB3", "KLBN11"],
    "sections": {
        "valuation":  {"title": "Valuation Ratios",
                       "columns": ["Ticker", "Preço", "Market Cap", "EV", "P/L", "P/VPA",
                                    "P/EBIT", "EV/EBITDA", "PSR", "Div Yield", "DPA", "EPS",
                                    "VPA", "Total Ações",
                                    "ROE (val)", "ROA (val)", "Marg. Líq. (val)",
                                    "Dívida/PL", "Liquidez Corrente",
                                    # [v1.4] 15 new columns
                                    "EV/Sales", "EV/FCF", "Cash Ratio", "Quick Ratio",
                                    "OCF Margin", "FCF Margin", "Working Capital",
                                    "Cash Flow to Debt", "Retention Ratio",
                                    "Sustainable Growth", "Interest Coverage",
                                    "Inventory Turnover", "Receivables Turnover",
                                    "Fixed Asset Turnover", "P/Tangible Book"],
                       "rows": [[...], ...],
                       "formats": {"Ticker": "text", "P/L": "num", "ROE (val)": "pct",
                                   "EV/Sales": "num", "Working Capital": "brl",
                                   "OCF Margin": "pct", ...}},
        "financials": {"title": "Financial Metrics (latest annual)", "columns": [...], "rows": [...], "formats": {...}},
        "dividends":  {"title": "Dividend Metrics", "columns": [...], "rows": [...], "formats": {...}},
    },
    "errors": [],  # list of per-ticker failure strings (empty if all succeeded)
}
```

### `mode="summary"`

Single quick-compare table: 1 row per ticker, ~10 KPI columns (Preço, Market Cap, P/L, P/VPA, EV/EBITDA, ROE, Div Yield, Receita, EBITDA, Lucro Líquido).

```python
params = '{"tickers":["PETR4","VALE3","ITUB4"]}'
```

**Returns:**
```python
{
    "status": "ok",
    "tickers": ["PETR4", "VALE3", "ITUB4"],
    "sections": [{"title": "Quick Compare", "columns": [...], "rows": [...], "formats": {...}}],
    "errors": [],
}
```

### `mode="growth"`

Growth metrics: QoQ + YoY % change for Receita, EBITDA, Lucro Líquido + TTM Marg. EBITDA + ROE. Calls `financials.quarterly(periods=8)` per ticker.

```python
params = '{"tickers":["SUZB3","KLBN11"]}'
```

**Returns:**
```python
{
    "status": "ok",
    "tickers": ["SUZB3", "KLBN11"],
    "sections": [{"title": "Growth Metrics (QoQ + YoY + TTM)", "columns": [...], "rows": [...], "formats": {...}}],
    "errors": [],
}
```

Columns: Ticker, Receita QoQ, Receita YoY, EBITDA QoQ, EBITDA YoY, Lucro Liq. QoQ, Lucro Liq. YoY, Marg. EBITDA (TTM), ROE (TTM).

---

## 🔌 Report Adapters

| Adapter | Source mode | What it tables |
|---------|-------------|----------------|
| `comparison_side_by_side` | side_by_side | 3 sections (valuation, financials, dividends), tickers as rows |
| `comparison_summary` | summary | Single quick-compare table + KPI strip (one card per ticker showing P/L) |
| `comparison_growth` | growth | Growth metrics table (QoQ + YoY + TTM ratios) |

```
report(action="table", title="SUZB3 vs KLBN11",
       data=<comparison JSON>, config={"adapter":"comparison_side_by_side"})

report(action="export", title="SUZB3 vs KLBN11",
       data=<comparison JSON>, config={"format":"xlsx","adapter":"comparison_side_by_side"})
```

---

## ⚠️ Error Handling

- **Tickers < 2** → `{"status":"error","error":"need at least 2 tickers to compare"}`
- **No tickers** → `{"status":"error","error":"tickers (list) is required"}`
- **Per-ticker skill failure** → ticker appears with `None` cells in the failed section; `errors` list captures what failed. Comparison never raises on per-ticker failures.
- **All tickers fail all sources** → `status:"ok"` with empty rows + populated `errors` list.

---

*Last updated: 2026-07-29 (v1.4).*
