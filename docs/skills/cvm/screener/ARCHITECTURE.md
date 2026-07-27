<- Back to [SCREENER Overview](../SCREENER.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `skills/cvm/screener/__init__.py` | MANIFEST + route() — dispatches sector / compare |
| `skills/cvm/screener/screener.py` | Sector search, peer valuation, median computation, comparison. [v1.2] `_roe_from_ratios()` simplified to `ratios.get("roe")` (was lucro_liquido/patrimonio_liquido division). `_compute_medians()` + `_build_comparison()` extended with roa, margem_liquida, divida_pl. |
| `tools/report_ops/adapters/screener.py` | screener_sector report adapter (NOT updated for v1.2 — still shows v1.1 columns; data flows through but new metrics aren't surfaced in the table yet) |
| `tests/skills/cvm/screener/conftest.py` | Shared fixtures — synthetic CAD_COMPANIES, BRIDGE_*, VAL_* data + `mock_all` + `papel_env` helpers |
| `tests/skills/cvm/screener/test_validation.py` | TestValidation (2 tests) — input validation |
| `tests/skills/cvm/screener/test_sector.py` | TestSectorMode (6 tests) — sector mode end-to-end |
| `tests/skills/cvm/screener/test_compare.py` | TestCompareMode (3 tests) — compare mode + vs_sector classification |
| `tests/skills/cvm/screener/test_route.py` | TestRoute (2 tests) — route dispatch |
| `tests/tools/report/test_report_adapters.py` | Adapter tests (TestScreenerSector class) |

### Test module tree

```
tests/skills/cvm/screener/
├── conftest.py            # mock_all, papel_env, CAD_COMPANIES, BRIDGE_*, VAL_* fixtures
├── test_validation.py     # 2 tests  — TestValidation
├── test_sector.py         # 6 tests  — TestSectorMode
├── test_compare.py        # 3 tests  — TestCompareMode
└── test_route.py          # 2 tests  — TestRoute
                          # 13 tests total
```

---

## 🔀 Data Flow

```mermaid
graph TD
    A["skill(domain='cvm', sub_domain='screener', mode='sector', params='{\"setor\":\"Papel e Celulose\"}')"]
    A --> B["screener.sector(setor)"]
    B --> C["CAD.search(setor) -> companies list"]
    C --> D["For each company: bridge.lookup(cd_cvm) -> ticker"]
    D --> E["For each ticker: valuation.ratios(ticker)"]
    E --> F["peers list with P/L, ROE, EV/EBITDA, etc."]
    F --> G["_compute_medians(peers)"]
    F --> H["Sort by P/L cheapest-first"]
    G & H --> I["{status, setor, peer_count, medians, peers, errors}"]
    E -.->|v1.2| K["valuation.ratios() now returns roe, roa, margem_liquida, divida_pl from calculations metrics"]
    K -.->|transitive| F
    K -.->|transitive| G
```

[v1.2] The dashed edge marks the transitive calculations integration. Screener does NOT import calculations directly — it just consumes the enriched `ratios` dict that `valuation.ratios()` returns after Phase 2B.

---

## 💡 Key Design Decisions

- **Orchestration only** — screener imports and calls CAD + bridge + valuation. No database, no sync, no duplicate SQL. If valuation changes, screener picks up the changes automatically.
- **Best-effort per company** — companies without a ticker (not in bridge) or with failed valuation are skipped. The `errors` list captures what was skipped. The screener never fails wholesale.
- **Sorted by P/L cheapest-first** — investors want to see value opportunities first. None P/L goes last.
- **Sector medians** — uses `statistics.median()` over non-None values. If a metric is None for all peers, median is None.
- **Compare mode** resolves the ticker's sector from CAD (via bridge → CNPJ → CAD lookup → SETOR_ATIV), then reuses `sector()` to get peers + medians, then builds a per-metric comparison with "cheap"/"expensive"/"above"/"below" labels.
- **[v1.2] Transitive calculations integration** — screener does NOT import calculations directly. It consumes the enriched `ratios` dict that `valuation.ratios()` returns (which since Phase 2B calls the calculations engines + metrics internally). This keeps the orchestration boundary clean: screener talks to valuation, valuation talks to calculations. If a metric is needed that valuation doesn't expose, the right fix is to extend valuation.ratios() to expose it — not to have screener call calculations directly.

### Calculations Integration (v1.2)

The peer dict + medians + comparison were extended with 3 metrics sourced from calculations via `valuation.ratios()`:

| Metric | `ratios` key | Calculations source | In medians | In comparison | vs_sector logic |
|--------|--------------|---------------------|------------|---------------|-----------------|
| ROA | `roa` | `metrics.roa.roa_at` | ✅ | ✅ | above/below (higher = better) |
| Marg. Líquida | `margem_liquida` | `metrics.net_margin.net_margin_at` | ✅ | ✅ | above/below (higher = better) |
| Dívida/PL | `divida_pl` | `metrics.debt_equity.debt_equity_at` | ✅ | ✅ | cheap/expensive (lower leverage = cheaper risk profile) |

ROE handling was simplified: `_roe_from_ratios(ratios)` is now just `ratios.get("roe")` (was `ratios["lucro_liquido"] / ratios["patrimonio_liquido"]`). The fallback was removed because those two keys aren't reliably populated in `valuation.ratios()` output — they live in `financials.summary` instead. Since Phase 2B, `roe` is computed by `calculations.metrics.roe_at` and surfaced directly.

---

## 📊 Comparison Logic

For each metric, the comparison dict contains:

| Metric | "cheap" / "expensive" logic |
|--------|----------------------------|
| P/L | below median = "cheap", above = "expensive" |
| P/VPA | below median = "cheap", above = "expensive" |
| EV/EBITDA | below median = "cheap", above = "expensive" |
| Dívida/PL | below median = "cheap" (less leveraged), above = "expensive" (more leveraged) |
| ROE | above median = "above", below = "below" |
| ROA | above median = "above", below = "below" |
| Marg. Líquida | above median = "above", below = "below" |
| Div Yield | above median = "above", below = "below" |

`delta_pct` = `(my_value - median) / |median|` — positive = above median.

[v1.2] New rows added for Dívida/PL, ROA, Marg. Líquida. All v1.1 rows (P/L, P/VPA, EV/EBITDA, ROE, Div Yield) preserved unchanged.

---

*Last updated: 2026-07-27 (v1.2).*
