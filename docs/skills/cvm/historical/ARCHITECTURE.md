<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/historical/__init__.py` | MANIFEST + route — skill hub, 3 modes |
| `skills/cvm/historical/historical.py` | Main: pe_history, ratio_history, summary. Orchestrates engines + metrics. |
| `skills/cvm/historical/engines/__init__.py` | Engine registry |
| `skills/cvm/historical/engines/price.py` | COTAHIST daily close prices: `price_at()`, `price_series()` |
| `skills/cvm/historical/engines/earnings.py` | TTM earnings at any date: `ttm_earnings_at()`, `ttm_earnings_periods()`. Uses DFP + ITR. |
| `skills/cvm/historical/engines/shares.py` | FRE shares outstanding at any date: `shares_at()`, `shares_periods()` |
| `skills/cvm/historical/metrics/__init__.py` | Metric registry (METRICS dict) |
| `skills/cvm/historical/metrics/pe.py` | P/L metric: `pe_at()`, `pe_history()`. Imports price + earnings + shares engines. |
| `skills/cvm/historical/metrics/pvpa.py` | P/VPA stub for future |
| `skills/cvm/historical/metrics/ev_ebitda.py` | EV/EBITDA stub for future |

## TTM Earnings Algorithm

The core innovation. Derives trailing twelve months earnings at any date.

```
For date D, find the most recent ITR period (data_fim_exerc <= D):

  ITR current period (e.g., Q2 2024, meses=6) = cumulative H1 2024 earnings
  ITR prior year same period (Q2 2023, meses=6) = cumulative H1 2023 earnings
  DFP prior year (2023, meses=12) = full year 2023 earnings

  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1
       = (full year 2023) - (H1 2023) + (H1 2024)
       = 12 months ending 2024-06-30

For Q4 dates (Oct-Dec), most recent ITR = Q3 (meses=9):
  TTM = DFP_prior - ITR_prior_9M + ITR_current_9M

For Q1 dates (Jan-Mar), most recent ITR = Q3 prior year (meses=9):
  TTM = DFP_prior2 - ITR_prior2_9M + ITR_prior_9M
```

**Earnings change quarterly** (when new ITR/DFP is filed). Between filings, TTM is constant.

## Data Flow

```
pe_history("PETR4", "2020-01-01", "2024-12-31")
  │
  ├── price_series("PETR4", "2020-01-01", "2024-12-31")
  │     → COTAHIST: ~1200 daily close prices
  │
  ├── ttm_earnings_periods("PETR4")
  │     → DFP: all annual earnings (codigo 3.11, meses=12)
  │     → ITR: all quarterly cumulative earnings (codigo 3.11, meses 3/6/9)
  │     → Compute TTM for each ITR period (~4 per year)
  │     → Step function: [{date, ttm}, ...]
  │
  ├── shares_periods("PETR4")
  │     → FRE: distribuicao_capital (annual)
  │     → Step function: [{date, shares}, ...]
  │
  └── For each daily price:
        find most recent TTM (step function lookup)
        find most recent shares (step function lookup)
        PE = price / (TTM / shares)
        → [{date, price, ttm_earnings, shares, pe}, ...]
```

## Design Decisions

- **Engines are standalone**: `price.py`, `earnings.py`, `shares.py` can be imported independently by any skill (e.g., future backtest). No coupling to historical.py.
- **Metrics compose engines**: `pe.py` imports `price + earnings + shares`. New metrics (pvpa, ev_ebitda) import different engine combinations.
- **Step function optimization**: TTM earnings change ~4x per year, shares ~1x per year. Instead of computing TTM for each of ~1200 daily prices, we precompute the step functions and do O(1) lookups per day.
- **parse_escala applied**: DFP/ITR store raw values with escala ("MIL", "MILHOES"). The earnings engine applies parse_escala to convert to BRL.
- **Negative earnings → None PE**: When TTM earnings <= 0, PE is meaningless. The series includes these days with pe=None so the chart shows gaps.

## How to Add a New Metric

1. Create a new file in `metrics/` (e.g., `psr.py`)
2. Import the engines you need:
   ```python
   from skills.cvm.historical.engines.price import price_at, price_series
   from skills.cvm.historical.engines.earnings import ttm_earnings_at
   from skills.cvm.historical.engines.shares import shares_at
   ```
3. Implement `metric_at(ticker, date)` and `metric_history(ticker, date_from, date_to)`
4. Register the metric in `metrics/__init__.py` METRICS dict
5. Add a report adapter in `tools/report_ops/adapters/historical.py` if you want chart/table rendering
6. Add the metric to `ratio_history()` and `summary()` dispatch in `historical.py`

## How to Add a New Engine

1. Create a new file in `engines/` (e.g., `balance_sheet.py`)
2. Implement `*_at(company, date)` and `*_periods(company)` functions
3. Import from the appropriate data source (DFP/ITR/FRE/COTAHIST)
4. Apply parse_escala to raw CVM values
5. Import the engine in the metric that needs it

## Backtest Foundation

The engines are designed for reuse by a future `skills/cvm/backtest/` skill:

```python
# Future backtest skill
from skills.cvm.historical.engines.price import price_at
from skills.cvm.historical.metrics.pe import pe_at

# Signal: buy when P/L < 5
if pe_at("PETR4", "2022-06-30") < 5:
    entry_price = price_at("PETR4", "2022-06-30")
    # ... compute returns
```

No duplication — the backtest skill reuses the same engines.

---

*Last updated: 2026-07-25 (v1.0).*
