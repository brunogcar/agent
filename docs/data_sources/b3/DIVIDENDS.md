<- Back to [B3 Data Sources](../B3.md)

# 💰 DIVIDENDS — B3 Corporate Actions (Cash/Stock Dividends, Subscriptions)

B3 corporate actions via per-ticker JSON API. Returns cash dividends, stock dividends (bonus shares), and subscription rights for a single company.

**Key characteristics:**
- **Per-ticker API** — not paginated. One HTTP call per ticker returns all corporate actions.
- **ISIN stored** — `cash_dividends.isin_code` field contains the real ISIN (e.g., `BRPETRACNOR9`), used by the bridge ISIN fallback.
- **`company_info.code_cvm`** — the dividends API returns `codeCVM` (e.g., `9512` for PETR4), which the bridge uses as the primary ticker → cd_cvm link.
- **Date normalization** — DD/MM/YYYY → YYYY-MM-DD at ingest.
- **5 modes** — sync, status, dividends, stock_dividends, subscriptions, company_info.

---

## 🚀 Quick Start

```
# Sync dividends for a ticker
data_source(domain="b3", sub_domain="dividends", mode="sync", params='{"ticker":"PETR4"}')

# Query cash dividends
data_source(domain="b3", sub_domain="dividends", mode="dividends", params='{"ticker":"PETR4"}')

# Check sync status
data_source(domain="b3", sub_domain="dividends", mode="status")
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| Dividends DB | `memory_db/b3/dividends.db` |

| Source | URL |
|--------|-----|
| API | `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{base64}` |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](dividends/ARCHITECTURE.md) | API flow, 4-table schema, design decisions |
| [API.md](dividends/API.md) | 5 modes: sync, status, dividends, stock_dividends, subscriptions, company_info |
| [CHANGELOG.md](dividends/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](dividends/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-23 (v1.0).*
