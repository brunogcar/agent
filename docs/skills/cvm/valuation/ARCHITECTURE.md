<- Back to [VALUATION Overview](../VALUATION.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|------|---------|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |

```text
skills/cvm/valuation/
├── __init__.py        [v2.0] uses auto_discover_modes() + make_route() from skills/_base.py — ~50 lines
├── _registry.py       [v2.0] delegates to skills/_base.py — creates skill's own MODES dict via make_registry(). ~16 lines.
├── modes/             one file per mode, auto-discovered via importlib
│   ├── __init__.py    minimal package marker
│   ├── ratios.py      @register_mode("ratios")      — include_in_all=True (default)
│   ├── summary.py     @register_mode("summary")     — include_in_all=False
│   └── dashboard.py   @register_mode("dashboard")   — include_in_all=False (NEW v1.4)
├── fetchers.py        price fetching (_get_price / _get_price_brapi /
│                     _get_price_investsite / _get_latest_price — b3 trades.db fallback)
├── helpers.py         _safe_call, _safe_div (shared utilities)
└── report.py          dashboard section builders (7 builders for the 5-tab payload,
                       incl. _safe_get defensive accessor for failed-ratios() case)
```

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

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; see CHANGELOG.md for details). Public API unchanged for `ratios` + `summary`; `dashboard` mode is new.*
