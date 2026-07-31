<- Back to [VALUATION Overview](../VALUATION.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

```text
skills/cvm/valuation/
├── __init__.py        manifest + route() dispatch (auto-discovery)
├── _registry.py       ModeSpec + register_mode + MODES dict
├── modes/             one file per mode, auto-discovered via importlib
│   ├── __init__.py    minimal package marker
│   ├── ratios.py      @register_mode("ratios")      — include_in_all=True (default)
│   ├── summary.py     @register_mode("summary")     — include_in_all=False
│   └── dashboard.py   @register_mode("dashboard")   — include_in_all=False (v1.4 5-tab,
│                     v1.5 reorganized to 6 tabs with sub-tabs + charts + collapsibles)
├── fetchers.py        price fetching (_get_price / _get_price_brapi /
│                     _get_price_investsite / _get_latest_price — b3 trades.db fallback)
├── helpers.py         _safe_call, _safe_div (shared utilities)
└── report.py          dashboard section builders (v1.5: 7 builders for the 6-tab payload,
                       incl. _safe_get defensive accessor for failed-ratios() case +
                       _derive_multiples / _derive_per_share / _derive_detailed_leverage
                       helpers that compute additional metrics from ratios_dict components)
```

**v1.5 reorg (2026-07-29):** `dashboard.py` + `report.py` rewritten to produce 6 tabs (was 5). New tab "Per-share" inserted between Multiples and Profitability. Each tab builder is independently try/except-wrapped via the `_safe_build()` helper in `dashboard.py` so a failure in one tab degrades to an error section in that tab, not a crash of the whole dashboard. `ratios()` is now called ONCE in `dashboard()` and the resulting dict is passed to every tab builder (previously each builder received the same dict but the pattern was less explicit). Three new helpers added to `report.py`: `_derive_multiples()` (P/EBITDA, EV/EBIT, P/EV, P/CG, P/DB), `_derive_per_share()` (CGPA, DBPA), `_derive_detailed_leverage()` (DL/EBIT, Gross D/E) — these compute additional metrics from components already in `ratios_dict` without requiring new engine calls.

**v1.4 split (2026-07-29):** the 528-line `valuation.py` was split into the structure above + a new `dashboard` mode was added (the third valuation mode after `ratios` + `summary`). `__init__.py` now auto-discovers modes by globbing `modes/*.py` (sorted) + `importlib.import_module()` — same pattern as `skills/cvm/financials/` (v1.6) and `tools/git_ops/actions/`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`, no edits to `__init__.py` or `_registry.py`. Public API unchanged for `ratios` + `summary`; `dashboard` is new.

| External File | Purpose |
|------|---------|
| `core/br_validator.py` | `validate_ticker()`, `parse_escala()` — shared parsing |

## Data Flow

```
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
  │
  ▼  1. validate_ticker("PETR4") → "PETR4"  [core/br_validator]
  │
  ▼  2. _get_latest_price("PETR4")
  │     → b3 trades.db: SELECT LastPric FROM trades WHERE TckrSymb=? ORDER BY RptDt DESC
  │
  ▼  3. _get_latest_financials("PETR4")
  │     → resolve_company(ticker) → empresa_ids  [bridge auto-sync]
  │     → dfp.db: SELECT valor, escala FROM contas WHERE codigo IN (3.11, 2.03, 3.05, ...)
  │     → parse_escala("MIL") → 1000.0  [core/br_validator]
  │     → valor × escala = actual BRL
  │
  ▼  4. _get_shares_outstanding("PETR4")
  │     → _resolve_via_bridge(ticker) → CNPJ
  │     → fre.db: SELECT qtd_total_circulacao FROM distribuicao_capital WHERE cnpj=?
  │
  ▼  5. Compute ratios
       → Market Cap = price × shares
       → EPS = lucro_liquido / shares → P/L = price / EPS
       → VPA = PL / shares → P/VPA = price / VPA
       → EV = Market Cap + Debt - Cash
       → P/EBIT = price / (EBIT / shares)
       → P/FCO = price / (FCO / shares)
       → Dividend Yield = (annual_dividends / shares) / price
```

## Ratio Formulas

| Ratio | Formula | DFP Codes |
|-------|---------|-----------|
| Market Cap | price × total_shares | b3 trades + fre shares |
| EPS | lucro_liquido / total_shares | DFP 3.11 |
| P/L (P/E) | price / EPS | b3 trades + DFP 3.11 |
| VPA | patrimonio_liquido / total_shares | DFP 2.03 |
| P/VPA (P/B) | price / VPA | b3 trades + DFP 2.03 |
| EV | Market Cap + divida_bruta - caixa | Market Cap + DFP 2.01.04 + 2.02.01 + 1.01.01 |
| P/EBIT | price / (EBIT / shares) | b3 trades + DFP 3.05 |
| P/FCO | price / (FCO / shares) | b3 trades + DFP 6.01 |
| Dividend Yield | (proventos / shares) / price | DFP 7.08.04 + b3 trades + fre shares |

## Data Source Requirements

| Source | What | Required for |
|--------|------|-------------|
| b3/api trades.db | LastPric (latest price) | All ratios (price denominator) |
| cvm/dfp dfp.db | Annual financials (meses=12) | EPS, VPA, EV, P/EBIT, P/FCO, Div Yield |
| cvm/fre fre.db | Shares outstanding (distribuicao_capital) | Market Cap, EPS, VPA, per-share ratios |
| cvm/bridge bridge.db | ticker → CNPJ | FRE lookup (shares) |

If any source is missing, the affected ratios return `None` with a note.

## Uses core/br_validator

This skill uses `validate_ticker()` and `parse_escala()` from `core/br_validator.py`.
**All financial skills MUST use br_validator** for consistent BRL/date/ticker handling.

---

*Last updated: 2026-07-29 (v1.5 — 6-tab dashboard reorg; see CHANGELOG.md for details). Public API unchanged for `ratios` + `summary`; `dashboard` mode v1.5 adds Per-share tab + charts + collapsibles on top of v1.4.*
