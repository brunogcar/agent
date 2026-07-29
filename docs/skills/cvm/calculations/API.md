<- Back to [Calculations Overview](../CALCULATIONS.md)

# 📝 API Reference

## 🔌 Engine API (30 engines)

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

### `engines/ebt.py`
```python
ebt_at(company: str, date: str) -> float | None       # TTM EBT (DRE 3.07, with description-search fallback)
ebt_periods(company: str) -> list[dict]
```

### `engines/tax.py`
```python
tax_at(company: str, date: str) -> float | None
tax_periods(company: str) -> list[dict]
```

### `engines/current_assets.py`
```python
current_assets_at(company: str, date: str) -> float | None      # BPA 1.01 (Ativo Circulante)
current_assets_periods(company: str) -> list[dict]
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

### `engines/operating_cf.py`
```python
operating_cf_at(company: str, date: str) -> float | None       # TTM FCO (DFC 6.01)
operating_cf_periods(company: str) -> list[dict]
```

### `engines/investing_cf.py`
```python
investing_cf_at(company: str, date: str) -> float | None       # TTM FCI (DFC 6.02)
investing_cf_periods(company: str) -> list[dict]
```

### `engines/financing_cf.py`
```python
financing_cf_at(company: str, date: str) -> float | None       # TTM FCF (DFC 6.03, Financing CF -- not Free CF)
financing_cf_periods(company: str) -> list[dict]
```

### `engines/cogs.py`
```python
cogs_at(company: str, date: str) -> float | None              # TTM COGS (DRE 3.02, typically NEGATIVE)
cogs_periods(company: str) -> list[dict]
```

### `engines/financial_result.py`
```python
financial_result_at(company: str, date: str) -> float | None # TTM Resultado Financeiro (DRE 3.06, net: income - expense, sign preserved)
financial_result_periods(company: str) -> list[dict]
```

### `engines/receivables.py`
```python
receivables_at(company: str, date: str) -> float | None      # BPA 1.01.03 (Contas a Receber) snapshot
receivables_periods(company: str) -> list[dict]
```

### `engines/inventory.py`
```python
inventory_at(company: str, date: str) -> float | None        # BPA 1.01.04 (Estoques) snapshot
inventory_periods(company: str) -> list[dict]
```

### `engines/ppe.py`
```python
ppe_at(company: str, date: str) -> float | None              # BPA 1.02.03 (Imobilizado líquido) snapshot
ppe_periods(company: str) -> list[dict]
```

### `engines/intangibles.py`
```python
intangibles_at(company: str, date: str) -> float | None      # BPA 1.02.04 (Intangível) snapshot
intangibles_periods(company: str) -> list[dict]
```

### `engines/payables.py`
```python
payables_at(company: str, date: str) -> float | None         # BPP 2.01.01 (Fornecedores) snapshot
payables_periods(company: str) -> list[dict]
```

### `engines/interest_paid.py`
```python
interest_paid_at(company: str, date: str) -> float | None    # TTM interest paid (DVA grupo='DVA' codigo 8.3, typically NEGATIVE)
interest_paid_periods(company: str) -> list[dict]
```

### `engines/total_tax.py`
```python
total_tax_at(company: str, date: str) -> float | None    # TTM total tax burden (DVA grupo='DVA' codigo 8.2, typically NEGATIVE)
total_tax_periods(company: str) -> list[dict]
```

### `engines/value_added.py`
```python
value_added_at(company: str, date: str) -> float | None  # TTM total value added (DVA grupo='DVA' codigo 7, typically POSITIVE)
value_added_periods(company: str) -> list[dict]
```

---

## 📐 Metric API (37 metrics)

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

#### `metrics/p_ebit.py`
```python
ebit_ps_at(company, date) -> float | None     # EBIT/share = ebit / shares
p_ebit_at(company, date) -> float | None       # P/EBIT = price / (ebit / shares)
p_ebit_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/p_fco.py`
```python
fco_ps_at(company, date) -> float | None      # FCO/share = operating_cf / shares
p_fco_at(company, date) -> float | None        # P/FCO = price / (operating_cf / shares)
p_fco_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/p_fcf.py`
```python
fcf_ps_at(company, date) -> float | None      # FCF/share = (operating_cf + investing_cf) / shares
p_fcf_at(company, date) -> float | None        # P/FCF = price / (fcf / shares)
p_fcf_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/price_to_tangible_book.py` (v1.3)
```python
tangible_book_ps_at(company, date) -> float | None  # Tangible Book/share = (pl - intangibles) / shares
p_tangible_book_at(company, date) -> float | None   # P/Tangible Book = price / tangible_book_ps
price_to_tangible_book_history(company, date_from, date_to) -> list[dict]
```

### Fundamental ratio metrics (per_share=None)

#### `metrics/roe.py`
```python
roe_at(company, date) -> float | None    # ROE = earnings / PL
roe_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/roa.py`
```python
roa_at(company, date) -> float | None    # ROA = earnings / total_assets (v1.2: total_assets, was assets)
roa_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/roic.py`
```python
roic_at(company, date) -> float | None   # ROIC = NOPAT / (PL+Debt-Cash), NOPAT = EBIT × (1 - tax/EBT) (v2.0 EBT-based)
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
asset_turnover_at(company, date) -> float | None   # = revenue / total_assets (v1.2: total_assets, was assets)
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

#### `metrics/graham_number.py`
```python
graham_number_at(company, date) -> float | None   # Graham Number = sqrt(22.5 × EPS × VPS)
graham_number_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/effective_tax_rate.py`
```python
effective_tax_rate_at(company, date) -> float | None       # = tax_expense / EBT, clamped to [0, 1.0] (v2.0)
effective_tax_rate_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/ev_sales.py` (v1.3)
```python
ev_sales_at(company, date) -> float | None       # EV/Sales = (price*shares + debt - cash) / revenue
ev_sales_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/ev_fcf.py` (v1.3)
```python
ev_fcf_at(company, date) -> float | None         # EV/FCF = (price*shares + debt - cash) / (FCO + FCI), with FCO/FCI date-alignment guard
ev_fcf_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/cash_ratio.py` (v1.3)
```python
cash_ratio_at(company, date) -> float | None     # Cash Ratio = cash / current_liabilities
cash_ratio_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/ocf_margin.py` (v1.3)
```python
ocf_margin_at(company, date) -> float | None     # OCF Margin = operating_cf / revenue
ocf_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/fcf_margin.py` (v1.3)
```python
fcf_margin_at(company, date) -> float | None     # FCF Margin = (FCO + FCI) / revenue, with FCO/FCI date-alignment guard
fcf_margin_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/working_capital.py` (v1.3)
```python
working_capital_at(company, date) -> float | None # Working Capital = current_assets - current_liabilities (BRL value, can be negative)
working_capital_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/cash_flow_to_debt.py` (v1.3)
```python
cash_flow_to_debt_at(company, date) -> float | None # Cash Flow to Debt = operating_cf / debt
cash_flow_to_debt_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/retention_ratio.py` (v1.3)
```python
retention_ratio_at(company, date) -> float | None # Retention Ratio = 1 - (dividends / earnings), with edge-case guards
retention_ratio_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/sustainable_growth.py` (v1.3)
```python
sustainable_growth_at(company, date) -> float | None # Sustainable Growth = ROE × Retention Ratio (composes 2 metrics)
sustainable_growth_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/quick_ratio.py` (v1.3)
```python
quick_ratio_at(company, date) -> float | None    # Quick Ratio (Acid Test) = (cash + receivables) / current_liabilities
quick_ratio_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/interest_coverage.py` (v1.3 approximation)
```python
interest_coverage_at(company, date) -> float | None # Interest Coverage = EBIT / abs(financial_result) (approximation: uses net financial_result, not gross interest expense)
interest_coverage_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/inventory_turnover.py` (v1.3)
```python
inventory_turnover_at(company, date) -> float | None # Inventory Turnover = abs(COGS) / inventory
inventory_turnover_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/receivables_turnover.py` (v1.3)
```python
receivables_turnover_at(company, date) -> float | None # Receivables Turnover = revenue / receivables
receivables_turnover_history(company, date_from, date_to) -> list[dict]
```

#### `metrics/fixed_asset_turnover.py` (v1.3)
```python
fixed_asset_turnover_at(company, date) -> float | None # Fixed Asset Turnover = revenue / ppe
fixed_asset_turnover_history(company, date_from, date_to) -> list[dict]
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

*Last updated: 2026-07-28 (v1.4). See [ARCHITECTURE.md](ARCHITECTURE.md) for design, [ROADMAP.md](ROADMAP.md) for deferred items, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
