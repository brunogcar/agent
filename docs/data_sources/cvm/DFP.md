<- Back to [CVM Data Sources](CVM.md)

# 📊 DFP — Annual Financial Statements (Demonstrações Financeiras Padronizadas)

DFP is the CVM annual financial statements dataset. Contains all publicly traded Brazilian companies' balance sheets (BPA/BPP), income statements (DRE), cash flow (DFC), value added (DVA), and equity changes (DMPL — excluded, 2D statement).

**Key characteristics:**
- **rapinav2-accurate `meses`** — computed from DT_INI/DT_FIM_EXERC (not a CSV column). Mirrors rapinav2's `monthsDiff()`.
- **ORDEM_EXERC filter** — keeps ÚLTIMO only (+ PENÚLTIMO for 2009 transition).
- **VERSAO dedup** — keeps highest version per (cnpj, ano).
- **5 modes** — sync, status, query (by company/grupo/codigo), resumo (summary), search.
- **Raw annual values** — skills/ layer derives ratios + trimestral transforms.

---

## 🚀 Quick Start

```
# Sync (downloads DFP ZIPs per year, ~5.4M rows total)
data_source(domain="cvm", sub_domain="dfp", mode="sync")

# Query by company (ticker via bridge, name, or CNPJ)
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')

# Resumo (summary metrics)
data_source(domain="cvm", sub_domain="dfp", mode="resumo", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| DFP DB | `memory_db/cvm/dfp.db` |

| Source | URL |
|--------|-----|
| ZIPs | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip` |

**Shared schema** (with ITR): `empresas` + `contas` + `sync_state`. See ARCHITECTURE.md for the full DDL.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](dfp/ARCHITECTURE.md) | Schema, source code reference, meses computation, design decisions |
| [API.md](dfp/API.md) | 5 modes: sync, status, query, resumo, search — full parameter reference |
| [CHANGELOG.md](dfp/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](dfp/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0).*
