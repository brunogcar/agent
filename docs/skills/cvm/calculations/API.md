<- Back to [Calculations Overview](../CALCULATIONS.md)

# 📝 API Reference

## 🔌 Engine API (16 engines)

Every engine exposes two functions — `<quantity>_at(company, date) -> float | None` (value at most recent data point <= date) and `<quantity>_periods(company) -> list[dict]` (all data points, sorted oldest-first, for step-function optimization). Each engine self-registers via `register_engine(EngineSpec(...))` at module level.

Engines are standalone — importable by any skill (historical, future valuation/financials/backtest) without coupling to the registry.

### `engines/price.py` (market — COTAHIST)
```python
price_at(ticker: str, date: str) -> float | None
# Close price on date (or nearest trading day <= date). Returns None if no data.
# Source: COTAHIST (B3 daily OHLCV, 2010+)

price_series(ticker: str, date_from: str, date_to: str) -> list[dict]
# [{date, close}, ...] sorted oldest-first. All trading days in the range.
```

### `engines/dividends.py` (market — B3 cash_dividends)
```python
dividends_at(ticker: str, date: str) -> float | None
# DPA TTM (R$/share) — SUM(rate) over event_date in [D-365, D].
# event_date = COALESCE(payment_date, last_date_prior, approved_on).
# None = no dividends data available; 0.0 = no dividends paid in window (different from None).
# JCP (Juros sobre Capital Próprio) is included.

dividends_periods(ticker: str) -> list[dict]
# [{date, dpa}, ...] — one entry per event date with DPA TTM up to that date.
```

### `engines/shares.py` (shares — FRE + investsite fallback)
```python
shares_at(company: str, date: str) -> int | None
# Shares outstanding at most recent FRE data point <= date.
# Falls back to investsite.com.br when FRE qtd_total_circulacao is NULL (cached, treated as constant across dates).

shares_periods(company: str) -> list[dict]
# [{date, shares}, ...] sorted oldest-first. ~1 data point per year.
```

### `engines/earnings.py` (dre — DFP+ITR DRE 3.11 TTM)
```python
ttm_earnings_at(company: str, date: str) -> float | None
# TTM net income (Lucro Líquido) ending <= date (BRL). Uses TTM derivation.
# None if can't derive TTM (no DFP for prior year, etc.).

ttm_earnings_periods(company: str) -> list[dict]
# [{date, ttm}, ...] sorted oldest-first. ~4 data points per year (DFP annual + ITR quarterly cumulative).
```

### `engines/revenue.py` (dre — DFP+ITR DRE 3.01 TTM)
```python
revenue_at(company: str, date: str) -> float | None
# TTM net revenue (Receita Líquida) ending <= date (BRL). Uses TTM derivation.

revenue_periods(company: str) -> list[dict]
# [{date, ttm_rev}, ...]
```

### `engines/gross_profit.py` (dre — DFP+ITR DRE 3.03 TTM)
```python
gross_profit_at(company: str, date: str) -> float | None
# TTM gross profit (Lucro Bruto) ending <= date (BRL). Uses TTM derivation.

gross_profit_periods(company: str) -> list[dict]
# [{date, ttm_gp}, ...]
```

### `engines/ebit.py` (dre — DFP+ITR DRE 3.05 TTM)
```python
ebit_at(company: str, date: str) -> float | None
# TTM EBIT ending <= date (BRL). Uses TTM derivation.

ebit_periods(company: str) -> list[dict]
# [{date, ttm_ebit}, ...]
```

### `engines/tax.py` (dre — DFP+ITR DRE 3.08 TTM)
```python
tax_at(company: str, date: str) -> float | None
# TTM IR+CSLL ending <= date (BRL). Typically NEGATIVE on DRE (expense).
# Consumers (e.g., ROIC) use max(0, -tax) to get the positive tax expense.

tax_periods(company: str) -> list[dict]
# [{date, ttm_tax}, ...]
```

### `engines/assets.py` (bpa — DFP+ITR BPA 1.01 snapshot)
```python
assets_at(company: str, date: str) -> float | None
# Ativo snapshot at most recent data point <= date (BRL). BPA code 1.01.
# NOTE: this is "Ativo" (current assets line, code 1.01), NOT "Ativo Total" (code 1).
# Used by current_ratio (which needs current assets) and asset_turnover (which historically used this).

assets_periods(company: str) -> list[dict]
# [{date, assets}, ...] — ~4 snapshots per year (DFP annual + ITR quarterly).
```

### `engines/cash.py` (bpa — DFP+ITR BPA 1.01.01 snapshot)
```python
cash_at(company: str, date: str) -> float | None
# Caixa e Equivalentes de Caixa snapshot at most recent data point <= date (BRL).
# BPA code 1.01.01. Used by ev_ebitda, roic, net_debt_ebitda.

cash_periods(company: str) -> list[dict]
# [{date, cash}, ...]
```

### `engines/total_assets.py` (bpa — DFP+ITR BPA 1 snapshot)
```python
total_assets_at(company: str, date: str) -> float | None
# Ativo Total snapshot at most recent data point <= date (BRL). BPA code 1 (top-level).
# Different from assets.py (code 1.01 — current assets subset).

total_assets_periods(company: str) -> list[dict]
# [{date, total_assets}, ...]
```

### `engines/pl.py` (bpp — DFP+ITR BPP 2.03 snapshot)
```python
pl_at(company: str, date: str) -> float | None
# Patrimônio Líquido snapshot at most recent data point <= date (BRL).
# BPP code 2.03. Used by vpa, roe, roic, debt_equity.

pl_periods(company: str) -> list[dict]
# [{date, pl}, ...]
```

### `engines/debt.py` (bpp — DFP+ITR BPP 2.01.04+2.02.01 snapshot, multi-code sum)
```python
debt_at(company: str, date: str) -> float | None
# Total debt (Empréstimos e Financiamentos) at most recent data point <= date (BRL).
# Sum of BPP codes 2.01.04 (current) + 2.02.01 (non-current). Multi-code sum engine.

debt_periods(company: str) -> list[dict]
# [{date, debt}, ...]
```

### `engines/current_liabilities.py` (bpp — DFP+ITR BPP 2.01 snapshot)
```python
current_liabilities_at(company: str, date: str) -> float | None
# Passivo Circulante snapshot at most recent data point <= date (BRL). BPP code 2.01.
# Used by current_ratio.

current_liabilities_periods(company: str) -> list[dict]
# [{date, current_liabilities}, ...]
```

### `engines/da.py` (dfc — DFP+ITR DFC description-search TTM)
```python
da_at(company: str, date: str) -> float | None
# TTM Depreciação e Amortização ending <= date (BRL). Uses TTM derivation.
# Searches DFC by descricao LIKE '%deprec%' OR '%amort%' (no fixed CVM code).
# Filtered by grupo LIKE '%Fluxo de Caixa%' (matches both DFC_MI and DFC_MD).
# SUMs all matching line items per period (filers may split D&A into multiple lines).

da_periods(company: str) -> list[dict]
# [{date, ttm_da}, ...]
```

### `engines/capex.py` (dfc — DFP+ITR DFC description-search TTM)
```python
capex_at(company: str, date: str) -> float | None
# TTM CapEx ending <= date (BRL). Typically NEGATIVE (cash outflow).
# Searches DFC by descricao LIKE '%imobilizado%' OR '%intangivel%' (no fixed CVM code).
# Same grupo filter + SUM + TTM derivation as da engine.

capex_periods(company: str) -> list[dict]
# [{date, ttm_capex}, ...]
```

---

## 📐 Metric API (17 metrics)

Each metric self-registers via `register_metric(MetricSpec(...))` at module level. Type 1 metrics (per-share+ratio) produce both a per-share value AND a price ratio. Type 2 metrics (fundamental) produce only a ratio. All metrics expose `<name>_history(company, date_from, date_to) -> list[dict]` for time series.

### Per-share + price ratio metrics (5)

#### `metrics/lpa.py` — LPA + P/L (engines: price + earnings + shares)
```python
lpa_at(company: str, date: str) -> float | None
# LPA = TTM earnings / shares (R$/share). Per-share value.

pe_at(company: str, date: str) -> float | None
# P/L = price / LPA. Returns None if LPA <= 0 (negative earnings — ratio meaningless).

lpa_history(company: str, date_from: str, date_to: str) -> list[dict]
# [{date, price, ttm_earnings, shares, lpa, pe}, ...] — daily series driven by price dates.
```

#### `metrics/vpa.py` — VPA + P/VPA (engines: price + pl + shares)
```python
vpa_at(company: str, date: str) -> float | None
# VPA = PL / shares (R$/share). Per-share value.

pvpa_at(company: str, date: str) -> float | None
# P/VPA = price / VPA. Returns None if VPA <= 0 (negative equity — ratio meaningless).

vpa_history(company: str, date_from: str, date_to: str) -> list[dict]
# [{date, price, pl, shares, vpa, pvpa}, ...]
```

#### `metrics/dpa.py` — DPA + Div Yield + Payout bonus (engines: price + dividends + earnings + shares)
```python
dpa_at(ticker: str, date: str) -> float | None
# DPA = dividends TTM (R$/share). Per-share value.
# None = no dividends data available; 0.0 = no dividends paid in window.

dy_at(ticker: str, date: str) -> float | None
# Div Yield = DPA / price. Returns None if DPA is None or price is None/<=0.

payout_at(ticker: str, date: str) -> float | None
# Payout = DPA / LPA. Bonus ratio. Returns None if LPA <= 0 or DPA is None.

dpa_history(ticker: str, date_from: str, date_to: str) -> list[dict]
# [{date, price, dpa, dy, payout, ttm_earnings, shares, lpa}, ...]
```

#### `metrics/rps.py` — RPS + PSR (engines: price + revenue + shares)
```python
rps_at(company: str, date: str) -> float | None
# RPS = TTM revenue / shares (R$/share). Per-share value.

psr_at(company: str, date: str) -> float | None
# PSR = price / RPS. Returns None if RPS <= 0 (no revenue — ratio meaningless).

rps_history(company: str, date_from: str, date_to: str) -> list[dict]
# [{date, price, ttm_rev, shares, rps, psr}, ...]
```

#### `metrics/ev_ebitda.py` — EBITDA/Ação + EV/EBITDA (engines: price + shares + debt + cash + ebit + da — 6 engines, most complex)
```python
ebitda_ps_at(company: str, date: str) -> float | None
# EBITDA per share = (TTM EBIT + TTM D&A) / shares. Per-share value.
# Returns None if EBITDA <= 0 (negative EBITDA — meaningless).

ev_ebitda_at(company: str, date: str) -> float | None
# EV/EBITDA = (price × shares + debt − cash) / (EBIT + D&A).
# EV = market_cap + debt − cash. Returns None if EBITDA <= 0 or shares missing.

ev_ebitda_history(company: str, date_from: str, date_to: str) -> list[dict]
# [{date, price, ebitda_ps, ev_ebitda, ebit, da, debt, cash, shares}, ...]
```

### Fundamental ratio metrics (12, per_share_*=None)

Fundamental ratios have no per-share value, no price. Each produces only `<ratio>_at()` + `<ratio>_history()`. The history series is built from the union of engine period dates (~4-8 points/year, no daily price driver).

| Metric | Function | Formula | Engines | Returns None when |
|---|---|---|---|---|
| `roe` | `roe_at()` | earnings / PL | earnings + pl | earnings None/<=0, PL None/<=0 |
| `roa` | `roa_at()` | earnings / assets | earnings + assets | earnings None/<=0, assets None/<=0 |
| `roic` | `roic_at()` | NOPAT / (PL+Debt−Cash) | ebit + tax + pl + debt + cash | EBIT None/<=0, NOPAT<=0, PL None/<=0, Debt None, IC<=0 |
| `gross_margin` | `gross_margin_at()` | gross_profit / revenue | gross_profit + revenue | gross_profit None, revenue None/<=0 |
| `operating_margin` | `operating_margin_at()` | EBIT / revenue | ebit + revenue | EBIT None, revenue None/<=0 |
| `net_margin` | `net_margin_at()` | earnings / revenue | earnings + revenue | earnings None, revenue None/<=0 |
| `ebitda_margin` | `ebitda_margin_at()` | (EBIT+D&A) / revenue | ebit + da + revenue | EBIT None, D&A None, revenue None/<=0, EBITDA<=0 |
| `debt_equity` | `debt_equity_at()` | debt / PL | debt + pl | debt None/<0, PL None/<=0 |
| `net_debt_ebitda` | `net_debt_ebitda_at()` | (debt−cash) / (EBIT+D&A) | debt + cash + ebit + da | any None, EBITDA<=0 |
| `asset_turnover` | `asset_turnover_at()` | revenue / assets | revenue + assets | revenue None/<=0, assets None/<=0 |
| `capex_revenue` | `capex_revenue_at()` | capex / revenue | capex + revenue | capex None, revenue None/<=0 (result typically negative — CapEx is outflow) |
| `current_ratio` | `current_ratio_at()` | assets / current_liabilities | assets + current_liabilities | assets None/<=0, current_liabilities None/<=0 |

Each fundamental metric also exposes `<name>_history(company, date_from, date_to) -> list[dict]` returning `[{date, <ratio_key>, ...engine quantities}, ...]` based on the union of engine period dates.

### Metric aliases (PT + EN)

All 17 metrics expose both Portuguese and English aliases. `resolve_metric(name)` accepts canonical names or any alias (case-insensitive, trimmed).

| Canonical | PT aliases | EN aliases |
|---|---|---|
| `lpa` | `preco_lucro` | `pe`, `pl`, `p/l` |
| `vpa` | `preco_vpa`, `p_vpa` | `pvpa`, `p/vpa` |
| `dpa` | `rendimento`, `rendimento_dividendo`, `div_yield` | `dy`, `dividend_yield`, `yld`, `payout` |
| `rps` | `preco_venda`, `p_venda` | `psr`, `p/sr`, `price_sales` |
| `ev_ebitda` | — | `ev_ebit`, `evebitda`, `eva_ebitda` |
| `roe` | `retorno_pl`, `retorno_patrimonio` | `return_on_equity` |
| `roa` | `retorno_ativos` | `return_on_assets` |
| `roic` | `retorno_capital_investido` | `return_on_invested_capital` |
| `gross_margin` | `margem_bruta` | `gm`, `gross_margin_pct` |
| `operating_margin` | `margem_operacional` | `om`, `operating_margin_pct` |
| `net_margin` | `margem_liquida`, `ml` | `nm`, `net_margin_pct` |
| `ebitda_margin` | `margem_ebitda` | `em`, `ebitda_margin_pct` |
| `debt_equity` | `divida_pl`, `divida_patrimonio` | `de` |
| `net_debt_ebitda` | `dl_ebitda`, `divida_liquida_ebitda` | `nde`, `net_debt_to_ebitda` |
| `asset_turnover` | `giro_ativos` | `at`, `asset_turnover_ratio` |
| `capex_revenue` | `intensidade_capex` | `capex_intensity` |
| `current_ratio` | `liquidez_corrente` | `cr`, `current_liquidity` |

---

## 📐 Registry API

The central `_registry.py` holds all specs + auto-discovery logic. Import from `skills.cvm.calculations._registry`.

### Dataclasses

```python
@dataclass
class EngineSpec:
    name: str           # "price", "earnings", "shares", "pl", "da", ...
    quantity: str       # "close", "ttm", "shares", "pl", "ttm_da", ... — JSON key in periods entries
    at_fn: Callable     # price_at, ttm_earnings_at, shares_at, pl_at, da_at, ...
    periods_fn: Callable # price_series, ttm_earnings_periods, da_periods, ...
    source: str         # "COTAHIST (B3 daily OHLCV, 2010+)" — for docs + backtest discovery
    category: str = "other"  # "market" | "shares" | "dre" | "bpa" | "bpp" | "dfc" | "other"

@dataclass
class MetricSpec:
    name: str                          # canonical metric name ("lpa", "vpa", "roe", ...)
    ratio_label: str                   # human label ("P/L", "ROE", ...)
    ratio_key: str                     # JSON key in series entries ("pe", "roe", ...)
    ratio_fn: Callable                 # fn(company, date) -> ratio float | None
    history_fn: Callable               # fn(company, date_from, date_to) -> list[dict]
    engines: list[str]                 # engine names this metric composes
    per_share_label: str | None = None # "LPA", "VPA", ... — None for fundamental ratios
    per_share_key: str | None = None   # "lpa", "vpa", ... — None for fundamental ratios
    per_share_fn: Callable | None = None # fn(company, date) -> per-share float | None
    aliases: list[str] = field(default_factory=list)  # PT + EN aliases for dispatch
```

**Note:** Both `EngineSpec` and `MetricSpec` are mutable `@dataclass` (NOT frozen) — tests need to `monkeypatch.setattr(spec, "history_fn", fake_fn)` to mock registry-captured functions. See [INSTRUCTIONS.md](INSTRUCTIONS.md) anti-patterns (v1.2 lesson).

### Module-level dicts

```python
ENGINES: dict[str, EngineSpec]   # all registered engines, keyed by canonical name
METRICS: dict[str, MetricSpec]   # all registered metrics, keyed by canonical name
_ALIASES: dict[str, str]         # alias → canonical metric name (internal)
```

### Registration functions

```python
register_engine(spec: EngineSpec) -> EngineSpec
# Called at import time by each engine module. Raises ValueError on duplicate name.

register_metric(spec: MetricSpec) -> MetricSpec
# Called at import time by each metric module. Raises ValueError on duplicate name or alias.
```

### Resolution + listing functions

```python
resolve_metric(name: str) -> MetricSpec
# Resolve a metric name or alias (case-insensitive, trimmed) to its MetricSpec.
# Raises ValueError with available names if not found. Used by ratio_history() + summary() dispatch.

list_engines(category: str | None = None) -> list[str]
# Sorted list of engine names. If category provided, filter to that category.

list_engine_categories() -> list[str]
# Sorted list of all categories currently in use (e.g., ["bpa", "bpp", "dfc", "market", "shares", "dre"]).

list_metrics() -> list[str]
# Sorted list of canonical metric names only (no aliases).

list_all_metric_names() -> list[str]
# Sorted list of all metric names (canonical + aliases). Used to build "Available: ..." error messages.
```

### Auto-discovery (internal)

```python
_auto_discover() -> None
# Globs engines/*.py + metrics/*.py (excluding __init__.py), imports each via importlib.
# This triggers register_engine() / register_metric() in each module.
# Idempotent — uses a _done flag to avoid re-running on re-import.
# Called once at module load (last line of _registry.py).
# DO NOT call manually — it runs at import time.
```

---

## ⚠️ Error Handling

### None returns (every engine + metric)

Every `<quantity>_at()` and `<ratio>_at()` function returns `None` to signal "can't compute". This is intentional — the consumer (chart, summary, backtest) handles None gracefully (chart shows gaps, summary reports "no data", backtest skips the date).

**When engines return None:**
- TTM engines: no DFP for prior year, no ITR for prior-year same period AND no DFP annual, ticker not found
- Snapshot engines: no snapshots <= date, ticker not found
- Price engine: no trading days <= date
- Dividends engine: no event dates at all, OR all event dates after query date
- Description-search engines (da, capex): no line items matched, OR no periods found

**When metrics return None (beyond engine None propagation):**
- Denominator <= 0 (negative earnings/equity/EBIT/revenue — ratio meaningless)
- Any composed engine returned None
- Special case: DPA returns `0.0` (not None) when company exists but paid no dividends in window — this is a valid value distinct from None

### Negative denominators (mathematical guard)

Every ratio computation guards against non-positive denominators. Examples:

```python
# lpa.py — P/L
def pe_at(company, date):
    lpa = lpa_at(company, date)
    if lpa is None or lpa <= 0:    # ← negative earnings guard
        return None
    price = price_at(company, date)
    if price is None or price <= 0:
        return None
    return price / lpa

# roe.py — ROE (fundamental ratio)
def roe_at(company, date):
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:  # ← negative earnings guard
        return None
    pl = pl_at(company, date)
    if pl is None or pl <= 0:               # ← negative equity guard
        return None
    return earnings / pl
```

**The per-share value MAY be returned when the ratio is None** — negative LPA (loss per share) is a valid number. The ratio (P/L) is None because P/L with negative earnings is meaningless.

### DPA: 0.0 vs None (special case)

```python
# 0.0 = "company exists but pays no dividends in the trailing 12-month window"
#       → Div Yield = 0.0 (valid, computable)
# None = "no dividends data available for this ticker"
#       → Div Yield = None (can't compute)
```

The dividends engine distinguishes these explicitly. Chart adapters and summary adapters handle both: `0.0` renders as a 0 line, `None` renders as a gap.

### Unknown metric (dispatch error)

`resolve_metric()` raises `ValueError` with available names when the caller passes an unknown metric:

```python
>>> resolve_metric("foo")
ValueError: Unknown metric 'foo'. Available: ['capex_revenue', 'current_ratio', 'debt_equity',
'dpa', 'ebitda_margin', 'ev_ebitda', 'gross_margin', 'lpa', 'net_debt_ebitda', 'net_margin',
'operating_margin', 'roa', 'roe', 'roic', 'rps', 'vpa']
```

Consumer skills (historical, etc.) catch this and return `{"status": "error", "error": "Unknown metric 'foo'. Available: [...]"}` to the caller.

---

*Last updated: 2026-07-26 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
