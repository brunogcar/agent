<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 🏗️ Architecture — shareholders skill

## Purpose

Combines two CVM data sources into a single shareholder/equity view:

| Source | What it provides |
|--------|-----------------|
| FRE `posicao_acionaria` | Named shareholders + ownership % (ON/PN/total), controlling status |
| FRE `distribuicao_capital` | Free float %, shareholder counts (PF/PJ/inst) |
| DFP BPP 2.03.* | Equity structure in BRL (capital, reservas, minority) over N periods |

## Why a skill (not just data_source)?

The legacy `cvm_shareholders` skill only had aggregate equity amounts (BPP). The
real value is **named shareholders with ownership %** — which lives in FRE, not
DFP. This skill combines both into one queryable view.

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|---|---|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/cvm/shareholders/__init__.py` | [v2.0] Uses `auto_discover_modes()` + `make_route()` from `skills/_base.py` — ~50 lines. MANIFEST + route — modes auto-generated from `_registry.py`. |
| `skills/cvm/shareholders/_registry.py` | [v2.0] Delegates to `skills/_base.py` — creates skill's own MODES dict via `make_registry()`. ~16 lines. |
| `skills/cvm/shareholders/report.py` | Skill-level report helpers — dashboard section builders (v1.1) |
| `skills/cvm/shareholders/modes/__init__.py` | Empty package marker for the `modes/` directory |
| `skills/cvm/shareholders/modes/shareholders.py` | `mode="shareholders"` — named shareholders with ownership % (FRE) |
| `skills/cvm/shareholders/modes/free_float.py` | `mode="free_float"` — free float % + shareholder counts (FRE) |
| `skills/cvm/shareholders/modes/equity_structure.py` | `mode="equity_structure"` — equity breakdown in BRL over N periods (DFP BPP 2.03.*) |
| `skills/cvm/shareholders/modes/summary.py` | `mode="summary"` — combined: top shareholders + free float + latest equity total |
| `skills/cvm/shareholders/modes/dashboard.py` | `mode="dashboard"` — multi-tab dashboard payload (v1.1) |
| `tools/report_ops/adapters/shareholders.py` | `shareholders_shareholders` + `shareholders_free_float` + `shareholders_equity_structure` + `shareholders_summary` table adapters |
| `tools/report_ops/adapters/shareholders_dashboard.py` | `shareholders_dashboard` adapter (v1.1 — 73rd adapter) |

## Data Flow

```
skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
  │
  ▼  shareholders mode → FRE.query_engine.shareholders(company="PETR4")
  │    → resolve_company("PETR4") → bridge → CNPJ → FRE posicao_acionaria
  │
  ▼  equity_structure mode → DFP.connect_dfp + resolve_company + BPP 2.03.* query
  │    → resolve_company("PETR4") → bridge → empresa_ids → contas WHERE codigo LIKE '2.03.%'
  │
  ▼  summary mode → calls shareholders + free_float + equity_structure
  │
  ▼  dashboard mode → calls summary + reshapes into 4-tab payload
```

## Modes

| Mode | Source | Returns |
|------|--------|---------|
| `shareholders` | FRE | Named shareholders + ownership % (ON/PN/total) |
| `free_float` | FRE | Free float %, shareholder counts |
| `equity_structure` | DFP | Equity breakdown in BRL over N periods |
| `summary` | FRE + DFP | Top shareholders + free float + latest equity total |
| `dashboard` (v1.1) | summary() | Multi-tab dashboard payload (Overview / Top Shareholders / Free Float / Equity Structure) — optimized for the report tool's dashboard action |

## Modular file layout (v1.1)

```
skills/cvm/shareholders/
├── __init__.py                  # Auto-discovery + MANIFEST + route (5 modes)
├── _registry.py                 # ModeSpec + register_mode + MODES dict
├── report.py                    # Dashboard composition helpers (v1.1)
└── modes/
    ├── __init__.py              # Empty package marker
    ├── shareholders.py          # @register_mode("shareholders")
    ├── free_float.py            # @register_mode("free_float")
    ├── equity_structure.py      # @register_mode("equity_structure")
    ├── summary.py               # @register_mode("summary")
    └── dashboard.py             # @register_mode("dashboard") — v1.1
```

## Resolution

All modes accept `company` (B3 ticker, name fragment, or CNPJ). The underlying
data_source query engines call `resolve_company()` with `auto_sync=True`, so
the first query for a new ticker auto-syncs the bridge transparently.

## No Sync

This skill is read-only. It assumes `fre.db` + `dfp.db` are already synced.
If they're not, queries return `not_synced` / `not_found`.

## Design Decisions

- **Modular pattern (v1.1)**: Decomposed monolithic `shareholders.py` (233 lines) into `_registry.py` + `modes/` + `report.py`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`; no edits to `__init__.py`. Mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends`/`governance`/`historical`/`screener` modular pattern.
- **Dashboard composition (thin)**: The `dashboard` mode is a thin pass-through of `summary()` into a multi-tab dashboard dict (Overview text + 3 table tabs). 3 top-level KPI cards (% Free Float, Total Acionistas, PL Total) live above all tabs — matches the dashboard contract used by the other 8 CVM skills. Section-building helpers live in `report.py` so they can be reused by other modes / tests.
- **Read-only**: No sync. Calls FRE + DFP query engines directly. Assumes `fre.db` + `dfp.db` are already synced.
- **Bridge resolution**: Ticker → CNPJ via bridge (FCA first → bridge.db → B3 API). Auto-sync on miss.
- **Best-effort summary**: `summary()` and `dashboard()` degrade gracefully — if FRE or DFP is missing, the affected section renders an empty/error payload instead of crashing the whole call.

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; see CHANGELOG.md for details).*
