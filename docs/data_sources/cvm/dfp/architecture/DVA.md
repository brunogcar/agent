<- Back to [DFP Architecture](../ARCHITECTURE.md)

# 📊 DVA — Demonstração do Valor Adicionado

The DVA is the Brazilian Value Added Statement — it shows how a company
creates wealth (generation side) and distributes it across stakeholders
(distribution side: personnel, government, lenders, shareholders).

## ⚠️ The 7.xx vs 1-8 trap

CVM's metadata suggests DVA uses codes `1`–`8`:

| Code (metadata) | Label (metadata) |
|-----------------|------------------|
| 1 | Receitas |
| 2 | Insumos |
| 3 | Valor Adicionado Bruto |
| 4 | Retenções |
| 5 | Valor Adicionado Líquido |
| 6 | VA Recebido em Transferência |
| 7 | Valor Adicionado Total a Distribuir |
| 8.1 | Pessoal |
| 8.2 | Impostos |
| 8.3 | Remuneração Capital Terceiros |
| 8.4 | Remuneração Capital Próprio |

**This is wrong for the actual DFP database.** The real DFP DVA uses codes
prefixed with `7.xx`:

| Real code | Rows in DFP | Metadata code equivalent |
|-----------|-------------|--------------------------|
| `7`       | **0 rows**  | "Valor Adicionado Total a Distribuir" (claimed as code 7) |
| `7.08`    | **16808 rows** (total) | The actual "Total a Distribuir" line |
| `7.08.01` | (pessoal)   | 8.1 |
| `7.08.02` | (impostos)  | 8.2 |
| `7.08.03` | (capital terceiros) | 8.3 |
| `7.08.04` | (capital próprio)   | 8.4 |

Code `7` literally has **0 rows** in DFP. The dominant format is `7.08.xx`
(16808 rows for `7.08.04`). A newer `7.11.xx` format exists with ~75 rows
only.

## grupo filter (DVA grupo filter bug — fixed v1.7)

DFP stores the DVA `grupo` value as:

| grupo | Statement |
|-------|-----------|
| `DF Consolidado - Demonstração de Valor Adicionado` | DVA (consolidated) |
| `DF Individual - Demonstração de Valor Adicionado` | DVA (individual) |

**The grupo is NOT "DVA"** — it's the full Portuguese statement name.
Three calculations engines (`ebit_at`, `da_at`, `ttm_earnings_at`) were
originally written with a `grupo LIKE '%DVA%'` filter, which returned 0
rows. Fixed in v1.7 (previous commit) — they now use
`grupo LIKE '%Valor Adicionado%'`.

## Chart of accounts (real DFP, v1.7+)

| Code | Label | Section | Format |
|------|-------|---------|--------|
| `7.01` | Receitas | generation | old |
| `7.03` | Insumos Adquiridos de Terceiros | generation | old |
| `7.04` | Valor Adicionado Bruto | generation | old |
| `7.05` | Retenções | generation | old |
| `7.06` | Valor Adicionado Líquido Produzido | generation | old |
| `7.07` | Vlr Adicionado Recebido em Transferência | generation | old |
| `7.08` | Valor Adicionado Total a Distribuir | generation | old |
| `7.10` | Valor Adicionado Total a Distribuir (alt) | generation | **new** (~75 rows) |
| `7.08.01` | Pessoal | distribution | old |
| `7.08.02` | Impostos, Taxas e Contribuições | distribution | old |
| `7.08.03` | Remuneração de Capital de Terceiros | distribution | old |
| `7.08.04` | Remuneração de Capital Próprio | distribution | old |
| `7.11.01` | Pessoal (novo formato) | distribution | **new** |
| `7.11.02` | Impostos (novo formato) | distribution | **new** |
| `7.11.03` | Remuneração de Capital de Terceiros (novo) | distribution | **new** |
| `7.11.04` | Remuneração de Capital Próprio (novo) | distribution | **new** |

> The `dva` standalone mode queries ALL of these codes; the per-period
> rendering uses the `7.08.xx` values if present, falling back to
> `7.11.xx` if not (via `_extract_metrics`).

## How the financials skill uses these codes

### `mode="dva"` (v1.7, standalone)

Surfaces ALL 16 codes above, with `label` + `section` + `valor_brl` per
period. Filters `grupo LIKE '%Valor Adicionado%'`. Supports both annual
(DFP, `meses=12`) and quarterly (ITR `meses=3/6/9` + DFP `meses=12`).

### `SUMMARY_CODES` (annual / quarterly / summary / dashboard)

After v1.7 the SUMMARY_CODES for DVA are:

| Code | Metric key in `_extract_metrics` |
|------|----------------------------------|
| `7.08` (or `7.10`) | `dva_total` |
| `7.08.01` (or `7.11.01`) | `dva_pessoal` |
| `7.08.02` (or `7.11.02`) | `dva_impostos` |
| `7.08.03` (or `7.11.03`) | `dva_remu_capital_terceiros` |
| `7.08.04` (or `7.11.04`) | `dva_remu_capital_proprio` (also surfaced as `proventos`) |

### `complete` mode

`KEY_CODES_BY_GRUPO["DVA"]` (v1.7+): the full 18-code list (15 above +
`7.08.04.01` / `7.08.04.02` for dividend sub-categories).

## Common pitfalls

1. **The metadata 1-8 codes don't exist in DFP.** Don't write SQL with
   `codigo IN ('1','2',...'8.4')` against DFP DVA rows — you'll get zero
   rows. Use the `7.xx` codes from the table above.

2. **`grupo LIKE '%DVA%'` returns zero rows.** The grupo field is the
   Portuguese statement name "Demonstração de Valor Adicionado", not "DVA".
   Use `grupo LIKE '%Valor Adicionado%'`.

3. **Code 7 has zero rows.** "Total a Distribuir" is at code `7.08` (old
   format) or `7.10` (new format). Query both; prefer `7.08`.

4. **The new 7.11 format is rare (~75 rows).** Most filers still use
   `7.08.xx`. But a complete DVA implementation must handle both — the new
   format will likely grow as CVM rolls it out.

5. **DVA is available in BOTH DFP and ITR.** Annual DVA comes from DFP
   (`meses=12`). Quarterly cumulative DVA comes from ITR (`meses=3/6/9`).
   The `dva` mode with `quarterly=1` queries both.

---

*Last updated: 2026-07-30 (v1.8 — documents the v1.7 DVA fix; sibling of DRE.md).*
