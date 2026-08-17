<- Back to [TERM](../TERM.md)

# AI Instructions

## ❌ NEVER DO

1. Never strip the ticker digit (PETR4 ≠ PETR3 — share class matters for term).
2. Never create a separate data source for derivatives — use `data_sources.b3.cotahist.derivatives_query`.
3. Never query the `cotahist` equities table for term data — use `cotahist_derivatives` table.
4. Never write to the database — term skill is read-only.
5. Never hardcode term prices — always query from the DB.

## ✅ ALWAYS DO

1. Always use graceful degradation (status=ok with error sections).
2. Always pass `title=f"{ticker}_term"` for file naming.
3. Always use `data_sources.b3.cotahist.derivatives_query` for term queries.
4. Always include timing logs.
5. Always handle the case where no term data exists for the ticker.
