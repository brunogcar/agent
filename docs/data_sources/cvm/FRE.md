<- Back to [CVM Data Sources](CVM.md)

# 🏛️ FRE — Formulário de Referência (Reference Form)

FRE is the CVM annual governance filing. Contains shareholder composition, free float, executive/board compensation, stock capital + share counts, and a filing index with links to full documents.

**Key characteristics:**
- **Named shareholders** — `posicao_acionaria` table has individual shareholder names + ownership % (ON/PN/total). This is the "better info" not available in DFP.
- **5 tables imported** (out of 50+ CSVs in the ZIP) — documentos, posicao_acionaria, distribuicao_capital, remuneracao_orgao, capital_social.
- **Point-in-time snapshots** — annual filings, not period flows. No meses/flow/snapshot concept.
- **7 modes** — sync, status, shareholders, free_float, compensation, capital, search.

---

## 🚀 Quick Start

```
# Sync (downloads FRE ZIPs per year)
data_source(domain="cvm", sub_domain="fre", mode="sync")

# Query shareholders
data_source(domain="cvm", sub_domain="fre", mode="shareholders", params='{"company":"PETR4"}')

# Query free float
data_source(domain="cvm", sub_domain="fre", mode="free_float", params='{"company":"VALE3"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| FRE DB | `memory_db/cvm/fre.db` |

| Source | URL |
|--------|-----|
| ZIPs | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](fre/ARCHITECTURE.md) | 5-table schema, source code reference, design decisions |
| [API.md](fre/API.md) | 7 modes: sync, status, shareholders, free_float, compensation, capital, search |
| [CHANGELOG.md](fre/CHANGELOG.md) | Version history (v1.0 → v1.0.1) |
| [INSTRUCTIONS.md](fre/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0.1).*
