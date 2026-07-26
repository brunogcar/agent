<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.2** | 2026-07-26 | **Auto-discovery + registry + per-share-and-ratio pattern.** New `metrics/_registry.py` with `MetricSpec` dataclass + `register_metric()` + `resolve_metric()`. Auto-discovery for both `engines/` and `metrics/` via glob + importlib. `<metric>_history` modes auto-generate from the registry. Chart adapters auto-register. Renamed `pe.py` → `lpa.py` (metric file = per-share quantity name). Each metric now produces BOTH a per-share value (LPA, VPA) AND a price ratio (P/L, P/VPA). Dual-dataset charts. Metric-aware summary with both per-share + ratio + engine components. Alias resolution: pe/pl/p/l → lpa, pvpa/p/vpa → vpa. This skill is now the pattern template for auto-discovery + registry architecture. 130 tests. |
| v1.1 | 2026-07-26 | PL engine + VPA metric + engine/metric separation. New `engines/pl.py` (Patrimônio Líquido snapshot from DFP+ITR BPP 2.03). New `metrics/vpa.py` (P/VPA = price / (PL / shares)). New `vpa_history` mode. `summary` + `ratio_history` made metric-aware. Documented engine vs metric pattern. |
| v1.0 | 2026-07-25 | Initial implementation. 3 modes: pe_history, ratio_history, summary. TTM earnings engine (DFP + ITR derivation). Price engine (COTAHIST). Shares engine (FRE + investsite fallback). P/L metric. 2 report adapters. |

---

### ⚠️ Breaking Changes

#### v1.2 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/pe.py` renamed → `metrics/lpa.py` | Old import path no longer exists. | `from skills.cvm.historical.metrics.pe import ...` → `from skills.cvm.historical.metrics.lpa import ...` |
| `pe_history` mode removed | Old mode name no longer in MANIFEST. | Use `lpa_history` instead. |
| `vpa` key in series changes meaning | Was: P/VPA ratio. Now: VPA per-share value. | The ratio is now under the `pvpa` key. Update chart/table consumers. |
| `METRICS` dict format changes | Was: `dict[str, str]` (name → description). Now: `dict[str, MetricSpec]`. | Use `METRICS["lpa"].ratio_label` instead of `METRICS["lpa"]`. |
| `summary()` result: `current` block changes | Now includes both per-share value and ratio. | Check `result["metric"]` to know which keys are present. |
| `historical_pe_chart` adapter renamed | Was: `historical_pe_chart`. Now: `historical_lpa_chart`. | Update `config["adapter"]` calls. |
| Chart adapters now produce 2 datasets | Was: 1 dataset (ratio only). Now: 2 datasets (per-share + ratio). | Chart builder handles multi-dataset natively. |

#### v1.1 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/pvpa.py` renamed → `metrics/vpa.py` | Old import path no longer exists. | `from skills.cvm.historical.metrics.pvpa import ...` → `from skills.cvm.historical.metrics.vpa import ...` |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **EV/EBITDA metric** (ev_ebitda) | Needs balance_sheet engine (debt, cash, EBIT, D&A). 4 DFP/ITR accounts. TTM for flows, snapshot for balances. | P1 |
| 2 | **PSR metric** (psr) | Needs revenue engine (DFP/ITR DRE codigo 3.01, TTM derivation like earnings). | P2 |
| 3 | **Dividend Yield metric** (dy) | Needs dividends engine (B3 dividends API + DPA from DFP). | P2 |
| 4 | **Backtest skill** | Reuse historical engines + metrics. `skills/cvm/backtest/`. Signal generation + return computation. | P3 |
| 5 | **Dual-axis charts** | Chart adapters currently emit 2 datasets. Configure dual-axis (yAxisID) when scales differ significantly (e.g., VPA ~25 vs P/VPA ~1.5). | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Intraday data | COTAHIST is daily. Intraday needs B3 API trades. | Skip |
| 2 | International stocks | CVM/B3 data only. US stocks need a different data source. | Skip |
| 3 | Options pricing | COTAHIST has options data (BDI filter excludes it). Would need separate handling. | Skip |
| 4 | Standalone quarter computation | ITR is cumulative. Standalone T2/T3/T4 derivation belongs in the financials skill. | Skip |
| 5 | Shared registry helper across skills | Each skill copies the pattern (no cross-skill coupling). The pattern is small enough (~50 lines). | Skip |

---

## 📐 Pattern Template Notes

This skill is the **pattern template** for auto-discovery + registry architecture. Other skills that need extensibility (e.g., a future screener with multiple filter metrics) should copy:

1. **Engine/metric separation** — engines are leaves (one per raw quantity), metrics compose engines.
2. **Auto-discovery** — `__init__.py` globs `*.py` and imports them via importlib.
3. **Self-registration** — each module calls `register_*()` at module level.
4. **Registry with spec dataclass** — `MetricSpec` (or equivalent) holds all metadata.
5. **Alias resolution** — `resolve_metric()` accepts canonical names + aliases.
6. **Auto-generated MANIFEST modes** — `<name>_history` modes appear in the MANIFEST automatically.
7. **Auto-registered adapters** — chart/table adapters auto-register from the registry.

**Do NOT create a shared registry helper across skills.** Each skill has its own `_registry.py`. Skills should be independent — the pattern is small enough that copying is fine, and a shared helper would couple skills that should evolve independently.

---

*Last updated: 2026-07-26 (v1.2 — auto-discovery + registry).*
