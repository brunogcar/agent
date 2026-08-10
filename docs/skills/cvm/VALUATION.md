<- Back to [CVM Skills](../CVM.md)

# 💰 VALUATION — Valuation Ratios Skill

Computes valuation ratios from local data: b3 price + CVM DFP financials + FRE shares. The "investsite goldmine" — but computed from our own databases instead of scraped.

**Key characteristics:**
- **Combines 3 data sources** — b3/api (trades.db price) + cvm/dfp (financials) + cvm/fre (shares outstanding) + cvm/bridge (ticker resolution)
- **Ratios computed via `compute_all_ratios()`** (v1.3) — 37 calculations metrics auto-discovered; plus manual market-cap-based ratios (P/L, P/VPA, PSR, EV, Dividend Yield, Market Cap)
- **Underlying values included** — each ratio returns the inputs (price, EPS, VPA, etc.) so callers can verify
- **Data source status** — `summary` mode shows which DBs are synced vs missing
- **3 modes** — ratios (default), summary, dashboard, historical_valuation (v1.8)
- **6-tab dashboard (v1.10)** — grouped into 3 sidebar sections: Resumo (Overview with company header + price chart, Multiples with subtabs + P/L-LPA 5Y history chart, Valor Intrínseco with DCF/IRR/sensitivity), Fundamentos (Profitability with Retornos/Margens subtabs + ROIC/ROE/ROA 5Y step-line history chart, Liquidity & Leverage with Liquidez/Endividamento subtabs), Crescimento (Efficiency & Growth with Eficiência/Crescimento subtabs). Company header (FCA/CAD/COTAHIST) + historical price chart with Tudo/5A/1A/1M range selector at top of Overview. Tooltips on all ratio_grid items. Chart titles + descriptions. Freshness footer. engine_cache_scope wraps the ENTIRE dashboard (ratios fetch + section building + DCF sensitivity + history charts share one cache). Reuses `build_company_header` + `build_price_chart` + `get_tooltip` from `skills/cvm/_shared_report/`.
- **Modular file structure (v1.4)** — split into `_registry.py` + `modes/` (3 files) + `fetchers.py` + `helpers.py` + `report.py`. `__init__.py` auto-discovers modes via importlib (same pattern as `skills/cvm/financials/` v1.6). Public API unchanged for `ratios` + `summary`; `dashboard` was new in v1.4 (5 tabs), reorganized in v1.5 (6 tabs). See [ARCHITECTURE.md](valuation/ARCHITECTURE.md) for the file map.
- **Uses core/br_validator** — `validate_ticker()`, `parse_escala()` for consistent parsing
- **Read-only** — no sync. Assumes b3 trades.db + dfp.db + fre.db are already synced.

---

## 🚀 Quick Start

```
# All valuation ratios
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')

# Ratios + data source availability
skill(domain="cvm", sub_domain="valuation", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/b3/api` synced (trades table — latest price)
- `data_sources/cvm/dfp` synced (annual financials)
- `data_sources/cvm/fre` synced (distribuicao_capital — shares outstanding)
- `data_sources/cvm/bridge` synced (ticker → CNPJ)

---

## 📊 Rendering & Export

Pipe a `valuation` result into the `report` tool (adapters: `valuation_ratios`,
`valuation_summary`):

```
report(action="table", title="PETR4 Valuation",
       data=<valuation JSON>, config={"adapter":"valuation_ratios"})
report(action="export", title="PETR4 Valuation",
       data=<valuation JSON>, config={"format":"xlsx","adapter":"valuation_ratios"})
```

The `valuation_ratios` adapter builds a KPI strip (Preço, P/L, P/VPA,
EV/EBITDA, Div Yield, Market Cap) + a full indicator table. See
[CVM Skills — Report Integration](../CVM.md#-report-integration-v12).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](valuation/ARCHITECTURE.md) | Ratio formulas, data flow, data source requirements, modular file map (v1.10) |
| [API.md](valuation/API.md) | 4 modes: ratios, summary, dashboard (6-tab with sidebar groups + subtabs), historical_valuation |
| [CHANGELOG.md](valuation/CHANGELOG.md) | Version history (v1.10 — chart rework + Menos Comuns fix + doc cleanup) |
| [ROADMAP.md](valuation/ROADMAP.md) | Backlog + priorities (ROI, CAGR, margin trend chart, D3 cash flow metrics, D6 report adapters) |
| [INSTRUCTIONS.md](valuation/INSTRUCTIONS.md) | AI editing rules — what NOT to break (v1.10) |

---

*Last updated: 2026-08-10 (v1.10 — Graham overlay removed, P/L-LPA history chart, ROE trend rewrite, Menos Comuns fix, doc cleanup; see CHANGELOG.md).*
