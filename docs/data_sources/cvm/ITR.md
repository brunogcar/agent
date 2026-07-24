<- Back to [CVM Data Sources](CVM.md)

# 📈 ITR — Quarterly Financial Statements (Informações Trimestrais)

ITR is the CVM quarterly financial statements dataset. Same schema as DFP but contains cumulative quarterly data (meses=3/6/9/12). Values are cumulative within the year (Q1 = Jan–Mar, Q2 = Jan–Jun, etc.).

**Key characteristics:**
- **Same schema as DFP** — shared `empresas` + `contas` + `sync_state` tables (separate DB).
- **Cumulative values** — ITR returns cumulative YTD figures, NOT standalone quarters. The skills/ layer derives standalone quarters (Q2 = H1 − Q1).
- **FIRST_YEAR=2011** — CVM has ITR data from 2011 onward.
- **5 modes** — sync, status, query, resumo, search.

---

## 🚀 Quick Start

```
# Sync (downloads ITR ZIPs per year, ~12.9M rows total)
data_source(domain="cvm", sub_domain="itr", mode="sync")

# Query by company
data_source(domain="cvm", sub_domain="itr", mode="query", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| ITR DB | `memory_db/cvm/itr.db` |

| Source | URL |
|--------|-----|
| ZIPs | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](itr/ARCHITECTURE.md) | Schema (identical to DFP), cumulative value semantics, design decisions |
| [API.md](itr/API.md) | 5 modes: sync, status, query, resumo, search |
| [CHANGELOG.md](itr/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](itr/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0).*
