<- Back to [B3 Skills](../B3.md)

# 📊 INDEX — B3 Index Analytics Skill

The `index` skill combines B3 INDEX (composition + history) + B3 API instruments to produce index analytics: dashboard, comparison, and ticker reverse-lookup.

**Key characteristics:**
- **5 active indices** — IBOV (Ibovespa), SMLL (Small Cap), BDRX (BDRs), IFIX (FIIs), IDIV (Dividendos). 26 catalogued.
- **Three analytical modes** — dashboard (single-index deep dive), compare (side-by-side multi-index), ticker (reverse-lookup: which indices contain a given ticker + weight).
- **Modular file structure (v1.0)** — `_registry.py` + `modes/` (3 files: dashboard, compare, ticker) + `helpers.py` + `report.py`. `__init__.py` auto-discovers modes via importlib (same pattern as `tools/git_ops/actions/`).
- **Read-only** — no sync. Calls INDEX query engines directly.
- **Sync guard integration (v1.0)** — `__init__.py` declares `REQUIRED_SOURCES = ["index"]` + passes it to `make_route()`. The `route()` wrapper calls `ensure_fresh()` before dispatch — force-syncs `index.db` if older than 24h.

---

## 🚀 Quick Start

```
# Index dashboard (IBOV)
skill(domain="b3", sub_domain="index", mode="dashboard", params='{"index":"IBOV"}')

# Compare IBOV vs SMLL
skill(domain="b3", sub_domain="index", mode="compare", params='{"indices":["IBOV","SMLL"]}')

# Which indices does PETR4 belong to?
skill(domain="b3", sub_domain="index", mode="ticker", params='{"ticker":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Read-only over already-synced data sources:
- `data_sources/b3/index` (index.db — composition + history)
- `data_sources/b3/api` (instruments.db — ticker segment metadata, optional)
- `data_sources/cvm/bridge` (bridge.db — ticker→CNPJ, auto-syncs on ticker query)

---

## 📊 Rendering & Export

Pipe an `index` result into the `report` tool to render a table or export to Excel (adapters: `index_dashboard`, `index_compare`, `index_ticker`):

```
report(action="table", title="IBOV Dashboard",
       data=<index JSON>, config={"adapter":"index_dashboard"})
report(action="export", title="IBOV Dashboard",
       data=<index JSON>, config={"format":"xlsx","adapter":"index_dashboard"})
```

See [B3 Skills — Report Integration](../B3.md#-report-integration-v10) and [report API](../../tools/report/API.md#adapters-skill-json--table-data).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](index/ARCHITECTURE.md) | File map, mode → source mapping, sync guard wiring |
| [API.md](index/API.md) | 3 modes: dashboard, compare, ticker |
| [CHANGELOG.md](index/CHANGELOG.md) | Version history (v1.0) |
| [ROADMAP.md](index/ROADMAP.md) | Backlog + priorities (P2/P3) |
| [INSTRUCTIONS.md](index/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-08-05 (v1.0).*
