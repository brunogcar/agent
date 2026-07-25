<- Back to [CVM Data Sources](../CVM.md)

# 📋 FCA — Formulário Cadastral (Registration Form)

FCA contains company registration data + listed securities. The `fca_valor_mobiliario` table maps **ticker → CNPJ** directly, making FCA the primary bridge resolver (local query, no network).

**Key characteristics:**
- **3 tables** (of 9 available — skips contact info): `fca_geral`, `fca_valor_mobiliario`, `fca_pais_estrangeiro`
- **Ticker → CNPJ** in one local query — simplifies the bridge (FCA first, then bridge.db, then B3 API)
- **Listing segment** (Novo Mercado, Nível 1, Nível 2) — used by screener skill
- **Foreign listings** (ADR) — VALE/PETR4 on NYSE/Nasdaq
- **SQLite** — `memory_db/cvm/fca.db`

---

## 🚀 Quick Start

```powershell
# Sync single year
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.fca.sync_engine import sync; print(sync(year=2025))"

# Sync full history
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.fca.sync_engine import sync; print(sync(full_history=True))"

# Query ticker -> CNPJ + listing segment
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.fca.query_engine import query; print(query(ticker='PETR4'))"
```

---

## 🔗 Bridge Integration

FCA is the **primary bridge resolver** (v1.3). When resolving a ticker:
1. **FCA first** — local query `fca_valor_mobiliario.Codigo_Negociacao → CNPJ` (no network)
2. **bridge.db fallback** — cached from prior B3 dividends API + CAD sync
3. **B3 API + CAD fallback** — network fetch when both local sources miss

---

*Last updated: 2026-07-25 (v1.0).*

