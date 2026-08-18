<- Back to [BCB Data Sources](../BCB.md)

# 📡 FOCUS — Boletim Focus (Market Expectations Survey)

FOCUS is the BCB's weekly market-expectations survey, published via the Olinda OData API. Free, no auth, no token. Returns per-indicator market expectations (median, mean, min, max + respondent count) for IPCA, Selic, PIB, and Cambio.

**Key characteristics:**
- **4 curated indicators** x frequency: IPCA (monthly), Selic (annual), PIB (annual), Cambio (monthly).
- **7 modes** -- sync_all, sync_expectations, sync_indicator, expectations, last, summary, status.
- **Thread-safe fetcher** -- `Semaphore(5)` caps concurrent HTTP; 5-min Lock-guarded in-memory cache (mirrors the sgs fetcher pattern).
- **Idempotent sync** -- `INSERT OR REPLACE` on the composite PK per table.
- **2 tables** -- `expectations_monthly` (PK: indicador, data, data_referencia, base_calculo) + `expectations_annual` (PK: indicador, data, data_referencia).
- **Olinda OData query** -- `$filter=Indicador eq 'IPCA'&$orderby=Data desc&$top=N&$format=json`.

---

## 📊 Indicator Catalog (4 indicators)

| Indicador | Frequency | Unit | Description |
|-----------|-----------|------|-------------|
| IPCA | monthly | % | Inflacao - IPCA mensal (% no mes) |
| Selic | annual | % a.a. | Juros - Meta Selic (% a.a.) |
| PIB | annual | % | Atividade - PIB (% var. real anual) |
| Cambio | monthly | R$ | Cambio - USD/BRL (R$ por dolar, fim mes) |

---

## 🚀 Quick Start

```python
# Sync all 4 indicators concurrently (Semaphore(5), ~4 HTTP calls)
data_source(domain="bcb", sub_domain="focus", mode="sync_all")

# Sync one indicator (primary frequency)
data_source(domain="bcb", sub_domain="focus", mode="sync_indicator", params='{"indicador":"Selic"}')

# Sync one (indicador, frequency) pair explicitly
data_source(domain="bcb", sub_domain="focus", mode="sync_expectations",
            params='{"indicador":"IPCA","frequency":"monthly"}')

# Query the most recent 20 IPCA expectations
data_source(domain="bcb", sub_domain="focus", mode="expectations",
            params='{"indicador":"IPCA","frequency":"monthly","limit":20}')

# Get the latest Selic expectation
data_source(domain="bcb", sub_domain="focus", mode="last",
            params='{"indicador":"Selic","frequency":"annual"}')

# Catalog overview
data_source(domain="bcb", sub_domain="focus", mode="summary")

# DB stats
data_source(domain="bcb", sub_domain="focus", mode="status")
```

---

## ⚙️ Configuration

| Storage | Path |
|---------|------|
| Focus DB | `memory_db/bcb/focus.db` |

| Source | URL |
|--------|-----|
| Olinda OData | `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/` |
| Monthly entity | `ExpectativaMercadoMensais` |
| Annual entity | `ExpectativasMercadoAnuais` |

Query params (OData): `$filter=Indicador eq 'IPCA'`, `$orderby=Data desc`, `$top=N`, `$format=json`.

---

## 🔧 Sync Commands

```bash
# Sync all 4 indicators (~5s, concurrent via Semaphore(5))
python3 -c "from data_sources.bcb.focus.sync_engine import sync_all; print(sync_all())"

# Sync one indicator using its primary frequency
python3 -c "from data_sources.bcb.focus.sync_engine import sync_indicator; print(sync_indicator('Selic'))"

# Sync one (indicador, frequency) pair explicitly
python3 -c "from data_sources.bcb.focus.sync_engine import sync_expectations; print(sync_expectations('IPCA', 'monthly'))"
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](focus/ARCHITECTURE.md) | File map, 3-table schema, design decisions, data flow |
| [API.md](focus/API.md) | 7 modes documented with params + examples |
| [CHANGELOG.md](focus/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](focus/INSTRUCTIONS.md) | AI editing rules -- what NOT to break |

---

*Last updated: 2026-08-22 (v1.0).*
