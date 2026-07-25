<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `skills/cvm/comparison/__init__.py` | MANIFEST + route() — dispatches side_by_side / summary |
| `skills/cvm/comparison/comparison.py` | Orchestration logic — calls financials + valuation + dividends per ticker, merges into side-by-side |
| `tools/report_ops/adapters/comparison.py` | 2 report adapters: comparison_side_by_side, comparison_summary |
| `tests/skills/cvm/test_comparison.py` | Skill tests (mocked underlying skills, no network) |
| `tests/tools/report/test_report_adapters.py` | Adapter tests (TestComparisonAdapters class) |

---

## 🔀 Data Flow

```mermaid
graph TD
    A["skill(domain='cvm', sub_domain='comparison', mode='side_by_side', params='{\"tickers\":[\"SUZB3\",\"KLBN11\"]}')"]
    A --> B["comparison.side_by_side(tickers)"]
    B --> C["_fetch_all(tickers)"]
    C --> D1["valuation.ratios(SUZB3)"]
    C --> D2["financials.summary(SUZB3)"]
    C --> D3["dividends.summary(SUZB3)"]
    C --> E1["valuation.ratios(KLBN11)"]
    C --> E2["financials.summary(KLBN11)"]
    C --> E3["dividends.summary(KLBN11)"]
    D1 & D2 & D3 & E1 & E2 & E3 --> F["per_ticker list (best-effort)"]
    F --> G["_build_section(Valuation, cols, per_ticker)"]
    F --> H["_build_section(Financials, cols, per_ticker)"]
    F --> I["_build_section(Dividends, cols, per_ticker)"]
    G & H & I --> J["{status, tickers, sections: {valuation, financials, dividends}, errors}"]
```

---

## 💡 Key Design Decisions

- **Orchestration only** — comparison imports and calls the 3 existing skills. No database, no sync, no duplicate SQL. If financials/valuation/dividends change, comparison picks up the changes automatically.
- **Best-effort per ticker** — `_fetch_all()` wraps each skill call in try/except. A ticker failing one source gets `None` cells in that section but still appears in the others. The `errors` list collects what failed so the caller knows data is partial. The comparison never raises on a per-ticker failure.
- **Tickers as rows, metrics as columns** — each section is unit-homogeneous (all valuation ratios are multiples/fractions, all financials are BRL/%, all dividends are BRL/fractions). This lets the table builder use per-**column** format specs (the existing mechanism) — no per-row format concept needed.
- **Column sets are module-level constants** (`_VALUATION_COLS`, `_FINANCIALS_COLS`, `_DIVIDENDS_COLS`, `_SUMMARY_COLS`) — each entry is `(label, dict_key, spec)`. Adding a column = one line in the list. The `_build_section()` helper is generic over any column list.
- **Summary mode merges dicts** — `summary()` merges each ticker's valuation + financials + dividends dicts into one row, then builds a single section from `_SUMMARY_COLS`. This is why `dict_key`s must not collide across the 3 sources (e.g. `dividend_yield` comes from valuation, not dividends).

---

## 📊 Column Definitions

### Valuation (from `valuation.ratios`)
| Column | dict_key | spec |
|--------|----------|------|
| Preço | `price` | brl_full |
| Market Cap | `market_cap` | brl |
| EV | `ev` | brl |
| P/L | `p_l` | num |
| P/VPA | `p_vpa` | num |
| P/EBIT | `p_ebit` | num |
| EV/EBITDA | `ev_ebitda` | num |
| PSR | `psr` | num |
| Div Yield | `dividend_yield` | pct |
| DPA | `dpa` | brl_full |
| EPS | `eps` | brl_full |
| VPA | `vpa` | brl_full |
| Total Ações | `total_shares` | int |

### Financials (from `financials.summary` → `latest_annual`)
| Column | dict_key | spec |
|--------|----------|------|
| Receita Líquida | `receita_liquida` | brl |
| Lucro Bruto | `lucro_bruto` | brl |
| EBIT | `ebit` | brl |
| EBITDA | `ebitda` | brl |
| Lucro Líquido | `lucro_liquido` | brl |
| Ativo Total | `ativo_total` | brl |
| Patrimônio Líq. | `patrimonio_liquido` | brl |
| Caixa | `caixa` | brl |
| Dívida Bruta | `divida_bruta` | brl |
| FCO | `fco` | brl |
| Marg. Bruta | `marg_bruta` | pct |
| Marg. EBITDA | `marg_ebitda` | pct |
| Marg. Líquida | `marg_liquida` | pct |
| ROE | `roe` | pct |
| ROA | `roa` | pct |

### Dividends (from `dividends.summary`)
| Column | dict_key | spec |
|--------|----------|------|
| Eventos (B3) | `event_count` | int |
| DPA (B3 médio) | `b3_dpa_avg` | brl_full |
| Dividendos (últ ano) | `annual_dividendos` | brl |
| JCP (últ ano) | `annual_jcp` | brl |
| Total Remun. (últ a) | `annual_total` | brl |
| Payout | `payout` | pct |

---

*Last updated: 2026-07-25 (v1.0).*
