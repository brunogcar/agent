<- Back to [CVM Data Sources](CVM.md)

# 📰 IPE — Material Events (Informações Periódicas e Eventuais)

IPE is the CVM material events index. Contains every material filing by publicly listed companies: earnings releases, dividend announcements, board changes, M&A, regulatory filings, etc.

**Key characteristics:**
- **Event index, not document content** — `link_download` points to the actual PDF/XML on CVM's servers. This is metadata + download link.
- **Single table** — simplest CVM data source (one table, one CSV per ZIP).
- **Protocolo_Entrega** — unique dedup key (idempotent re-syncs).
- **4 modes** — sync, status, query (filters: company, categoria, tipo, keyword, date range), search.
- **FIRST_YEAR=2003** — data available from 2003 onward.

---

## 🚀 Quick Start

```
# Sync (downloads IPE ZIPs per year)
data_source(domain="cvm", sub_domain="ipe", mode="sync")

# Query by company
data_source(domain="cvm", sub_domain="ipe", mode="query", params='{"company":"PETR4"}')

# Search by keyword
data_source(domain="cvm", sub_domain="ipe", mode="query", params='{"keyword":"dividendo","data_from":"2024-01-01"}')
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| IPE DB | `memory_db/cvm/ipe.db` |

| Source | URL |
|--------|-----|
| ZIPs | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](ipe/ARCHITECTURE.md) | Schema, source code reference, design decisions |
| [API.md](ipe/API.md) | 4 modes: sync, status, query, search — full parameter reference |
| [CHANGELOG.md](ipe/CHANGELOG.md) | Version history (v1.0 → v1.0.1) |
| [INSTRUCTIONS.md](ipe/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0.1).*
