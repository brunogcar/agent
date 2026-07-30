<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|---|---|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/cvm/governance/__init__.py` | [v2.0] Uses `auto_discover_modes()` + `make_route()` from `skills/_base.py` — ~50 lines. MANIFEST + route — modes auto-generated from `_registry.py`. |
| `skills/cvm/governance/_registry.py` | [v2.0] Delegates to `skills/_base.py` — creates skill's own MODES dict via `make_registry()`. ~16 lines. |
| `skills/cvm/governance/report.py` | Skill-level report helpers (consumed by adapters) |
| `skills/cvm/governance/modes/practices.py` | `mode="practices"` — all practices for the latest filing |
| `skills/cvm/governance/modes/score.py` | `mode="score"` — % Sim/Não/Parcialmente + score_pct |
| `skills/cvm/governance/modes/by_chapter.py` | `mode="by_chapter"` — practices grouped by Capítulo |
| `skills/cvm/governance/modes/dashboard.py` | `mode="dashboard"` — multi-tab dashboard payload (v1.1) |
| `tools/report_ops/adapters/governance.py` | `governance_practices` + `governance_score` + `governance_by_chapter` table adapters |
| `tools/report_ops/adapters/governance_dashboard.py` | `governance_dashboard` adapter (v1.1 — 70th adapter) |

## Data Flow

```
skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
  ↓
governance.score(company="PETR4")
  ↓
CGVN query_engine.query(company="PETR4", score=True)
  ↓
Bridge resolution: ticker → CNPJ (FCA first → bridge.db → B3 API)
  ↓
SQLite query: cgvn_practices WHERE CNPJ = ? AND Data_Referencia = (latest)
  ↓
GROUP BY Pratica_Adotada → count Sim/Não/Parcialmente
  ↓
Compute: score_pct = Sim / total, partial_pct, not_adopted_pct
  ↓
Add data_freshness
  ↓
Return {status, company, total_practices, adopted_sim, score_pct, ...}
```

## Design Decisions

- **Read-only**: No sync. Calls CGVN query_engine directly. Assumes cgvn.db is already synced.
- **Latest filing only**: Queries the most recent Data_Referencia for the company. Historical governance scores are possible but not implemented yet.
- **Score computation**: `score_pct = adopted_sim / total_practices`. Simple percentage — no weighting by chapter or principle importance.
- **Bridge resolution**: Ticker → CNPJ via bridge (FCA first → bridge.db → B3 API). Auto-sync on miss.
- **Data freshness**: Returns `data_freshness` field with sync timestamps.
- **Modular pattern (v1.1)**: Decomposed monolithic `governance.py` (75 lines) into `_registry.py` + `modes/` + `report.py`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`; no edits to `__init__.py`. Mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends` modular pattern.

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; see CHANGELOG.md for details).*
