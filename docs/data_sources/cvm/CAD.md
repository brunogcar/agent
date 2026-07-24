<- Back to [CVM Data Sources](CVM.md)

# 🏢 CAD — Company Register (Cadastro de Companhias Abertas)

CAD is the CVM company register — a single CSV file (~1.5MB, ~2677 companies) updated weekly. Contains CNPJ, CD_CVM, legal/commercial names, status, sector, market type, registration dates, cancellation info, address, contact, auditor.

**Key characteristics:**
- **The BRIDGE data source** — CD_CVM links to DFP/ITR/FRE filings, CNPJ links to B3 instruments. Primary use case: company resolution (ticker → CNPJ → CD_CVM → financials).
- **Full replace** — each sync downloads the complete CSV and replaces the DB (file is a snapshot, not incremental).
- **46 columns stored** — `DEFAULT_COLS` returns 24 key columns; `full=True` returns all 46.
- **5 modes** — sync, status, lookup (by CNPJ/CD_CVM/name), search (filters: setor, sit, controle, uf), sectors.

---

## 🚀 Quick Start

```
# Sync (downloads ~1.5MB CSV, ~2s)
data_source(domain="cvm", sub_domain="cad", mode="sync")

# Look up by CNPJ
data_source(domain="cvm", sub_domain="cad", mode="lookup", params='{"cnpj":"33000167000101"}')

# Search by sector
data_source(domain="cvm", sub_domain="cad", mode="search", params='{"setor":"Petróleo"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| CAD DB | `memory_db/cvm/cad.db` |

| Source | URL |
|--------|-----|
| CSV | `https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](cad/ARCHITECTURE.md) | Schema (46 columns), source code reference, design decisions |
| [API.md](cad/API.md) | 5 modes: sync, status, lookup, search, sectors — full parameter reference |
| [CHANGELOG.md](cad/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](cad/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0).*
