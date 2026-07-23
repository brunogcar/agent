<- Back to [Data Sources Overview](../DATA_SOURCES.md)

# 📊 CVM Data Sources

CVM (Comissão de Valores Mobiliários) — the Brazilian SEC. Provides financial statements for all publicly traded Brazilian companies.

## Sub-domains

| Sub-domain | What | Storage | Source |
|---|---|---|---|
| [DFP](cvm/dfp/) | Annual financial statements (Demonstrações Financeiras Padronizadas) | `memory_db/cvm/dfp.db` | `dados.cvm.gov.br/.../DFP/` |
| [ITR](cvm/itr/) | Quarterly financial statements (Informações Trimestrais) | `memory_db/cvm/itr.db` | `dados.cvm.gov.br/.../ITR/` |

## Statement Groups (shared)

Both DFP + ITR contain the same statement types:

| Code | Name | Type | Has DT_INI_EXERC? |
|---|---|---|---|
| BPA | Balanço Patrimonial Ativo (Assets) | Snapshot | No (`""`) |
| BPP | Balanço Patrimonial Passivo (Liabilities) | Snapshot | No (`""`) |
| DRE | Demonstração do Resultado (Income) | Flow | Yes |
| DFC_MI | Fluxo de Caixa (Indirect Method) | Flow | Yes |
| DFC_MD | Fluxo de Caixa (Direct Method) | Flow | Yes |
| DVA | Valor Adicionado (Value Added) | Flow | Yes |
| ~~DMPL~~ | ~~Mutações do Patr. Líquido~~ | ~~Flow~~ | ~~Yes~~ — **excluded v1.0.1** (2D statement, COLUNA_DF) |

## The `meses` Field

`meses` is computed from `DT_INI_EXERC` + `DT_FIM_EXERC` (not a CSV column). Mirrors [rapinav2](https://github.com/dude333/rapinav2)'s `monthsDiff()`:

| meses | Meaning | Source |
|---|---|---|
| 3 | Q1 cumulative (Jan→Mar) | ITR |
| 6 | H1 cumulative (Jan→Jun) | ITR |
| 9 | 9M cumulative (Jan→Sep) | ITR |
| 12 | Annual flow (Jan→Dec) or BPA/BPP snapshot | DFP |
| 15 | 15-month transition period | DFP (rare) |

## Shared Modules

| File | Purpose |
|---|---|
| `_db.py` | Path resolution, CNPJ normalization, connection helpers, schema creation |
| `_bridge.py` | Company resolution: ticker → CNPJ → empresa_id (via optional bridge.db) |
| `_meses.py` | `compute_meses()`, `is_snapshot()`, `is_flow()`, `should_keep_row()` (ORDEM_EXERC filter) |

---

*Last updated: 2026-07-23.*
