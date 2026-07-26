<- Back to [INSIDER Overview](../INSIDER.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/insider/__init__.py` | MANIFEST + route — skill hub, 3 modes |
| `skills/cvm/insider/insider.py` | Main logic: `history()`, `by_role()`, `summary()`. Wraps VLMO query_engine with bridge resolution + freshness. |

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

## Design Decisions

- **Read-only**: No sync. Calls VLMO query_engine directly. Assumes vlmo.db is already synced.
- **Bridge resolution**: Ticker → CNPJ via bridge (FCA first → bridge.db → B3 API). Auto-sync on miss.
- **Sentiment computation**: `summary()` computes net_volume = total_bought - total_sold. If positive → "buying", negative → "selling", zero → "neutral".
- **Data freshness**: Returns `data_freshness` field with sync timestamps for all CVM/B3 databases.
- **Best-effort**: If VLMO data is missing, returns not_synced/not_found — never crashes.

---

*Last updated: 2026-07-25 (v1.0).*
