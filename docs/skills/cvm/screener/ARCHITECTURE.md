<- Back to [SCREENER Overview](../SCREENER.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|------|---------|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/cvm/screener/__init__.py` | [v2.0] Uses `auto_discover_modes()` + `make_route()` from `skills/_base.py` — ~50 lines. MANIFEST + route() — dispatches sector / compare / dashboard via the MODES registry. |
| `skills/cvm/screener/_registry.py` | [v2.0] Delegates to `skills/_base.py` — creates skill's own MODES dict via `make_registry()`. ~16 lines. |
| `skills/cvm/screener/helpers.py` | [v1.4] Internal helpers — `_roe_from_ratios`, `_pct_change`, `_compute_medians`, `_build_comparison`. Shared by modes/sector.py + modes/compare.py. [v1.2] `_roe_from_ratios()` simplified to `ratios.get("roe")` (was lucro_liquido/patrimonio_liquido division). `_compute_medians()` + `_build_comparison()` extended with roa, margem_liquida, divida_pl. |
| `skills/cvm/screener/report.py` | [v1.4] Dashboard composition helpers — `_fmt`/`_num`/`_kpi`/`_ok` + `build_overview_kpis` (5 sector-median KPI cards) + `build_overview_section` (Overview Summary text) + `build_peers_section` (13-column peers table) + `build_comparison_section` (8-metric my-vs-sector table). Mirrors governance/report.py. |
| `skills/cvm/screener/modes/__init__.py` | [v1.4] Empty package marker — auto-discovered by `__init__.py`. |
| `skills/cvm/screener/modes/sector.py` | [v1.4] Mode: sector — `@register_mode("sector", include_in_all=True)`. Lists companies in a sector + computes median P/L, ROE, EV/EBITDA. |
| `skills/cvm/screener/modes/compare.py` | [v1.4] Mode: compare — `@register_mode("compare", include_in_all=False)`. Compares a ticker vs its sector medians. |
| `skills/cvm/screener/modes/dashboard.py` | [v1.4] Mode: dashboard — `@register_mode("dashboard", include_in_all=False)`. Thin composition of compare() (which internally calls sector()). 3 tabs (Overview/Peers/Comparison) + 5 top-level KPI cards. |
| `tools/report_ops/adapters/screener.py` | screener_sector report adapter (NOT updated for v1.2 — still shows v1.1 columns; data flows through but new metrics aren't surfaced in the table yet) |
| `tools/report_ops/adapters/screener_dashboard.py` | [v1.4] NEW screener_dashboard report adapter (72nd adapter). Thin pass-through of screener.dashboard() tabs + KPI re-formatting via unit → spec map. |
| `tests/skills/cvm/screener/conftest.py` | Shared fixtures — synthetic CAD_COMPANIES, BRIDGE_*, VAL_* data + `mock_all` + `papel_env` helpers |
| `tests/skills/cvm/screener/test_validation.py` | TestValidation (2 tests) — input validation |
| `tests/skills/cvm/screener/test_sector.py` | TestSectorMode (6 tests) — sector mode end-to-end |
| `tests/skills/cvm/screener/test_compare.py` | TestCompareMode (3 tests) — compare mode + vs_sector classification |
| `tests/skills/cvm/screener/test_route.py` | TestRoute (2 tests) — route dispatch |
| `tests/skills/cvm/screener/test_dashboard.py` | [v1.4] TestDashboardMode (13 tests) — dashboard mode validation / tab structure / KPI labels / Overview text / Peers table / Comparison table / cheap vs above labels / compare-failure degradation / compare-exception propagation / route dispatch |
| `tests/tools/report/test_report_adapters.py` | Adapter tests (TestScreenerSector class + TestScreenerDashboardAdapter class [v1.4]) |

### Test module tree

```
tests/skills/cvm/screener/
├── conftest.py            # mock_all, papel_env, CAD_COMPANIES, BRIDGE_*, VAL_* fixtures
├── test_validation.py     # 2 tests   — TestValidation
├── test_sector.py         # 6 tests   — TestSectorMode
├── test_compare.py        # 3 tests   — TestCompareMode
├── test_route.py          # 2 tests   — TestRoute
└── test_dashboard.py      # 13 tests  — TestDashboardMode  [v1.4]
                          # 26 tests total
```

### Modular file layout (v1.4)

```
skills/cvm/screener/
├── __init__.py            # MANIFEST + route() — auto-discovery of modes/*.py
├── _registry.py           # ModeSpec + register_mode + MODES + build_manifest_modes
├── helpers.py             # _roe_from_ratios, _pct_change, _compute_medians, _build_comparison
├── report.py              # build_overview_kpis, build_overview_section, build_peers_section, build_comparison_section
└── modes/
    ├── __init__.py        # empty package marker
    ├── sector.py          # @register_mode("sector", include_in_all=True)
    ├── compare.py         # @register_mode("compare", include_in_all=False)
    └── dashboard.py       # @register_mode("dashboard", include_in_all=False)
```

Adding a new mode = drop a file in `modes/` + `@register_mode()`. No edits to `__init__.py` or `_registry.py` needed (matches the auto-discovery pattern from financials + valuation + backtest + comparison + dividends + governance + historical + documented in `_registry.py`'s module docstring).

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

- **[v1.4] Modular pattern (v1.1 in governance-speak)** — The 356-line monolithic `screener.py` was split into `_registry.py` + `helpers.py` + `report.py` + `modes/{sector,compare,dashboard}.py`. Each mode is decorated with `@register_mode(name, ..., include_in_all=...)` and auto-discovered by `__init__.py` via `importlib.glob` over `modes/*.py`. Adding a new mode = drop a file in `modes/` + `@register_mode()` — no edits to `__init__.py` or `_registry.py` needed. Mirrors the modular pattern from financials + valuation + backtest + comparison + dividends + governance + historical.
- **[v1.4] Dashboard composition (thin)** — `dashboard()` does NOT fetch new data. It calls `compare()` (which internally calls `sector()`) and reshapes the result into a 3-tab payload. The `compare()` call is wrapped in try/except so a partial failure (e.g. ticker not in bridge) still renders an Overview tab + an empty Peers tab + an empty Comparison tab + 5 KPI cards with "—" values. Section-building helpers live in `report.py` (reusable across modes + tests).
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

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; see CHANGELOG.md for details).*
