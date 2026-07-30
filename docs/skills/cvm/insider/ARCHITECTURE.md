<- Back to [INSIDER Overview](../INSIDER.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|---|---|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/cvm/insider/__init__.py` | [v2.0] Uses `auto_discover_modes()` + `make_route()` from `skills/_base.py` — ~50 lines. MANIFEST + route — skill hub, auto-discovers modes/*.py and builds MANIFEST["modes"] from the registry. 4 modes: history, by_role, summary, dashboard. |
| `skills/cvm/insider/_registry.py` | [v2.0] Delegates to `skills/_base.py` — creates skill's own MODES dict via `make_registry()`. ~16 lines. |
| `skills/cvm/insider/report.py` | Dashboard composition helpers used by `modes/dashboard.py`: `_fmt` / `_num` / `_kpi` / `_ok` + `build_overview_kpis` + `build_overview_section` + `build_recent_transactions_section` + `build_by_role_section` + `build_monthly_section`. Pre-formats KPI values via `apply_fmt` so adapters pass through verbatim. |
| `skills/cvm/insider/modes/__init__.py` | Empty package marker — auto-discovered by `__init__.py`. |
| `skills/cvm/insider/modes/history.py` | `history(company, limit)` mode — wraps `data_sources.cvm.vlmo.query_engine.query` + `add_freshness`. Registered as `history`. |
| `skills/cvm/insider/modes/by_role.py` | `by_role(company, limit)` mode — wraps `query(..., by_role=True)`. Registered as `by_role`. |
| `skills/cvm/insider/modes/summary.py` | `summary(company)` mode — wraps `query(..., summary=True)` + computes `net_volume` / `total_volume_bought` / `total_volume_sold` / `sentiment`. Registered as `summary` (default `include_in_all=True`). |
| `skills/cvm/insider/modes/dashboard.py` | `dashboard(company)` mode — thin composition of `summary()` + `history(company, limit=10)` + `by_role()`. Each sub-call independently try/except-wrapped. Builds 4 tabs + 4 top-level KPI cards via `report.py`. Registered as `dashboard`. |
| `tools/report_ops/adapters/insider.py` | Adapters `insider_history` / `insider_by_role` / `insider_summary` — flatten the non-dashboard modes' results into report-ready table data. (Not modified in v1.1.) |
| `tools/report_ops/adapters/insider_dashboard.py` | Adapter `insider_dashboard` — thin pass-through for the dashboard mode's already-shaped tabs; re-formats top-level KPI cards via unit -> spec map. |
| `tests/skills/cvm/insider/test_insider.py` | Per-mode tests for history / by_role / summary + TestRoute dispatch (11 tests). |
| `tests/skills/cvm/insider/test_dashboard.py` | TestDashboardMode covering the new `dashboard` mode (15 tests). |

## Modular file layout (v1.1)

```
skills/cvm/insider/
├── __init__.py        # MANIFEST + route (auto-discovers modes/)
├── _registry.py       # ModeSpec + register_mode + MODES + build_manifest_modes
├── report.py          # Dashboard composition helpers (NEW in v1.1)
└── modes/
    ├── __init__.py    # Empty package marker
    ├── history.py     # history mode
    ├── by_role.py     # by_role mode
    ├── summary.py     # summary mode (default for sub_domain="all")
    └── dashboard.py   # dashboard mode (NEW in v1.1)
```

Adding a new mode = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py` needed.

## Modes

| Mode | Description | include_in_all | Params |
|---|---|---|---|
| `history` | Recent insider transactions (newest-first). | `False` | `company`, `limit` |
| `by_role` | Insider transactions grouped by role (Tipo_Cargo). | `False` | `company`, `limit` |
| `summary` | Net buy/sell summary per month (last 24 months). | `True` | `company` |
| `dashboard` | Multi-tab composition (Overview / Recent Transactions / By Role / Monthly Net). | `False` | `company` |

## Data Flow

```
skill(domain="cvm", sub_domain="insider", mode="summary", params='{"company":"PETR4"}')
  ↓
insider.summary(company="PETR4")
  ↓
VLMO query_engine.query(company="PETR4", summary=True)
  ↓
Bridge resolution: ticker → CNPJ (FCA first → bridge.db → B3 API)
  ↓
SQLite query: vlmo_movements WHERE CNPJ = ? GROUP BY month
  ↓
Compute: net_volume, total_volume_bought/sold, sentiment ("buying"/"selling"/"neutral")
  ↓
Add data_freshness
  ↓
Return {status, company, monthly, sentiment, net_volume, ...}
```

### Dashboard mode data flow (v1.1)

```
skill(domain="cvm", sub_domain="insider", mode="dashboard", params='{"company":"PETR4"}')
  ↓
insider.dashboard(company="PETR4")
  ↓
  ├── summary(company="PETR4")          # try/except-wrapped
  ├── history(company="PETR4", limit=10) # try/except-wrapped
  └── by_role(company="PETR4")          # try/except-wrapped
  ↓
report.build_overview_kpis(summary_payload)        # 4 KPI cards (top-level)
report.build_overview_section(summary_payload)     # Overview tab Summary text
report.build_recent_transactions_section(history_payload)  # Recent Transactions table
report.build_by_role_section(by_role_payload)      # By Role table
report.build_monthly_section(summary_payload)      # Monthly Net table
  ↓
Return {status:"ok", company, tabs:[4], kpis:[4]}
```

Each sub-call is independently try/except-wrapped so a missing VLMO DB degrades the corresponding tab to an error payload (table with 0 rows, KPIs render as "—") instead of crashing the whole dashboard.

## Design Decisions

- **Modular pattern (v1.1)**: The skill uses the standard CVM modular layout (`_registry.py` + `modes/*.py` + `report.py` + auto-discovery in `__init__.py`). Adding a new mode = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py` needed.
- **Dashboard composition (thin)**: The `dashboard` mode is a thin composition of `summary()` + `history(company, limit=10)` + `by_role()`. It does NOT fetch new data — it just reshapes existing mode outputs into a 4-tab payload. Each sub-call is independently try/except-wrapped so partial failures degrade gracefully (table with 0 rows, KPIs as "—") instead of crashing the whole dashboard.
- **Read-only**: No sync. Calls VLMO query_engine directly. Assumes vlmo.db is already synced.
- **Bridge resolution**: Ticker → CNPJ via bridge (FCA first → bridge.db → B3 API). Auto-sync on miss.
- **Sentiment computation**: `summary()` computes net_volume = total_bought - total_sold. If positive → "buying", negative → "selling", zero → "neutral".
- **Data freshness**: Returns `data_freshness` field with sync timestamps for all CVM/B3 databases.
- **Best-effort**: If VLMO data is missing, returns not_synced/not_found — never crashes.

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; see CHANGELOG.md for details).*
