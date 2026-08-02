<- Back to [CVM Skills](../CVM.md)

# 📐 CALCULATIONS — Shared Engine + Metric Library

Shared calculations layer between raw `data_sources/` and user-facing skills (historical, valuation, financials, future backtest). Contains **18 engines** (one per raw financial quantity) and **21 metrics** (per-share values + price ratios + fundamental ratios), all auto-discovered via a central registry.

**Architecture — engines vs metrics:**
- **Engines** (`engines/`) — one per raw quantity. Self-register via `register_engine()`. Auto-discovered by the central `_registry.py`. Engines are leaves: they never import each other or metrics.
  - `market`: price, dividends
  - `shares`: shares
  - `dre`: earnings, revenue, gross_profit, ebit, tax
  - `bpa`: assets, cash, total_assets
  - `bpp`: pl, debt, current_liabilities
  - `dfc`: da (D&A), capex
- **Metrics** (`metrics/`) — one per ratio. Self-register via `register_metric()`. Compose 2+ engines.
  - Per-share + price ratio: lpa (P/L), vpa (P/VPA), dpa (DY+Payout), rps (PSR), ev_ebitda (EV/EBITDA)
  - Fundamental: roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin, debt_equity, net_debt_ebitda, asset_turnover, capex_revenue, current_ratio

**Key characteristics:**
- **Central auto-discovery** — `_registry.py` at the top level, globs both `engines/*.py` and `metrics/*.py`
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`
- **Engine categories** — `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc` for filtering via `list_engines(category=...)`
- **3 metric types** — per-share+ratio (dual-axis charts), fundamental (single-dataset), per-share only (future)
- **TTM + snapshot patterns** — flow engines use DFP+ITR TTM derivation, balance engines use snapshot lookup
- **Description-based search** — da + capex engines search DFC by description (no fixed CVM code)
- **Multi-code sum** — debt engine sums BPP 2.01.04 + 2.02.01
- **PT + EN aliases** on all 21 metrics
- **Pattern template** for other skills that need extensibility

---

## 🚀 Quick Start

```python
# Import engines directly
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.engines.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.pl import pl_at

# Import metrics directly
from skills.cvm.calculations.metrics.lpa import lpa_at, pe_at
from skills.cvm.calculations.metrics.roe import roe_at

# Use the registry
from skills.cvm.calculations._registry import list_engines, list_metrics, resolve_metric

for name in list_engines(category="dre"):
    print(f"  {name}: {ENGINES[name].source}")

for name in list_metrics():
    spec = METRICS[name]
    print(f"  {name}: {spec.ratio_label} engines={spec.engines}")
```

---

## ⚙️ Configuration

No own config. Uses:
- `data_sources/b3/cotahist` synced (daily prices)
- `data_sources/b3/dividends` synced (cash dividends)
- `data_sources/cvm/dfp` synced (annual financials)
- `data_sources/cvm/itr` synced (quarterly financials)
- `data_sources/cvm/fre` synced (shares outstanding)
- `data_sources/cvm/bridge` synced (ticker → CNPJ resolution)

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](calculations/ARCHITECTURE.md) | Engine/metric pattern, auto-discovery, categories, algorithms, how to add engines/metrics |
| [API.md](calculations/API.md) | All 34 engine APIs + 58 metric APIs + registry API |
| [CHANGELOG.md](calculations/CHANGELOG.md) | Version history (v1.11 — Magic Number metric) |
| [ROADMAP.md](calculations/ROADMAP.md) | Backlog + priorities (DVA generation engines, BCB SGS/COE, performance, new engines/metrics) |
| [INSTRUCTIONS.md](calculations/INSTRUCTIONS.md) | AI editing rules — engine/metric separation, auto-discovery, NEVER DO, ALWAYS DO |

---

*Last updated: 2026-08-01 (v1.11 — Magic Number metric: EV/EBITDA × ROIC; see CHANGELOG.md).*
