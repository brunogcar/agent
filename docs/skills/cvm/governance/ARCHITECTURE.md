<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/governance/__init__.py` | MANIFEST + route — skill hub, 3 modes |
| `skills/cvm/governance/governance.py` | Main logic: `practices()`, `score()`, `by_chapter()`. Wraps CGVN query_engine with bridge resolution + freshness. |

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

---

*Last updated: 2026-07-25 (v1.0).*
