<- Back to [Calculations Overview](../CALCULATIONS.md)

# 📝 API Reference

## 🔌 Engine API (18 engines)

### `engines/price.py`
```python
price_at(ticker: str, date: str) -> float | None
price_series(ticker: str, date_from: str, date_to: str) -> list[dict]
```

### `engines/earnings.py`
```python
ttm_earnings_at(company: str, date: str) -> float | None
ttm_earnings_periods(company: str) -> list[dict]
```

### `engines/shares.py`
```python
shares_at(company: str, date: str) -> int | None
shares_periods(company: str) -> list[dict]
```

### `engines/pl.py`
```python
pl_at(company: str, date: str) -> float | None
pl_periods(company: str) -> list[dict]
```

### `engines/dividends.py`
```python
dividends_at(ticker: str, date: str) -> float | None
dividends_periods(ticker: str) -> list[dict]
```

### `engines/revenue.py`
```python
revenue_at(company: str, date: str) -> float | None
revenue_periods(company: str) -> list[dict]
```

### `engines/gross_profit.py`
```python
gross_profit_at(company: str, date: str) -> float | None
gross_profit_periods(company: str) -> list[dict]
```

### `engines/ebit.py`
```python
ebit_at(company: str, date: str) -> float | None
ebit_periods(company: str) -> list[dict]
```

### `engines/tax.py`
```python
tax_at(company: str, date: str) -> float | None
tax_periods(company: str) -> list[dict]
```

### `engines/assets.py`
```python
assets_at(company: str, date: str) -> float | None
assets_periods(company: str) -> list[dict]
```

### `engines/cash.py`
```python
cash_at(company: str, date: str) -> float | None
cash_periods(company: str) -> list[dict]
```

### `engines/total_assets.py`
```python
total_assets_at(company: str, date: str) -> float | None
total_assets_periods(company: str) -> list[dict]
```

### `engines/debt.py`
```python
debt_at(company: str, date: str) -> float | None
debt_periods(company: str) -> list[dict]
```

### `engines/current_liabilities.py`
```python
current_liabilities_at(company: str, date: str) -> float | None
current_liabilities_periods(company: str) -> list[dict]
```

### `engines/da.py`
```python
da_at(company: str, date: str) -> float | None
da_periods(company: str) -> list[dict]
```

### `engines/capex.py`
```python
capex_at(company: str, date: str) -> float | None
capex_periods(company: str) -> list[dict]
```

---

## 📐 Metric API (21 metrics)

### Per-share + price ratio metrics

#### `metrics/lpa.py`
```python
lpa_at(company, date) -> float | None    # LPA = earnings / shares
pe_at(company, date) -> float | None     # P/L = price / LPA
lpa_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/vpa.py`
```python
vpa_at(company, date) -> float | None    # VPA = pl / shares
pvpa_at(company, date) -> float | None   # P/VPA = price / VPA
vpa_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/dpa.py`
```python
dpa_at(ticker, date) -> float | None     # DPA = dividends TTM
dy_at(ticker, date) -> float | None      # Div Yield = DPA / price
payout_at(ticker, date) -> float | None  # Payout = DPA / LPA
dpa_history(ticker, date_from, date_to) -> list[dict]
```

#### `metrics/rps.py`
```python
rps_at(company, date) -> float | None    # RPS = revenue / shares
psr_at(company, date) -> float | None    # PSR = price / RPS
rps_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/ev_ebitda.py`
```python
ebitda_ps_at(company, date) -> float | None   # EBITDA/share = (EBIT+D&A)/shares
ev_ebitda_at(company, date) -> float | None   # EV/EBITDA = (price*shares+debt-cash)/(EBIT+D&A)
ev_ebitda_history(company, date_from, date_to) -> list[dict]
```

### Fundamental ratio metrics (per_share=None)

#### `metrics/roe.py`
```python
roe_at(company, date) -> float | None    # ROE = earnings / PL
roe_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/roa.py`
```python
roa_at(company, date) -> float | None    # ROA = earnings / assets
roa_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/roic.py`
```python
roic_at(company, date) -> float | None   # ROIC = NOPAT / (PL+Debt-Cash)
roic_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/gross_margin.py`
```python
gross_margin_at(company, date) -> float | None   # = gross_profit / revenue
gross_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/operating_margin.py`
```python
operating_margin_at(company, date) -> float | None   # = EBIT / revenue
operating_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/net_margin.py`
```python
net_margin_at(company, date) -> float | None   # = earnings / revenue
net_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/ebitda_margin.py`
```python
ebitda_margin_at(company, date) -> float | None   # = (EBIT+D&A) / revenue
ebitda_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/debt_equity.py`
```python
debt_equity_at(company, date) -> float | None   # = debt / PL
debt_equity_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/net_debt_ebitda.py`
```python
net_debt_ebitda_at(company, date) -> float | None   # = (debt-cash) / (EBIT+D&A)
net_debt_ebitda_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/asset_turnover.py`
```python
asset_turnover_at(company, date) -> float | None   # = revenue / assets
asset_turnover_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/capex_revenue.py`
```python
capex_revenue_at(company, date) -> float | None   # = capex / revenue
capex_revenue_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/current_ratio.py`
```python
current_ratio_at(company, date) -> float | None   # = current_assets / current_liabilities
current_ratio_history(company, date_from, date_to) -> list[dict]
```

---

## 📐 Registry API

### `_registry.py` (central — at the calculations top level)
```python
# Engine spec
EngineSpec(name, quantity, at_fn, periods_fn, source, category="other")

# Metric spec
MetricSpec(name, ratio_label, ratio_key, ratio_fn, history_fn, engines,
           per_share_label=None, per_share_key=None, per_share_fn=None, aliases=[])

ENGINES: dict[str, EngineSpec]
METRICS: dict[str, MetricSpec]

register_engine(spec: EngineSpec) -> EngineSpec
register_metric(spec: MetricSpec) -> MetricSpec

resolve_metric(name: str) -> MetricSpec
list_engines(category: str | None = None) -> list[str]
list_engine_categories() -> list[str]
list_metrics() -> list[str]
list_all_metric_names() -> list[str]
```

---

*Last updated: 2026-07-26 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for design, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
