<- Back to [CVM Data Sources](../CVM.md)

# 📊 VLMO — Valores Mobiliários (Insider Trading)

VLMO contains insider trading disclosures — when directors, officers, or controlling shareholders buy or sell company securities.

**Key characteristics:**
- **2 tables** — vlmo_documents (filing metadata) + vlmo_movements (actual transactions)
- **Insider signals** — buy/sell by role (director, officer, controlling shareholder), with quantity, price, volume, date
- **Read-only** — query + status modes only
- **SQLite** — `workspace/data/cvm/vlmo.db`

---

## 🚀 Quick Start

```powershell
# Sync (download from CVM)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.vlmo.sync_engine import sync; print(sync(year=2025))"

# Query insider transactions
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.vlmo.query_engine import query; print(query(company='PETR4', limit=10))"

# Status
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.vlmo.status_reporter import status; print(status())"
```

Or via MCP tool:
```
data_source(domain="cvm", sub_domain="vlmo", mode="sync", params='{"year":2025}')
data_source(domain="cvm", sub_domain="vlmo", mode="query", params='{"company":"PETR4","limit":20}')
```

---

## 📊 Insider Skill

See [Insider Skill](../../skills/cvm/INSIDER.md) for the analytical skill that wraps VLMO with bridge resolution + freshness.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](vlmo/ARCHITECTURE.md) | Schema, sync flow, query patterns |
| [API.md](vlmo/API.md) | sync + query + status modes |
| [CHANGELOG.md](vlmo/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](vlmo/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-07-25 (v1.0).*
