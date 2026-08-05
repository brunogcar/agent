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

[v1.12] The standalone `dva` mode (along with `dre`, `bpa`, `bpp`, `dfc`)
was refactored to use the shared `fetch_statement_data` helper from
`skills/cvm/financials/helpers`. The `_DVA_CODES` list + grupo filter +
statement name ("DVA") are passed as parameters; the helper owns the
DFP/ITR fetch + periods-data assembly logic.

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

### Calculations engines (v1.12 — generation side added)

The `skills/cvm/calculations/engines/` package now has engines covering
**both sides** of the DVA statement. The distribution-side engines were
added incrementally (v1.2 → v1.4); the generation-side engines were added
in v1.12 (2026-08-05), completing the DVA coverage.

**Generation side (v1.12, new):**

| Engine file | Code | Label |
|-------------|------|-------|
| `dva_revenue.py` | `7.01` | Receitas |
| `dva_inputs.py` | `7.03` | Insumos Adquiridos de Terceiros |
| `dva_gross_va.py` | `7.04` | Valor Adicionado Bruto |
| `dva_retentions.py` | `7.05` | Retenções |
| `dva_net_va.py` | `7.06` | Valor Adicionado Líquido Produzido |
| `dva_va_received.py` | `7.07` | Vlr Adicionado Recebido em Transferência |

**Distribution side (v1.2 → v1.4, pre-existing):**

| Engine file | Code | Label |
|-------------|------|-------|
| `value_added.py` | `7.08` / `7.10` | Valor Adicionado Total a Distribuir (the total) |
| `total_tax.py` | `7.08.02` / `7.11.02` | Impostos, Taxas e Contribuições |
| `interest_paid.py` | `7.08.03` / `7.11.03` | Remuneração de Capital de Terceiros |
| `dividends_paid.py` | `7.08.04` / `7.11.04` | Remuneração de Capital Próprio |

All 10 engines follow the same template: `*_at()` point-in-time +
`*_history()` time-series + TTM derivation via `compute_ttm_with_engines()`
(4-quarter sum for flow lines) + `@engine_cached` decorator (added at
module definition time, participates in `engine_cache_scope`) +
`@register_engine` (auto-discovered by `_registry.py`). All use the
`grupo LIKE '%Valor Adicionado%'` filter (the v1.7 fix). The 4 distribution
engines query both old (`7.08.0x`) + new (`7.11.0x`) taxonomies via
`codigo IN ('7.08.0x', '7.11.0x')`; the 6 generation engines use single-code
lookup (codes `7.0x` are unique — no old/new taxonomy split).

> **Note on the `dva_` prefix.** The v1.4 sprint removed the `dva_` prefix
> from the 4 distribution-side engines (e.g. `dva_interest_paid` →
> `interest_paid`) to follow the no-category-prefix convention. The 6
> generation-side engines added in v1.12 retain the `dva_` prefix because
> names like `revenue` (already used for DRE 3.01), `inputs`, and
> `retentions` would be ambiguous without it. The prefix is therefore
> **policy-by-necessity**, not a convention reversal.

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
   format will likely grow as CVM rolls it out. **[v1.8]** The 4 DVA
   calculations engines (`value_added`, `dva_total_tax`, `dva_interest_paid`,
   `dividends_paid`) all query both old + new codes via
   `codigo IN ('7.08.0x', '7.11.0x')` — the same pattern is applied to
   `7.08`/`7.10` (total) and `7.08.0x`/`7.11.0x` (distribution components).

5. **DVA is available in BOTH DFP and ITR.** Annual DVA comes from DFP
   (`meses=12`). Quarterly cumulative DVA comes from ITR (`meses=3/6/9`).
   The `dva` mode with `quarterly=1` queries both.

6. **`DVA_GRUPO = "DVA"` is dead code.** [v1.8] The 4 DVA calculations
   engines used to define a `DVA_GRUPO = "DVA"` module-level constant,
   ostensibly for the SQL `grupo = '{DVA_GRUPO}'` clause. But the SQL
   actually used `grupo LIKE '%Valor Adicionado%'` (which matches the real
   DFP grupo value `DF Consolidado - Demonstração de Valor Adicionado`),
   so the constant was never referenced. v1.8 removed the dead constant +
   its stale "Without this filter, codigo = '7' would match nothing"
   comment from all 4 engines. Callers that imported `DVA_GRUPO` from
   these engines should switch to the literal `'%Valor Adicionado%'` or
   to the engine's `*_CODE` constants.

---

*Last updated: 2026-08-05 (v1.12 — documents the 6 new DVA generation-side
calculation engines: `dva_revenue` 7.01, `dva_inputs` 7.03, `dva_gross_va`
7.04, `dva_retentions` 7.05, `dva_net_va` 7.06, `dva_va_received` 7.07.
Completes the DVA — both generation + distribution sides now have engines.
Sibling of DRE.md).*
